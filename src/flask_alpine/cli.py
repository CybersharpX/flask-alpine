"""``flask alpine ...`` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from flask import current_app
from flask.cli import AppGroup

from . import assets, vendor
from .errors import AlpineError

alpine_cli = AppGroup("alpine", help="Manage the Alpine.js assets.")


def _settings():  # type: ignore[no-untyped-def]
    return current_app.extensions["alpine"].settings


@alpine_cli.command("info")
def info() -> None:
    """Show which Alpine.js build is being served."""
    settings = _settings()
    manifest = assets.load_manifest(settings.root)
    kind = "vendored" if manifest.vendored else "PLACEHOLDER"
    click.echo(f"Alpine.js {settings.version} ({kind})")
    click.echo(f"Served from: {assets.static_dir(settings.root)}")
    click.echo("Plugins: " + (", ".join(settings.available) or "none"))


@alpine_cli.command("check")
def check() -> None:
    """Compare the served version with the latest release (needs internet)."""
    settings = _settings()
    try:
        latest = vendor.latest_version()
    except AlpineError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"served: {settings.version}  latest: {latest}")
    if settings.version != latest:
        raise SystemExit(1)


@alpine_cli.command("update")
@click.option("--plugins", default="all", help="Comma-separated plugins, 'all' or 'none'.")
@click.option("--version", "version", default=None, help="Specific version (default: latest).")
@click.option(
    "--dest",
    type=click.Path(path_type=Path),
    default=None,
    help="Target directory (default: ALPINE_ASSET_DIR or the user cache dir).",
)
def update(plugins: str, version: Optional[str], dest: Optional[Path]) -> None:
    """Download Alpine.js and all official plugins (needs internet)."""
    settings = _settings()
    target = dest or settings.asset_dir or vendor.default_cache_dir()
    try:
        manifest = vendor.download_assets(version, target, plugins=plugins)
    except AlpineError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Downloaded to {target}")
    click.echo("\n".join(vendor.summary(manifest)))
    if target != settings.root:
        click.echo(f"Restart the app with ALPINE_ASSET_DIR={target!s} to serve it.")
