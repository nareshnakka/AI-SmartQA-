from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from app.integrations.base import BaseIntegration, IntegrationConfig
from app.integrations.enterprise import JenkinsIntegration, JiraIntegration
from app.integrations.git_providers import (
    AzureDevOpsIntegration,
    BitbucketIntegration,
    GiteaIntegration,
    GitHubIntegration,
    GitLabIntegration,
)
from app.models.schemas import GitRepositoryInfo, IntegrationProvider, IntegrationResponse

logger = structlog.get_logger()


class IntegrationManager:
    """Central hub for managing all external integrations."""

    def __init__(self) -> None:
        self._integrations: dict[IntegrationProvider, BaseIntegration] = {}
        self._configs: dict[UUID, IntegrationConfig] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        providers = [
            GitHubIntegration(),
            BitbucketIntegration(),
            GitLabIntegration(),
            GiteaIntegration(),
            AzureDevOpsIntegration(),
            JiraIntegration(),
            JenkinsIntegration(),
        ]
        for integration in providers:
            self._integrations[integration.provider] = integration

    def list_providers(self) -> list[dict]:
        return [
            {
                "provider": p.value,
                "name": i.name,
                "description": i.description,
                "category": self._category(p),
            }
            for p, i in self._integrations.items()
        ]

    def _category(self, provider: IntegrationProvider) -> str:
        git_providers = {
            IntegrationProvider.GITHUB,
            IntegrationProvider.BITBUCKET,
            IntegrationProvider.GITLAB,
            IntegrationProvider.GITEA,
            IntegrationProvider.FORGEJO,
            IntegrationProvider.AZURE_DEVOPS,
        }
        cicd_providers = {
            IntegrationProvider.JENKINS,
            IntegrationProvider.GITHUB_ACTIONS,
            IntegrationProvider.GITLAB_CI,
            IntegrationProvider.AZURE_PIPELINES,
            IntegrationProvider.CIRCLECI,
            IntegrationProvider.BAMBOO,
        }
        if provider in git_providers:
            return "source_control"
        if provider in cicd_providers:
            return "ci_cd"
        return "enterprise"

    def get_integration(self, provider: IntegrationProvider, base_url: str | None = None) -> BaseIntegration:
        if provider in (IntegrationProvider.GITLAB, IntegrationProvider.GITEA, IntegrationProvider.FORGEJO):
            if base_url:
                if provider == IntegrationProvider.GITLAB:
                    return GitLabIntegration(base_url=base_url)
                return GiteaIntegration(base_url=base_url)
        if provider not in self._integrations:
            raise KeyError(f"Integration not supported: {provider}")
        return self._integrations[provider]

    async def connect(
        self,
        provider: IntegrationProvider,
        project_id: UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> IntegrationResponse:
        base_url = config.get("base_url") if config else None
        integration = self.get_integration(provider, base_url=base_url)

        valid = await integration.validate_credentials(credentials)
        if not valid:
            raise ValueError(f"Invalid credentials for {provider.value}")

        integration_config = IntegrationConfig(
            provider=provider,
            project_id=project_id,
            credentials=credentials,
            config=config or {},
            status="active",
        )
        self._configs[integration_config.id] = integration_config

        logger.info("integration_connected", provider=provider.value, project_id=str(project_id))

        return IntegrationResponse(
            id=integration_config.id,
            provider=provider,
            project_id=project_id,
            status="active",
            config={k: v for k, v in (config or {}).items() if k != "credentials"},
            created_at=datetime.now(timezone.utc),
        )

    async def list_repositories(self, integration_id: UUID) -> list[GitRepositoryInfo]:
        config = self._configs.get(integration_id)
        if not config:
            raise KeyError(f"Integration not found: {integration_id}")

        base_url = config.config.get("base_url")
        integration = self.get_integration(config.provider, base_url=base_url)
        return await integration.list_repositories(config.credentials)

    async def handle_webhook(
        self,
        provider: IntegrationProvider,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        integration = self.get_integration(provider)
        result = await integration.handle_webhook(event_type, payload)
        logger.info("webhook_processed", provider=provider.value, event=event_type, action=result.get("action"))
        return result

    def get_oauth_url(
        self,
        provider: IntegrationProvider,
        client_id: str,
        redirect_uri: str,
        state: str,
        base_url: str | None = None,
    ) -> str | None:
        integration = self.get_integration(provider, base_url=base_url)
        return integration.get_oauth_url(client_id, redirect_uri, state)

    def list_connected(self, project_id: UUID | None = None) -> list[IntegrationResponse]:
        configs = list(self._configs.values())
        if project_id:
            configs = [c for c in configs if c.project_id == project_id]

        return [
            IntegrationResponse(
                id=c.id,
                provider=c.provider,
                project_id=c.project_id,
                status=c.status,
                config={k: v for k, v in c.config.items()},
                created_at=datetime.now(timezone.utc),
            )
            for c in configs
        ]

    def hydrate(self, configs: list[IntegrationConfig]) -> None:
        for config in configs:
            self._configs[config.id] = config


_manager: IntegrationManager | None = None


def get_integration_manager() -> IntegrationManager:
    global _manager
    if _manager is None:
        _manager = IntegrationManager()
    return _manager
