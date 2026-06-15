"""Phase 3B — Full performance engineering service."""

import difflib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRunModel, DiscoverySessionModel, LoadAgentModel, PerformanceAssetModel, PerformanceRunModel, TestCaseModel
from app.models.schemas import AgentStatus, AgentType
from app.services.performance.correlation import extract_from_har, extract_from_openapi, inject_correlations_into_k6
from app.services.performance.engine import PerformanceEngine
from app.services.performance.execution import run_k6
from app.services.performance.parameterization import generate_data_pools, inject_parameterization_k6
from app.services.performance.replay_extractor import build_flows_from_replay
from app.services.performance.workload import WORKLOAD_PROFILES, build_workload_model
from app.services.runner_agent import ensure_localhost_agent


class PerformanceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = PerformanceEngine()

    async def generate(
        self,
        project_id: uuid.UUID,
        tool: str = "k6",
        flow_distribution: dict | None = None,
        name: str | None = None,
        workload_profile: str = "load",
        base_url: str = "https://example.com",
        har_content: dict | str | None = None,
        openapi_content: dict | str | None = None,
        throughput_config: dict | None = None,
        discovery_session_id: uuid.UUID | None = None,
        flows: list[dict] | None = None,
    ) -> PerformanceAssetModel:
        navigation_log: list | None = None
        proposed_test_cases: list | None = None

        if discovery_session_id:
            session = await self.db.get(DiscoverySessionModel, discovery_session_id)
            if session and session.project_id == project_id:
                navigation_log = session.navigation_log or []
                proposed_test_cases = session.proposed_test_cases or []
                if session.base_url:
                    base_url = session.base_url

        resolved_base = base_url
        if flows is None:
            result = await self.db.execute(
                select(TestCaseModel).where(TestCaseModel.project_id == project_id)
            )
            cases = list(result.scalars().all())
            test_case_dicts = [
                {"title": c.title, "steps": c.steps or [], "expected_results": c.expected_results or []}
                for c in cases
            ]

            flows, resolved_base = build_flows_from_replay(
                navigation_log=navigation_log,
                test_cases=test_case_dicts,
                har_content=har_content,
                proposed_test_cases=proposed_test_cases,
                base_url=base_url,
            )

        if flow_distribution:
            flows = [{"name": k, "weight": v, "steps": next((f["steps"] for f in flows if f["name"] == k), flows[0]["steps"] if flows else [])} for k, v in flow_distribution.items()]

        correlation_rules: list[dict] = []
        if har_content:
            correlation_rules.extend(extract_from_har(har_content))
        if openapi_content:
            correlation_rules.extend(extract_from_openapi(openapi_content))

        pools = generate_data_pools()
        output = self.engine.generate(
            tool=tool,
            flows=flows or [{"name": "Default", "weight": 100, "steps": []}],
            profile=workload_profile,
            correlation_rules=correlation_rules,
            data_pools=pools,
            throughput_config=throughput_config,
            base_url=resolved_base,
        )

        replay_label = output.get("replay_source", "test_cases")
        asset = PerformanceAssetModel(
            project_id=project_id,
            name=name or f"{tool.upper()} — {WORKLOAD_PROFILES.get(workload_profile, {}).get('name', workload_profile)} (from {replay_label})",
            tool=tool,
            workload_model=output.get("workload_model"),
            throughput_config=output.get("throughput_config"),
            scripts=output.get("scripts", []),
            scenarios=output.get("scenarios", []),
            correlation_rules=output.get("correlation_rules", []),
            parameterization=output.get("parameterization"),
            data_pools=output.get("data_pools", []),
            flow_distribution=output.get("flow_distribution"),
            status="generated",
        )
        self.db.add(asset)

        run = AgentRunModel(
            project_id=project_id,
            agent_type=AgentType.PERFORMANCE.value,
            status=AgentStatus.COMPLETED.value,
            input_data={"tool": tool, "profile": workload_profile, "flows": flows, "replay_source": replay_label},
            output_data=output,
            llm_provider="qeos-native",
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()
        return asset

    async def apply_correlation_from_source(
        self, asset_id: uuid.UUID, source_type: str, content: dict | str
    ) -> PerformanceAssetModel | None:
        asset = await self.get_asset(asset_id)
        if not asset:
            return None
        rules = extract_from_har(content) if source_type == "har" else extract_from_openapi(content)
        asset.correlation_rules = (asset.correlation_rules or []) + rules
        asset = await self._rebuild_scripts(asset)
        await self.db.flush()
        return asset

    async def update_scenario(self, asset_id: uuid.UUID, scenarios: list[dict]) -> PerformanceAssetModel | None:
        asset = await self.get_asset(asset_id)
        if not asset:
            return None
        asset.scenarios = scenarios
        flows = [{"name": s.get("name", "flow"), "weight": s.get("weight", 10)} for s in scenarios]
        asset.flow_distribution = {f["name"]: f["weight"] for f in flows}
        asset = await self._rebuild_scripts(asset, flows=flows)
        await self.db.flush()
        return asset

    async def update_data_pools(self, asset_id: uuid.UUID, pools: list[dict]) -> PerformanceAssetModel | None:
        asset = await self.get_asset(asset_id)
        if not asset:
            return None
        asset.data_pools = pools
        asset.parameterization = {"pools": [{"id": p["id"], "filename": p.get("filename")} for p in pools]}
        asset = await self._rebuild_scripts(asset, pools=pools)
        await self.db.flush()
        return asset

    async def update_workload(
        self, asset_id: uuid.UUID, profile: str, throughput_config: dict | None = None
    ) -> PerformanceAssetModel | None:
        asset = await self.get_asset(asset_id)
        if not asset:
            return None
        asset.workload_model = build_workload_model(profile, throughput_config)
        asset.throughput_config = throughput_config or asset.throughput_config
        asset = await self._rebuild_scripts(asset, profile=profile, throughput=throughput_config)
        await self.db.flush()
        return asset

    async def _rebuild_scripts(
        self,
        asset: PerformanceAssetModel,
        flows: list | None = None,
        pools: list | None = None,
        profile: str | None = None,
        throughput: dict | None = None,
    ) -> PerformanceAssetModel:
        flows = flows or [{"name": k, "weight": v, "steps": []} for k, v in (asset.flow_distribution or {"Default": 100}).items()]
        # Preserve replay steps from scenarios when rebuilding
        if asset.scenarios and not any(f.get("steps") for f in flows):
            flows = [
                {"name": s.get("name", "flow"), "weight": s.get("weight", 10), "steps": s.get("steps", [])}
                for s in asset.scenarios
            ]
        pools = pools or asset.data_pools or generate_data_pools()
        profile = profile or "load"
        if profile not in WORKLOAD_PROFILES:
            profile = "load"
        base_url = "https://example.com"
        if asset.scenarios and asset.scenarios[0].get("steps"):
            first_url = asset.scenarios[0]["steps"][0].get("url", "")
            if isinstance(first_url, str) and first_url.startswith("http"):
                from urllib.parse import urlparse
                p = urlparse(first_url)
                base_url = f"{p.scheme}://{p.netloc}"
        output = self.engine.generate(
            tool=asset.tool,
            flows=flows,
            profile=profile,
            correlation_rules=asset.correlation_rules or [],
            data_pools=pools,
            throughput_config=throughput or asset.throughput_config,
            base_url=base_url if isinstance(base_url, str) else "https://example.com",
        )
        asset.scripts = output.get("scripts", [])
        return asset

    async def update_file(
        self, asset_id: uuid.UUID, file_path: str, content: str, save_version: bool = True
    ) -> PerformanceAssetModel:
        asset = await self.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")
        files = list(asset.scripts or [])
        found = False
        for f in files:
            if f.get("path") == file_path:
                f["content"] = content
                found = True
                break
        if not found:
            files.append({"path": file_path, "content": content, "type": "script"})

        if save_version:
            new_asset = PerformanceAssetModel(
                project_id=asset.project_id,
                name=asset.name,
                tool=asset.tool,
                workload_model=asset.workload_model,
                throughput_config=asset.throughput_config,
                scripts=files,
                scenarios=asset.scenarios,
                correlation_rules=asset.correlation_rules,
                parameterization=asset.parameterization,
                data_pools=asset.data_pools,
                flow_distribution=asset.flow_distribution,
                version=asset.version + 1,
                parent_id=asset.id,
                status="edited",
            )
            self.db.add(new_asset)
            await self.db.flush()
            return new_asset

        asset.scripts = files
        asset.status = "edited"
        asset.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return asset

    async def list_versions(self, asset_id: uuid.UUID) -> list[PerformanceAssetModel]:
        asset = await self.get_asset(asset_id)
        if not asset:
            return []
        result = await self.db.execute(
            select(PerformanceAssetModel)
            .where(PerformanceAssetModel.project_id == asset.project_id, PerformanceAssetModel.name == asset.name)
            .order_by(PerformanceAssetModel.version.asc())
        )
        return list(result.scalars().all())

    def diff_scripts(self, scripts_a: list, scripts_b: list) -> list[dict]:
        map_a = {f["path"]: f.get("content", "") for f in scripts_a}
        map_b = {f["path"]: f.get("content", "") for f in scripts_b}
        diffs = []
        for path in sorted(set(map_a) | set(map_b)):
            if map_a.get(path) != map_b.get(path):
                diff_lines = list(difflib.unified_diff(
                    map_a.get(path, "").splitlines(keepends=True),
                    map_b.get(path, "").splitlines(keepends=True),
                    fromfile=f"prev/{path}", tofile=f"curr/{path}",
                ))
                diffs.append({"path": path, "changed": True, "diff": "".join(diff_lines)})
            else:
                diffs.append({"path": path, "changed": False, "diff": ""})
        return diffs

    async def execute(
        self,
        project_id: uuid.UUID,
        asset_id: uuid.UUID,
        workload_profile: str = "smoke",
        agent_id: uuid.UUID | None = None,
        background: bool = True,
    ) -> PerformanceRunModel:
        asset = await self.get_asset(asset_id)
        if not asset or asset.project_id != project_id:
            raise ValueError("Asset not found")

        agent = await self._resolve_agent(project_id, agent_id)

        run = PerformanceRunModel(
            project_id=project_id,
            asset_id=asset_id,
            agent_id=agent.id,
            workload_profile=workload_profile,
            status="running",
            summary={
                "agent": agent.name,
                "progress": {"percent": 0, "phase": "Queued"},
                "background": background,
            },
        )
        self.db.add(run)
        await self.db.flush()

        if background:
            from app.services.performance.performance_worker import enqueue_performance_run

            await self.db.commit()
            enqueue_performance_run(run.id)
            return run

        await self._execute_run_sync(run, asset, workload_profile)
        return run

    async def _execute_run_sync(self, run: PerformanceRunModel, asset: PerformanceAssetModel, workload_profile: str) -> None:
        main_script = next(
            (s for s in (asset.scripts or []) if s.get("type") in ("k6", "script") or s["path"].endswith(".js")),
            (asset.scripts or [{}])[0],
        )
        data_files = [s for s in (asset.scripts or []) if s.get("type") == "data" or "data/" in s.get("path", "")]
        duration = "30s" if workload_profile == "smoke" else "60s"
        outcome = await run_k6(main_script.get("content", ""), data_files, duration_override=duration)
        dashboard = outcome.get("dashboard", {})
        run.status = outcome.get("status", "completed")
        run.metrics = dashboard
        run.summary = {
            **(run.summary or {}),
            "exit_code": outcome.get("exit_code"),
            "available": outcome.get("available", True),
            "passed": run.status == "completed",
            "transactions": len(dashboard.get("transactions", [])),
            "progress": {"percent": 100, "phase": "Complete"},
        }
        run.logs = (outcome.get("stdout", "") + outcome.get("stderr", ""))[:50000]
        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _resolve_agent(self, project_id: uuid.UUID, agent_id: uuid.UUID | None) -> LoadAgentModel:
        if agent_id:
            agent = await self.db.get(LoadAgentModel, agent_id)
            if agent:
                return agent
        localhost = await ensure_localhost_agent(self.db, project_id)
        return localhost

    async def seed_local_agent(self, project_id: uuid.UUID | None = None) -> LoadAgentModel:
        """Ensure localhost agent is available for performance runs."""
        return await ensure_localhost_agent(self.db, project_id)

    async def list_runs(self, project_id: uuid.UUID) -> list[PerformanceRunModel]:
        result = await self.db.execute(
            select(PerformanceRunModel)
            .where(PerformanceRunModel.project_id == project_id)
            .order_by(PerformanceRunModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_run(self, run_id: uuid.UUID) -> PerformanceRunModel | None:
        return await self.db.get(PerformanceRunModel, run_id)

    # Load agents
    async def register_agent(
        self, name: str, host: str = "localhost", agent_type: str = "local",
        max_vus: int = 500, project_id: uuid.UUID | None = None,
    ) -> LoadAgentModel:
        agent = LoadAgentModel(
            project_id=project_id,
            name=name,
            host=host,
            agent_type=agent_type,
            max_vus=max_vus,
            status="online",
            capabilities={"tools": ["k6"], "max_vus": max_vus},
            last_heartbeat=datetime.now(timezone.utc),
        )
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def list_agents(self, project_id: uuid.UUID | None = None) -> list[LoadAgentModel]:
        query = select(LoadAgentModel).order_by(LoadAgentModel.created_at.desc())
        if project_id:
            query = query.where(
                (LoadAgentModel.project_id == project_id) | (LoadAgentModel.project_id.is_(None))
            )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_assets(self, project_id: uuid.UUID) -> list[PerformanceAssetModel]:
        result = await self.db.execute(
            select(PerformanceAssetModel)
            .where(PerformanceAssetModel.project_id == project_id)
            .order_by(PerformanceAssetModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_asset(self, asset_id: uuid.UUID) -> PerformanceAssetModel | None:
        return await self.db.get(PerformanceAssetModel, asset_id)

    async def update_scripts(
        self, asset_id: uuid.UUID, project_id: uuid.UUID,
        scripts: list[dict] | None = None, name: str | None = None,
        workload_model: dict | None = None,
    ) -> PerformanceAssetModel | None:
        asset = await self.get_asset(asset_id)
        if not asset or asset.project_id != project_id:
            return None
        if scripts is not None:
            asset.scripts = scripts
        if name:
            asset.name = name
        if workload_model is not None:
            asset.workload_model = workload_model
        asset.version += 1
        asset.status = "updated"
        asset.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return asset

    def to_dict(self, asset: PerformanceAssetModel) -> dict:
        return {
            "id": str(asset.id),
            "project_id": str(asset.project_id),
            "name": asset.name,
            "tool": asset.tool,
            "workload_model": asset.workload_model,
            "throughput_config": asset.throughput_config,
            "scripts": asset.scripts,
            "scenarios": asset.scenarios,
            "correlation_rules": asset.correlation_rules,
            "parameterization": asset.parameterization,
            "data_pools": asset.data_pools,
            "flow_distribution": asset.flow_distribution,
            "version": asset.version,
            "parent_id": str(asset.parent_id) if asset.parent_id else None,
            "status": asset.status,
            "created_at": asset.created_at.isoformat(),
            "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        }

    def run_to_dict(self, run: PerformanceRunModel) -> dict:
        metrics = run.metrics if isinstance(run.metrics, dict) else {}
        return {
            "id": str(run.id),
            "project_id": str(run.project_id),
            "asset_id": str(run.asset_id),
            "agent_id": str(run.agent_id) if run.agent_id else None,
            "workload_profile": run.workload_profile,
            "status": run.status,
            "summary": run.summary,
            "metrics": metrics.get("summary", metrics) if isinstance(metrics, dict) else metrics,
            "dashboard": metrics,
            "logs": run.logs,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    def agent_to_dict(self, agent: LoadAgentModel) -> dict:
        return {
            "id": str(agent.id),
            "project_id": str(agent.project_id) if agent.project_id else None,
            "name": agent.name,
            "host": agent.host,
            "agent_type": agent.agent_type,
            "max_vus": agent.max_vus,
            "status": agent.status,
            "capabilities": agent.capabilities,
            "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        }
