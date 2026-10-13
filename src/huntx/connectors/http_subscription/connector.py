"""Go-backed public HTTPS feed connector for HUNTX's governed state pipeline."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from ..base import AsyncSyncIterator
from ...core.source_reliability import append_retrieval_observation
from .parser import MAX_FEED_BYTES, normalize_feed

logger = logging.getLogger(__name__)
ALLOWED_FEED_HOSTS = frozenset({
    "raw.githubusercontent.com",
    "sub.iampedi5.live",
    "sub.whitedns.one",
    "key.zarazaex.xyz",
})


class GoFeedWorkerUnavailable(FileNotFoundError):
    """A local execution dependency failed; this is not an upstream feed failure."""


def validate_public_feed_url(url: str) -> str:
    """Enforce one fixed HTTPS origin per public subscription source."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme.lower() != "https" or
            parsed.hostname not in ALLOWED_FEED_HOSTS or
            parsed.username is not None or parsed.password is not None or
            parsed.port not in (None, 443) or parsed.fragment or
            not parsed.path.startswith("/")):
        raise ValueError("HTTP feed must be an approved public HTTPS URL")
    return url


def _engine_path() -> str:
    configured = os.environ.get("HUNTX_ENGINE_BIN", "").strip()
    if configured:
        resolved = Path(configured).expanduser()
        if not resolved.is_file():
            raise GoFeedWorkerUnavailable("configured Go engine binary does not exist")
        return str(resolved)
    binary = "huntx-engine.exe" if os.name == "nt" else "huntx-engine"
    local = Path(__file__).resolve().parents[4] / ".bin" / binary
    if local.is_file():
        return str(local)
    installed = shutil.which(binary)
    if installed:
        return installed
    raise GoFeedWorkerUnavailable(
        "Go feed network worker is unavailable; build: "
        "go build -o .bin/huntx-engine ./cmd/huntx-engine"
    )


@dataclass(frozen=True)
class SubscriptionObservation:
    external_id: str
    data: bytes
    metadata: dict[str, Any]


