from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.models.schemas import GitRepositoryInfo, IntegrationProvider


@dataclass
class IntegrationConfig:
    id: UUID = field(default_factory=uuid4)
    provider: IntegrationProvider = IntegrationProvider.GITHUB
    project_id: UUID | None = None
    credentials: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    status: str = "active"


class BaseIntegration(ABC):
    """Base class for all external integrations."""

    provider: IntegrationProvider
    name: str
    description: str

    @abstractmethod
    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        pass

    async def handle_webhook(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "received", "event": event_type, "provider": self.provider.value}

    def get_oauth_url(self, client_id: str, redirect_uri: str, state: str) -> str | None:
        return None
