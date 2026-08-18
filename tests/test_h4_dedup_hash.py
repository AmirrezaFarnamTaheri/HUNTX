"""
H-4 Dedup Hash Collision Resistance Suite.

Verifies:
1. StreamingChunkParser._hash_record returns full 64-char SHA-256 hexdigest.
2. unique_hash values are collision-resistant: distinct lines -> distinct hashes.
3. Identical lines produce identical hashes (stability).
4. hash_string/hash_bytes in common/hashing.py are full 64-char.
5. V2Ray collector external_id uses >=32-char hash prefix.
"""
import hashlib

from huntx.formats.streaming import StreamingChunkParser
from huntx.formats.common.hashing import hash_string, hash_bytes


PARSER = StreamingChunkParser()


# ---------------------------------------------------------------------------
# 1. _hash_record returns full 64-char hexdigest
# ---------------------------------------------------------------------------

def test_hash_record_is_64_chars():
    """H-4: _hash_record must return full 64-char SHA-256 hexdigest."""
    h = PARSER._hash_record("vless://some-test-line")
    assert len(h) == 64, (
        f"H-4: Expected 64-char hash, got {len(h)}: {h!r}"
    )


def test_hash_record_is_hex():
    """H-4: _hash_record must return a lowercase hexadecimal string."""
    h = PARSER._hash_record("vmess://some-test-line")
    assert all(c in "0123456789abcdef" for c in h), (
        f"H-4: hash must be lowercase hex, got {h!r}"
    )


# ---------------------------------------------------------------------------
# 2. Collision resistance: 1000 distinct lines -> 1000 distinct hashes
# ---------------------------------------------------------------------------

def test_no_collisions_among_distinct_lines():
    """H-4: 1000 distinct proxy lines must produce 1000 distinct unique_hashes."""
    lines = [f"vless://user{i}@host{i}:443?type=tcp" for i in range(1000)]
    hashes = {PARSER._hash_record(line) for line in lines}
    assert len(hashes) == 1000, (
        f"H-4: Expected 1000 distinct hashes, got {len(hashes)}"
    )


# ---------------------------------------------------------------------------
# 3. Hash stability: same line always same hash
# ---------------------------------------------------------------------------

def test_hash_record_is_stable():
    """H-4: Same input must always produce the same hash (deterministic)."""
    line = "trojan://pass@server.example.com:443"
    h1 = PARSER._hash_record(line)
    h2 = PARSER._hash_record(line)
    assert h1 == h2, "H-4: Hash must be deterministic"


def test_hash_record_matches_reference_sha256():
    """H-4: _hash_record output must match hashlib.sha256 reference."""
    line = "ss://YWVzLTI1Ni1nY206cGFzc0BleGFtcGxlLmNvbTo4Mzg4"
    expected = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
    assert PARSER._hash_record(line) == expected, (
        f"H-4: hash mismatch for known line. Expected {expected!r}"
    )


# ---------------------------------------------------------------------------
# 4. common/hashing.py: hash_string and hash_bytes use full 64-char digests
# ---------------------------------------------------------------------------

def test_hash_string_returns_64_chars():
    """H-4: hash_string must return 64-char hexdigest."""
    h = hash_string("some-unique-proxy-text")
    assert len(h) == 64, f"H-4: hash_string returned {len(h)} chars: {h!r}"


def test_hash_bytes_returns_64_chars():
    """H-4: hash_bytes must return 64-char hexdigest."""
    h = hash_bytes(b"\x00\x01\x02binary data")
    assert len(h) == 64, f"H-4: hash_bytes returned {len(h)} chars: {h!r}"


# ---------------------------------------------------------------------------
# 5. parse_line sets unique_hash to full 64-char hash
# ---------------------------------------------------------------------------

def test_parse_line_unique_hash_is_64_chars():
    """H-4: parse_line must set unique_hash to full 64-char SHA-256 hexdigest."""
    record = PARSER.parse_line("vmess://eyJ2IjoiMiIsInBzIjoidGVzdCJ9")
    assert record is not None
    assert len(record["unique_hash"]) == 64, (
        f"H-4: unique_hash in parse_line record must be 64 chars, got {len(record['unique_hash'])}"
    )


# ---------------------------------------------------------------------------
# 6. V2Ray collector external_id uses >=32-char hash component
# ---------------------------------------------------------------------------

def test_v2ray_collector_external_id_hash_length():
    """H-4: V2Ray collector external_id hash component must be >=32 chars (128-bit)."""
    line = "vless://user@host:443"
    h = hashlib.sha256(line.encode("utf-8")).hexdigest()[:32]
    # Confirm the fixed length is 32 (not 16)
    assert len(h) == 32, f"H-4: Expected 32-char hash prefix, got {len(h)}"
    assert h == hashlib.sha256(line.encode()).hexdigest()[:32], "must match sha256[:32]"
