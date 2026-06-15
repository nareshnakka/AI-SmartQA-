"""Automation generation from multimodal / multi-source inputs."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRunModel, AutomationAssetModel, DiscoverySessionModel
from app.intelligence.generators import AutomationGenerator
from app.models.schemas import AgentStatus, AgentType
from app.services.automation import FRAMEWORK_LANGUAGES


class InputAdapterRegistry:
    """Parse external sources into test-case-like structures for automation."""

    @staticmethod
    def from_openapi(content: dict | str, base_url: str = "") -> list[dict]:
        if isinstance(content, str):
            content = json.loads(content)
        base = base_url or content.get("servers", [{}])[0].get("url", "https://api.example.com")
        cases = []
        for path, methods in content.get("paths", {}).items():
            for method, op in methods.items():
                if method.startswith("x-"):
                    continue
                summary = op.get("summary", f"{method.upper()} {path}")
                cases.append({
                    "title": summary,
                    "description": op.get("description", ""),
                    "steps": [
                        f"Send {method.upper()} request to {base}{path}",
                        "Verify response status is 2xx",
                        "Validate response schema if defined",
                    ],
                    "expected_results": ["Request succeeds", "Response matches API contract"],
                    "priority": "high" if method.lower() in ("post", "put", "delete") else "medium",
                    "tags": ["api", "openapi", method.lower()],
                })
        return cases[:30]

    @staticmethod
    def from_har(content: dict | str) -> list[dict]:
        if isinstance(content, str):
            content = json.loads(content)
        entries = content.get("log", {}).get("entries", [])
        seen_urls: set[str] = set()
        cases = []
        for entry in entries[:25]:
            req = entry.get("request", {})
            url = req.get("url", "")
            method = req.get("method", "GET")
            if url in seen_urls or not url.startswith("http"):
                continue
            seen_urls.add(url)
            status = entry.get("response", {}).get("status", 200)
            cases.append({
                "title": f"{method} {url.split('?')[0][-60:]}",
                "description": f"Recorded HAR request — expected status {status}",
                "steps": [f"Execute {method} {url}", f"Assert status code {status}"],
                "expected_results": [f"HTTP {status}", "Response body valid"],
                "priority": "medium",
                "tags": ["har", "recorded", method.lower()],
            })
        return cases

    @staticmethod
    def from_postman(content: dict | str) -> list[dict]:
        if isinstance(content, str):
            content = json.loads(content)
        items = content.get("item", [])
        cases = []

        def walk(nodes: list, folder: str = ""):
            for node in nodes:
                if "item" in node:
                    walk(node["item"], folder + "/" + node.get("name", ""))
                elif "request" in node:
                    req = node["request"]
                    method = req.get("method", "GET")
                    url = req.get("url")
                    if isinstance(url, dict):
                        url = "/".join(url.get("path", []))
                    cases.append({
                        "title": node.get("name", "Request"),
                        "description": f"Postman collection{folder}",
                        "steps": [f"{method} {url}", "Verify response"],
                        "expected_results": ["Success response"],
                        "priority": "medium",
                        "tags": ["postman", method.lower()],
                    })

        walk(items)
        return cases[:30]

    @staticmethod
    def from_figma(content: dict | str) -> list[dict]:
        if isinstance(content, str):
            content = json.loads(content)
        cases = []
        document = content.get("document", content)
        pages = document.get("children", []) if isinstance(document, dict) else []

        def walk_nodes(nodes: list, screen: str = ""):
            for node in nodes:
                ntype = node.get("type", "")
                name = node.get("name", "")
                if ntype in ("FRAME", "COMPONENT", "INSTANCE") and name:
                    screen = name
                if ntype == "TEXT" and "button" in name.lower():
                    cases.append({
                        "title": f"Interact with {name} on {screen}",
                        "description": f"Figma UI element on screen {screen}",
                        "steps": [f"Navigate to {screen}", f"Click/tap {name}", "Verify UI response"],
                        "expected_results": ["Element visible", "Action completes"],
                        "priority": "medium",
                        "tags": ["figma", "ui", screen.lower().replace(" ", "-")],
                    })
                if "children" in node:
                    walk_nodes(node["children"], screen)

        for page in pages:
            walk_nodes(page.get("children", []), page.get("name", "Page"))
        return cases[:20] if cases else [{
            "title": "Figma screen navigation",
            "description": "Navigate primary Figma screens",
            "steps": ["Load application", "Verify main frame renders"],
            "expected_results": ["UI renders correctly"],
            "priority": "medium",
            "tags": ["figma", "ui"],
        }]

    @staticmethod
    def from_discovery(session: dict) -> list[dict]:
        cases = []
        for flow in session.get("flow_map", []):
            steps = flow.get("steps", ["Navigate", "Interact", "Verify"])
            cases.append({
                "title": f"Discovery: {flow.get('name', 'Flow')}",
                "description": f"Auto-discovered flow at {flow.get('entry_url', session.get('base_url', ''))}",
                "steps": steps,
                "expected_results": ["Flow completes successfully"],
                "priority": "high" if flow.get("risk") == "high" else "medium",
                "tags": ["discovery", flow.get("id", "flow")],
            })
        for api in session.get("apis", [])[:10]:
            cases.append({
                "title": f"API: {api.get('method', 'GET')} {api.get('path', '/')}",
                "description": api.get("purpose", "Discovered API"),
                "steps": [f"Call {api.get('method', 'GET')} {api.get('path')}"],
                "expected_results": ["Valid response"],
                "priority": "medium",
                "tags": ["api", "discovery"],
            })
        return cases


class AutomationIngestService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.generator = AutomationGenerator()
        self.adapters = InputAdapterRegistry()

    async def generate_from_source(
        self,
        project_id: uuid.UUID,
        source_type: str,
        content: Any,
        framework: str = "playwright",
        name: str | None = None,
        base_url: str = "",
        discovery_session_id: uuid.UUID | None = None,
    ) -> AutomationAssetModel:
        test_cases = await self._parse_source(
            source_type, content, base_url, discovery_session_id, project_id
        )
        if not test_cases:
            raise ValueError(f"No test cases extracted from source type: {source_type}")

        output = self.generator.generate({"framework": framework, "test_cases": test_cases})
        language = FRAMEWORK_LANGUAGES.get(framework, output.get("language", "typescript"))

        asset = AutomationAssetModel(
            project_id=project_id,
            name=name or f"{framework.title()} from {source_type}",
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

        run = AgentRunModel(
            project_id=project_id,
            agent_type=AgentType.AUTOMATION.value,
            status=AgentStatus.COMPLETED.value,
            input_data={"source_type": source_type, "framework": framework, "case_count": len(test_cases)},
            output_data={"test_cases": test_cases, **output},
            llm_provider="qeos-native",
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()
        return asset

    async def _parse_source(
        self,
        source_type: str,
        content: Any,
        base_url: str,
        discovery_session_id: uuid.UUID | None,
        project_id: uuid.UUID,
    ) -> list[dict]:
        if source_type == "discovery" and discovery_session_id:
            session = await self.db.get(DiscoverySessionModel, discovery_session_id)
            if session and session.project_id == project_id:
                from app.services.discovery import DiscoveryService
                return self.adapters.from_discovery(DiscoveryService(self.db).to_dict(session))

        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass

        parsers = {
            "openapi": lambda c: self.adapters.from_openapi(c, base_url),
            "swagger": lambda c: self.adapters.from_openapi(c, base_url),
            "har": self.adapters.from_har,
            "postman": self.adapters.from_postman,
            "figma": self.adapters.from_figma,
            "discovery": self.adapters.from_discovery,
            "test_cases": lambda c: c if isinstance(c, list) else [c],
        }
        parser = parsers.get(source_type)
        if not parser:
            raise ValueError(f"Unsupported source type: {source_type}. Supported: {list(parsers.keys())}")
        return parser(content)

    def list_source_types(self) -> list[dict]:
        return [
            {"id": "test_cases", "name": "Test Cases", "description": "Existing project test cases (Phase 1)"},
            {"id": "openapi", "name": "OpenAPI / Swagger", "description": "REST API specification JSON/YAML"},
            {"id": "har", "name": "HAR Recording", "description": "Browser HTTP archive"},
            {"id": "postman", "name": "Postman Collection", "description": "Postman v2.1 collection JSON"},
            {"id": "figma", "name": "Figma Export", "description": "Figma file JSON export"},
            {"id": "discovery", "name": "Discovery Session", "description": "Application discovery flows and APIs"},
        ]
