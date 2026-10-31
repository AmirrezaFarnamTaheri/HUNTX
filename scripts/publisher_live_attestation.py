"""Publication-time proxy authentication receipt. See issue #182."""
from __future__ import annotations


def build_attestation(*args, **kwargs):
    raise NotImplementedError("last-mile publisher HTTPS authentication is missing")


def verify_attestation(*args, **kwargs):
    raise NotImplementedError("publication-time proof validation is missing")
