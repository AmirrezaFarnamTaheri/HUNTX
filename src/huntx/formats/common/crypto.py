import base64
import logging
import struct
import urllib.parse
import os
from typing import Any, Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

# --- HA Tunnel Plus (happ://) ---

HAPP_KEYS_PEM = {
    "crypt": os.getenv("HUNTX_HAPP_CRYPT_PEM") or "",
    "crypt2": os.getenv("HUNTX_HAPP_CRYPT2_PEM") or "",
    "crypt3": os.getenv("HUNTX_HAPP_CRYPT3_PEM") or "",
}

# Resolve local keys folder if present
for k in ["crypt", "crypt2", "crypt3"]:
    if not HAPP_KEYS_PEM[k]:
        key_path = os.path.join("persist", "keys", f"happ_{k}.pem")
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    HAPP_KEYS_PEM[k] = f.read()
            except Exception as e:
                logger.warning(f"Could not read HAPP key file {key_path}: {e}")

_HAPP_KEYS_CACHE: dict[str, Any] = {}


def _get_happ_keys():
    if not _HAPP_KEYS_CACHE:
        for k, pem in HAPP_KEYS_PEM.items():
            try:
                _HAPP_KEYS_CACHE[k] = serialization.load_pem_private_key(
                    pem.encode(), password=None, backend=default_backend()
                )
            except Exception as e:
                logger.error(f"Failed to load HAPP key {k}: {e}")
    return _HAPP_KEYS_CACHE


def decrypt_happ_link(link_str: str) -> Optional[str]:
    """Decrypt a happ:// link using RSA-PKCS1v15."""
    decoded_text = urllib.parse.unquote(link_str)
    version = None
    prefix = ""
    for v in ["crypt3", "crypt2", "crypt"]:
        p = f"happ://{v}/"
        if p in decoded_text:
            version = v
            prefix = p
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
    except Exception as e:
        logger.debug(f"HAPP decryption failed for {version}: {e}")
        return None


# --- SlipNet (slipnet-enc://) ---


def decrypt_slipnet_link(link_str: str) -> Optional[str]:
    """Decrypt a slipnet-enc:// link using AES-256-GCM."""
    if not link_str.startswith("slipnet-enc://"):
        return None

    try:
        b64_payload = link_str.replace("slipnet-enc://", "").strip()
        # Handle URL-safe base64 and padding
        b64_payload = b64_payload.replace("-", "+").replace("_", "/")
        while len(b64_payload) % 4 != 0:
            b64_payload += "="

        payload = base64.b64decode(b64_payload)
        if len(payload) < 13:
            return None

        version = payload[0]
        if version != 0x01:
            return None

        iv = payload[1:13]
        ciphertext = payload[13:]

        # Key assembly via XOR (from Slipnet decoder.html)
        s0, m0 = 0x1C8986F91DD8EC9A, 0x557034DC3DDDA3BB
        s1, m1 = 0xC70A4A42712024EE, 0x6F5577AE58747E8E
        s2, m2 = 0x924D4AF0D8A43E0B, 0xFCD9E79819861E07
        s3, m3 = 0x4A5573B012F4D08B, 0x998E67C256D955E3

        key = struct.pack("<QQQQ", s0 ^ m0, s1 ^ m1, s2 ^ m2, s3 ^ m3)

        # NOTE: cryptography requires the tag separately. JS's decrypt combines them.
        tag = ciphertext[-16:]
        actual_ciphertext = ciphertext[:-16]

        decryptor = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend()).decryptor()

        return (decryptor.update(actual_ciphertext) + decryptor.finalize()).decode("utf-8")
    except Exception as e:
        logger.debug(f"SlipNet decryption failed: {e}")
        return None


# --- TutDecryptor (.tut, .sks, .tmt) ---

