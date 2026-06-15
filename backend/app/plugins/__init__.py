"""
Plugin loader — drop new integrations/features into app/plugins/.

To add a new integration:
  1. Create app/plugins/integrations/my_provider.py
  2. Implement BaseIntegration
  3. Call register_plugin() at module bottom

The loader auto-discovers modules on startup.
"""

from app.plugins.loader import discover_plugins, register_plugin

__all__ = ["discover_plugins", "register_plugin"]
