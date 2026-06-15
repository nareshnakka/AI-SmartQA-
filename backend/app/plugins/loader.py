"""Auto-discovery plugin loader."""

import importlib
import pkgutil
from pathlib import Path

import structlog

from app.core.extensions import ExtensionDescriptor, ExtensionPoint, get_extension_registry

logger = structlog.get_logger()

_plugin_dir = Path(__file__).parent


def register_plugin(
    extension_id: str,
    name: str,
    description: str,
    point: ExtensionPoint,
    version: str = "1.0.0",
    **metadata,
) -> None:
    """Call from plugin modules to register with the extension registry."""
    registry = get_extension_registry()
    if registry.get(extension_id):
        logger.debug("plugin_already_registered", id=extension_id)
        return
    registry.register(ExtensionDescriptor(
        id=extension_id,
        point=point,
        name=name,
        description=description,
        version=version,
        metadata=metadata,
    ))
    logger.info("plugin_registered", id=extension_id, point=point.value)


def discover_plugins() -> int:
    """
    Scan app/plugins/ subpackages and import them.
    Each plugin module should call register_plugin() on import.
    """
    count = 0
    for subdir in ["integrations", "agents", "features"]:
        path = _plugin_dir / subdir
        if not path.is_dir():
            continue
        package = f"app.plugins.{subdir}"
        for finder, name, is_pkg in pkgutil.iter_modules([str(path)]):
            if name.startswith("_"):
                continue
            module_path = f"{package}.{name}"
            try:
                importlib.import_module(module_path)
                count += 1
                logger.info("plugin_discovered", module=module_path)
            except Exception as e:
                logger.error("plugin_load_failed", module=module_path, error=str(e))
    return count
