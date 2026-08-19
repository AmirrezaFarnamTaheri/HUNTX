"""H-3 secret externalization and fail-closed regression tests."""

import ast
import hashlib
from pathlib import Path

import pytest

from huntx.formats.common.crypto import (
    MissingSecretError,
    _get_tut_password,
    _require_env_bytes,
    _require_env_hex_bytes,
    decrypt_netmod_data,
    decrypt_slipnet_link,
)


@pytest.mark.parametrize(
    "env_key",
    [
        "HUNTX_TUT_PASS_TUT",
        "HUNTX_TUT_PASS_SKS",
        "HUNTX_TUT_PASS_TMT",
        "HUNTX_NETMOD_KEY",
        "HUNTX_SLIPNET_KEY_HEX",
    ],
)
def test_missing_decryption_secret_fails_closed(env_key, monkeypatch):
    monkeypatch.delenv(env_key, raising=False)
    if env_key == "HUNTX_SLIPNET_KEY_HEX":
        with pytest.raises(MissingSecretError, match=env_key):
            _require_env_hex_bytes(env_key, "test secret", expected_length=32)
    else:
        with pytest.raises(MissingSecretError, match=env_key):
            _require_env_bytes(env_key, "test secret")


def test_require_env_bytes_preserves_configured_value(monkeypatch):
    monkeypatch.setenv("HUNTX_TUT_PASS_TUT", "configured-secret")
    assert _require_env_bytes("HUNTX_TUT_PASS_TUT", "TUT password") == b"configured-secret"


def test_empty_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("HUNTX_TUT_PASS_TUT", "")
    with pytest.raises(MissingSecretError, match="HUNTX_TUT_PASS_TUT"):
        _require_env_bytes("HUNTX_TUT_PASS_TUT", "TUT password")


def test_fixed_length_secret_is_validated(monkeypatch):
    monkeypatch.setenv("HUNTX_NETMOD_KEY", "too-short")
    with pytest.raises(MissingSecretError, match="exactly 16 bytes"):
        _require_env_bytes("HUNTX_NETMOD_KEY", "NetMod AES key", expected_length=16)


def test_slipnet_key_must_be_32_hex_bytes(monkeypatch):
    monkeypatch.setenv("HUNTX_SLIPNET_KEY_HEX", "not-hex")
    with pytest.raises(MissingSecretError, match="hexadecimal"):
        _require_env_hex_bytes("HUNTX_SLIPNET_KEY_HEX", "SlipNet key", expected_length=32)

    monkeypatch.setenv("HUNTX_SLIPNET_KEY_HEX", "00" * 31)
    with pytest.raises(MissingSecretError, match="exactly 32 bytes"):
        _require_env_hex_bytes("HUNTX_SLIPNET_KEY_HEX", "SlipNet key", expected_length=32)

    monkeypatch.setenv("HUNTX_SLIPNET_KEY_HEX", "ab" * 32)
    assert _require_env_hex_bytes(
        "HUNTX_SLIPNET_KEY_HEX", "SlipNet key", expected_length=32
    ) == bytes.fromhex("ab" * 32)


@pytest.mark.parametrize(
    "extension,env_key,value",
    [
        (".tut", "HUNTX_TUT_PASS_TUT", "tut-secret"),
        (".sks", "HUNTX_TUT_PASS_SKS", "sks-secret"),
        (".tmt", "HUNTX_TUT_PASS_TMT", "tmt-secret"),
    ],
)
def test_tut_passwords_are_resolved_lazily(extension, env_key, value, monkeypatch):
    monkeypatch.setenv(env_key, value)
    assert _get_tut_password(extension) == value.encode("utf-8")


def test_netmod_decryptor_requires_secret_before_processing(monkeypatch):
    monkeypatch.delenv("HUNTX_NETMOD_KEY", raising=False)
    with pytest.raises(MissingSecretError, match="HUNTX_NETMOD_KEY"):
        decrypt_netmod_data(b"AA==")


def test_slipnet_decryptor_requires_secret_before_processing(monkeypatch):
    monkeypatch.delenv("HUNTX_SLIPNET_KEY_HEX", raising=False)
    with pytest.raises(MissingSecretError, match="HUNTX_SLIPNET_KEY_HEX"):
        decrypt_slipnet_link("slipnet-enc://AQ==")


def test_crypto_source_contains_no_known_leaked_literal_fingerprints():
    """Reject known leaked constants without re-embedding those secrets in tests."""
    source_path = (
        Path(__file__).parent.parent
        / "src"
        / "huntx"
        / "formats"
        / "common"
        / "crypto.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    literal_fingerprints = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if isinstance(node.value, str):
            value = node.value.encode("utf-8")
        elif isinstance(node.value, bytes):
            value = node.value
        else:
            continue
        literal_fingerprints.add(hashlib.sha256(value).hexdigest())

    # SHA-256 fingerprints of credentials/key fragments exposed by the legacy
    # implementation. Fingerprinting lets the regression detect their return
    # without publishing the credential material again in the current tree.
    leaked_literal_fingerprints = {
        "6ecce1be094efccf37944fff9387548ef4c3bc248bbe529686cc4328e1742b9d",
        "dd33e620e1d40afdfd238c4b28b3b5e4b0c9f94f86149c00338f39fc1efa094c",
        "b35cf460b4bcff9e548f5dff2e986accc482ee19ad27b271020f4cd6be4477ec",
        "6387742565fa517ed44225dbc5758ffa15b8ed561b2216b63944caf850beb381",
        "7487cfde4ea6c6874fc26a60c9b172110ba3231f06adaee46e9091da9389f2d1",
        "bb8c5a5ffbeafcb118a7f4f0e9cd9d0f77ef5d75a95a7ab5e1d3ea4390d6809f",
        "df4cc8115d2aaae21712405df7ca1defbb446d0ed036ad988eed6ec5c89f5953",
        "8f734da16401b01b04d6fe8e4e4905d79262e20542b91e95c59aa22b4508d3f0",
        "dd40b8bde97e6bd71b2a52666691cc1fb2cd0ea55e479d2495d218ed74a7bad6",
        "0896b84b739529efdd3d1912372434769cdb29191a2ee9f02e8fe80625e39f8b",
        "d3da2f9f2f8a5af2ee2fa844639674b53323108af6607e50b2d14b93ff4e026a",
        "f16ef299b79797b9e1653399513976001018f95297f1acdf9f5e158d7d602469",
    }
    assert literal_fingerprints.isdisjoint(leaked_literal_fingerprints)
