"""Hatch build hook: bundle the latest Alpine.js into every sdist/wheel.

Set FLASK_ALPINE_SKIP_VENDOR=1 to build with whatever is already in the tree.
If the download fails but real assets are already present, the build continues
with them; if only placeholders are present, the build fails loudly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class VendorAlpineHook(BuildHookInterface):  # type: ignore[misc]
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if os.environ.get("FLASK_ALPINE_SKIP_VENDOR"):
            return
        sys.path.insert(0, str(Path(self.root) / "src"))
        from flask_alpine import assets, vendor
        from flask_alpine.errors import AlpineError

        package = Path(self.root) / "src" / "flask_alpine"
        self.app.display_info("flask-alpine: downloading the latest Alpine.js ...")
        try:
            manifest = vendor.download_assets(dest=package)
        except AlpineError as exc:
            if assets.load_manifest(package).vendored:
                self.app.display_warning(f"flask-alpine: {exc}; using existing assets.")
                return
            raise RuntimeError(
                f"{exc}\nNo vendored Alpine.js found. Connect to the internet or run "
                "`python -m flask_alpine update --dest src/flask_alpine` first."
            ) from exc
        for line in vendor.summary(manifest):
            self.app.display_info(f"flask-alpine: {line}")
