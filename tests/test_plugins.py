import pytest

from flask_alpine import PLUGIN_NAMES, PluginUnavailableError, UnknownPluginError
from flask_alpine.plugins import normalize_plugins


def test_none_and_empty():
    assert normalize_plugins(None) == ()
    assert normalize_plugins([]) == ()
    assert normalize_plugins("") == ()


def test_all_expands():
    assert normalize_plugins("all") == PLUGIN_NAMES
    assert normalize_plugins(["*"]) == PLUGIN_NAMES


def test_string_forms_and_aliases():
    assert normalize_plugins("mask, persist") == ("mask", "persist")
    assert normalize_plugins("@alpinejs/mask") == ("mask",)
    assert normalize_plugins(["MASK"]) == ("mask",)


def test_canonical_order_and_dedupe():
    assert normalize_plugins(["sort", "anchor", "sort"]) == ("anchor", "sort")


def test_unknown_suggests_close_match():
    with pytest.raises(UnknownPluginError, match="Did you mean 'collapse'"):
        normalize_plugins(["colapse"])


def test_non_string_rejected():
    with pytest.raises(TypeError):
        normalize_plugins([1])  # type: ignore[list-item]


def test_none_selects_nothing():
    assert normalize_plugins("none") == ()


def test_available_limits_all_and_rejects_missing():
    available = ("mask", "persist")
    assert normalize_plugins("all", available=available) == available
    assert normalize_plugins("mask", available=available) == ("mask",)
    with pytest.raises(PluginUnavailableError, match="'sort'"):
        normalize_plugins("sort", available=available)
    with pytest.raises(UnknownPluginError):
        normalize_plugins("nope", available=available)