class HttpSubscriptionConnector:
    """Go fetches; Python validates node semantics and commits durable observations."""

    def __init__(
        self,
        url: str,
        *,
        mode: str = "auto",
        timeout_seconds: int = 12,
        raw_store: Any = None,
    ):
        self.url = validate_public_feed_url(url)
        if mode not in ("auto", "xray_profile_audit"):
            raise ValueError("unsupported HTTP subscription inspection mode")
        if isinstance(timeout_seconds, bool) or not 2 <= timeout_seconds <= 40:
            raise ValueError("timeout_seconds must be between 2 and 40")
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.raw_store = raw_store
        self.deadline: float | None = None
        self._state: dict[str, Any] = {}
        self._previous: dict[str, Any] = {}
        self._fetch_headers: dict[str, str] = {}
        self._revalidated = False

    def _cached_payload(self) -> bytes | None:
        """Use the content-addressed raw store; never persist feed credentials in state."""
        if self.mode != "auto" or self.raw_store is None:
            return None
        url_hash = hashlib.sha256(self.url.encode("utf-8")).hexdigest()
        if self._previous.get("url_sha256") != url_hash:
            return None
        fingerprint = self._previous.get("normalized_sha256")
        if (not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in fingerprint)):
            return None
        try:
            cached = self.raw_store.get(fingerprint)
        except (OSError, ValueError, KeyError):
            return None
        if (
            not isinstance(cached, bytes)
            or not cached
            or len(cached) > MAX_FEED_BYTES
            or hashlib.sha256(cached).hexdigest() != fingerprint
        ):
            return None
        return cached

    def _fetch(self) -> bytes:
        """Run a bounded Go subprocess; never echo its stdout/stderr into logs."""
        cached = self._cached_payload()
        timeout = float(self.timeout_seconds)
        if self.deadline is not None:
            remaining = float(self.deadline) - time.time()
            if remaining <= 0:
                raise TimeoutError("HTTP feed deadline elapsed before fetch")
            timeout = min(timeout, remaining)
        cmd = [
            _engine_path(),
            "feed-fetch", "--request-stdin", "--timeout", f"{max(1., timeout):.2f}s",
        ]
        request: dict[str, str] = {"url": self.url}
        if cached is not None:
            for name in ("etag", "last_modified"):
                value = self._previous.get(name)
                if isinstance(value, str) and 0 < len(value) <= 512:
                    request[name] = value
        stdin_payload = json.dumps(request, separators=(",", ":")).encode("utf-8")

        try:
            result = subprocess.run(
                cmd, input=stdin_payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=max(2.0, timeout + 3.0),
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("Go feed fetch exceeded the permitted time budget") from exc
        if result.returncode:
            raise OSError("Go network fetcher rejected or failed this source")
        if len(result.stdout) > 4 * MAX_FEED_BYTES:
            raise ValueError("Go fetch envelope exceeds permitted bytes")
        try:
            response = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid Go fetch response envelope") from exc
        if not isinstance(response, dict):
            raise ValueError("invalid Go fetch response type")
        self._fetch_headers = {
            field: str(response.get(field, ""))
            for field in ("etag", "last_modified")
        }
        if response.get("status") == "not_modified":
            if cached is None:
                raise ValueError("conditional response has no verified local cache")
            self._revalidated = True
            return cached
        if response.get("status") != "ok":
            raise ValueError("Go fetch returned unsupported result")
        encoded = response.get("content_b64")
        if not isinstance(encoded, str):
            raise ValueError("Go fetch response lacks content")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid Go feed base64 envelope") from exc
        if not raw or len(raw) > MAX_FEED_BYTES or response.get("bytes") != len(raw):
            raise ValueError("inconsistent Go feed byte count")
        self._revalidated = False
        return raw

    def list_new(self, state: dict[str, Any] | None = None):
        return AsyncSyncIterator(self._list_new_async(state))

    async def _list_new_async(self, state: dict[str, Any] | None):
        self._previous = dict(state or {})
        self._fetch_headers = {}
        self._revalidated = False
        raw = await asyncio.to_thread(self._fetch)
        payload, report = normalize_feed(raw, self.mode)
        now = int(time.time())
        raw_digest = (
            self._previous.get("feed_sha256")
            if self._revalidated
            else hashlib.sha256(raw).hexdigest()
        )
        changed = raw_digest != self._previous.get("feed_sha256")
        self._state = {
            "feed_sha256": raw_digest,
            "url_sha256": hashlib.sha256(self.url.encode("utf-8")).hexdigest(),
            "normalized_sha256": hashlib.sha256(payload).hexdigest() if payload else "",
            "checked_at": now,
            "first_seen_at": self._previous.get("first_seen_at") or now,
            "last_changed_at": now if changed else self._previous.get("last_changed_at", now),
            "previous_successes": int(self._previous.get("previous_successes", 0)) + 1,
            "last_success_at": now,
            "total_failures": int(self._previous.get("total_failures", 0)),
            "consecutive_failures": 0,
            "last_failed_at": self._previous.get("last_failed_at"),
            "last_error_type": "",
            "last_node_count": int(report.get("nodes", 0)),
            "node_count_delta": (
                int(report.get("nodes", 0)) -
                int(self._previous.get("last_node_count", 0))
            ),
            "etag": (
                self._previous.get("etag", "") if self._revalidated
                else self._fetch_headers.get("etag", "")
            ),
            "last_modified": (
                self._previous.get("last_modified", "") if self._revalidated
                else self._fetch_headers.get("last_modified", "")
            ),
            "revalidated": self._revalidated,
            "mode": self.mode,
            "report": report,
            "retrieval_history": append_retrieval_observation(
                self._previous, success=True, now=now,
                nodes=int(report.get("nodes", 0)), cache_revalidated=self._revalidated,
            ),
        }
        if self.mode == "xray_profile_audit":
            logger.info(
                "[HTTPS Feed] inspected profile bundle: profiles=%s policy_bound=%s",
                report["profiles"], report["policy_bound_endpoints"],
            )
            return
        if report.get("skipped_incompatible"):
            logger.warning(
                "[HTTPS Feed] skipped lossy Mihomo entries: count=%s",
                report["skipped_incompatible"],
            )
        hostname = urllib.parse.urlsplit(self.url).hostname or ""
        for fmt, filename in (
            ("npvt", "public-subscription.txt"),
            ("npvtsub", "public-subscription.npvtsub"),
        ):
            yield SubscriptionObservation(
                external_id=f"verified-feed:{fmt}",
                data=payload,
                metadata={
                    "filename": filename,
                    "is_text": True,
                    "origin_type": "http_subscription",
                    "origin_host": hostname,
                    "refresh_unchanged": True,
                    "observation_health": "syntax_validated",
                    "parsed_nodes": report["nodes"],
                    "input_format": report["kind"],
                    "cache_revalidated": self._revalidated,
                },
            )

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)
