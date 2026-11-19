import hashlib

import pytest

from flask_alpine import PLUGIN_NAMES, assets


def test_all_files_present():
    for rel in [assets.CORE_FILE, assets.CSP_CORE_FILE, *map(assets.plugin_file, PLUGIN_NAMES)]:
        assert assets.asset_path(rel).is_file(), rel


def test_manifest_loads():
    manifest = assets.load_manifest()
    assert manifest.version
    assert isinstance(manifest.vendored, bool)


@pytest.fixture
def vendored():
    manifest = assets.load_manifest()
    if not manifest.vendored:
        pytest.skip("assets not vendored yet (run scripts/vendor_assets.py)")
    return manifest


def test_bundled_files_match_manifest_hashes(vendored):
    for rel, expected in vendored.sha256.items():
        assert hashlib.sha256(assets.asset_path(rel).read_bytes()).hexdigest() == expected


def test_bundled_files_are_real_builds(vendored):
    for rel in vendored.sha256:
        assert assets.asset_path(rel).stat().st_size > 500, rel
