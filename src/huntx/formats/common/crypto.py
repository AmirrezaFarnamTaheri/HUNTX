import base64
import logging
import os
import struct
import urllib.parse
from typing import Any, Optional

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _HAVE_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover
    # Keep optional cryptography imports usable when the dependency is absent.
    # The imported symbols are typed as concrete cryptography objects in the
    # success branch, so mypy needs an explicit ignore for their ``None``
    # fallback values.
    default_backend = None  # type: ignore[assignment]
    hashes = None  # type: ignore[assignment]
    serialization = None  # type: ignore[assignment]
    padding = None  # type: ignore[assignment]
    Cipher = None  # type: ignore[assignment,misc]
    algorithms = None  # type: ignore[assignment]
    modes = None  # type: ignore[assignment]
    PBKDF2HMAC = None  # type: ignore[assignment,misc]
    _HAVE_CRYPTOGRAPHY = False

logger = logging.getLogger(__name__)


class MissingSecretError(RuntimeError):
    """Raised when a decryption credential is not configured safely."""


# --- HA Tunnel Plus (happ://) ---

HAPP_KEYS_PEM = {
    "crypt": os.getenv("HUNTX_HAPP_CRYPT_PEM") or "",
    "crypt2": os.getenv("HUNTX_HAPP_CRYPT2_PEM") or "",
    "crypt3": os.getenv("HUNTX_HAPP_CRYPT3_PEM") or "",
}

# Resolve local keys folder if present.
for k in ["crypt", "crypt2", "crypt3"]:
    if not HAPP_KEYS_PEM[k]:
        key_path = os.path.join("persist", "keys", f"happ_{k}.pem")
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    HAPP_KEYS_PEM[k] = f.read()
            except Exception as exc:
                logger.warning("Could not read HAPP key file %s: %s", key_path, exc)

_HAPP_KEYS_CACHE: dict[str, Any] = {}


def _get_happ_keys():
    if not _HAPP_KEYS_CACHE:
        for key_name, pem in HAPP_KEYS_PEM.items():
            if not pem:
                continue
            try:
                _HAPP_KEYS_CACHE[key_name] = serialization.load_pem_private_key(
                    pem.encode(), password=None, backend=default_backend()
                )
            except Exception as exc:
                logger.error("Failed to load HAPP key %s: %s", key_name, exc)
    return _HAPP_KEYS_CACHE


def decrypt_happ_link(link_str: str) -> Optional[str]:
    """Decrypt a happ:// link using RSA-PKCS1v15."""
    decoded_text = urllib.parse.unquote(link_str)
    version = None
    prefix = ""
    for candidate in ["crypt3", "crypt2", "crypt"]:
        candidate_prefix = f"happ://{candidate}/"
        if candidate_prefix in decoded_text:
            version = candidate
            prefix = candidate_prefix
            break

    if not version:
        return None

    keys = _get_happ_keys()
    if version not in keys:
        return None

    try:
        encrypted_b64 = decoded_text.split(prefix, 1)[1]
        data = base64.b64decode(encrypted_b64)
        decrypted = keys[version].decrypt(data, padding.PKCS1v15())
        return decrypted.decode("utf-8")
    except Exception as exc:
        logger.debug("HAPP decryption failed for %s: %s", version, exc)
        return None


# --- Required secret helpers ---


def _require_env_bytes(
    env_key: str,
    name: str = "credential",
    *,
    expected_length: Optional[int] = None,
) -> bytes:
    """Return an environment-provided secret as bytes, failing closed when absent.

    HUNTX intentionally has no source-visible fallback credentials. Operators
    must provision the named variable before the corresponding decryptor can be
    used. This keeps imports safe while making the sensitive operation itself
    fail closed.
    """
    value = os.environ.get(env_key)
    if value is None or value == "":
        raise MissingSecretError(
            f"[SECURITY] {name}: environment variable {env_key!r} is required but not set."
        )

    encoded = value.encode("utf-8")
    if expected_length is not None and len(encoded) != expected_length:
        raise MissingSecretError(
            f"[SECURITY] {name}: environment variable {env_key!r} must encode to "
            f"exactly {expected_length} bytes."
        )
    return encoded


def _require_env_hex_bytes(env_key: str, name: str, *, expected_length: int) -> bytes:
    """Return a required hexadecimal environment secret with strict length validation."""
    value = os.environ.get(env_key)
    if value is None or value == "":
        raise MissingSecretError(
            f"[SECURITY] {name}: environment variable {env_key!r} is required but not set."
        )
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise MissingSecretError(
            f"[SECURITY] {name}: environment variable {env_key!r} must contain hexadecimal bytes."
        ) from exc
    if len(decoded) != expected_length:
        raise MissingSecretError(
            f"[SECURITY] {name}: environment variable {env_key!r} must decode to "
            f"exactly {expected_length} bytes."
        )
    return decoded


# --- SlipNet (slipnet-enc://) ---


