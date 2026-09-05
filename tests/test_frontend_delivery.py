"""Regression checks for the static dashboard delivery contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_frontend_builder():
    spec = importlib.util.spec_from_file_location(
        "update_frontend", ROOT / "scripts" / "update_frontend.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_bundle_matches_frontend_modules() -> None:
    builder = _load_frontend_builder()

    expected = builder.build_bundle_code(ROOT)
    published = (ROOT / "docs" / "assets" / "js" / "bundle.js").read_text(encoding="utf-8")

    assert published == expected


def test_service_worker_uses_network_first_for_deployment_shell() -> None:
    worker = (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")

    assert "const deploymentShell" in worker
    assert "(freshReleaseData || deploymentShell) ? networkFirst(event.request)" in worker
    assert "Promise.allSettled" in worker
    assert "await caches.delete(CACHE_NAME)" in worker
    assert "throw new Error(`[HUNTX-SW] Cache prefetch failed" in worker
    assert "self.skipWaiting()" in worker
    assert "self.clients.claim()" in worker


def test_frontend_verifies_the_catalogued_proxy_artifact() -> None:
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")

    assert "crypto.subtle.digest(\"SHA-256\"" in application
    assert "loadVerifiedJsonArtifact" in application
    assert "getDecodedArtifactRecord" in application


def test_frontend_i18n_supports_requested_locales_and_rtl() -> None:
    i18n = (ROOT / "docs" / "assets" / "js" / "i18n.js").read_text(encoding="utf-8")
    application = (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    for locale in ('"fa"', '"zh-CN"', '"ru"'):
        assert locale in i18n
    assert 'document.documentElement.dir = locale === "fa" ? "rtl" : "ltr"' in i18n
    assert 'new URLSearchParams(globalThis.location?.search || "").get("lang")' in i18n
    assert 'id="language-selector"' in application
    assert "i18n.setLocale" in application
    # Runtime rendering now translates newly inserted subtrees only. Watching every
    # character/attribute mutation caused unnecessary full-document churn on rerenders.
    assert "characterData: true" not in i18n
    assert "attributeFilter:" not in i18n
    assert "childList: true" in i18n
    assert "subtree: true" in i18n
    for key in ("Telemetry Radar", "Live Proxies", "Protocol Studio", "Protocol Inspector", "Artifacts & Feeds", "Germany", "United States", "Iran"):
        assert f'"{key}"' in i18n
    assert 'id="toast-container" role="status" aria-live="polite" aria-atomic="true"' in html


def test_i18n_module_is_included_before_application_module() -> None:
    builder = _load_frontend_builder()

    assert builder.MODULE_ORDER.index("i18n.js") < builder.MODULE_ORDER.index("app.js")
