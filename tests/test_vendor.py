import json
import os

import pytest

from flask_alpine import assets, vendor
from flask_alpine.errors import AlpineError, DownloadError


def fake_fetch(latest="9.9.9", fail_on=None, body=None, missing=(), plugin_latest=None):
    """Offline stand-in for vendor._fetch.

    ``missing``: URL fragments that 404. ``plugin_latest``: plugin -> own latest version.
    """
    calls = []

    def fetch(url):
        calls.append(url)
        if fail_on and fail_on in url:
            raise OSError("boom")
        if any(m in url for m in missing):
            raise vendor.NotFound(url)
        assert "registry.npmjs.org" not in url, "npm registry must never be contacted"
        if url == vendor.latest_url("alpinejs"):
            return json.dumps({"version": latest}).encode()
        if url.endswith("@latest/package.json"):
            name = url.split("/npm/@alpinejs/")[1].split("@latest")[0]
            if plugin_latest and name in plugin_latest:
                return json.dumps({"version": plugin_latest[name]}).encode()
            raise vendor.NotFound(url)
        return body if body is not None else (b"/* " + url.encode() + b" */ var a=1;")

    fetch.calls = calls
    return fetch


def test_downloads_latest_into_dest(tmp_path):
    fetch = fake_fetch()
    manifest = vendor.download_assets(dest=tmp_path, fetch=fetch)
    assert manifest.version == "9.9.9" and manifest.vendored
    assert fetch.calls[0] == vendor.latest_url("alpinejs")
    for relative, package in vendor.targets().items():
        assert assets.asset_path(relative, tmp_path).is_file()
        assert f"{package}@9.9.9" in assets.asset_path(relative, tmp_path).read_text()
    loaded = assets.load_manifest(tmp_path)
    assert loaded.version == "9.9.9" and len(loaded.sha256) == len(vendor.targets())


def test_downloads_every_official_plugin_and_csp(tmp_path):
    fetch = fake_fetch()
    vendor.download_assets(dest=tmp_path, fetch=fetch)
    joined = " ".join(fetch.calls)
    assert "@alpinejs/csp@" in joined and "alpinejs@9.9.9" in joined
    for name in ("anchor", "collapse", "focus", "intersect", "mask", "morph",
                 "navigate", "persist", "resize", "sort"):
        assert f"@alpinejs/{name}@9.9.9" in joined


def test_explicit_version_skips_registry(tmp_path):
    fetch = fake_fetch()
    vendor.download_assets("3.1.0", tmp_path, fetch=fetch)
    assert vendor.latest_url("alpinejs") not in fetch.calls
    assert assets.load_manifest(tmp_path).version == "3.1.0"


def test_invalid_version_rejected(tmp_path):
    with pytest.raises(DownloadError):
        vendor.download_assets("../evil", tmp_path, fetch=fake_fetch())


def test_failure_writes_nothing(tmp_path):
    with pytest.raises(DownloadError, match="sort"):
        vendor.download_assets(dest=tmp_path, fetch=fake_fetch(fail_on="/sort@"))
    assert not (tmp_path / "static").exists()
    assert not (tmp_path / assets.MANIFEST_NAME).exists()


def test_html_response_rejected(tmp_path):
    with pytest.raises(DownloadError, match="non-JavaScript"):
        vendor.download_assets("3.1.0", tmp_path, fetch=fake_fetch(body=b"<html>404</html>"))


def test_registry_failure_is_download_error(tmp_path):
    with pytest.raises(DownloadError):
        vendor.download_assets(dest=tmp_path, fetch=fake_fetch(fail_on="package.json"))


def test_check_reports_versions(tmp_path):
    vendor.download_assets("3.1.0", tmp_path, fetch=fake_fetch())
    assert vendor.check(tmp_path, fetch=fake_fetch("3.2.0")) == ("3.1.0", "3.2.0")


def test_default_cache_dir_override():
    old = os.environ.get("FLASK_ALPINE_CACHE_DIR")
    os.environ["FLASK_ALPINE_CACHE_DIR"] = "/tmp/xyz"
    try:
        assert str(vendor.default_cache_dir()) == "/tmp/xyz"
    finally:
        if old is None:
            del os.environ["FLASK_ALPINE_CACHE_DIR"]
        else:
            os.environ["FLASK_ALPINE_CACHE_DIR"] = old


def test_main_update_and_check(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "_fetch", fake_fetch())
    assert vendor.main(["update", "--dest", str(tmp_path)]) == 0
    assert vendor.main(["check", "--dest", str(tmp_path)]) == 0


def test_missing_plugin_is_skipped_not_fatal(tmp_path):
    """Regression: @alpinejs/navigate 404 used to abort the whole download."""
    fetch = fake_fetch(missing=("/navigate@9.9.9",))
    manifest = vendor.download_assets(dest=tmp_path, fetch=fetch)
    assert "navigate" not in manifest.plugins and "mask" in manifest.plugins
    assert not assets.asset_path(assets.plugin_file("navigate"), tmp_path).exists()
    assert assets.asset_path(assets.CORE_FILE, tmp_path).is_file()
    assert any("plugins: " in line and "navigate" not in line for line in vendor.summary(manifest))
    assert assets.load_manifest(tmp_path).plugins == manifest.plugins


def test_missing_plugin_falls_back_to_its_own_latest(tmp_path):
    fetch = fake_fetch(missing=("/navigate@9.9.9",), plugin_latest={"navigate": "3.14.0"})
    manifest = vendor.download_assets(dest=tmp_path, fetch=fetch)
    assert manifest.plugins["navigate"] == "3.14.0"
    assert "different version" in "\n".join(vendor.summary(manifest))


def test_missing_core_is_fatal(tmp_path):
    with pytest.raises(DownloadError, match="alpinejs@9.9.9"):
        vendor.download_assets(dest=tmp_path, fetch=fake_fetch(missing=("/alpinejs@9.9.9",)))


def test_plugin_selection(tmp_path):
    fetch = fake_fetch()
    manifest = vendor.download_assets(dest=tmp_path, plugins="mask, persist", fetch=fetch)
    assert set(manifest.plugins) == {"mask", "persist"}
    assert not any("/collapse@" in url for url in fetch.calls)


def test_no_plugins_and_stale_files_removed(tmp_path):
    vendor.download_assets(dest=tmp_path, fetch=fake_fetch())
    assert assets.asset_path(assets.plugin_file("collapse"), tmp_path).exists()
    manifest = vendor.download_assets(dest=tmp_path, plugins="none", fetch=fake_fetch())
    assert manifest.plugins == {}
    assert not assets.asset_path(assets.plugin_file("collapse"), tmp_path).exists()


def test_only_jsdelivr_is_contacted(tmp_path):
    fetch = fake_fetch(missing=("/navigate@9.9.9",), plugin_latest={"navigate": "3.14.0"})
    vendor.download_assets(dest=tmp_path, fetch=fetch)
    assert fetch.calls and all(u.startswith("https://cdn.jsdelivr.net/npm/") for u in fetch.calls)