def decrypt_slipnet_link(link_str: str) -> Optional[str]:
    """Decrypt a slipnet-enc:// link using an operator-provided AES-256-GCM key."""
    if not link_str.startswith("slipnet-enc://"):
        return None

    # Resolve the key outside the parsing/decryption catch block so a missing or
    # malformed secret is never silently treated as malformed input.
    key = _require_env_hex_bytes(
        "HUNTX_SLIPNET_KEY_HEX",
        "SlipNet AES-256 key",
        expected_length=32,
    )

    try:
        b64_payload = link_str.replace("slipnet-enc://", "", 1).strip()
        b64_payload = b64_payload.replace("-", "+").replace("_", "/")
        while len(b64_payload) % 4 != 0:
            b64_payload += "="

        payload = base64.b64decode(b64_payload)
        if len(payload) < 29:  # version + IV + at least a 16-byte GCM tag
            return None

        version = payload[0]
        if version != 0x01:
            return None

        iv = payload[1:13]
        ciphertext = payload[13:]
        tag = ciphertext[-16:]
        actual_ciphertext = ciphertext[:-16]

        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend(),
        ).decryptor()
        return (decryptor.update(actual_ciphertext) + decryptor.finalize()).decode("utf-8")
    except Exception as exc:
        logger.debug("SlipNet decryption failed: %s", exc)
        return None


# --- TutDecryptor (.tut, .sks, .tmt) ---

_TUT_PASSWORD_ENV_VARS = {
    ".tut": "HUNTX_TUT_PASS_TUT",
    ".sks": "HUNTX_TUT_PASS_SKS",
    ".tmt": "HUNTX_TUT_PASS_TMT",
}


def _get_tut_password(extension: str) -> bytes:
    normalized = extension if extension in _TUT_PASSWORD_ENV_VARS else ".tmt"
    env_key = _TUT_PASSWORD_ENV_VARS[normalized]
    return _require_env_bytes(env_key, f"TUT password ({normalized})")


def decrypt_tut_data(data_str: str, extension: str = ".tmt") -> Optional[str]:
    """Decrypt .tut/.sks/.tmt file content using PBKDF2 + AES-GCM."""
    normalized = extension if extension in _TUT_PASSWORD_ENV_VARS else ".tmt"
    password = _get_tut_password(normalized)

    try:
        parts = data_str.strip().split(".")
        if len(parts) != 3:
            return None

        salt, iv, encrypted = [base64.b64decode(part) for part in parts]
        if len(encrypted) < 16:
            return None

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=1000,
            backend=default_backend(),
        )
        key = kdf.derive(password)

        tag = encrypted[-16:]
        ciphertext = encrypted[:-16]
        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend(),
        ).decryptor()
        return (decryptor.update(ciphertext) + decryptor.finalize()).decode("utf-8")
    except Exception as exc:
        logger.debug("TUT decryption failed: %s", exc)
        return None


# --- XXTEA with custom Delta (from vpndecrypt-Lol) ---


def decrypt_xxtea(data: bytes, key: bytes, delta: int) -> bytes:
    """XXTEA decryption with support for a custom delta."""
    if not data:
        return b""

    def _str2long(value, with_length):
        n = len(value)
        m = (4 - (n & 3) & 3) + n
        value = value.ljust(m, b"\0")
        words = list(struct.unpack("<%iL" % (m >> 2), value))
        if with_length:
            words.append(n)
        return words

    def _long2str(words, with_length):
        n = (len(words) - 1) * 4
        if with_length:
            m = words[-1]
            if (m < n - 3) or (m > n):
                return b""
            n = m
        value = struct.pack("<%iL" % len(words), *words)
        return value[0:n] if with_length else value

    values = _str2long(data, False)
    key_words = _str2long(key.ljust(16, b"\0")[:16], False)

    n = len(values) - 1
    if n < 1:
        return data

    z = values[n]
    y = values[0]
    rounds = 6 + 52 // (n + 1)
    sum_val = (rounds * delta) & 0xFFFFFFFF

    while sum_val != 0:
        e = (sum_val >> 2) & 3
        for p in range(n, 0, -1):
            z = values[p - 1]
            values[p] = (
                values[p]
                - (
                    (z >> 5 ^ y << 2)
                    + (y >> 3 ^ z << 4)
                    ^ (sum_val ^ y)
                    + (key_words[p & 3 ^ e] ^ z)
                )
            ) & 0xFFFFFFFF
            y = values[p]
        z = values[n]
        values[0] = (
            values[0]
            - (
                (z >> 5 ^ y << 2)
                + (y >> 3 ^ z << 4)
                ^ (sum_val ^ y)
                + (key_words[e] ^ z)
            )
        ) & 0xFFFFFFFF
        y = values[0]
        sum_val = (sum_val - delta) & 0xFFFFFFFF

    return _long2str(values, True)


# --- NetMod (.nm) ---


def decrypt_netmod_data(data: bytes) -> Optional[str]:
    """Decrypt NetMod VPN Client encrypted config files (.nm) using AES-ECB."""
    if not data:
        return None

    key = _require_env_bytes(
        "HUNTX_NETMOD_KEY",
        "NetMod AES key",
        expected_length=16,
    )

    try:
        content_str = data.decode("utf-8", errors="ignore").strip()
        if "://" in content_str:
            proto, payload = content_str.split("://", 1)
            ciphertext = base64.b64decode(payload)
        else:
            proto = None
            try:
                ciphertext = base64.b64decode(data)
            except Exception:
                ciphertext = data

        if len(ciphertext) % 16 != 0:
            return None

        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_bytes = decryptor.update(ciphertext) + decryptor.finalize()
        decrypted_str = decrypted_bytes.rstrip(b"\x00").decode("utf-8", "ignore")

        if proto:
            return f"{proto}://{decrypted_str}"
        return decrypted_str
    except Exception as exc:
        logger.debug("NetMod decryption failed: %s", exc)
        return None
