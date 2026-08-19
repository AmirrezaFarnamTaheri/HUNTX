import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from huntx.formats.nm import NmHandler
from huntx.formats.slipnet import SlipNetHandler
from huntx.formats.tut import TutHandler


class TestPortedFormats(unittest.TestCase):
    def test_slipnet_rich_parsing(self):
        handler = SlipNetHandler()

        decrypted = "1|SSH|TestNode|example.com|1.1.1.1|Password|1|US|443|host.com|1"

        with patch("huntx.formats.slipnet.decrypt_slipnet_link", return_value=decrypted):
            link = "slipnet-enc://dummy"
            records = handler.parse(link.encode("utf-8"))

            self.assertEqual(len(records), 1)
            profile = records[0]["data"]["profile"]

            self.assertEqual(profile["Version"], "1")
            self.assertEqual(profile["Tunnel Type/Mode"], "SSH")
            self.assertEqual(profile["Name"], "TestNode")
            self.assertEqual(profile["Domain"], "example.com")
            self.assertEqual(profile["GSO"], True)
            self.assertEqual(profile["KeepAlive"], "1")

    def test_nm_decryption_parsing(self):
        mock_store = MagicMock()
        handler = NmHandler(mock_store)

        decrypted = '{"server": "1.2.3.4", "port": 8080}'

        with patch("huntx.formats.nm.decrypt_netmod_data", return_value=decrypted):
            data = b"encrypted_bytes"
            records = handler.parse(data)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["decrypted"], decrypted)

    def test_nm_real_decryption_integration(self):
        plaintext = b"vless://user@host:443?security=xtls"
        pad_len = 16 - (len(plaintext) % 16)
        padded_plaintext = plaintext + (b"\x00" * pad_len)

        # Integration fixtures use an explicit non-production credential. The
        # decryptor must never depend on a source-visible operational fallback.
        test_key = b"0123456789abcdef"
        cipher = Cipher(algorithms.AES(test_key), modes.ECB(), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

        b64_payload = base64.b64encode(ciphertext).decode("utf-8")
        raw_config = f"nm-vless://{b64_payload}".encode("utf-8")

        mock_store = MagicMock()
        handler = NmHandler(mock_store)

        with patch.dict(os.environ, {"HUNTX_NETMOD_KEY": test_key.decode("ascii")}, clear=False):
            records = handler.parse(raw_config)

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["data"]["decrypted"],
            "nm-vless://vless://user@host:443?security=xtls",
        )

    def test_tut_real_decryption_integration(self):
        plaintext = b"vmess://some-decrypted-config-payload"
        salt = os.urandom(16)
        iv = os.urandom(12)
        test_password = b"test-tut-password"

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=1000,
            backend=default_backend(),
        )
        key = kdf.derive(test_password)

        encryptor = Cipher(
            algorithms.AES(key), modes.GCM(iv), backend=default_backend()
        ).encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        encrypted_blob = ciphertext + encryptor.tag

        salt_b64 = base64.b64encode(salt).decode("utf-8")
        iv_b64 = base64.b64encode(iv).decode("utf-8")
        blob_b64 = base64.b64encode(encrypted_blob).decode("utf-8")
        tut_raw = f"{salt_b64}.{iv_b64}.{blob_b64}".encode("utf-8")

        mock_store = MagicMock()
        handler = TutHandler(mock_store)

        with patch.dict(
            os.environ,
            {"HUNTX_TUT_PASS_TUT": test_password.decode("ascii")},
            clear=False,
        ):
            records = handler.parse(tut_raw)

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["data"]["decrypted"],
            "vmess://some-decrypted-config-payload",
        )


if __name__ == "__main__":
    unittest.main()
