import shutil

import pytest
from flask import Flask, render_template_string

from flask_alpine import Alpine, AlpineError, AssetsNotVendoredWarning, assets, vendor
from test_vendor import fake_fetch


def unvendor_package(monkeypatch, tmp_path):
    """Point the package root at an unvendored copy (placeholders only)."""
    package = tmp_path / "pkg"
    shutil.copytree(assets.PACKAGE_DIR / "static", package / "static")
    (package / "manifest.json").write_text(
        '{"version": "0.0.0-unvendored", "vendored": false, "sha256": {}}'
    )
    monkeypatch.setattr(assets, "PACKAGE_DIR", package)


def boom(url):
    raise AssertionError("network must not be used")


def render(app):
    with app.test_request_context():
        return render_template_string("{{ alpine_scripts() }}")


def make(config):
    app = Flask(__name__)
    app.config.update(TESTING=True, **config)
    Alpine(app)
    return app


def test_auto_download_fetches_latest_and_serves_it(monkeypatch, tmp_path):
    unvendor_package(monkeypatch, tmp_path)
    monkeypatch.setattr(vendor, "_fetch", fake_fetch("9.9.9"))
    app = make({"ALPINE_AUTO_DOWNLOAD": True, "ALPINE_ASSET_DIR": str(tmp_path / "cache"),
                "ALPINE_PLUGINS": ["mask"]})
    body = app.test_client().get("/_alpine/plugins/mask.min.js").data
    assert b"@alpinejs/mask@9.9.9" in body
    assert "?v=9.9.9" in render(app)


def test_cached_download_is_reused_offline(monkeypatch, tmp_path):
    unvendor_package(monkeypatch, tmp_path)
    cache = tmp_path / "cache"
    vendor.download_assets("9.9.9", cache, fetch=fake_fetch())
    monkeypatch.setattr(vendor, "_fetch", boom)
    app = make({"ALPINE_AUTO_DOWNLOAD": True, "ALPINE_ASSET_DIR": str(cache)})
    assert "?v=9.9.9" in render(app)


def test_asset_dir_preferred_over_bundled(monkeypatch, tmp_path):
    vendor.download_assets("9.9.9", tmp_path, fetch=fake_fetch())
    app = make({"ALPINE_ASSET_DIR": str(tmp_path)})
    assert "?v=9.9.9" in render(app)


def test_no_download_unless_enabled(monkeypatch, tmp_path):
    unvendor_package(monkeypatch, tmp_path)
    monkeypatch.setattr(vendor, "_fetch", boom)
    with pytest.warns(AssetsNotVendoredWarning):
        make({})


def test_failed_download_warns_and_falls_back(monkeypatch, tmp_path):
    unvendor_package(monkeypatch, tmp_path)

    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(vendor, "_fetch", offline)
    with pytest.warns(AssetsNotVendoredWarning):
        app = make({"ALPINE_AUTO_DOWNLOAD": True, "ALPINE_ASSET_DIR": str(tmp_path / "c")})
    assert "alpine.min.js" in render(app)  # app still works with placeholders


def test_cli_info_update_check(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "_fetch", fake_fetch("9.9.9"))
    app = make({})
    runner = app.test_cli_runner()

    result = runner.invoke(args=["alpine", "info"])
    assert result.exit_code == 0 and "Alpine.js" in result.output

    dest = tmp_path / "out"
    result = runner.invoke(args=["alpine", "update", "--dest", str(dest)])
    assert result.exit_code == 0 and "9.9.9" in result.output
    assert assets.load_manifest(dest).version == "9.9.9"

    result = runner.invoke(args=["alpine", "check"])
    assert result.exit_code == 1 and "latest: 9.9.9" in result.output


def test_all_only_loads_available_plugins(tmp_path):
    vendor.download_assets(dest=tmp_path, fetch=fake_fetch(missing=("/navigate@9.9.9",)))
    app = make({"ALPINE_ASSET_DIR": str(tmp_path), "ALPINE_PLUGINS": "all"})
    out = render(app)
    assert "plugins/mask.min.js" in out and "navigate" not in out
    with app.app_context():
        assert "navigate" not in app.extensions["alpine"].extension.available_plugins


def test_requesting_unavailable_plugin_is_a_clear_error(tmp_path):
    vendor.download_assets(dest=tmp_path, fetch=fake_fetch(missing=("/navigate@9.9.9",)))
    with pytest.raises(AlpineError, match="navigate"):
        make({"ALPINE_ASSET_DIR": str(tmp_path), "ALPINE_PLUGINS": ["navigate"]})
    app = make({"ALPINE_ASSET_DIR": str(tmp_path)})
    with app.test_request_context():
        with pytest.raises(AlpineError, match="navigate"):
            render_template_string("{{ alpine_use('navigate') }}")


def test_cli_update_plugins_option(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "_fetch", fake_fetch("9.9.9"))
    runner = make({}).test_cli_runner()
    dest = tmp_path / "o"
    result = runner.invoke(args=["alpine", "update", "--plugins", "mask", "--dest", str(dest)])
    assert result.exit_code == 0 and "plugins: mask" in result.output
