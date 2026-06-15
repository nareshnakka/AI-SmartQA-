"""QEOS Native LLM Provider — proprietary intelligence, always available."""

from typing import Any

from app.intelligence.engine import get_intelligence_engine
from app.llm.base import LLMMessage, LLMProvider, LLMResponse


class QEOSNativeProvider(LLMProvider):
    """
    QEOS proprietary intelligence engine.
    No external API keys, no cloud dependency, no GPU required.
    Uses domain-specific knowledge base + pattern engine.
    """

    name = "qeos-native"

    def __init__(self) -> None:
        self._engine = get_intelligence_engine()

    def is_available(self) -> bool:
        return True  # Always available — zero external dependencies

    def list_models(self) -> list[str]:
        return [
            "qeos-intelligence-v1",      # Rule + knowledge engine (default)
            "qeos-intelligence-v1-fast", # Same engine, optimized path
        ]

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

        content = self._engine.generate_from_messages(system, user)

        return LLMResponse(
            content=content,
            model=model or "qeos-intelligence-v1",
            provider=self.name,
            usage={"prompt_tokens": len(system) + len(user), "completion_tokens": len(content), "total_tokens": len(system) + len(user) + len(content)},
            raw={"engine": "qeos-native", "version": self._engine.VERSION},
        )
