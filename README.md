# flask-alpine

Add [Alpine.js](https://alpinejs.dev) to any Flask app in two lines. Alpine core and
every official plugin ship **inside the package**: no CDN, no npm, no build step, and
nothing is fetched at runtime.

```python
from flask import Flask
from flask_alpine import Alpine

app = Flask(__name__)
Alpine(app, plugins=["persist", "collapse"])
```

```html
<div x-data="{ open: false }">
  <button @click="open = !open">Toggle</button>
  <p x-show="open" x-collapse>Hello!</p>
</div>
{{ alpine_scripts() }}   {# put this last in <body> #}
```

## Install

```bash
pip install flask-alpine
```

Requires Python 3.9+ and Flask 2.2+.

## How it works

`Alpine` registers a small blueprint that serves the bundled files from
`/_alpine/` (`alpine.min.js`, `alpine.csp.min.js`, `plugins/<name>.min.js`) and adds
template helpers. Plugins are always emitted **before** the core script, which Alpine
requires, so you never think about load order.

## Template helpers

| Helper | Purpose |
| --- | --- |
| `{{ alpine_scripts() }}` | `<script>` tags for the configured plugins + core |
| `{{ alpine_scripts('mask', 'persist') }}` | Add plugins for this page (`plugins=`, `defaults=False`, `csp=`, `defer=`, `nonce=`) |
| `{{ alpine_use('mask') }}` | Require a plugin from any template/partial/macro (call **before** `alpine_scripts()`) |
| `{{ alpine_url('mask') }}` / `{{ alpine_url() }}` | URL of a plugin / the core build |

Python equivalents: `alpine.use("mask")` (per request, handy in `before_request` hooks),
`alpine.scripts(...)`, `alpine.url(...)`, `alpine.selected_plugins()`, `alpine.alpine_version`.

## Configuration

Resolution order: `app.config["ALPINE_*"]` → constructor keyword → default.
Set code defaults in the constructor and override per environment in config classes.

| Config key | Default | Description |
| --- | --- | --- |
| `ALPINE_PLUGINS` | `()` | List, comma-separated string, or `"all"` |
| `ALPINE_CSP` | `False` | Use the CSP-safe core build (no `eval`) |
| `ALPINE_DEFER` | `True` | Emit `defer` on scripts |
| `ALPINE_URL_PREFIX` | `"/_alpine"` | Where assets are served |
| `ALPINE_VERSIONED_URLS` | `True` | Append `?v=<version>` for cache busting |
| `ALPINE_SRI` | `False` | Add `integrity="sha384-…"` attributes |
| `ALPINE_NONCE` | `None` | CSP nonce: string or zero-arg callable |
| `ALPINE_CACHE_MAX_AGE` | `None` | Seconds for `Cache-Control` (e.g. `31536000` in production) |
| `ALPINE_AUTO_DOWNLOAD` | `False` | If no real Alpine.js is available, download the latest release on startup |
| `ALPINE_ASSET_DIR` | `None` | Directory of downloaded assets; used instead of the bundled files when it holds a real release (default with auto-download: per-user cache dir) |

```python
class Production(Config):
    ALPINE_PLUGINS = "all"
    ALPINE_CACHE_MAX_AGE = 31536000
    ALPINE_SRI = True
```

Official plugins: `anchor collapse focus intersect mask morph navigate persist resize sort`.
Names are validated at startup (`UnknownPluginError` suggests the closest match).

Not every plugin is published for every Alpine.js release. The downloader skips a plugin
whose build doesn't exist (after trying that plugin's own latest version) instead of
failing. `"all"` then means "every plugin that is actually present", and explicitly
requesting a missing one raises `PluginUnavailableError`. `flask alpine info` lists what is
served; `alpine.available_plugins` does the same in Python.

## Application factories and blueprints

```python
alpine = Alpine()

def create_app():
    app = Flask(__name__)
    app.config["ALPINE_PLUGINS"] = ["persist"]
    alpine.init_app(app)
    return app
```

Helpers are app-wide, so templates in any blueprint can use them. A blueprint can also
require plugins for all its pages:

```python
@admin.before_request
def _():
    alpine.use("mask", "sort")
```

## Content Security Policy

```python
Alpine(app, csp=True, nonce=lambda: g.csp_nonce)
```

`csp=True` switches to Alpine's CSP build. Assets are same-origin, so `script-src 'self'`
works without allowing any CDN.

## Getting the latest Alpine.js

The package always serves local files. There are three ways to get the newest release:

1. **Automatically at build time.** Building an sdist/wheel runs a Hatch hook that
   downloads the latest `alpinejs`, `@alpinejs/csp` and all plugins and records their
   versions and SHA-256 hashes. Users installing the wheel need no internet.
   If the download fails but real files are already present, the build continues with
   them; set `FLASK_ALPINE_SKIP_VENDOR=1` to skip the hook.
2. **Automatically at first run (opt-in).** `ALPINE_AUTO_DOWNLOAD = True` fetches the
   latest release into the user cache dir (or `ALPINE_ASSET_DIR`) when no real assets
   exist, e.g. in a fresh git checkout. Later starts reuse the cache and work offline.
   A failed download warns and falls back to the placeholders instead of crashing.
3. **On demand.**

   ```bash
   flask alpine info                  # what is being served
   flask alpine check                 # served vs latest (exit 1 if outdated)
   flask alpine update                # download latest to ALPINE_ASSET_DIR / cache dir
   flask alpine update --version 3.14.9
   flask alpine update --plugins collapse,focus   # or 'none'
   python -m flask_alpine update --dest src/flask_alpine   # maintainers: refresh the package
   ```

Downloads are validated and written only after every file succeeds, so a failed update
never leaves a half-updated directory. The only host contacted is
`cdn.jsdelivr.net` (the npm registry is never used): `package.json` at the `@latest` tag gives the
version and `dist/cdn.min.js` gives the files. jsDelivr may cache `@latest` for a while, so pin
with `--version` if you need a release that was published moments ago.

## Development

```bash
pip install -e ".[dev]"
pytest
mypy
```

## License

MIT. Alpine.js is MIT-licensed; see `THIRD_PARTY_NOTICES.md`.
