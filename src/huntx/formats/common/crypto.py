import base64
import json
import logging
import struct
import urllib.parse
from typing import Dict, Optional, Tuple
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

# --- HA Tunnel Plus (happ://) ---

HAPP_KEYS_PEM = {
    "crypt": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIICXwIBAAKBgQCxsS7PUq1biQlVD92rf6eXKr9oG1/SrYx3qWahZP+Jq35m4Wb/\n"
        "Z+mB6eBWrPzJ/zZpZLWLQorcvOKt+sLaCHyH1HLNkti4jlaEQX6x97XgBm8GK08+\n"
        "lLLWquFDhWRNxsrfzJyNdpVopzBRmCJKTc8ObYyPbrv9T35a8Kd5WqjnUwIDAQAB\n"
        "AoGBAJoqe85skPPF5U7jwRM2YhUJhZ+xgGWtJR3834pPslWjcLuZ/F7DrRiF7ZnF\n"
        "5FztDCxMsCXuycPSLWl9EulQS5mrL/fnwpK2jVE8O1Em9RsBOOrWwzuZnAuooRIb\n"
        "/8zC0fvH2oGkk60zSKycMe69uvYUDjhvULX2Spjmf9CS9/HhAkEA3I797En/DrpA\n"
        "Zz6NM4GqZ1mkH0kEX/kAHLP1lBgYL1kVK455EG/ecJkMJmtK7A+fWw0N0IcxrpYA\n"
        "bbOAo19vjwJBAM4+0MAZ8TIZUk6Rs2gYUo04A6mYUy5MWtRa9pyFIgD71oHDR+1j\n"
        "rnPLqQyCj0tfbZBc1iVgsisJBpocC8sKaf0CQQDRNd3Mxb/nY2p1xJLBmaxezlvs\n"
        "xSEePB4MG/PFXzmJqBF5uHJD0imIWtR4mOt/ka4R+wbwl1zcAzMy28MYtQ0nAkEA\n"
        "uUILWML0uL+uAw01TeerH1aVU52T+h5z6BPdOTMNHD0arWywCzhi13i03JvaAyYw\n"
        "0F/Tq7dz0txEpeFTZopwMQJBANnHbzB87/xTjDQA4/L8sSU8m0vM1nRWmJIaAC94\n"
        "pcM+KDGLnbBhWrvZGy8Zg8vQwNvdvCLvylk0jVTTFqW3ibM=\n"
        "-----END RSA PRIVATE KEY-----"
    ),
    "crypt2": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "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\n"
        "-----END RSA PRIVATE KEY-----"
    ),
    "crypt3": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "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\n"
        "-----END RSA PRIVATE KEY-----"
    ),
}

_HAPP_KEYS_CACHE = {}

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
        s0, m0 = 0x1c8986f91dd8ec9a, 0x557034dc3ddda3bb
        s1, m1 = 0xc70a4a42712024ee, 0x6f5577ae58747e8e
        s2, m2 = 0x924d4af0d8a43e0b, 0xfcd9e79819861e07
        s3, m3 = 0x4a5573b012f4d08b, 0x998e67c256d955e3
        
        key = struct.pack("<QQQQ", s0 ^ m0, s1 ^ m1, s2 ^ m2, s3 ^ m3)
        
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
        # AES-GCM tag is usually the last 16 bytes of ciphertext in many impls, 
        # but subtle-crypto (JS) appends it.
        # decrypt = cipher.decryptor()
        # decrypted = decrypt.update(ciphertext[:-16]) + decrypt.finalize_with_tag(ciphertext[-16:])
        
        # NOTE: cryptography requires the tag separately. JS's decrypt combines them.
        tag = ciphertext[-16:]
        actual_ciphertext = ciphertext[:-16]
        
        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend()
        ).decryptor()
        
        return (decryptor.update(actual_ciphertext) + decryptor.finalize()).decode("utf-8")
    except Exception as e:
        logger.debug(f"SlipNet decryption failed: {e}")
        return None

# --- TutDecryptor (.tut, .sks, .tmt) ---

TUT_PASSWORDS = {
    ".tut": b"fubvx788b46v",
    ".sks": b"dyv35224nossas!!",
    ".tmt": b"fubvx788B4mev",
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
            iterations=1000, # Default for PBKDF2 in pycryptodome if not specified? 
            # Actually decrypt.py uses PBKDF2 from pycryptodome. 
            # Looking at decrypt.py again: PBKDF2(PASSWORDS[file_ext], split_contents[0], hmac_hash_module=SHA256)
            # Default iterations in pycryptodome PBKDF2 is 1000.
            backend=default_backend()
        )
        key = kdf.derive(TUT_PASSWORDS[extension])
        
        # AES-GCM decryption. Decrypt.py: split_contents[2][:-16] is data, last 16 is tag
        tag = encrypted[-16:]
        ciphertext = encrypted[:-16]
        
        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend()
        ).decryptor()
        
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
    sum_val = (q * delta) & 0xffffffff
    
    while sum_val != 0:
        e = (sum_val >> 2) & 3
        for p in range(n, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4) ^ (sum_val ^ y) + (k[p & 3 ^ e] ^ z))) & 0xffffffff
            y = v[p]
        z = v[n]
        v[0] = (v[0] - ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4) ^ (sum_val ^ y) + (k[0 & 3 ^ e] ^ z))) & 0xffffffff
        y = v[0]
        sum_val = (sum_val - delta) & 0xffffffff
        
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
        
    key = b"_netsyna_netmod_"
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