TUT_PASSWORDS = {
    ".tut": os.getenv("HUNTX_TUT_PASS_TUT", "").encode() or b"fubvx788b46v",
    ".sks": os.getenv("HUNTX_TUT_PASS_SKS", "").encode() or b"dyv35224nossas!!",
    ".tmt": os.getenv("HUNTX_TUT_PASS_TMT", "").encode() or b"fubvx788B4mev",
}


def decrypt_tut_data(data_str: str, extension: str = ".tmt") -> Optional[str]:
    """Decrypt .tut/.sks/.tmt file content using PBKDF2 + AES-GCM."""
    if extension not in TUT_PASSWORDS:
        extension = ".tmt"

    try:
        parts = data_str.strip().split(".")
        if len(parts) != 3:
            return None

        salt, iv, encrypted = [base64.b64decode(p) for p in parts]

        # Key derivation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=1000,  # Default for PBKDF2 in pycryptodome if not specified?
            # Actually decrypt.py uses PBKDF2 from pycryptodome.
            # Looking at decrypt.py again: PBKDF2(PASSWORDS[file_ext], split_contents[0], hmac_hash_module=SHA256)
            # Default iterations in pycryptodome PBKDF2 is 1000.
            backend=default_backend(),
        )
        key = kdf.derive(TUT_PASSWORDS[extension])

        # AES-GCM decryption. Decrypt.py: split_contents[2][:-16] is data, last 16 is tag
        tag = encrypted[-16:]
        ciphertext = encrypted[:-16]

        decryptor = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend()).decryptor()

        return (decryptor.update(ciphertext) + decryptor.finalize()).decode("utf-8")
    except Exception as e:
        logger.debug(f"TUT decryption failed: {e}")
        return None


# --- XXTEA with custom Delta (from vpndecrypt-Lol) ---


def decrypt_xxtea(data: bytes, key: bytes, delta: int) -> bytes:
    """
    XXTEA decryption with support for custom Delta.
    Ported from vpndecrypt-Lol.
    """
    if not data:
        return b""

    def _str2long(s, w):
        n = len(s)
        m = (4 - (n & 3) & 3) + n
        s = s.ljust(m, b"\0")
        v = list(struct.unpack("<%iL" % (m >> 2), s))
        if w:
            v.append(n)
        return v

    def _long2str(v, w):
        n = (len(v) - 1) * 4
        if w:
            m = v[-1]
            if (m < n - 3) or (m > n):
                return b""
            n = m
        s = struct.pack("<%iL" % len(v), *v)
        return s[0:n] if w else s

    v = _str2long(data, False)
    # Key must be 16 bytes
    k = _str2long(key.ljust(16, b"\0")[:16], False)

    n = len(v) - 1
    if n < 1:
        return data

    z = v[n]
    y = v[0]
    q = 6 + 52 // (n + 1)
    sum_val = (q * delta) & 0xFFFFFFFF

    while sum_val != 0:
        e = (sum_val >> 2) & 3
        for p in range(n, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4) ^ (sum_val ^ y) + (k[p & 3 ^ e] ^ z))) & 0xFFFFFFFF
            y = v[p]
        z = v[n]
        v[0] = (v[0] - ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4) ^ (sum_val ^ y) + (k[0 & 3 ^ e] ^ z))) & 0xFFFFFFFF
        y = v[0]
        sum_val = (sum_val - delta) & 0xFFFFFFFF

    return _long2str(v, True)


# --- NetMod (.nm) ---


def decrypt_netmod_data(data: bytes) -> Optional[str]:
    """
    Decrypt NetMod VPN Client encrypted config files (.nm) using AES-ECB.
    Key: _netsyna_netmod_
    Fully aligned with netmod.go in Pantegnos-main (the source of truth).
    """
    if not data:
        return None

    key_env = os.getenv("HUNTX_NETMOD_KEY")
    key = key_env.encode() if key_env else b"_netsyna_netmod_"
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
    except Exception as e:
        logger.debug(f"NetMod decryption failed: {e}")
        return None
