"""Core platform primitives — registries, extensions, module loading."""

from app.core.registry import Registry
from app.core.extensions import ExtensionRegistry, get_extension_registry

__all__ = ["Registry", "ExtensionRegistry", "get_extension_registry"]
