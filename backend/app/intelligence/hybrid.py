"""Hybrid intelligence — combines QEOS Native engine with local neural enhancement."""

import json
import re
from typing import Any

import httpx
import structlog

from app.config import settings
from app.intelligence.engine import TaskType, get_intelligence_engine
from app.llm.base import LLMMessage, LLMProvider, LLMResponse

logger = structlog.get_logger()

ENHANCE_PROMPT = """You are QEOS Neural Enhancer, a quality engineering specialist.
You receive baseline QA output from the QEOS rule engine. Your job is to ADD valuable
edge cases, boundary tests, and scenarios the rule engine may have missed.

Rules:
- Return ONLY valid JSON with the SAME schema as the baseline
- KEEP all existing test_cases and test_scenarios from baseline
- ADD new test_cases for edge cases (don't remove existing ones)
- Focus on: boundary values, error paths, security edge cases, integration gaps
- If baseline is complete, return it unchanged

Baseline output:
{baseline}

Original requirement:
{requirement}
"""


class QEOSHybridProvider(LLMProvider):
    """
    Hybrid mode: QEOS Native engine (always) + optional Ollama neural enhancement.
    Works offline with native-only when Ollama is unavailable.
    """

    name = "qeos-hybrid"

    def __init__(self) -> None:
        self._engine = get_intelligence_engine()
        self._ollama_url = settings.ollama_base_url.rstrip("/")
        self._ollama_model = settings.ollama_model

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        models = ["qeos-hybrid-v1"]
        if self._ollama_available_sync():
            models.append(f"qeos-hybrid+{self._ollama_model}")
        return models

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        system = next((m.content for m in messages if m.role.value == "system"), "")
        user = next((m.content for m in reversed(messages) if m.role.value == "user"), "")

        # Step 1: Always run native engine first
        input_data = self._engine._parse_user_input(user)
        task = self._engine.detect_task(system, user)
        native_result = self._engine.generate(task, input_data)
        native_result["_mode"] = "native"

        # Step 2: Try neural enhancement if Ollama is available
        neural_used = False
        if await self._ollama_available():
            try:
                enhanced = await self._neural_enhance(native_result, input_data, temperature)
                if enhanced:
                    native_result = self._merge_results(native_result, enhanced)
                    native_result["_mode"] = "hybrid"
                    neural_used = True
            except Exception as e:
                logger.warning("hybrid_neural_skipped", error=str(e))

        content = json.dumps(native_result, indent=2)
        resolved_model = model or ("qeos-hybrid+neural" if neural_used else "qeos-hybrid-v1")

        return LLMResponse(
            content=content,
            model=resolved_model,
            provider=self.name,
            usage={
                "prompt_tokens": len(system) + len(user),
                "completion_tokens": len(content),
                "total_tokens": len(system) + len(user) + len(content),
            },
            raw={
                "engine": "qeos-hybrid",
                "native_version": self._engine.VERSION,
                "neural_enhanced": neural_used,
                "neural_model": self._ollama_model if neural_used else None,
            },
        )

    async def _ollama_available(self) -> bool:
        if not settings.qeos_enable_neural and not settings.qeos_hybrid_auto:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._ollama_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def _ollama_available_sync(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self._ollama_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def _neural_enhance(
        self, baseline: dict, input_data: dict, temperature: float
    ) -> dict | None:
        requirement = input_data.get("content", json.dumps(input_data))[:2000]
        prompt = ENHANCE_PROMPT.format(
            baseline=json.dumps(baseline, indent=2)[:4000],
            requirement=requirement,
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._ollama_url}/api/chat",
                json={
                    "model": self._ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": min(temperature, 0.4)},
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        return None

    def _merge_results(self, native: dict, neural: dict) -> dict:
        """Merge native baseline with neural additions — native structure wins."""
        merged = dict(native)

        # Merge test_cases (dedupe by title)
        native_cases = merged.get("test_cases", [])
        neural_cases = neural.get("test_cases", [])
        seen_titles = {c.get("title", "") for c in native_cases}
        for case in neural_cases:
            title = case.get("title", "")
            if title and title not in seen_titles:
                case["_source"] = "neural"
                native_cases.append(case)
                seen_titles.add(title)
        merged["test_cases"] = native_cases

        # Merge scenarios
        native_scenarios = set(merged.get("test_scenarios", []))
        for scenario in neural.get("test_scenarios", []):
            if scenario not in native_scenarios:
                merged.setdefault("test_scenarios", []).append(scenario)
                native_scenarios.add(scenario)

        # Update coverage if present
        if "coverage_matrix" in merged and neural_cases:
            cm = merged["coverage_matrix"]
            cm["covered_requirements"] = cm.get("covered_requirements", 0)
            total = cm.get("total_requirements", 1)
            cm["coverage_percentage"] = round(
                min(100.0, (len(native_cases) / max(total, 1)) * 100), 1
            )

        merged["_neural_enhanced"] = True
        merged["_neural_added_cases"] = len(neural_cases)
        return merged
