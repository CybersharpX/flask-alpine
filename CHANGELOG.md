# Changelog

## 0.2.2
- Downloads use only the jsDelivr CDN; the npm registry is no longer contacted (latest version is read from `package.json` on the CDN).

## 0.2.1
- Fix: a plugin build missing from npm/jsDelivr (e.g. `@alpinejs/navigate`) no longer aborts the download or the build; it is skipped and reported.
- `PluginUnavailableError`, `Alpine.available_plugins`; `"all"` expands to available plugins.
- `--plugins` option for `flask alpine update` / `python -m flask_alpine update`.

## 0.2.0
- Automatic download of the latest Alpine.js: Hatch build hook, `ALPINE_AUTO_DOWNLOAD`, `ALPINE_ASSET_DIR`, `flask alpine info|check|update`, `python -m flask_alpine`.
- Downloads are validated and atomic; version/hash manifest per asset root.

## 0.1.0
- Initial release.
