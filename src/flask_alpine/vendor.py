"""Download Alpine.js and the official plugins.

Used by the build hook, ``flask alpine update``, ``python -m flask_alpine`` and
the optional ``ALPINE_AUTO_DOWNLOAD`` runtime fallback. Nothing here runs
unless one of those is invoked, so normal operation stays fully offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

from . import assets
from .errors import AlpineError, DownloadError
from .plugins import PLUGIN_NAMES, PluginSelection, normalize_plugins

# Everything comes from the jsDelivr CDN; the npm registry is never contacted.
CDN = "https://cdn.jsdelivr.net/npm/{package}@{version}/dist/cdn.min.js"
LATEST = "https://cdn.jsdelivr.net/npm/{package}@latest/package.json"


def latest_url(package: str) -> str:
    """CDN URL of a package's ``package.json`` at its ``latest`` tag (carries the version)."""
    return LATEST.format(package=package)



Fetch = Callable[[str], bytes]
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class NotFound(OSError):
    """The requested file or package does not exist (HTTP 404)."""


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "flask-alpine"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return bytes(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(url) from exc
        raise


def default_cache_dir() -> Path:
    """Per-user directory for downloaded assets (override: ``FLASK_ALPINE_CACHE_DIR``)."""
    override = os.environ.get("FLASK_ALPINE_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "flask-alpine"


def targets(plugins: Sequence[str] = PLUGIN_NAMES) -> dict[str, str]:
    """Relative file path -> npm package name (core builds plus ``plugins``)."""
    result = {assets.CORE_FILE: "alpinejs", assets.CSP_CORE_FILE: "@alpinejs/csp"}
    for name in plugins:
        result[assets.plugin_file(name)] = f"@alpinejs/{name}"
    return result


def _checked_version(version: str) -> str:
    if not _VERSION.match(version):
        raise DownloadError(f"Invalid Alpine.js version {version!r} (expected e.g. 3.14.9).")
    return version


def _latest_version_of(package: str, get: Fetch) -> str:
    return _checked_version(str(json.loads(get(latest_url(package)))["version"]))


def latest_version(*, fetch: Optional[Fetch] = None) -> str:
    """Latest published ``alpinejs`` version, read from the jsDelivr CDN."""
    get = fetch or _fetch
    try:
        return _latest_version_of("alpinejs", get)
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"Could not determine the latest Alpine.js version: {exc}") from exc


def _cdn_js(package: str, version: str, get: Fetch) -> bytes:
    body = get(CDN.format(package=package, version=version))
    if not body.strip() or body.lstrip().startswith(b"<"):
        raise DownloadError(f"Unexpected (non-JavaScript) response for {package}@{version}.")
    return body


def _download_plugin(name: str, version: str, get: Fetch) -> Optional[tuple[str, bytes]]:
    """Fetch one plugin build; ``None`` if it is not published at all.

    Plugins normally share the core's version, but not every plugin is
    published for every release. On a 404 we try the plugin's own latest
    version before giving up.
    """
    package = f"@alpinejs/{name}"
    try:
        return version, _cdn_js(package, version, get)
    except NotFound:
        pass
    try:
        own = _latest_version_of(package, get)
        if own != version:
            return own, _cdn_js(package, own, get)
    except NotFound:
        pass
    return None


def download_assets(
    version: Optional[str] = None,
    dest: Optional[Path] = None,
    *,
    plugins: PluginSelection = "all",
    fetch: Optional[Fetch] = None,
) -> assets.Manifest:
    """Download core, CSP build and plugins into ``dest`` (default: cache dir).

    Core and CSP builds are required. A plugin that is not published for the
    requested release is skipped (and reported by :func:`summary`) rather than
    failing the whole run. Everything is downloaded and validated *before*
    anything is written, so a failed run never leaves a half-updated directory.
    """
    get = fetch or _fetch
    root = Path(dest) if dest is not None else default_cache_dir()
    resolved = _checked_version(version) if version else latest_version(fetch=get)
    selected = normalize_plugins(plugins)

    bodies: dict[str, bytes] = {}
    present: dict[str, str] = {}
    for relative, package in targets(()).items():
        try:
            bodies[relative] = _cdn_js(package, resolved, get)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(f"Failed to download {package}@{resolved}: {exc}") from exc
    for name in selected:
        try:
            found = _download_plugin(name, resolved, get)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(f"Failed to download @alpinejs/{name}@{resolved}: {exc}") from exc
        if found is not None:
            present[name] = found[0]
            bodies[assets.plugin_file(name)] = found[1]

    checksums: dict[str, str] = {}
    for relative, body in bodies.items():
        path = assets.asset_path(relative, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        checksums[relative] = hashlib.sha256(body).hexdigest()
    for name in PLUGIN_NAMES:  # drop stale files of plugins that are no longer present
        if name not in present:
            assets.asset_path(assets.plugin_file(name), root).unlink(missing_ok=True)

    manifest = assets.Manifest(resolved, True, checksums, present)
    assets.write_manifest(root, manifest)
    assets.integrity.cache_clear()
    return manifest


def summary(manifest: assets.Manifest) -> list[str]:
    """Human-readable lines describing what a download produced."""
    lines = [f"Alpine.js {manifest.version}"]
    lines.append("plugins: " + (", ".join(manifest.plugins) or "none"))
    odd = [f"{n} {v}" for n, v in manifest.plugins.items() if v != manifest.version]
    if odd:
        lines.append(f"note: published under a different version: {', '.join(odd)}")
    return lines


def check(root: Optional[Path] = None, *, fetch: Optional[Fetch] = None) -> tuple[str, str]:
    """Return ``(installed_version, latest_version)`` for an asset root."""
    installed = assets.load_manifest(root if root is not None else assets.PACKAGE_DIR)
    return installed.version, latest_version(fetch=fetch)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m flask_alpine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    update = sub.add_parser("update", help="download Alpine.js")
    update.add_argument("--version", help="specific version (default: latest)")
    update.add_argument("--dest", type=Path, help="target directory (default: user cache dir)")
    update.add_argument(
        "--plugins", default="all", help="comma-separated plugins, 'all' or 'none' (default: all)"
    )
    check_cmd = sub.add_parser("check", help="compare installed and latest versions")
    check_cmd.add_argument("--dest", type=Path, help="asset directory to inspect")
    args = parser.parse_args(argv)

    try:
        if args.command == "update":
            manifest = download_assets(args.version, args.dest, plugins=args.plugins)
            where = args.dest or default_cache_dir()
            print(f"Downloaded to {where}")
            print("\n".join(summary(manifest)))
            return 0
        installed, latest = check(args.dest)
        print(f"installed: {installed}  latest: {latest}")
        return 0 if installed == latest else 1
    except AlpineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
