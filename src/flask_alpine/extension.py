"""The :class:`Alpine` Flask extension."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional, Union

from flask import Blueprint, Flask, current_app, g, url_for
from markupsafe import Markup, escape

from . import assets, vendor
from .cli import alpine_cli
from .errors import AlpineError, AssetsNotVendoredWarning
from .plugins import PLUGIN_NAMES, PluginSelection, normalize_plugins

__all__ = ["Alpine", "AlpineError", "AssetsNotVendoredWarning"]

Nonce = Union[str, Callable[[], Optional[str]], None]


#: Option name -> default. Each maps to the config key ``ALPINE_<NAME>``.
_DEFAULTS: dict[str, Any] = {
    "plugins": (),  # plugin names, a comma separated string, or "all"
    "csp": False,  # use the CSP-safe core build (no eval)
    "defer": True,  # emit <script defer>
    "url_prefix": "/_alpine",  # where bundled files are served
    "versioned_urls": True,  # append ?v=<alpine version> for cache busting
    "sri": False,  # add integrity="sha384-..." attributes
    "nonce": None,  # CSP nonce: a string or a zero-arg callable
    "cache_max_age": None,  # seconds; None keeps Flask's default
    "auto_download": False,  # download latest Alpine.js if none is bundled
    "asset_dir": None,  # directory with downloaded assets (see vendor.download_assets)
}


@dataclass(frozen=True)
class AlpineSettings:
    """Resolved, validated settings for one Flask app."""

    plugins: tuple[str, ...]
    csp: bool
    defer: bool
    url_prefix: str
    versioned_urls: bool
    sri: bool
    nonce: Nonce
    cache_max_age: Optional[int]
    asset_dir: Optional[Path]  # configured download directory, if any
    root: Path  # asset root actually being served
    version: str  # Alpine.js version being served
    available: tuple[str, ...]  # plugins present in the served assets


@dataclass(frozen=True)
class _AppState:
    extension: "Alpine"
    settings: AlpineSettings


class _AlpineBlueprint(Blueprint):
    """Blueprint serving the bundled files with a configurable cache lifetime."""

    def __init__(self, *args: Any, max_age: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._max_age = max_age

    def get_send_file_max_age(self, filename: Optional[str]) -> Optional[int]:
        if self._max_age is not None:
            return self._max_age
        return super().get_send_file_max_age(filename)


def _config_key(option: str) -> str:
    return f"ALPINE_{option.upper()}"


class Alpine:
    """Integrate Alpine.js (and its official plugins) into a Flask app.

    Works directly or with the application factory pattern::

        alpine = Alpine(app)               # direct
        alpine = Alpine(); alpine.init_app(app)   # factory

    Settings are resolved as: ``app.config["ALPINE_*"]`` first, then keyword
    arguments given to the constructor, then built-in defaults. That lets code
    set sensible defaults while each environment's config can override them.

    Templates get three globals: ``alpine_scripts()``, ``alpine_use()`` and
    ``alpine_url()``.
    """

    def __init__(
        self,
        app: Optional[Flask] = None,
        *,
        plugins: PluginSelection = None,
        csp: Optional[bool] = None,
        defer: Optional[bool] = None,
        url_prefix: Optional[str] = None,
        versioned_urls: Optional[bool] = None,
        sri: Optional[bool] = None,
        nonce: Nonce = None,
        cache_max_age: Optional[int] = None,
        auto_download: Optional[bool] = None,
        asset_dir: Union[str, Path, None] = None,
    ) -> None:
        given = {
            "plugins": plugins,
            "csp": csp,
            "defer": defer,
            "url_prefix": url_prefix,
            "versioned_urls": versioned_urls,
            "sri": sri,
            "nonce": nonce,
            "cache_max_age": cache_max_age,
            "auto_download": auto_download,
            "asset_dir": asset_dir,
        }
        self._options: dict[str, Any] = {k: v for k, v in given.items() if v is not None}
        if app is not None:
            self.init_app(app)

    # ------------------------------------------------------------------ setup

    def init_app(self, app: Flask) -> None:
        """Register the asset blueprint and template helpers on ``app``."""
        values: dict[str, Any] = {}
        for option, default in _DEFAULTS.items():
            key = _config_key(option)
            if key in app.config:
                values[option] = app.config[key]
            else:
                values[option] = self._options.get(option, default)

        prefix = "/" + str(values["url_prefix"]).strip("/")
        if prefix == "/":
            raise AlpineError("ALPINE_URL_PREFIX must not be empty.")

        auto = bool(values["auto_download"])
        asset_dir: Optional[Path] = None
        if values["asset_dir"]:
            asset_dir = Path(values["asset_dir"]).expanduser()
        elif auto:
            asset_dir = vendor.default_cache_dir()
        root = self._resolve_root(asset_dir, auto)
        manifest = assets.load_manifest(root)
        available = tuple(
            n for n in PLUGIN_NAMES if assets.asset_path(assets.plugin_file(n), root).is_file()
        )

        settings = AlpineSettings(
            plugins=normalize_plugins(values["plugins"], available=available),
            csp=bool(values["csp"]),
            defer=bool(values["defer"]),
            url_prefix=prefix,
            versioned_urls=bool(values["versioned_urls"]),
            sri=bool(values["sri"]),
            nonce=values["nonce"],
            cache_max_age=values["cache_max_age"],
            asset_dir=asset_dir,
            root=root,
            version=manifest.version,
            available=available,
        )

        if not manifest.vendored:
            warnings.warn(
                "Alpine.js assets are placeholders (not vendored). Run "
                "`flask alpine update` or set ALPINE_AUTO_DOWNLOAD = True.",
                AssetsNotVendoredWarning,
                stacklevel=2,
            )
        for relative in self._files_for(settings, settings.plugins):
            if not assets.asset_path(relative, root).is_file():
                raise AlpineError(f"Bundled asset missing: {relative}")

        blueprint = _AlpineBlueprint(
            "alpine",
            __name__,
            static_folder=str(assets.static_dir(root)),
            static_url_path=prefix,
            max_age=settings.cache_max_age,
        )
        app.register_blueprint(blueprint)

        app.add_template_global(self.scripts, "alpine_scripts")
        app.add_template_global(self._template_use, "alpine_use")
        app.add_template_global(self.url, "alpine_url")
        app.cli.add_command(alpine_cli)
        app.extensions["alpine"] = _AppState(self, settings)

    @staticmethod
    def _resolve_root(asset_dir: Optional[Path], auto_download: bool) -> Path:
        """Pick the asset root: a vendored download dir, else the package.

        With ``auto_download`` and nothing vendored anywhere, fetch the latest
        release into ``asset_dir`` (a failure warns and falls back to the
        package's files so the app still starts).
        """
        if asset_dir is not None and assets.load_manifest(asset_dir).vendored:
            return asset_dir
        if assets.load_manifest(assets.PACKAGE_DIR).vendored:
            return assets.PACKAGE_DIR
        if auto_download and asset_dir is not None:
            try:
                vendor.download_assets(dest=asset_dir)
                return asset_dir
            except AlpineError as exc:
                warnings.warn(
                    f"Alpine.js auto-download failed: {exc}",
                    AssetsNotVendoredWarning,
                    stacklevel=3,
                )
        return assets.PACKAGE_DIR

    # --------------------------------------------------------------- accessors

    @property
    def settings(self) -> AlpineSettings:
        """Settings of the current app (requires an app context)."""
        state = current_app.extensions.get("alpine")
        if state is None:
            raise AlpineError("Alpine is not initialised on the current app.")
        return state.settings  # type: ignore[no-any-return]

    @property
    def available_plugins(self) -> tuple[str, ...]:
        """Plugins present in the assets being served (requires an app context)."""
        return self.settings.available

    @property
    def alpine_version(self) -> str:
        """The Alpine.js version being served (requires an app context)."""
        return self.settings.version

    # -------------------------------------------------------------- selection

    def use(self, *plugins: str) -> tuple[str, ...]:
        """Require extra plugins for the *current request only*.

        Call from a view, ``before_request`` or a blueprint hook, before the
        template calls ``alpine_scripts()``.
        """
        available = self.settings.available
        names = normalize_plugins(plugins, available=available)
        current = g.get("_alpine_plugins", ())
        g._alpine_plugins = normalize_plugins(current + names, available=available)
        return names

    def _template_use(self, *plugins: str) -> str:
        self.use(*plugins)
        return ""

    def selected_plugins(
        self, plugins: PluginSelection = None, *, defaults: bool = True
    ) -> tuple[str, ...]:
        """Plugins that would be loaded, in canonical order."""
        names: list[str] = []
        if defaults:
            names.extend(self.settings.plugins)
            names.extend(g.get("_alpine_plugins", ()))
        names.extend(normalize_plugins(plugins, available=self.settings.available))
        return normalize_plugins(names, available=self.settings.available)

    # ------------------------------------------------------------------- URLs

    @staticmethod
    def _files_for(settings: AlpineSettings, plugins: tuple[str, ...]) -> list[str]:
        """Relative file paths in load order: plugins first, then the core."""
        core = assets.CSP_CORE_FILE if settings.csp else assets.CORE_FILE
        return [assets.plugin_file(p) for p in plugins] + [core]

    def _url_for_file(self, relative: str) -> str:
        params: dict[str, str] = {}
        if self.settings.versioned_urls:
            params["v"] = self.settings.version
        return url_for("alpine.static", filename=relative, **params)

    def url(self, name: str = "core") -> str:
        """URL of the core build (``"core"``) or of one plugin."""
        if name == "core":
            core = assets.CSP_CORE_FILE if self.settings.csp else assets.CORE_FILE
            return self._url_for_file(core)
        resolved = normalize_plugins(name, available=self.settings.available)
        if len(resolved) != 1:
            raise AlpineError(f"alpine_url() expects 'core' or one plugin name, got {name!r}.")
        return self._url_for_file(assets.plugin_file(resolved[0]))

    # -------------------------------------------------------------- rendering

    def scripts(
        self,
        plugins: PluginSelection = None,
        *,
        defaults: bool = True,
        csp: Optional[bool] = None,
        defer: Optional[bool] = None,
        nonce: Optional[str] = None,
    ) -> Markup:
        """Render ``<script>`` tags for the selected plugins and Alpine core.

        Plugins are always emitted *before* the core, as Alpine requires.

        :param plugins: extra plugins for this call (names or ``"all"``).
        :param defaults: include configured and per-request plugins.
        :param csp: override ``ALPINE_CSP`` for this call.
        :param defer: override ``ALPINE_DEFER`` for this call.
        :param nonce: override the configured CSP nonce for this call.
        """
        settings = self.settings
        if csp is not None and csp != settings.csp:
            settings = replace(settings, csp=csp)
        use_defer = settings.defer if defer is None else defer

        if nonce is None:
            nonce = settings.nonce() if callable(settings.nonce) else settings.nonce

        selected = self.selected_plugins(plugins, defaults=defaults)
        tags = []
        for relative in self._files_for(settings, selected):
            attrs = ["defer"] if use_defer else []
            attrs.append(f'src="{escape(self._url_for_file(relative))}"')
            if settings.sri:
                attrs.append(f'integrity="{assets.integrity(relative, settings.root)}"')
            if nonce:
                attrs.append(f'nonce="{escape(nonce)}"')
            tags.append(f"<script {' '.join(attrs)}></script>")
        return Markup("\n".join(tags))
