"""Phase 5 — Discovery with QA Agent navigation + selective test commit."""

import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DiscoverySessionModel, RequirementModel, TestCaseModel
from app.runners.browser_discovery import crawl_application
from app.runners.qa_agent import navigate_as_qa_user


FLOW_KEYWORDS = {
    "login": {"screens": ["Login", "Dashboard"], "apis": ["/api/auth/login", "/api/auth/session"]},
    "checkout": {"screens": ["Cart", "Checkout", "Order Confirmation"], "apis": ["/api/cart", "/api/orders"]},
    "register": {"screens": ["Registration", "Email Verification"], "apis": ["/api/auth/register"]},
    "search": {"screens": ["Search Results", "Product Detail"], "apis": ["/api/search", "/api/products"]},
    "payment": {"screens": ["Payment", "Receipt"], "apis": ["/api/payments"]},
    "profile": {"screens": ["User Profile", "Settings"], "apis": ["/api/users/me"]},
    "admin": {"screens": ["Admin Dashboard", "User Management"], "apis": ["/api/admin/users"]},
}


class DiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_discovery(
        self,
        project_id: uuid.UUID,
        base_url: str,
        name: str | None = None,
        credentials_hint: str | None = None,
        requirements: str | None = None,
        mode: str = "agent",
        username: str | None = None,
        password: str | None = None,
        background: bool = True,
    ) -> DiscoverySessionModel:
        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        host = parsed.netloc or parsed.path
        base = f"{parsed.scheme or 'https'}://{host}"

        session = DiscoverySessionModel(
            project_id=project_id,
            name=name or f"QA Discovery — {host}",
            base_url=base,
            credentials_hint=credentials_hint,
            requirements=requirements,
            status="running",
            navigation_log=[{
                "type": "status",
                "message": "QA Agent initializing…",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        )
        self.db.add(session)
        await self.db.flush()

        use_agent = mode in ("agent", "browser", "both")
        if background and use_agent:
            from app.services.discovery_worker import enqueue_discovery

            await self.db.commit()
            enqueue_discovery(
                session.id, project_id, base, mode, requirements,
                username, password, name, credentials_hint,
            )
            return session

        await self.execute_discovery(
            session.id, project_id, base, mode, requirements,
            username, password, name, credentials_hint,
        )
        return session

    async def execute_discovery(
        self,
        session_id: uuid.UUID,
        project_id: uuid.UUID,
        base_url: str,
        mode: str,
        requirements: str | None,
        username: str | None,
        password: str | None,
        name: str | None,
        credentials_hint: str | None,
    ) -> None:
        session = await self.db.get(DiscoverySessionModel, session_id)
        if not session:
            raise ValueError("Discovery session not found")

        req_text = requirements or session.requirements or ""
        if not req_text:
            result = await self.db.execute(
                select(RequirementModel).where(RequirementModel.project_id == project_id).limit(5)
            )
            req_text = "\n".join(r.content for r in result.scalars().all())

        flows, screens, apis = self._infer_from_text(req_text, base_url)
        crawl_meta: dict = {}
        proposed: list[dict] = []
        nav_log: list[dict] = list(session.navigation_log or [])

        async def on_event(event: dict) -> None:
            from app.services.discovery_worker import (
                is_discovery_cancel_requested,
                is_nav_clear_requested,
                clear_nav_clear_request,
            )
            from sqlalchemy.orm.attributes import flag_modified

            if is_discovery_cancel_requested(session_id):
                return
            if is_nav_clear_requested(session_id):
                nav_log.clear()
                clear_nav_clear_request(session_id)
            fresh = await self.db.get(DiscoverySessionModel, session_id)
            if not fresh:
                return
            nav_log.append(event)
            fresh.navigation_log = list(nav_log[-200:])
            flag_modified(fresh, "navigation_log")
            await self.db.flush()

        if mode in ("agent", "browser", "both"):
            from app.services.discovery_worker import is_discovery_cancel_requested

            if is_discovery_cancel_requested(session_id):
                session.status = "cancelled"
                session.completed_at = datetime.now(timezone.utc)
                await self.db.flush()
                return

            agent_result = await navigate_as_qa_user(
                base_url,
                username=username,
                password=password,
                requirements=req_text,
                on_event=on_event,
            )
            crawl_meta = {
                "crawl_mode": agent_result.get("mode"),
                "pages_crawled": agent_result.get("pages_crawled", 0),
            }
            proposed = agent_result.get("proposed_test_cases", [])
            nav_log = agent_result.get("navigation_log", nav_log)
            if agent_result.get("screens"):
                screens = self._merge_screens(screens, agent_result["screens"])
            if agent_result.get("flow_map"):
                flows = self._merge_flows(flows, agent_result["flow_map"])
            if agent_result.get("apis"):
                apis = self._merge_apis(apis, agent_result["apis"])

        if mode == "static" or (mode == "both" and not proposed):
            if mode != "agent":
                crawled = await crawl_application(base_url, username=username, password=password)
                crawl_meta = {"crawl_mode": crawled.get("mode"), "pages_crawled": crawled.get("pages_crawled", 0)}
                if crawled.get("screens"):
                    screens = self._merge_screens(screens, crawled["screens"])
                if crawled.get("flow_map"):
                    flows = self._merge_flows(flows, crawled["flow_map"])
                if crawled.get("apis"):
                    apis = self._merge_apis(apis, crawled["apis"])

        if mode == "static" and not proposed:
            proposed = self._propose_from_static_flows(flows, base_url)

        journeys = await self._journeys_from_tests(project_id, flows)
        coverage = self._coverage_matrix(journeys, screens)
        coverage["crawl"] = crawl_meta
        coverage["discovery_mode"] = mode
        coverage["proposed_test_cases"] = len(proposed)

        from app.services.discovery_worker import is_discovery_cancel_requested

        session = await self.db.get(DiscoverySessionModel, session_id)
        if not session:
            return
        if is_discovery_cancel_requested(session_id):
            session.status = "cancelled"
            session.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            return

        session.flow_map = flows
        session.screens = screens
        session.apis = apis
        session.critical_journeys = journeys
        session.coverage_matrix = coverage
        session.proposed_test_cases = proposed
        session.navigation_log = nav_log
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        if name:
            session.name = name
        if credentials_hint:
            session.credentials_hint = credentials_hint
        if req_text:
            session.requirements = req_text
        await self.db.flush()

    def _propose_from_static_flows(self, flows: list, base_url: str) -> list[dict]:
        cases = []
        for flow in flows:
            steps_raw = flow.get("steps") or []
            steps = []
            for i, s in enumerate(steps_raw, start=1):
                steps.append({"order": i, "action": "navigate" if i == 1 else "verify", "description": str(s)})
            cases.append({
                "id": f"ptc-{flow.get('id', uuid.uuid4().hex[:8])}",
                "title": f"{flow.get('name', 'Flow')} — journey test",
                "type": "functional",
                "priority": "high" if flow.get("risk") == "high" else "medium",
                "source": "static",
                "risk": flow.get("risk", "medium"),
                "steps": steps,
                "expected_results": [f"User completes {flow.get('name')} successfully"],
            })
        return cases

    async def discover(
        self,
        project_id: uuid.UUID,
        base_url: str,
        name: str | None = None,
        credentials_hint: str | None = None,
        requirements: str | None = None,
        mode: str = "agent",
        username: str | None = None,
        password: str | None = None,
    ) -> DiscoverySessionModel:
        return await self.start_discovery(
            project_id, base_url, name, credentials_hint, requirements,
            mode, username, password, background=False,
        )

    def _merge_screens(self, static: list, crawled: list) -> list:
        seen = {s.get("name") for s in static}
        merged = list(static)
        for s in crawled:
            key = s.get("name") or s.get("url")
            if key not in seen:
                seen.add(key)
                merged.append(s)
        return merged

    def _merge_flows(self, static: list, crawled: list) -> list:
        if not static:
            return crawled
        ids = {f.get("id") for f in static}
        merged = list(static)
        for f in crawled:
            if f.get("id") not in ids:
                merged.append(f)
        return merged

    def _merge_apis(self, static: list, crawled: list) -> list:
        paths = {a.get("path") for a in static}
        merged = list(static)
        for a in crawled:
            if a.get("path") not in paths:
                merged.append(a)
        return merged

    def _infer_from_text(self, text: str, base: str) -> tuple[list, list, list]:
        lower = text.lower()
        flows: list[dict] = []
        screens: list[dict] = []
        apis: list[dict] = []
        seen_screens: set[str] = set()

        for keyword, template in FLOW_KEYWORDS.items():
            if keyword in lower or keyword.replace("_", " ") in lower:
                flow_id = f"flow-{keyword}"
                flows.append({
                    "id": flow_id,
                    "name": keyword.replace("_", " ").title(),
                    "entry_url": f"{base}/{keyword.replace('_', '-')}",
                    "steps": template["screens"],
                    "risk": "high" if keyword in ("payment", "checkout", "login") else "medium",
                    "source": "static",
                })
                for screen in template["screens"]:
                    if screen not in seen_screens:
                        seen_screens.add(screen)
                        screens.append({
                            "name": screen,
                            "url_pattern": f"{base}/**/{screen.lower().replace(' ', '-')}",
                            "elements": ["primary_action", "form_fields", "navigation"],
                        })
                for api_path in template["apis"]:
                    apis.append({
                        "method": "POST" if "auth" in api_path or "orders" in api_path else "GET",
                        "path": api_path,
                        "purpose": keyword,
                    })

        if not flows:
            flows = [{
                "id": "flow-home",
                "name": "Homepage Exploration",
                "entry_url": base,
                "steps": ["Landing", "Navigation", "Primary CTA"],
                "risk": "medium",
                "source": "static",
            }]
            screens = [{"name": "Landing", "url_pattern": base, "elements": ["header", "nav", "cta"]}]
            apis = [{"method": "GET", "path": "/api/health", "purpose": "health_check"}]

        return flows, screens, apis

    async def _journeys_from_tests(self, project_id: uuid.UUID, flows: list) -> list[dict]:
        result = await self.db.execute(
            select(TestCaseModel).where(TestCaseModel.project_id == project_id).limit(20)
        )
        cases = list(result.scalars().all())
        if not cases:
            return [
                {
                    "name": f["name"],
                    "priority": "critical" if f.get("risk") == "high" else "medium",
                    "flow_id": f["id"],
                    "test_coverage": "unmapped",
                }
                for f in flows[:5]
            ]

        journeys = []
        for i, case in enumerate(cases[:10]):
            journeys.append({
                "name": case.title,
                "priority": case.priority,
                "flow_id": flows[i % len(flows)]["id"] if flows else None,
                "test_case_id": str(case.id),
                "test_coverage": "mapped",
                "steps_count": len(case.steps or []),
            })
        return journeys

    def _coverage_matrix(self, journeys: list, screens: list) -> dict:
        mapped = sum(1 for j in journeys if j.get("test_coverage") == "mapped")
        return {
            "total_journeys": len(journeys),
            "mapped_to_tests": mapped,
            "unmapped": len(journeys) - mapped,
            "screen_inventory": len(screens),
            "coverage_percentage": round(mapped / len(journeys) * 100, 1) if journeys else 0,
        }

    async def list_sessions(self, project_id: uuid.UUID) -> list[DiscoverySessionModel]:
        result = await self.db.execute(
            select(DiscoverySessionModel)
            .where(DiscoverySessionModel.project_id == project_id)
            .order_by(DiscoverySessionModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_session(self, session_id: uuid.UUID) -> DiscoverySessionModel | None:
        return await self.db.get(DiscoverySessionModel, session_id)

    def to_dict(self, session: DiscoverySessionModel) -> dict:
        return {
            "id": str(session.id),
            "project_id": str(session.project_id),
            "name": session.name,
            "base_url": session.base_url,
            "credentials_hint": session.credentials_hint,
            "requirements": session.requirements,
            "flow_map": session.flow_map,
            "screens": session.screens,
            "apis": session.apis,
            "critical_journeys": session.critical_journeys,
            "coverage_matrix": session.coverage_matrix,
            "proposed_test_cases": session.proposed_test_cases or [],
            "navigation_log": session.navigation_log or [],
            "discovery_mode": (session.coverage_matrix or {}).get("discovery_mode", "agent"),
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }

    async def clear_navigation_log(self, project_id: uuid.UUID, session_id: uuid.UUID) -> DiscoverySessionModel:
        session = await self.get_session(session_id)
        if not session or session.project_id != project_id:
            raise ValueError("Discovery session not found")
        from app.services.discovery_worker import request_nav_clear
        from sqlalchemy.orm.attributes import flag_modified

        request_nav_clear(session_id)
        session.navigation_log = []
        flag_modified(session, "navigation_log")
        await self.db.flush()
        return session

    async def delete_session(self, project_id: uuid.UUID, session_id: uuid.UUID) -> None:
        session = await self.get_session(session_id)
        if not session or session.project_id != project_id:
            raise ValueError("Discovery session not found")
        if session.status == "running":
            from app.services.discovery_worker import request_cancel_discovery

            request_cancel_discovery(session_id)
        await self.db.delete(session)
        await self.db.flush()

    async def commit_proposed_tests(
        self,
        project_id: uuid.UUID,
        session_id: uuid.UUID,
        test_ids: list[str],
        default_module_id: uuid.UUID | None = None,
        environment_id: uuid.UUID | None = None,
    ) -> dict:
        from app.services.test_cases import create_project_test_case

        session = await self.get_session(session_id)
        if not session or session.project_id != project_id:
            raise ValueError("Discovery session not found")

        proposed = session.proposed_test_cases or []
        selected = [p for p in proposed if p.get("id") in test_ids]
        if not selected:
            raise ValueError("No matching proposed test cases selected")

        committed: list[dict] = []
        for p in selected:
            steps = p.get("steps") or []
            step_texts = [
                s.get("description") if isinstance(s, dict) else str(s)
                for s in steps
            ]
            module_name = p.get("module") or p.get("screen") or "General"
            case = await create_project_test_case(
                self.db,
                project_id,
                title=p.get("title", "Discovered Test"),
                description=f"Captured by QA Agent from {session.base_url}",
                steps=step_texts,
                expected_results=p.get("expected_results") or ["Test completes successfully"],
                priority=p.get("priority", "medium"),
                module_id=default_module_id,
                module_name=module_name if not default_module_id else None,
                environment_id=environment_id,
                tags=["discovery", "qa_agent", p.get("type", "functional"), f"session:{session_id}"],
                status="approved",
                case_type="functional",
            )
            committed.append({
                "id": str(case.id),
                "title": case.title,
                "case_code": case.case_code,
                "module_id": str(case.module_id) if case.module_id else None,
                "environment_id": str(case.environment_id) if case.environment_id else None,
                "steps_count": len(step_texts),
                "proposed_id": p.get("id"),
            })

        journeys = await self._journeys_from_tests(project_id, session.flow_map or [])
        session.critical_journeys = journeys
        session.coverage_matrix = {
            **(session.coverage_matrix or {}),
            **self._coverage_matrix(journeys, session.screens or []),
            "committed_from_session": len(committed),
            "proposed_test_cases": len([p for p in proposed if p.get("id") not in set(test_ids)]),
        }
        # Remove committed proposals from the session review list
        session.proposed_test_cases = [p for p in proposed if p.get("id") not in set(test_ids)]
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(session, "proposed_test_cases")
        await self.db.flush()

        return {
            "session_id": str(session_id),
            "committed_count": len(committed),
            "test_cases_created": len(committed),
            "test_cases": committed,
            "remaining_proposed": len(session.proposed_test_cases or []),
        }

    async def dismiss_proposed_tests(
        self,
        project_id: uuid.UUID,
        session_id: uuid.UUID,
        test_ids: list[str],
    ) -> dict:
        """Remove selected AI-proposed test cases from the session (does not delete project test cases)."""
        session = await self.get_session(session_id)
        if not session or session.project_id != project_id:
            raise ValueError("Discovery session not found")

        if not test_ids:
            raise ValueError("Select at least one proposed test case to remove")

        proposed = session.proposed_test_cases or []
        id_set = set(test_ids)
        remaining = [p for p in proposed if p.get("id") not in id_set]
        removed_count = len(proposed) - len(remaining)
        if removed_count == 0:
            raise ValueError("No matching proposed test cases to remove")

        session.proposed_test_cases = remaining
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(session, "proposed_test_cases")
        session.coverage_matrix = {
            **(session.coverage_matrix or {}),
            "proposed_test_cases": len(remaining),
        }
        await self.db.flush()

        return {
            "session_id": str(session_id),
            "removed_count": removed_count,
            "remaining_count": len(remaining),
        }

    async def generate_tests_from_session(
        self,
        project_id: uuid.UUID,
        session_id: uuid.UUID,
        generate_automation: bool = False,
    ) -> dict:
        """Commit all proposed test cases (legacy bulk action)."""
        session = await self.get_session(session_id)
        if not session or session.project_id != project_id:
            raise ValueError("Discovery session not found")

        ids = [p["id"] for p in (session.proposed_test_cases or []) if p.get("id")]
        if ids:
            return await self.commit_proposed_tests(project_id, session_id, ids)

        from app.services.generation import GenerationService
        from app.services.automation import AutomationService

        gen = GenerationService(self.db)
        created_cases: list[dict] = []
        created_reqs: list[str] = []
        flows = session.flow_map or [{"name": "Application Flow", "steps": ["Explore"], "risk": "medium"}]

        for flow in flows[:8]:
            steps = flow.get("steps") or ["Navigate", "Interact", "Verify"]
            content = (
                f"As a user, I want to complete the {flow.get('name', 'flow')} journey "
                f"on {session.base_url}.\nSteps: {', '.join(str(s) for s in steps)}"
            )
            result = await gen.generate_from_requirement(
                project_id=project_id, content=content, source_type="discovery",
                title=f"Discovery: {flow.get('name', 'Flow')}",
            )
            created_reqs.append(result["requirement_id"])
            created_cases.extend(result.get("test_cases", []))

        automation_asset = None
        if generate_automation and created_cases:
            auto = AutomationService(self.db)
            automation_asset = await auto.generate(project_id, framework="playwright")

        return {
            "session_id": str(session_id),
            "requirements_created": len(created_reqs),
            "test_cases_created": len(created_cases),
            "automation_asset_id": str(automation_asset.id) if automation_asset else None,
        }
