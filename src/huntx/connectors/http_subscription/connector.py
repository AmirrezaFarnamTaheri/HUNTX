"""HTTPS feed investigation integrated with HUNTX's governed ingestion.

Every URL is its own source/state identity. A bad or missing upstream must not
overwrite the last validated observation. No remote content is executed.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..base import AsyncSyncIterator
from .parser import MAX_FEED_BYTES, normalize_feed

logger = logging.getLogger(__name__)
ALLOWED_FEED_HOSTS = frozenset({
    "raw.githubusercontent.com",
    "sub.iampedi5.live",
    "sub.whitedns.one",
    "key.zarazaex.xyz",
})


def validate_public_feed_url(url: str) -> str:
    """Enforce an explicit fixed public HTTPS upstream boundary."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme.lower() != "https" or
            parsed.hostname not in ALLOWED_FEED_HOSTS or
            parsed.username is not None or parsed.password is not None or
            parsed.port not in (None, 443) or parsed.fragment or
            not parsed.path.startswith("/")):
        raise ValueError("HTTP feed must be an approved public HTTPS URL")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # Redirect chains may target local metadata endpoints or a private LAN.
        # Never follow them without an explicit URL added to the source catalog.
        raise ValueError("HTTP subscription redirected; review upstream URL explicitly")


@dataclass(frozen=True)
class SubscriptionObservation:
    external_id: str
    data: bytes
    metadata: dict[str, Any]


class HttpSubscriptionConnector:
    """Fetch a bounded feed and produce two canonical, independently tracked formats."""

    def __init__(self, url: str, *, mode: str = "auto", timeout_seconds: int = 12):
        self.url = validate_public_feed_url(url)
        if mode not in ("auto", "xray_profile_audit"):
            raise ValueError("unsupported HTTP subscription inspection mode")
        if isinstance(timeout_seconds, bool) or not 2 <= timeout_seconds <= 40:
            raise ValueError("timeout_seconds must be between 2 and 40")
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.deadline: float | None = None
        self._state: dict[str, Any] = {}

    def _fetch(self) -> bytes:
        timeout = float(self.timeout_seconds)
        if self.deadline is not None:
            remaining = float(self.deadline) - time.time()
            if remaining <= 0:
                raise TimeoutError("HTTP feed deadline exhausted before fetch")
            timeout = max(0.1, min(timeout, remaining))
        request = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "HUNTX-public-feed-investigator/1.0",
                "Accept": "text/plain, application/json, application/yaml, */*;q=0.5",
                "Accept-Encoding": "identity",
            },
            method="GET",
        )
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError("feed response was not HTTP 200")
                data = response.read(MAX_FEED_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"feed HTTP status {exc.code}") from None
        except urllib.error.URLError as exc:
            raise OSError("feed network request failed") from exc
        if not data or len(data) > MAX_FEED_BYTES:
            raise ValueError("HTTP feed is empty or exceeds byte limit")
        return data

    def list_new(self, state: dict[str, Any] | None = None):
        return AsyncSyncIterator(self._list_new_async(state))

    async def _list_new_async(self, state: dict[str, Any] | None):
        raw = await asyncio.to_thread(self._fetch)
        payload, report = normalize_feed(raw, self.mode)
        self._state = {
            "feed_sha256": hashlib.sha256(raw).hexdigest(),
            "checked_at": int(time.time()),
            "mode": self.mode,
            "report": report,
            "previous_successes": int((state or {}).get("previous_successes", 0)) + 1,
        }
        if self.mode == "xray_profile_audit":
            logger.info(
                "[HTTPS Feed] inspected profile bundle: profiles=%s policy_bound=%s",
                report["profiles"], report["policy_bound_endpoints"],
            )
            return
        if report.get("skipped_incompatible"):
            logger.warning(
                "[HTTPS Feed] skipped incompatible Mihomo entries: count=%s",
                report["skipped_incompatible"],
            )
        hostname = urllib.parse.urlsplit(self.url).hostname or ""
        for format_id, filename in (
            ("npvt", "public-subscription.txt"),
            ("npvtsub", "public-subscription.npvtsub"),
        ):
            yield SubscriptionObservation(
                external_id=f"verified-feed:{format_id}",
                data=payload,
                metadata={
                    "filename": filename,
                    "is_text": True,
                    "origin_type": "http_subscription",
                    "origin_host": hostname,
                    "refresh_unchanged": True,
                    "parsed_nodes": report["nodes"],
                    "input_format": report["kind"],
                },
            )

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)
