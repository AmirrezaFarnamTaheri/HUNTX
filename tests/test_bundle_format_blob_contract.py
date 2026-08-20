from __future__ import annotations

import hashlib
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from huntx.formats.hat import HatHandler
from huntx.formats.npv4 import Npv4Handler
from huntx.formats.sks import SksHandler
from huntx.formats.tmt import TmtHandler
from huntx.formats.tut import TutHandler
from huntx.state import StateRepo


@pytest.mark.parametrize(
    ("handler_type", "patch_target", "extension"),
    [
        (TutHandler, "huntx.formats.tut.decrypt_tut_data", ".tut"),
        (SksHandler, "huntx.formats.sks.decrypt_tut_data", ".sks"),
        (TmtHandler, "huntx.formats.tmt.decrypt_tut_data", ".tmt"),
        (Npv4Handler, "huntx.formats.npv4.decrypt_tut_data", ".npv4"),
        (HatHandler, "huntx.formats.hat.decrypt_tut_data", ".hat"),
    ],
)
def test_deep_parsed_bundle_formats_preserve_buildable_raw_blob_contract(
    handler_type,
    patch_target,
    extension,
):
    raw = ("profile.example." + "x" * 80).encode()
    digest = hashlib.sha256(raw).hexdigest()
    raw_store = MagicMock()
    raw_store.get.return_value = raw
    handler = handler_type(raw_store)

    with patch(patch_target, return_value="decrypted-profile"):
        records = handler.parse(raw, {"filename": f"profile{extension}"})

    assert len(records) == 1
    data = records[0]["data"]
    assert records[0]["unique_hash"] == digest
    assert data["blob_hash"] == digest
    assert data["size"] == len(raw)
    assert data["filename"] == f"profile{extension}"

    artifact = handler.build(records)
    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        assert archive.read(f"profile{extension}") == raw


def test_hat_happ_enrichment_preserves_raw_blob_and_supports_base64_alphabet():
    link = "happ://crypt/AbCdEf0123+/=="
    raw = f"prefix {link} suffix".encode()
    digest = hashlib.sha256(raw).hexdigest()
    raw_store = MagicMock()
    raw_store.get.return_value = raw
    handler = HatHandler(raw_store)

    with patch("huntx.formats.hat.decrypt_happ_link", return_value="decrypted") as decrypt:
        records = handler.parse(raw, {"filename": "profile.hat"})

    decrypt.assert_called_once_with(link)
    assert records[0]["unique_hash"] == digest
    assert records[0]["data"]["blob_hash"] == digest
    assert records[0]["data"]["happ_links"] == [
        {"line": link, "decrypted": "decrypted"}
    ]


@pytest.mark.parametrize("format_id", ["tut", "sks", "tmt", "hat", "npv4"])
def test_deep_bundle_formats_are_protected_from_raw_blob_pruning(format_id):
    assert format_id in StateRepo._BLOB_DEPENDENT_FORMATS
