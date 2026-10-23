"""Dataset ingestion must validate upstream checksums before publication."""

from __future__ import annotations

import hashlib

import pytest

from scripts import prepare_geoip_data as downloader


def _country_rows() -> bytes:
    return b"5.5.5.0,5.5.5.255,DE\n" * 8


def _asn_rows() -> bytes:
    return b'5.5.5.0,5.5.5.255,64501,"Example Network"\n' * 4


def test_preparation_uses_checksum_verified_country_and_asn_tables(tmp_path, monkeypatch):
    def retrieve(url, limit=downloader._MAX_BYTES):
        name = url.split("/")[-1]
        dataset = _asn_rows() if name.startswith("origin-asn") else _country_rows()
        if name.endswith(".sha256"):
            return hashlib.sha256(dataset).hexdigest().encode("ascii") + b"  " + name[:-7].encode()
        return dataset

    monkeypatch.setattr(downloader, "_retrieve", retrieve)
    result = downloader.prepare_tables(tmp_path)
    assert set(result) == {
        "HUNTX_GEOIP_IPV4_CSV", "HUNTX_GEOIP_IPV6_CSV",
        "HUNTX_ASN_IPV4_CSV", "HUNTX_ASN_IPV6_CSV",
    }
    assert all(path.is_file() for path in result.values())
    assert result["HUNTX_ASN_IPV4_CSV"].read_bytes() == _asn_rows()


def test_checksum_mismatch_blocks_dataset_activation(tmp_path, monkeypatch):
    def invalid(url, limit=downloader._MAX_BYTES):
        if url.endswith(".sha256"):
            return b"a" * 64
        return _country_rows()

    monkeypatch.setattr(downloader, "_retrieve", invalid)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        downloader.prepare_tables(tmp_path, include_asn=False)
    assert not list(tmp_path.glob("*.csv"))


def test_preparation_country_only_skips_asn_inputs(tmp_path, monkeypatch):
    observed = []

    def retrieve(url, limit=downloader._MAX_BYTES):
        observed.append(url)
        if url.endswith(".sha256"):
            return hashlib.sha256(_country_rows()).hexdigest().encode("ascii")
        return _country_rows()

    monkeypatch.setattr(downloader, "_retrieve", retrieve)
    data = downloader.prepare_tables(tmp_path, include_asn=False)
    assert len(data) == 2
    assert all("origin-asn" not in url for url in observed)


def test_malformed_html_is_not_accepted_as_a_country_database():
    assert not downloader._valid_csv(b"<html>upstream error</html>" * 9, expected_columns=3)
