"""H-3 secret externalization and fail-closed regression tests."""

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


def test_crypto_source_contains_no_legacy_plaintext_fallbacks():
    source_path = (
        Path(__file__).parent.parent
        / "src"
        / "huntx"
        / "formats"
        / "common"
        / "crypto.py"
    )
    source = source_path.read_text(encoding="utf-8")
    forbidden = [
        "fubvx788b46v",
        "dyv35224nossas!!",
        "fubvx788B4mev",
        "_netsyna_netmod_",
        "1C8986F91DD8EC9A",
        "557034DC3DDDA3BB",
        "C70A4A42712024EE",
        "6F5577AE58747E8E",
        "924D4AF0D8A43E0B",
        "FCD9E79819861E07",
        "4A5573B012F4D08B",
        "998E67C256D955E3",
    ]
    for literal in forbidden:
        assert literal not in source, f"legacy credential material remains in crypto.py: {literal}"
