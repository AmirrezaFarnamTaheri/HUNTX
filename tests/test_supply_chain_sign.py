# Tests for Supply-Chain Cryptographic Signing and Manifest Verification
# Authority: NIST FIPS 180-4 (SHA-256) & Sigstore Manifest Spec
import pytest
from huntx.pipeline.sign import SupplyChainSigner, ManifestVerificationResult

def test_manifest_hash_generation():
    signer = SupplyChainSigner()
    files_payload = {
        "proxies.json": "sample-content-1",
        "proxies.txt": "sample-content-2"
    }
    manifest = signer.generate_manifest(files_payload)
    assert "entries" in manifest
    assert "root_hash" in manifest
    assert manifest["entries"]["proxies.json"]["sha256"] != ""
    assert manifest["entries"]["proxies.txt"]["sha256"] != ""

def test_manifest_signature_and_verification():
    signer = SupplyChainSigner(secret_key="master-signing-key")
    files_payload = {
        "proxies.json": "sample-content-1",
        "proxies_b64sub.txt": "sample-content-sub"
    }
    manifest = signer.generate_manifest(files_payload)
    sig = signer.sign_manifest(manifest)
    assert len(sig) == 64 # HMAC-SHA256 hex length

    # Verify valid signature
    res_valid = signer.verify_manifest(manifest, sig)
    assert isinstance(res_valid, ManifestVerificationResult)
    assert res_valid.is_valid is True

    # Verify invalid signature
    res_tampered = signer.verify_manifest(manifest, "bad_signature_deadbeef")
    assert res_tampered.is_valid is False
