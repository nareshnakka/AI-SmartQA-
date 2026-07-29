from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class LLMImage:
    """One image part for vision models (PNG/JPEG bytes as base64)."""

    data_base64: str
    mime_type: str = "image/jpeg"
    detail: str = "low"


@dataclass
class LLMMessage:
    role: MessageRole
    content: str
    images: list[LLMImage] = field(default_factory=list)


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        pass

    def supports_vision(self) -> bool:
        return False
