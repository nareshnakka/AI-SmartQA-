"""Platform metadata — extensions, modules, navigation for dynamic UI."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import get_agent_registry
from app.core.extensions import ExtensionPoint, get_extension_registry
from app.db.session import get_db
from app.integrations.manager import get_integration_manager
from app.plugins.loader import discover_plugins
from app.services.search import SearchService

router = APIRouter(prefix="/platform", tags=["Platform"])


@router.get("/manifest")
async def platform_manifest():
    """Single source of truth for UI — features, integrations, agents."""
    extensions = get_extension_registry()
    return {
        "name": "QEOS",
        "version": "0.2.0",
        "tagline": "Quality Engineering Operating System",
        **extensions.to_manifest(),
    }


@router.get("/features")
async def list_features():
    registry = get_extension_registry()
    return {
        "features": [
            {
                "id": e.id,
                "name": e.name,
                "description": e.description,
                "enabled": e.enabled,
            }
            for e in registry.list_by_point(ExtensionPoint.FEATURE)
        ]
    }


@router.get("/integrations/catalog")
async def integration_catalog():
    ext_registry = get_extension_registry()
    manager = get_integration_manager()
    registered = {p["provider"] for p in manager.list_providers()}
    catalog = []
    for ext in ext_registry.list_by_point(ExtensionPoint.INTEGRATION):
        catalog.append({
            "id": ext.id,
            "name": ext.name,
            "description": ext.description,
            "category": ext.metadata.get("category", "other"),
            "implemented": ext.id in registered,
            "version": ext.version,
        })
    return {"integrations": catalog}


@router.get("/agents/catalog")
async def agent_catalog():
    ext_registry = get_extension_registry()
    agent_registry = get_agent_registry()
    implemented = {a["type"] for a in agent_registry.list_agents()}
    catalog = []
    for ext in ext_registry.list_by_point(ExtensionPoint.AGENT):
        catalog.append({
            "id": ext.id,
            "name": ext.name,
            "description": ext.description,
            "implemented": ext.id in implemented,
        })
    return {"agents": catalog}


@router.post("/plugins/reload")
async def reload_plugins():
    count = discover_plugins()
    return {"discovered": count, "manifest": get_extension_registry().to_manifest()}


@router.get("/capabilities")
async def runner_capabilities():
    from app.runners.capabilities import get_runner_capabilities
    return get_runner_capabilities()


@router.get("/search")
async def global_search(
    q: str = Query("", min_length=0),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    return await SearchService(db).search(q, limit)


@router.get("/navigation")
async def navigation_config():
    """Navigation structure — frontend reads this for dynamic menus."""
    registry = get_extension_registry()
    features = registry.list_by_point(ExtensionPoint.FEATURE)

    nav_groups = [
        {
            "label": "Overview",
            "items": [
                {"id": "dashboard", "label": "Dashboard", "href": "/", "icon": "layout-dashboard"},
                {"id": "projects", "label": "Projects", "href": "/projects", "icon": "folder-kanban"},
            ],
        },
        {
            "label": "Quality Engineering",
            "items": [
                {"id": "agents", "label": "Agents", "href": "/agents", "icon": "bot"},
                {"id": "studio", "label": "QA Studio", "href": "/studio", "icon": "code-2"},
                {"id": "discovery", "label": "Discovery", "href": "/discovery", "icon": "search"},
                {"id": "executions", "label": "Executions", "href": "/executions", "icon": "play-circle"},
                {"id": "reports", "label": "Reports", "href": "/reports", "icon": "bar-chart-3"},
                {"id": "monitoring", "label": "Monitoring", "href": "/monitoring", "icon": "activity"},
            ],
        },
        {
            "label": "Platform",
            "items": [
                {"id": "integrations", "label": "Integrations", "href": "/integrations", "icon": "plug"},
                {"id": "training", "label": "Model Training", "href": "/training", "icon": "brain"},
                {"id": "settings", "label": "Settings", "href": "/settings", "icon": "settings"},
            ],
        },
    ]

    enabled_ids = {f.id for f in features if f.enabled}
    for group in nav_groups:
        group["items"] = [i for i in group["items"] if i["id"] in enabled_ids]

    return {"navigation": nav_groups}
