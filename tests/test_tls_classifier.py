# Tests for Python TLS JA4/JA4S Classifier and DPI-Resilience Scorer
# Authority: FoxIO JA4+ Network Fingerprinting Specification: https://github.com/FoxIO-LLC/ja4
import pytest
from huntx.pipeline.tls_classifier import TLSClassifier, TLSProfileScore

def test_ja4s_fingerprint_generation():
    classifier = TLSClassifier()
    # TLS 1.3 (0x0304 -> "13"), ALPN "h2" (first/last char "h2"), 2 extensions
    ciphers = [0x1301] # TLS_AES_128_GCM_SHA256
    extensions = [0x0000, 0x002b] # SNI, Supported Versions
    ja4s = classifier.compute_ja4s("13", "h2", len(extensions), ciphers, extensions)
    assert ja4s.startswith("t13")
    assert "h2" in ja4s
    assert len(ja4s.split("_")) == 3

def test_dpi_resilience_scoring_reality_and_alpn():
    classifier = TLSClassifier()
    node_reality = {
        "protocol": "vless",
        "tls": True,
        "security": "reality",
        "sni": "www.apple.com",
        "alpn": "h2,http/1.1",
        "pbk": "some_pub_key"
    }
    score_reality = classifier.score_node_resilience(node_reality)
    assert isinstance(score_reality, TLSProfileScore)
    assert score_reality.dpi_resilience >= 90 # Reality is highly resilient
    assert score_reality.is_stealth is True

    node_plain_tls = {
        "protocol": "vmess",
        "tls": False,
        "sni": "",
        "alpn": ""
    }
    score_plain = classifier.score_node_resilience(node_plain_tls)
    assert score_plain.dpi_resilience <= 30 # Plaintext is easily DPI-blocked
    assert score_plain.is_stealth is False
