"""Extension points — add features and integrations without modifying core code."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ExtensionPoint(str, Enum):
    """Well-defined extension points in the platform."""

    INTEGRATION = "integration"
    AGENT = "agent"
    GENERATOR = "generator"
    API_ROUTE = "api_route"
    WEBHOOK_HANDLER = "webhook_handler"
    CI_TRIGGER = "ci_trigger"
    REPORT = "report"
    FEATURE = "feature"


@dataclass
class ExtensionDescriptor:
    id: str
    point: ExtensionPoint
    name: str
    description: str
    version: str = "1.0.0"
    enabled: bool = True
    config_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ExtensionRegistry:
    """
    Central catalog of all platform extensions.
    New integrations/agents register here — UI reads this for dynamic menus.
    """

    def __init__(self) -> None:
        self._extensions: dict[str, ExtensionDescriptor] = {}
        self._hooks: dict[str, list[Callable]] = {}

    def register(self, descriptor: ExtensionDescriptor) -> None:
        if descriptor.id in self._extensions:
            raise ValueError(f"Extension already registered: {descriptor.id}")
        self._extensions[descriptor.id] = descriptor

    def unregister(self, extension_id: str) -> None:
        self._extensions.pop(extension_id, None)

    def get(self, extension_id: str) -> ExtensionDescriptor | None:
        return self._extensions.get(extension_id)

    def list_by_point(self, point: ExtensionPoint) -> list[ExtensionDescriptor]:
        return [e for e in self._extensions.values() if e.point == point and e.enabled]

    def list_all(self) -> list[ExtensionDescriptor]:
        return list(self._extensions.values())

    def register_hook(self, event: str, handler: Callable) -> None:
        self._hooks.setdefault(event, []).append(handler)

    async def emit(self, event: str, **payload) -> list[Any]:
        results = []
        for handler in self._hooks.get(event, []):
            result = handler(**payload)
            if hasattr(result, "__await__"):
                result = await result
            results.append(result)
        return results

    def to_manifest(self) -> dict:
        return {
            "extensions": [
                {
                    "id": e.id,
                    "point": e.point.value,
                    "name": e.name,
                    "description": e.description,
                    "version": e.version,
                    "enabled": e.enabled,
                    "metadata": e.metadata,
                }
                for e in self._extensions.values()
            ],
            "extension_points": [p.value for p in ExtensionPoint],
        }


_registry: ExtensionRegistry | None = None


def get_extension_registry() -> ExtensionRegistry:
    global _registry
    if _registry is None:
        _registry = ExtensionRegistry()
        _bootstrap_extensions(_registry)
    return _registry


def _bootstrap_extensions(registry: ExtensionRegistry) -> None:
    """Register built-in extensions. Add new ones here OR via plugins/."""

    # --- Integrations ---
    integrations = [
        ("github", "GitHub", "Repositories, Actions, webhooks", "source_control"),
        ("bitbucket", "Bitbucket", "Cloud repos and Pipelines", "source_control"),
        ("gitlab", "GitLab", "Repos and CI/CD (cloud + self-hosted)", "source_control"),
        ("gitea", "Gitea / Forgejo", "Self-hosted Git platforms", "source_control"),
        ("azure_devops", "Azure DevOps", "Repos and Pipelines", "source_control"),
        ("jira", "Jira", "Issues, epics, user stories", "alm"),
        ("jenkins", "Jenkins", "CI/CD job orchestration", "ci_cd"),
    ]
    for id_, name, desc, category in integrations:
        registry.register(ExtensionDescriptor(
            id=id_,
            point=ExtensionPoint.INTEGRATION,
            name=name,
            description=desc,
            metadata={"category": category},
        ))

    # --- Agents ---
    agents = [
        ("requirements", "Requirements Agent", "BRD/user stories → test cases"),
        ("test_design", "Test Design Agent", "Functional, API, security test design"),
        ("automation", "Automation Agent", "Framework-specific script generation"),
        ("performance", "Performance Agent", "Load scripts and workload models"),
        ("self_healing", "Self-Healing Agent", "Locator repair and impact analysis"),
        ("defect_intelligence", "Defect Intelligence Agent", "RCA and failure clustering"),
    ]
    for id_, name, desc in agents:
        registry.register(ExtensionDescriptor(
            id=id_,
            point=ExtensionPoint.AGENT,
            name=name,
            description=desc,
        ))

    # --- Features (UI modules) ---
    features = [
        ("dashboard", "Dashboard", "Quality overview and metrics"),
        ("projects", "Projects", "Project and workspace management"),
        ("agents", "Agent Workspace", "Run and monitor AI agents"),
        ("integrations", "Integrations", "Connect external systems"),
        ("studio", "QA Studio", "Script editor and debugger"),
        ("training", "Model Training", "Collect and export training data"),
        ("performance", "Performance Engineering", "Load test generation"),
        ("pipelines", "Autonomous Pipelines", "Multi-agent orchestration"),
        ("discovery", "App Discovery", "URL exploration and flow mapping"),
        ("executions", "Test Execution", "Dry-run and self-healing"),
        ("reports", "Reports", "Executive and engineering dashboards"),
        ("monitoring", "Production Monitoring", "Datadog, Sentry, custom events"),
        ("settings", "Settings", "Platform configuration"),
    ]
    for id_, name, desc in features:
        registry.register(ExtensionDescriptor(
            id=id_,
            point=ExtensionPoint.FEATURE,
            name=name,
            description=desc,
        ))
