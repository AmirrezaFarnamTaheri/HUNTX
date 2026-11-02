"""Country/ASN attribution must be tied to one upstream release asset digest.

The separately updated 'checksum' release is not an authoritative digest
for the independently refreshed 'latest' release. Never disable verification.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from scripts import prepare_geoip_data as downloader


def _country_rows() -> bytes:
    return b"5.5.5.0,5.5.5.255,DE\n" * 8


def _asn_rows() -> bytes:
    return b'5.5.5.0,5.5.5.255,64501,"Example Network"\n' * 4


def _datasets() -> dict[str, bytes]:
    return {
        "server-country-ipv4.csv": _country_rows(),
        "server-country-ipv6.csv": _country_rows(),
        "origin-asn-ipv4.csv": _asn_rows(),
        "origin-asn-ipv6.csv": _asn_rows(),
    }


def _release(datasets: dict[str, bytes]) -> bytes:
    return json.dumps({
        "tag_name": "latest",
        "assets": [
            {
                "name": name,
                "size": len(payload),
                "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "browser_download_url": f"{downloader._BASE}/latest/{name}",
            }
            for name, payload in datasets.items()
        ],
    }).encode("utf-8")


def test_preparation_uses_same_release_asset_digest_not_stale_checksum(
    tmp_path, monkeypatch
):
    datasets = _datasets()
    fetched = []

    def retrieve(url, limit=downloader._MAX_BYTES):
        fetched.append(url)
        if url == downloader._RELEASE_API:
            return _release(datasets)
        assert "/releases/download/latest/" in url
        assert not url.endswith(".sha256")
        return datasets[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(downloader, "_retrieve", retrieve)
    result = downloader.prepare_tables(tmp_path)
    assert set(result) == {
        "HUNTX_GEOIP_IPV4_CSV", "HUNTX_GEOIP_IPV6_CSV",
        "HUNTX_ASN_IPV4_CSV", "HUNTX_ASN_IPV6_CSV",
    }
    assert fetched.count(downloader._RELEASE_API) == 1
    assert len(fetched) == 5
    assert all(path.is_file() for path in result.values())
    assert result["HUNTX_ASN_IPV4_CSV"].read_bytes() == _asn_rows()


def test_mismatched_asset_content_refuses_activation_and_preserves_old(
    tmp_path, monkeypatch
):
    datasets = _datasets()
    original = tmp_path / "server-country-ipv4.csv"
    original.write_bytes(b"previous verified country data")

    def retrieve(url, limit=downloader._MAX_BYTES):
        if url == downloader._RELEASE_API:
            return _release(datasets)
        name = url.rsplit("/", 1)[-1]
        if name == "server-country-ipv6.csv":
            return b"5.5.5.0,5.5.5.255,ZZ\n" * 8
        return datasets[name]

    monkeypatch.setattr(downloader, "_retrieve", retrieve)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        downloader.prepare_tables(tmp_path, include_asn=False)
    assert original.read_bytes() == b"previous verified country data"
    assert not (tmp_path / "server-country-ipv6.csv").exists()


def test_incomplete_or_ambiguous_release_metadata_fails_closed(
    tmp_path, monkeypatch
):
    datasets = _datasets()

    def run(metadata):
        monkeypatch.setattr(
            downloader, "_retrieve",
            lambda url, limit=downloader._MAX_BYTES: metadata
            if url == downloader._RELEASE_API else datasets[url.rsplit("/", 1)[-1]],
        )
        with pytest.raises(ValueError, match="release|digest|metadata|ambiguous"):
            downloader.prepare_tables(tmp_path, include_asn=False)

    objects = json.loads(_release(datasets))
    objects["assets"][0]["digest"] = None
    run(json.dumps(objects).encode())
    objects = json.loads(_release(datasets))
    objects["assets"].append(dict(objects["assets"][0]))
    run(json.dumps(objects).encode())
    objects = json.loads(_release(datasets))
    objects["assets"][0]["browser_download_url"] = "https://untrusted.invalid/geo.csv"
    run(json.dumps(objects).encode())
    assert not list(tmp_path.glob("*.csv"))


def test_preparation_country_only_never_downloads_asn(tmp_path, monkeypatch):
    datasets = _datasets()
    observed = []

    def retrieve(url, limit=downloader._MAX_BYTES):
        observed.append(url)
        return (_release(datasets) if url == downloader._RELEASE_API
                else datasets[url.rsplit("/", 1)[-1]])

    monkeypatch.setattr(downloader, "_retrieve", retrieve)
    data = downloader.prepare_tables(tmp_path, include_asn=False)
    assert len(data) == 2
    assert observed.count(downloader._RELEASE_API) == 1
    assert all("origin-asn" not in url for url in observed)


def test_malformed_html_is_not_accepted_as_a_country_database():
    assert not downloader._valid_csv(
        b"<html>upstream error</html>" * 9, expected_columns=3,
    )
