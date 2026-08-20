from __future__ import annotations

import base64

from huntx.formats.npvt import NpvtHandler
from huntx.formats.npvtsub import NpvtSubHandler


def test_npvtsub_rejects_malformed_recognized_scheme_like_npvt():
    malformed = b"vless://not-a-uuid@example.com:443\nvmess://not-base64\n"

    assert NpvtHandler().parse(malformed, {}) == []
    assert NpvtSubHandler().parse(malformed, {}) == []


def test_npvtsub_accepts_authenticated_http_proxy_via_shared_validator():
    payload = b"https://user:password@example.com:8443#edge\n"
    records = NpvtSubHandler().parse(payload, {})

    assert len(records) == 1
    assert records[0]["data"]["line"] == "https://user:password@example.com:8443"


def test_npvtsub_base64_path_has_same_validation_contract():
    valid = "trojan://secret@example.com:443"
    malformed = "vless://not-a-uuid@example.com:443"
    encoded = base64.b64encode(f"{valid}\n{malformed}\n".encode())

    records = NpvtSubHandler().parse(encoded, {})

    assert [record["data"]["line"] for record in records] == [valid]
