"""Supply-Chain Cryptographic Signing & Manifest Verification.

Authority:
    NIST FIPS 180-4 (Secure Hash Standard): https://csrc.nist.gov/publications/detail/fips/180/4/final
    Sigstore Bundle & Cosign Specification: https://github.com/sigstore/cosign
"""
import hashlib
import hmac
import json
import os
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

    def __init__(self, secret_key: Optional[str] = None):
        secret_key = secret_key or os.environ.get("HUNTX_SIGNING_KEY")
        if not secret_key:
            raise ValueError("HUNTX_SIGNING_KEY or an explicit signing key is required")
        self.secret_key = secret_key.encode("utf-8")

    @staticmethod
    def _root_hash(entries: Dict[str, Any]) -> str:
        """Return the deterministic manifest root for validated entry metadata."""
        if not isinstance(entries, dict):
            raise ValueError("Manifest entries must be a mapping")
        parts = []
        for name in sorted(entries):
            entry = entries[name]
            if not isinstance(name, str) or not isinstance(entry, dict):
                raise ValueError("Malformed manifest entry")
            digest = entry.get("sha256")
            size = entry.get("size_bytes")
            if not isinstance(digest, str) or len(digest) != 64 or not isinstance(size, int) or size < 0:
                raise ValueError("Malformed manifest entry metadata")
            parts.append(f"{name}:{digest}:{size}")
        return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()

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
        root_hash = self._root_hash(entries)

        return {
            "version": "1.0",
            "root_hash": root_hash,
            "entries": entries
        }

    def sign_manifest(self, manifest: Dict[str, Any]) -> str:
        """Create HMAC-SHA256 signature for the manifest root hash."""
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hmac.new(self.secret_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_manifest(self, manifest: Dict[str, Any], signature: str) -> ManifestVerificationResult:
        """Verify the cryptographic authenticity of a manifest signature."""
        root_hash = manifest.get("root_hash", "") if isinstance(manifest, dict) else ""
        try:
            computed_root = self._root_hash(manifest.get("entries", {}))
        except (AttributeError, ValueError) as exc:
            return ManifestVerificationResult(False, root_hash, str(exc))
        if not hmac.compare_digest(computed_root, root_hash):
            return ManifestVerificationResult(False, root_hash, "Manifest root does not match entries")
        expected_sig = self.sign_manifest(manifest)
        if hmac.compare_digest(expected_sig, signature):
            return ManifestVerificationResult(
                is_valid=True,
                root_hash=root_hash
            )
        return ManifestVerificationResult(
            is_valid=False,
            root_hash=root_hash,
            error_message="Signature mismatch or tampered payload"
        )
