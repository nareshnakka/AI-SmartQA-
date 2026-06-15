"""Unified Quality Studio — one-stop orchestration for all QA needs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    AutomationAssetModel,
    ExecutionRunModel,
    NfrDocumentModel,
    PerformanceAssetModel,
    ReleaseModel,
    RequirementModel,
    SprintModel,
    TestCaseModel,
)
from app.services.automation import AutomationService, FRAMEWORK_LANGUAGES
from app.services.automation_ingest import AutomationIngestService
from app.services.execution import ExecutionService
from app.services.generation import GenerationService
from app.services.performance import PerformanceService
from app.services.studio_inputs import StudioInputParser
from app.intelligence.generators import AutomationGenerator


class QualityStudioService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def overview(self, project_id: uuid.UUID) -> dict:
        tc_count = await self.db.scalar(
            select(func.count()).select_from(TestCaseModel).where(TestCaseModel.project_id == project_id)
        ) or 0
        auto_count = await self.db.scalar(
            select(func.count()).select_from(AutomationAssetModel).where(AutomationAssetModel.project_id == project_id)
        ) or 0
        perf_count = await self.db.scalar(
            select(func.count()).select_from(PerformanceAssetModel).where(PerformanceAssetModel.project_id == project_id)
        ) or 0
        run_count = await self.db.scalar(
            select(func.count()).select_from(ExecutionRunModel).where(ExecutionRunModel.project_id == project_id)
        ) or 0
        sprints = await self.list_sprints(project_id)
        releases = await self.list_releases(project_id)
        nfrs = await self.list_nfr_documents(project_id)

        from app.llm.router import get_llm_router
        providers = get_llm_router().list_providers()

        return {
            "project_id": str(project_id),
            "stats": {
                "test_cases": tc_count,
                "automation_assets": auto_count,
                "performance_assets": perf_count,
                "execution_runs": run_count,
                "sprints": len(sprints),
                "releases": len(releases),
                "nfr_documents": len(nfrs),
            },
            "default_llm_provider": settings.default_llm_provider,
            "llm_providers": providers,
            "capabilities": [
                "functional_generation",
                "standalone_automation",
                "standalone_performance",
                "sprint_release_management",
                "batch_execution",
                "discovery",
            ],
            "automation_input_types": AutomationIngestService(self.db).list_source_types()
            + [
                {"id": "prompt", "name": "Natural Language Prompt", "description": "Describe flows in plain English"},
                {"id": "steps", "name": "Step List", "description": "Numbered or bulleted manual steps"},
                {"id": "video", "name": "Video / Session Transcript", "description": "Recording description or transcript"},
                {"id": "nfr", "name": "NFR Document", "description": "SLA, latency, throughput requirements"},
            ],
            "performance_input_types": [
                {"id": "prompt", "name": "Prompt", "description": "Describe load scenarios in natural language"},
                {"id": "steps", "name": "User Steps", "description": "Convert user journey steps to load flows"},
                {"id": "nfr", "name": "NFR / SLA Document", "description": "Latency, RPS, concurrency targets"},
                {"id": "video", "name": "Video Transcript", "description": "Replay flow from session recording"},
                {"id": "har", "name": "HAR Recording", "description": "HTTP archive from browser"},
                {"id": "openapi", "name": "OpenAPI Spec", "description": "API endpoints as load targets"},
            ],
        }

    # --- Sprint / Release ---

    async def list_sprints(self, project_id: uuid.UUID) -> list[SprintModel]:
        result = await self.db.execute(
            select(SprintModel).where(SprintModel.project_id == project_id).order_by(SprintModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_sprint(
        self,
        project_id: uuid.UUID,
        name: str,
        goal: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        test_case_ids: list[str] | None = None,
    ) -> SprintModel:
        sprint = SprintModel(
            project_id=project_id,
            name=name,
            goal=goal,
            start_date=start_date,
            end_date=end_date,
            test_case_ids=test_case_ids or [],
            status="active",
        )
        self.db.add(sprint)
        await self.db.flush()
        return sprint

    async def update_sprint(self, sprint_id: uuid.UUID, **fields) -> SprintModel | None:
        sprint = await self.db.get(SprintModel, sprint_id)
        if not sprint:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(sprint, k):
                setattr(sprint, k, v)
        await self.db.flush()
        return sprint

    async def list_releases(self, project_id: uuid.UUID) -> list[ReleaseModel]:
        result = await self.db.execute(
            select(ReleaseModel).where(ReleaseModel.project_id == project_id).order_by(ReleaseModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_release(
        self,
        project_id: uuid.UUID,
        name: str,
        version: str = "1.0.0",
        target_date: str | None = None,
        sprint_ids: list[str] | None = None,
        test_case_ids: list[str] | None = None,
        notes: str | None = None,
    ) -> ReleaseModel:
        release = ReleaseModel(
            project_id=project_id,
            name=name,
            version=version,
            target_date=target_date,
            sprint_ids=sprint_ids or [],
            test_case_ids=test_case_ids or [],
            notes=notes,
            status="planned",
        )
        self.db.add(release)
        await self.db.flush()
        return release

    # --- NFR ---

    async def list_nfr_documents(self, project_id: uuid.UUID) -> list[NfrDocumentModel]:
        result = await self.db.execute(
            select(NfrDocumentModel).where(NfrDocumentModel.project_id == project_id).order_by(NfrDocumentModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_nfr_document(
        self,
        project_id: uuid.UUID,
        title: str,
        content: str,
        source_type: str = "mixed",
    ) -> NfrDocumentModel:
        parser = StudioInputParser()
        slas = parser._extract_slas(content)
        doc = NfrDocumentModel(
            project_id=project_id,
            title=title,
            content=content,
            source_type=source_type,
            slas=slas or None,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    # --- Functional generation ---

    async def generate_functional(
        self,
        project_id: uuid.UUID,
        input_type: str,
        content: str | dict | list,
        title: str | None = None,
        llm_provider: str | None = None,
        persist: bool = True,
    ) -> dict:
        if input_type in ("prompt", "requirements", "user_story", "bdd") and isinstance(content, str):
            gen = GenerationService(self.db)
            text = content if isinstance(content, str) else str(content)
            result = await gen.generate_from_requirement(
                project_id,
                text,
                source_type=input_type if input_type != "prompt" else "user_story",
                title=title,
                llm_provider=llm_provider or settings.default_llm_provider,
            )
            return {"mode": "full_pipeline", **result}

        parser = StudioInputParser(llm_provider)
        cases_data = await parser.to_test_cases(input_type, content)
        if not persist:
            return {"test_cases": cases_data, "count": len(cases_data)}

        saved = []
        for tc in cases_data:
            case = TestCaseModel(
                project_id=project_id,
                title=tc.get("title", "Untitled"),
                description=tc.get("description", ""),
                steps=tc.get("steps", []),
                expected_results=tc.get("expected_results", []),
                priority=tc.get("priority", "medium"),
                tags=tc.get("tags", []) + ["studio"],
                status="generated",
            )
            self.db.add(case)
            saved.append(case)
        await self.db.flush()
        return {
            "test_cases": [{"id": str(c.id), "title": c.title, "steps": c.steps} for c in saved],
            "count": len(saved),
            "llm_provider": llm_provider or settings.default_llm_provider,
        }

    # --- Standalone automation (no manual test cases required) ---

    async def generate_automation_standalone(
        self,
        project_id: uuid.UUID,
        input_type: str,
        content: str | dict | list,
        framework: str = "playwright",
        name: str | None = None,
        base_url: str = "",
        llm_provider: str | None = None,
        discovery_session_id: uuid.UUID | None = None,
    ) -> dict:
        ingest = AutomationIngestService(self.db)
        known_sources = {s["id"] for s in ingest.list_source_types()}

        if input_type in known_sources:
            asset = await ingest.generate_from_source(
                project_id, input_type, content, framework, name, base_url, discovery_session_id
            )
            return {"asset": AutomationService(self.db).to_dict(asset), "source": input_type}

        parser = StudioInputParser(llm_provider)
        cases = await parser.to_test_cases(input_type, content)
        generator = AutomationGenerator()
        output = generator.generate({"framework": framework, "test_cases": cases})
        language = FRAMEWORK_LANGUAGES.get(framework, output.get("language", "typescript"))

        asset = AutomationAssetModel(
            project_id=project_id,
            name=name or f"{framework.title()} — {input_type}",
            framework=framework,
            language=language,
            files=output.get("files", []),
            dependencies=output.get("dependencies", []),
            ci_pipeline_snippet=output.get("ci_pipeline_snippet"),
            test_case_ids=[],
            version=1,
            status="generated",
        )
        self.db.add(asset)
        await self.db.flush()
        return {
            "asset": AutomationService(self.db).to_dict(asset),
            "source": input_type,
            "derived_cases": len(cases),
            "llm_provider": llm_provider or settings.default_llm_provider,
        }

    # --- Standalone performance (no automation dependency) ---

    async def generate_performance_standalone(
        self,
        project_id: uuid.UUID,
        input_type: str,
        content: str | dict | list,
        tool: str = "k6",
        workload_profile: str = "load",
        base_url: str = "https://example.com",
        name: str | None = None,
        llm_provider: str | None = None,
        nfr_document_id: uuid.UUID | None = None,
        discovery_session_id: uuid.UUID | None = None,
    ) -> dict:
        perf = PerformanceService(self.db)

        if input_type in ("har", "openapi") or discovery_session_id:
            asset = await perf.generate(
                project_id,
                tool=tool,
                name=name,
                workload_profile=workload_profile,
                base_url=base_url,
                har_content=content if input_type == "har" else None,
                openapi_content=content if input_type == "openapi" else None,
                discovery_session_id=discovery_session_id,
            )
            return {"asset": perf.to_dict(asset), "source": input_type or "discovery"}

        if nfr_document_id:
            doc = await self.db.get(NfrDocumentModel, nfr_document_id)
            if doc and doc.project_id == project_id:
                content = doc.content
                input_type = "nfr"

        parser = StudioInputParser(llm_provider)
        flows, throughput, slas = await parser.to_performance_inputs(input_type, content, base_url)

        asset = await perf.generate(
            project_id,
            tool=tool,
            name=name or f"{tool.upper()} — {input_type}",
            workload_profile=workload_profile,
            base_url=base_url,
            throughput_config=throughput,
            flows=flows,
        )
        if slas and asset.scenarios:
            scenarios = list(asset.scenarios or [])
            for s in scenarios:
                s["sla"] = slas
            asset.scenarios = scenarios
            await self.db.flush()

        return {
            "asset": perf.to_dict(asset),
            "source": input_type,
            "flows": len(flows),
            "slas": slas,
            "llm_provider": llm_provider or settings.default_llm_provider,
        }

    async def execute_sprint(
        self,
        project_id: uuid.UUID,
        sprint_id: uuid.UUID,
        framework: str = "playwright",
        base_url: str = "https://example.com",
        mode: str = "live",
    ) -> dict:
        sprint = await self.db.get(SprintModel, sprint_id)
        if not sprint or sprint.project_id != project_id:
            raise ValueError("Sprint not found")
        if not sprint.test_case_ids:
            raise ValueError("Sprint has no test cases assigned")

        exec_svc = ExecutionService(self.db)
        run = await exec_svc.start_batch_run(
            project_id=project_id,
            test_case_ids=[uuid.UUID(t) for t in sprint.test_case_ids],
            mode=mode,
            framework=framework,
            base_url=base_url,
            run_name=f"Sprint {sprint.name}",
            sprint=sprint.name,
            background=True,
        )
        return exec_svc.to_dict(run)

    @staticmethod
    def sprint_dict(s: SprintModel) -> dict:
        return {
            "id": str(s.id),
            "project_id": str(s.project_id),
            "name": s.name,
            "goal": s.goal,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "status": s.status,
            "test_case_ids": s.test_case_ids or [],
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    @staticmethod
    def release_dict(r: ReleaseModel) -> dict:
        return {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "name": r.name,
            "version": r.version,
            "target_date": r.target_date,
            "status": r.status,
            "sprint_ids": r.sprint_ids or [],
            "test_case_ids": r.test_case_ids or [],
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    @staticmethod
    def nfr_dict(n: NfrDocumentModel) -> dict:
        return {
            "id": str(n.id),
            "project_id": str(n.project_id),
            "title": n.title,
            "content": n.content,
            "source_type": n.source_type,
            "slas": n.slas,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
