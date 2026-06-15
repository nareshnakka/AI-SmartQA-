"""
Example integration plugin — copy this file to add a new provider.

Steps:
  1. Copy to my_provider.py (remove underscore prefix)
  2. Implement MyProviderIntegration(BaseIntegration)
  3. Uncomment register_integration() at bottom
  4. Add handler in IntegrationManager._register_defaults()

from app.integrations.base import BaseIntegration
from app.models.schemas import GitRepositoryInfo, IntegrationProvider
from app.plugins.loader import register_plugin
from app.core.extensions import ExtensionPoint


class CircleCIIntegration(BaseIntegration):
    provider = IntegrationProvider.CIRCLECI  # add to enum if needed
    name = "CircleCI"
    description = "CircleCI pipeline integration"

    async def validate_credentials(self, credentials):
        return bool(credentials.get("api_token"))

    async def list_repositories(self, credentials):
        return []


register_plugin(
    "circleci",
    "CircleCI",
    "CI/CD pipeline integration",
    ExtensionPoint.INTEGRATION,
    category="ci_cd",
)
"""
