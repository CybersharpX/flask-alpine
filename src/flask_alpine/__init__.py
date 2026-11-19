"""flask-alpine: offline-ready Alpine.js integration for Flask."""

from .errors import AlpineError, AssetsNotVendoredWarning, DownloadError, PluginUnavailableError
from .extension import Alpine
from .plugins import PLUGIN_NAMES, PLUGINS, PluginSpec, UnknownPluginError

__version__ = "0.2.2"

__all__ = [
    "Alpine",
    "AlpineError",
    "AssetsNotVendoredWarning",
    "DownloadError",
    "PluginUnavailableError",
    "PLUGINS",
    "PLUGIN_NAMES",
    "PluginSpec",
    "UnknownPluginError",
    "__version__",
]
