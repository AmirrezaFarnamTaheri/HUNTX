"""Supply-Chain Cryptographic Signing & Manifest Verification.

Authority:
    NIST FIPS 180-4 (Secure Hash Standard): https://csrc.nist.gov/publications/detail/fips/180/4/final
    Sigstore Bundle & Cosign Specification: https://github.com/sigstore/cosign
"""
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class ManifestVerificationResult:
    """Outcome of manifest cryptographic validation."""
    is_valid: bool
    root_hash: str
    error_message: Optional[str] = None

class SupplyChainSigner:
    """Generates cryptographic root digests and validates release payload integrity."""

    def __init__(self, secret_key: str = "huntx-default-signing-key"):
        self.secret_key = secret_key.encode("utf-8")

    def generate_manifest(self, files: Dict[str, Any]) -> Dict[str, Any]:
        """Compute SHA-256 digests for all files and derive a deterministic root hash."""
        entries: Dict[str, Any] = {}
        sorted_keys = sorted(files.keys())

        for name in sorted_keys:
            val = files[name]
            content_bytes = val.encode("utf-8") if isinstance(val, str) else json.dumps(val, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(content_bytes).hexdigest()
            entries[name] = {
                "sha256": digest,
                "size_bytes": len(content_bytes)
            }

        # Merkle-like root hash over sorted entry digests
        root_input = "".join(f"{k}:{entries[k]['sha256']}" for k in sorted_keys)
        root_hash = hashlib.sha256(root_input.encode("utf-8")).hexdigest()

        return {
            "version": "1.0",
            "root_hash": root_hash,
            "entries": entries
        }

    def sign_manifest(self, manifest: Dict[str, Any]) -> str:
        """Create HMAC-SHA256 signature for the manifest root hash."""
        root_hash = manifest.get("root_hash", "")
        return hmac.new(self.secret_key, root_hash.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_manifest(self, manifest: Dict[str, Any], signature: str) -> ManifestVerificationResult:
        """Verify the cryptographic authenticity of a manifest signature."""
        expected_sig = self.sign_manifest(manifest)
        if hmac.compare_digest(expected_sig, signature):
            return ManifestVerificationResult(
                is_valid=True,
                root_hash=manifest.get("root_hash", "")
            )
        return ManifestVerificationResult(
            is_valid=False,
            root_hash=manifest.get("root_hash", ""),
            error_message="Signature mismatch or tampered payload"
        )
