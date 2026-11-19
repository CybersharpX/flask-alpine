"""Exceptions and warnings raised by flask-alpine."""

from __future__ import annotations


class AlpineError(RuntimeError):
    """Raised for configuration or asset problems."""


class DownloadError(AlpineError):
    """Raised when Alpine.js could not be downloaded or validated."""


class PluginUnavailableError(AlpineError):
    """A valid plugin was requested but its build is not in the assets being served."""

    def __init__(self, name: str, available: "tuple[str, ...]") -> None:
        super().__init__(
            f"Alpine.js plugin {name!r} is not available in the assets being served "
            f"(available: {', '.join(available) or 'none'}). "
            "Not every plugin is published for every release; see `flask alpine info`."
        )
        self.name = name


class AssetsNotVendoredWarning(UserWarning):
    """The active asset directory has placeholder files instead of real Alpine.js builds."""
