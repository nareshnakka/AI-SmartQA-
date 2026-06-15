"""Parse multimodal studio inputs into test cases and performance flows."""

import json
import re
from typing import Any

from app.config import settings
from app.intelligence.engine import TaskType, get_intelligence_engine
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router


class StudioInputParser:
    """Convert prompts, steps, NFR docs, video transcripts into structured QA artifacts."""

    def __init__(self, llm_provider: str | None = None) -> None:
        self.provider = llm_provider or settings.default_llm_provider
        self.engine = get_intelligence_engine()

    async def to_test_cases(self, input_type: str, content: str | dict | list) -> list[dict]:
        text = self._as_text(content)
        if input_type in ("prompt", "requirements", "user_story", "bdd"):
            return await self._from_requirements(text, input_type)
        if input_type == "steps":
            return self._from_steps(text)
        if input_type == "video":
            return await self._from_video(text)
        if input_type == "nfr":
            return await self._from_nfr_functional(text)
        raise ValueError(f"Unsupported functional input type: {input_type}")

    async def to_performance_inputs(
        self,
        input_type: str,
        content: str | dict | list,
        base_url: str = "https://example.com",
    ) -> tuple[list[dict], dict | None, dict | None]:
        """Returns (flows, throughput_config, slas)."""
        text = self._as_text(content)
        if input_type == "nfr":
            return self._nfr_to_performance(text, base_url)
        if input_type == "prompt":
            cases = await self._from_requirements(text, "performance")
            flows = self._cases_to_flows(cases, base_url)
            return flows, {"target_rps": 100}, None
        if input_type == "steps":
            cases = self._from_steps(text)
            return self._cases_to_flows(cases, base_url), None, None
        if input_type == "video":
            cases = await self._from_video(text)
            return self._cases_to_flows(cases, base_url), None, None
        raise ValueError(f"Unsupported performance input type: {input_type}")

    async def _from_requirements(self, content: str, source_type: str) -> list[dict]:
        if self.provider in ("qeos-native", "qeos-hybrid"):
            output = self.engine.generate(
                TaskType.REQUIREMENTS,
                {"content": content, "source_type": source_type},
            )
            return output.get("test_cases", [])

        router = get_llm_router()
        system = (
            "You are a QA requirements analyst. Return ONLY valid JSON with key test_cases: "
            "array of {title, description, steps[], expected_results[], priority, tags[]}."
        )
        resp = await router.complete(
            [
                LLMMessage(role=MessageRole.SYSTEM, content=system),
                LLMMessage(role=MessageRole.USER, content=f"Source: {source_type}\n\n{content}"),
            ],
            provider=self.provider,
        )
        return self._parse_json_cases(resp.content)

    def _from_steps(self, content: str) -> list[dict]:
        lines = []
        for raw in content.splitlines():
            line = re.sub(r"^\s*(\d+[\.\)]\s*|[-*]\s*)", "", raw.strip())
            if line:
                lines.append(line)
        if not lines:
            raise ValueError("No steps found in input")
        return [{
            "title": lines[0][:120] if lines else "User flow",
            "description": "Generated from step list",
            "steps": lines,
            "expected_results": [f"Step {i + 1} completes successfully" for i in range(len(lines))],
            "priority": "high",
            "tags": ["studio", "steps"],
        }]

    async def _from_video(self, content: str) -> list[dict]:
        prompt = (
            "Extract a browser test flow from this video session description or transcript. "
            "Return JSON: {test_cases: [{title, steps[], expected_results[]}]}"
        )
        if self.provider in ("qeos-native", "qeos-hybrid"):
            output = self.engine.generate(
                TaskType.REQUIREMENTS,
                {"content": f"Video session flow:\n{content}", "source_type": "user_story"},
            )
            return output.get("test_cases", [])

        router = get_llm_router()
        resp = await router.complete(
            [
                LLMMessage(role=MessageRole.SYSTEM, content=prompt),
                LLMMessage(role=MessageRole.USER, content=content),
            ],
            provider=self.provider,
        )
        return self._parse_json_cases(resp.content)

    async def _from_nfr_functional(self, content: str) -> list[dict]:
        slas = self._extract_slas(content)
        cases = []
        if slas.get("max_response_ms"):
            cases.append({
                "title": f"Verify response time under {slas['max_response_ms']}ms",
                "description": "NFR latency validation",
                "steps": ["Execute primary user journey", "Measure end-to-end response time"],
                "expected_results": [f"p95 latency <= {slas['max_response_ms']}ms"],
                "priority": "critical",
                "tags": ["nfr", "latency"],
            })
        if slas.get("target_rps"):
            cases.append({
                "title": f"Verify throughput baseline {slas['target_rps']} RPS",
                "description": "NFR throughput smoke check",
                "steps": ["Run smoke load on critical endpoints"],
                "expected_results": [f"Sustain {slas['target_rps']} requests/sec with acceptable errors"],
                "priority": "high",
                "tags": ["nfr", "throughput"],
            })
        if not cases:
            output = self.engine.generate(
                TaskType.REQUIREMENTS,
                {"content": content, "source_type": "requirements"},
            )
            return output.get("test_cases", [])
        return cases

    def _nfr_to_performance(
        self, content: str, base_url: str
    ) -> tuple[list[dict], dict | None, dict | None]:
        slas = self._extract_slas(content)
        steps = []
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                if re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+", line, re.I):
                    steps.append({"action": "http", "description": line})
                elif "user" in line.lower() or "login" in line.lower() or "navigate" in line.lower():
                    steps.append({"action": "navigate", "description": line, "url": base_url})

        if not steps:
            steps = [
                {"action": "navigate", "description": "Load application home", "url": base_url},
                {"action": "http", "description": "GET /api/health", "method": "GET", "path": "/api/health"},
            ]

        flows = [{"name": "NFR Critical Path", "weight": 100, "steps": steps}]
        throughput = {}
        if slas.get("target_rps"):
            throughput["target_rps"] = slas["target_rps"]
        if slas.get("max_response_ms"):
            throughput["p95_ms"] = slas["max_response_ms"]
        if slas.get("virtual_users"):
            throughput["virtual_users"] = slas["virtual_users"]
        return flows, throughput or None, slas

    def _cases_to_flows(self, cases: list[dict], base_url: str) -> list[dict]:
        flows = []
        for i, tc in enumerate(cases[:10]):
            steps = []
            for step in tc.get("steps", []):
                desc = step if isinstance(step, str) else str(step)
                steps.append({"action": "step", "description": desc, "url": base_url})
            flows.append({
                "name": tc.get("title", f"Flow {i + 1}")[:80],
                "weight": max(10, 100 // max(len(cases), 1)),
                "steps": steps or [{"action": "navigate", "description": "Default", "url": base_url}],
            })
        return flows or [{"name": "Default", "weight": 100, "steps": []}]

    def _extract_slas(self, content: str) -> dict:
        slas: dict[str, Any] = {}
        patterns = [
            (r"(\d+)\s*(?:req(?:uests)?/?s(?:ec)?|rps)", "target_rps", int),
            (r"p95[^\d]*(\d+)\s*ms", "max_response_ms", int),
            (r"response[^\d]*(\d+)\s*ms", "max_response_ms", int),
            (r"latency[^\d]*(\d+)\s*ms", "max_response_ms", int),
            (r"(\d+)\s*(?:concurrent|virtual)\s*users?", "virtual_users", int),
            (r"(\d+)\s*%\s*(?:error|failure)", "max_error_rate", float),
        ]
        for pattern, key, caster in patterns:
            m = re.search(pattern, content, re.I)
            if m:
                slas[key] = caster(m.group(1))
        return slas

    def _parse_json_cases(self, text: str) -> list[dict]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                raise ValueError("LLM did not return valid JSON test cases")
            data = json.loads(m.group())
        if isinstance(data, list):
            return data
        return data.get("test_cases", data.get("cases", []))

    @staticmethod
    def _as_text(content: str | dict | list) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, indent=2)
