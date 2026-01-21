"""Plugin loader and registry.

Dynamically loads all plugins from this directory.
Each plugin file should contain a class that extends ServicePlugin.
"""

import importlib
import logging
import pkgutil
from typing import Optional

from app.core.plugin_base import ServicePlugin

logger = logging.getLogger(__name__)

# Registry of loaded plugins
_plugins: dict[str, ServicePlugin] = {}


def load_plugins() -> None:
    """
    Dynamically load all plugins from the plugins directory.

    Called once on startup. Scans for classes extending ServicePlugin
    and registers them by their name property.
    """
    global _plugins
    _plugins.clear()

    package = importlib.import_module("app.plugins")

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        # Skip private modules
        if module_name.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"app.plugins.{module_name}")

            # Find ServicePlugin subclasses in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                # Check if it's a class, subclass of ServicePlugin, and not the base
                if (
                    isinstance(attr, type)
                    and issubclass(attr, ServicePlugin)
                    and attr is not ServicePlugin
                ):
                    plugin = attr()
                    _plugins[plugin.name] = plugin
                    logger.info(
                        f"Loaded plugin: {plugin.name} ({plugin.display_name})"
                    )

        except Exception as e:
            logger.error(f"Failed to load plugin module {module_name}: {e}")


def get_plugin(name: str) -> Optional[ServicePlugin]:
    """Get a plugin by name."""
    return _plugins.get(name)


def get_all_plugins() -> list[ServicePlugin]:
    """Get all loaded plugins."""
    return list(_plugins.values())


def get_polling_plugins() -> list[ServicePlugin]:
    """Get plugins that require background polling."""
    return [p for p in _plugins.values() if p.requires_polling]
