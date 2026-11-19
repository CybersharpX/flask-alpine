"""Registry of the official Alpine.js plugins and selection helpers."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Union

from .errors import PluginUnavailableError

__all__ = [
    "PLUGINS",
    "PLUGIN_NAMES",
    "PluginSelection",
    "PluginSpec",
    "UnknownPluginError",
    "normalize_plugins",
]


@dataclass(frozen=True)
class PluginSpec:
    """Metadata about one official ``@alpinejs/*`` plugin."""

    name: str
    package: str
    directives: tuple[str, ...]
    description: str


def _spec(name: str, directives: tuple[str, ...], description: str) -> PluginSpec:
    return PluginSpec(name, f"@alpinejs/{name}", directives, description)


#: Official plugins, in canonical (alphabetical) load order.
PLUGINS: dict[str, PluginSpec] = {
    p.name: p
    for p in (
        _spec("anchor", ("x-anchor",), "Position an element next to another element."),
        _spec("collapse", ("x-collapse",), "Animate expanding/collapsing elements."),
        _spec("focus", ("x-trap", "$focus"), "Trap and manage keyboard focus."),
        _spec("intersect", ("x-intersect",), "React to elements entering the viewport."),
        _spec("mask", ("x-mask",), "Input masking."),
        _spec("morph", ("Alpine.morph",), "Morph one DOM tree into another."),
        _spec("navigate", ("x-navigate",), "SPA-style page navigation."),
        _spec("persist", ("$persist",), "Persist state in localStorage."),
        _spec("resize", ("x-resize",), "React to element size changes."),
        _spec("sort", ("x-sort",), "Drag-and-drop sorting."),
    )
}

PLUGIN_NAMES: tuple[str, ...] = tuple(PLUGINS)

PluginSelection = Union[None, str, Iterable[str]]

_SPLIT = re.compile(r"[,\s]+")


class UnknownPluginError(ValueError):
    """Raised when a plugin name is not an official Alpine.js plugin."""

    def __init__(self, name: str) -> None:
        hint = difflib.get_close_matches(name, PLUGIN_NAMES, n=1)
        msg = f"Unknown Alpine.js plugin {name!r}."
        msg += f" Did you mean {hint[0]!r}?" if hint else ""
        msg += f" Available: {', '.join(PLUGIN_NAMES)} (or 'all')."
        super().__init__(msg)
        self.name = name


def normalize_plugins(
    selection: PluginSelection, *, available: Optional[Iterable[str]] = None
) -> tuple[str, ...]:
    """Turn a user-supplied selection into a validated, de-duplicated tuple.

    Accepts ``None``, a comma/space separated string, or an iterable of names.
    ``"all"`` (or ``"*"``) expands to every plugin, and ``"@alpinejs/mask"``
    is accepted as an alias for ``"mask"``. The result is always in canonical
    order so rendered output is deterministic.

    ``"none"`` is accepted and selects nothing. If ``available`` is given,
    ``"all"`` expands to just those plugins and naming a valid plugin that is
    not available raises :class:`PluginUnavailableError`.
    """
    ok = tuple(PLUGIN_NAMES if available is None else (n for n in PLUGIN_NAMES if n in set(available)))
    if selection is None:
        return ()
    raw: Iterable[object] = [selection] if isinstance(selection, str) else selection
    wanted: set[str] = set()
    for chunk in raw:
        if not isinstance(chunk, str):
            raise TypeError(f"Plugin names must be strings, got {type(chunk).__name__}.")
        for item in _SPLIT.split(chunk.strip().lower()):
            if not item:
                continue
            if item == "none":
                continue
            if item in ("all", "*"):
                wanted.update(ok)
                continue
            name = item[len("@alpinejs/") :] if item.startswith("@alpinejs/") else item
            if name not in PLUGINS:
                raise UnknownPluginError(name)
            if name not in ok:
                raise PluginUnavailableError(name, ok)
            wanted.add(name)
    return tuple(n for n in PLUGIN_NAMES if n in wanted)
