"""Locating, describing and fingerprinting the JavaScript files.

An *asset root* is a directory laid out as ``<root>/manifest.json`` plus
``<root>/static/...``. The package itself is one root; a download cache
directory is another.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
STATIC_DIR = PACKAGE_DIR / "static"
MANIFEST_NAME = "manifest.json"

CORE_FILE = "alpine.min.js"
CSP_CORE_FILE = "alpine.csp.min.js"
UNVENDORED_VERSION = "0.0.0-unvendored"


def plugin_file(name: str) -> str:
    """Path of a plugin bundle relative to a static folder."""
    return f"plugins/{name}.min.js"


@dataclass(frozen=True)
class Manifest:
    """Describes which Alpine.js release a root contains."""

    version: str
    vendored: bool
    sha256: dict[str, str] = field(default_factory=dict)
    plugins: dict[str, str] = field(default_factory=dict)  # plugin -> version present


def static_dir(root: Path = PACKAGE_DIR) -> Path:
    return root / "static"


def load_manifest(root: Path = PACKAGE_DIR) -> Manifest:
    """Read a root's manifest; a missing or broken one means "not vendored"."""
    try:
        data = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
        return Manifest(
            version=str(data["version"]),
            vendored=bool(data["vendored"]),
            sha256=dict(data.get("sha256", {})),
            plugins=dict(data.get("plugins", {})),
        )
    except (OSError, ValueError, KeyError):
        return Manifest(UNVENDORED_VERSION, False)


def write_manifest(root: Path, manifest: Manifest) -> None:
    payload = {
        "version": manifest.version,
        "vendored": manifest.vendored,
        "plugins": manifest.plugins,
        "sha256": manifest.sha256,
    }
    temporary = root / (MANIFEST_NAME + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, root / MANIFEST_NAME)


def asset_path(relative: str, root: Path = PACKAGE_DIR) -> Path:
    return static_dir(root) / relative


@lru_cache(maxsize=None)
def integrity(relative: str, root: Path = PACKAGE_DIR) -> str:
    """Subresource Integrity value (sha384) for a file."""
    digest = hashlib.sha384(asset_path(relative, root).read_bytes()).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")
