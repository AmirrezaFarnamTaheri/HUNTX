"""
H-3 Secret Scan Suite — Phase 1 (warn-on-fallback).

Tests:
1. RuntimeWarning emitted when env var absent (fallback active).
2. No warning when env var is set.
3. _require_env_bytes returns env var bytes when set.
4. _require_env_bytes returns fallback when env var absent (Phase 1).
5-8. Parametrized: each credential key triggers RuntimeWarning when absent.
"""
import os
import warnings
import pytest


# ---------------------------------------------------------------------------
# Import module (will trigger warnings at import if env vars absent)
# ---------------------------------------------------------------------------

def _fresh_import():
    """Reload crypto module to re-evaluate TUT_PASSWORDS dict."""
    import importlib
    import huntx.formats.common.crypto as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# Tests for _require_env_bytes helper
# ---------------------------------------------------------------------------

def test_require_env_bytes_returns_env_value_when_set(monkeypatch):
    """H-3: _require_env_bytes must return env var bytes when set."""
    monkeypatch.setenv("HUNTX_TUT_PASS_TUT", "mySecretPass")
    from huntx.formats.common.crypto import _require_env_bytes
    result = _require_env_bytes("HUNTX_TUT_PASS_TUT", b"fallback", "test")
    assert result == b"mySecretPass", f"Expected b'mySecretPass', got {result!r}"


def test_require_env_bytes_returns_fallback_when_env_absent(monkeypatch):
    """H-3 Phase 1: _require_env_bytes returns fallback when env var absent."""
    monkeypatch.delenv("HUNTX_TUT_PASS_TUT", raising=False)
    from huntx.formats.common.crypto import _require_env_bytes
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        result = _require_env_bytes("HUNTX_TUT_PASS_TUT", b"myfallback", "test")
    assert result == b"myfallback", f"Expected fallback b'myfallback', got {result!r}"


def test_require_env_bytes_warns_on_fallback(monkeypatch):
    """H-3 Phase 1: RuntimeWarning emitted when env var absent."""
    monkeypatch.delenv("HUNTX_TUT_PASS_TUT", raising=False)
    from huntx.formats.common.crypto import _require_env_bytes
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _require_env_bytes("HUNTX_TUT_PASS_TUT", b"myfallback", "TUT password")
    runtime_warns = [x for x in w if issubclass(x.category, RuntimeWarning)]
    assert runtime_warns, "H-3: RuntimeWarning must be emitted when env var absent"
    assert "HUNTX_TUT_PASS_TUT" in str(runtime_warns[0].message), (
        "H-3: Warning message must name the missing env var"
    )


def test_require_env_bytes_no_warning_when_env_set(monkeypatch):
    """H-3 Phase 1: No RuntimeWarning when env var is properly configured."""
    monkeypatch.setenv("HUNTX_TUT_PASS_TUT", "properSecret")
    from huntx.formats.common.crypto import _require_env_bytes
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _require_env_bytes("HUNTX_TUT_PASS_TUT", b"myfallback", "TUT password")
    runtime_warns = [x for x in w if issubclass(x.category, RuntimeWarning)]
    assert not runtime_warns, (
        "H-3: No RuntimeWarning must be emitted when env var is set"
    )


# ---------------------------------------------------------------------------
# Parametrized: all 4 credential keys must each warn individually
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env_key,fallback,name", [
    ("HUNTX_TUT_PASS_TUT", b"fubvx788b46v",     "TUT password (.tut)"),
    ("HUNTX_TUT_PASS_SKS", b"dyv35224nossas!!", "TUT password (.sks)"),
    ("HUNTX_TUT_PASS_TMT", b"fubvx788B4mev",    "TUT password (.tmt)"),
    ("HUNTX_NETMOD_KEY",   b"_netsyna_netmod_", "NetMod AES key"),
])
def test_each_credential_warns_on_fallback(env_key, fallback, name, monkeypatch):
    """H-3: Each of the 4 credential env vars must trigger RuntimeWarning when absent."""
    monkeypatch.delenv(env_key, raising=False)
    from huntx.formats.common.crypto import _require_env_bytes
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _require_env_bytes(env_key, fallback, name)
    runtime_warns = [x for x in w if issubclass(x.category, RuntimeWarning)]
    assert runtime_warns, f"H-3: {env_key!r} must trigger RuntimeWarning when absent"
    assert env_key in str(runtime_warns[0].message), (
        f"H-3: Warning must name the missing key {env_key!r}"
    )
