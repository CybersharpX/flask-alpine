import base64
import hashlib

import pytest
from flask import Blueprint, Flask, render_template_string

from flask_alpine import Alpine, AlpineError, AssetsNotVendoredWarning, UnknownPluginError, assets


def make_app(config=None, **kwargs):
    app = Flask(__name__)
    app.config.update(TESTING=True, **(config or {}))
    alpine = Alpine(app, **kwargs)
    return app, alpine


def render(app, source="{{ alpine_scripts() }}"):
    with app.test_request_context():
        return render_template_string(source)


def test_registers_extension_and_blueprint():
    app, alpine = make_app()
    assert "alpine" in app.extensions
    assert "alpine" in app.blueprints


def test_core_only_by_default():
    out = render(make_app()[0])
    assert out.count("<script") == 1
    assert "/_alpine/alpine.min.js" in out
    assert "defer" in out


def test_application_factory_pattern():
    alpine = Alpine()

    def create_app(plugins):
        app = Flask(__name__)
        app.config["ALPINE_PLUGINS"] = plugins
        alpine.init_app(app)
        return app

    a, b = create_app(["mask"]), create_app("all")
    assert "plugins/mask.min.js" in render(a)
    assert "plugins/sort.min.js" not in render(a)
    assert "plugins/sort.min.js" in render(b)


def test_constructor_kwargs_and_config_precedence():
    app, _ = make_app({"ALPINE_PLUGINS": ["focus"]}, plugins=["mask"])
    out = render(app)
    assert "focus.min.js" in out and "mask.min.js" not in out


def test_plugins_load_before_core():
    out = render(make_app(plugins=["persist", "mask"])[0])
    core = out.index("/_alpine/alpine.min.js")
    assert out.index("plugins/mask") < core
    assert out.index("plugins/persist") < core


def test_template_argument_adds_plugins():
    app, _ = make_app(plugins=["mask"])
    out = render(app, "{{ alpine_scripts('persist') }}")
    assert "mask.min.js" in out and "persist.min.js" in out


def test_defaults_false_excludes_configured():
    app, _ = make_app(plugins=["mask"])
    out = render(app, "{{ alpine_scripts('persist', defaults=False) }}")
    assert "mask.min.js" not in out and "persist.min.js" in out


def test_alpine_use_in_template():
    app, _ = make_app()
    out = render(app, "{{ alpine_use('collapse') }}{{ alpine_scripts() }}")
    assert "collapse.min.js" in out


def test_use_in_blueprint_is_per_request():
    app, alpine = make_app()
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    @bp.before_request
    def need_mask():
        alpine.use("mask")

    @bp.route("/")
    def admin():
        return render_template_string("{{ alpine_scripts() }}")

    @app.route("/")
    def home():
        return render_template_string("{{ alpine_scripts() }}")

    app.register_blueprint(bp)
    client = app.test_client()
    assert b"mask.min.js" in client.get("/admin/").data
    assert b"mask.min.js" not in client.get("/").data  # no leak between requests


def test_csp_build_and_override():
    app, _ = make_app(csp=True)
    assert "alpine.csp.min.js" in render(app)
    assert "alpine.csp.min.js" not in render(app, "{{ alpine_scripts(csp=False) }}")


def test_defer_disabled():
    app, _ = make_app({"ALPINE_DEFER": False})
    assert "defer" not in render(app)


def test_nonce_string_callable_and_escaping():
    assert 'nonce="abc"' in render(make_app(nonce="abc")[0])
    assert 'nonce="xyz"' in render(make_app(nonce=lambda: "xyz")[0])
    assert "&#34;" in render(make_app(nonce='a"b')[0])


def test_sri_matches_file_hash():
    app, _ = make_app(sri=True)
    digest = hashlib.sha384((assets.STATIC_DIR / assets.CORE_FILE).read_bytes()).digest()
    assert f'integrity="sha384-{base64.b64encode(digest).decode()}"' in render(app)


def test_versioned_urls(monkeypatch):
    fake = assets.Manifest(version="1.2.3", vendored=True)
    monkeypatch.setattr(assets, "load_manifest", lambda root=None: fake)
    assert "?v=1.2.3" in render(make_app()[0])
    assert "?v=" not in render(make_app({"ALPINE_VERSIONED_URLS": False})[0])


def test_assets_are_served():
    app, _ = make_app(plugins="all")
    client = app.test_client()
    for url in ("/_alpine/alpine.min.js", "/_alpine/plugins/mask.min.js"):
        response = client.get(url)
        assert response.status_code == 200
        assert "javascript" in response.mimetype


def test_custom_prefix_and_cache_control():
    app, _ = make_app({"ALPINE_URL_PREFIX": "vendor/alpine/", "ALPINE_CACHE_MAX_AGE": 3600})
    client = app.test_client()
    response = client.get("/vendor/alpine/alpine.min.js")
    assert response.status_code == 200
    assert "max-age=3600" in response.headers["Cache-Control"]
    assert client.get("/_alpine/alpine.min.js").status_code == 404
    assert "/vendor/alpine/alpine.min.js" in render(app)


def test_alpine_url_helper():
    app, _ = make_app()
    assert "plugins/mask.min.js" in render(app, "{{ alpine_url('mask') }}")
    assert "/_alpine/alpine.min.js" in render(app, "{{ alpine_url() }}")
    with pytest.raises(UnknownPluginError):
        render(app, "{{ alpine_url('nope') }}")
    with pytest.raises(AlpineError):
        render(app, "{{ alpine_url('all') }}")


def test_unknown_plugin_fails_at_init():
    with pytest.raises(UnknownPluginError):
        make_app(plugins=["nope"])


def test_empty_prefix_rejected():
    with pytest.raises(AlpineError):
        make_app({"ALPINE_URL_PREFIX": "/"})


def test_warns_when_not_vendored(monkeypatch):
    fake = assets.Manifest(version="0.0.0-unvendored", vendored=False)
    monkeypatch.setattr(assets, "load_manifest", lambda root=None: fake)
    with pytest.warns(AssetsNotVendoredWarning):
        make_app()


def test_output_is_markup_not_escaped():
    app, _ = make_app()
    assert "&lt;" not in render(app)


def test_settings_require_initialised_app():
    with Flask(__name__).app_context():
        with pytest.raises(AlpineError):
            Alpine().settings
