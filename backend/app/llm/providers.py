import json
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def is_available(self) -> bool:
        return bool(settings.openai_api_key)

    def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini"]

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if not self._client:
            raise RuntimeError("OpenAI API key not configured")

        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=model,
            provider=self.name,
            usage=usage,
            raw=response,
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        self._client = None
        if settings.anthropic_api_key:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    def is_available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def list_models(self) -> list[str]:
        return [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        if not self._client:
            raise RuntimeError("Anthropic API key not configured")

        system = next((m.content for m in messages if m.role.value == "system"), None)
        user_messages = [
            {"role": m.role.value, "content": m.content}
            for m in messages
            if m.role.value != "system"
        ]

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens or 1024,
            system=system or "",
            messages=user_messages,
            temperature=temperature,
        )

        content = response.content[0].text if response.content else ""
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            usage=usage,
            raw=response,
        )


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self._configured = bool(settings.google_api_key)
        if self._configured:
            import google.generativeai as genai

            genai.configure(api_key=settings.google_api_key)
            self._genai = genai

    def is_available(self) -> bool:
        return self._configured

    def list_models(self) -> list[str]:
        return ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if not self._configured:
            raise RuntimeError("Google API key not configured")

        prompt = "\n".join(f"{m.role.value}: {m.content}" for m in messages)
        gemini_model = self._genai.GenerativeModel(model)
        response = await gemini_model.generate_content_async(
            prompt,
            generation_config={"temperature": temperature},
        )

        return LLMResponse(
            content=response.text or "",
            model=model,
            provider=self.name,
            raw=response,
        )


class OllamaProvider(LLMProvider):
    """Open-source / local models via Ollama."""

    name = "ollama"

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return ["llama3.2", "mistral", "deepseek-r1", "codellama", "qwen2.5"]

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": m.role.value, "content": m.content} for m in messages],
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            data = response.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            model=model,
            provider=self.name,
            raw=data,
        )
