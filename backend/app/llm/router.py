import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.intelligence.provider import QEOSNativeProvider
from app.llm.providers import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAIProvider

logger = structlog.get_logger()


class LLMRouter:
    """
    Routes requests to configured LLM providers with fallback support.
    Supports cost optimization by preferring cheaper models for simple tasks.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        # QEOS Native is always registered first — zero external dependencies
        from app.intelligence.hybrid import QEOSHybridProvider

        provider_classes = [
            QEOSNativeProvider,
            QEOSHybridProvider,
            OpenAIProvider,
            AnthropicProvider,
            GeminiProvider,
            OllamaProvider,
        ]
        for provider_cls in provider_classes:
            instance = provider_cls()
            if instance.is_available():
                self._providers[instance.name] = instance

    def list_providers(self) -> list[dict]:
        return [
            {
                "name": name,
                "models": provider.list_models(),
                "available": provider.is_available(),
            }
            for name, provider in self._providers.items()
        ]

    def get_provider(self, name: str | None = None) -> LLMProvider:
        provider_name = name or settings.default_llm_provider
        if provider_name not in self._providers:
            available = list(self._providers.keys())
            if not available:
                raise RuntimeError("No LLM providers configured")
            provider_name = available[0]
            logger.warning("provider_fallback", requested=name, using=provider_name)
        return self._providers[provider_name]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        provider: str | None = None,
        fallback_providers: list[str] | None = None,
        **kwargs,
    ) -> LLMResponse:
        providers_to_try = [provider or settings.default_llm_provider]
        if fallback_providers:
            providers_to_try.extend(fallback_providers)

        last_error: Exception | None = None
        for provider_name in providers_to_try:
            try:
                llm = self.get_provider(provider_name)
                resolved_model = model or settings.default_llm_model
                return await llm.complete(messages, resolved_model, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning("llm_provider_failed", provider=provider_name, error=str(e))

        raise RuntimeError(f"All LLM providers failed: {last_error}")


_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
