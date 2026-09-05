from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one occurrence, found {count}")
    return text.replace(old, new, 1)


def replace_all_required(text: str, old: str, new: str, label: str, minimum: int = 1) -> str:
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(f"{label}: expected at least {minimum} occurrence(s), found {count}")
    return text.replace(old, new)


def sub_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return updated


def run(*args: str, cwd: str | None = None) -> None:
    subprocess.run(args, cwd=ROOT / cwd if cwd else ROOT, check=True)


def commit(message: str) -> None:
    run("git", "add", "-A")
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if staged.returncode == 0:
        raise RuntimeError(f"No staged changes for commit: {message}")
    run("git", "commit", "-m", message)


def wave1_data_truth() -> None:
    path = "docs/assets/js/app.js"
    app = read(path)

    app = replace_once(
        app,
        'import { FALLBACK_CATALOG, SAMPLE_PROXIES, GLOBE_HUBS, INGEST_STATS } from "./data.js";\n',
        "",
        "remove eager fallback data import",
    )
    app = replace_once(
        app,
        '  IE: "Ireland"\n};',
        '  IE: "Ireland", ZZ: "Unknown"\n};',
        "add unknown country",
    )
    app = replace_once(
        app,
        'export function getFlagEmoji(countryCode) {\n  if (!countryCode || countryCode.length !== 2) return "🌐";',
        'export function getFlagEmoji(countryCode) {\n  if (!countryCode || countryCode.length !== 2 || String(countryCode).toUpperCase() === "ZZ") return "🌐";',
        "unknown flag",
    )

    helper_anchor = '''function debounce(fn, delay = 150) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
}
'''
    helpers = helper_anchor + '''
export const HEALTH_GRADES = Object.freeze([
  Object.freeze({ id: "A+", maxLatency: 45, score: 98, label: "Ultra Fast", color: "text-emerald-400 border-emerald-800/80 bg-emerald-950/60" }),
  Object.freeze({ id: "A", maxLatency: 80, score: 91, label: "Fast", color: "text-cyan-400 border-cyan-800/80 bg-cyan-950/60" }),
  Object.freeze({ id: "B", maxLatency: 140, score: 82, label: "Stable", color: "text-amber-400 border-amber-800/80 bg-amber-950/60" }),
  Object.freeze({ id: "C", maxLatency: Number.POSITIVE_INFINITY, score: 68, label: "Moderate", color: "text-rose-400 border-rose-800/80 bg-rose-950/60" })
]);

export function healthForLatency(ping) {
  if (ping === null || ping === undefined || ping === "") {
    return { score: null, grade: "—", label: "Unmeasured", color: "text-gray-400 border-gray-700 bg-gray-900" };
  }
  const value = Number(ping);
  if (!Number.isFinite(value) || value < 0) {
    return { score: null, grade: "—", label: "Unmeasured", color: "text-gray-400 border-gray-700 bg-gray-900" };
  }
  const grade = HEALTH_GRADES.find((candidate) => value <= candidate.maxLatency) || HEALTH_GRADES[HEALTH_GRADES.length - 1];
  return { score: grade.score, grade: grade.id, label: grade.label, color: grade.color };
}

export function securityGrade(security) {
  const value = String(security || "none").toLowerCase();
  if (value === "reality") return "A+";
  if (value === "tls") return "A";
  return "B+";
}
'''
    app = replace_once(app, helper_anchor, helpers, "health helpers")

    app = replace_once(
        app,
        '  let country = "US";\n  let carrier = "Direct Carrier";',
        '  let country = null;\n  let carrier = null;',
        "geo default",
    )
    app = sub_once(
        app,
        r'''  } else \{\n    let h = 0;\n    for \(let i = 0; i < addr\.length; i\+\+\) h \+= addr\.charCodeAt\(i\);\n    const pool = \[[\s\S]*?    const \[c, car\] = pool\[h % pool\.length\];\n    country = c;\n    carrier = car;\n  \}\n\n  const geoInfo = GEO_COORDINATES\[country\] \|\| \{ lat: 37\.7749, lon: -122\.4194, city: "Global Hub" \};\n  const countryName = COUNTRY_NAMES\[country\] \|\| "International";''',
        '''  } else {
    return {
      country: "ZZ",
      country_name: "Unknown",
      flag: "🌐",
      carrier: "Unverified",
      org: "Unverified",
      city: "Unknown",
      latitude: null,
      longitude: null,
      geo_source: "unknown",
      geo_verified: false
    };
  }

  const geoInfo = GEO_COORDINATES[country];
  const countryName = COUNTRY_NAMES[country] || "Unknown";''',
        "remove fabricated geo fallback",
    )
    app = replace_once(
        app,
        '''    city: geoInfo.city,
    latitude: geoInfo.lat,
    longitude: geoInfo.lon
  };''',
        '''    city: geoInfo.city,
    latitude: geoInfo.lat,
    longitude: geoInfo.lon,
    geo_source: "inferred",
    geo_verified: false
  };''',
        "geo provenance",
    )

    app = replace_once(
        app,
        '''  for (const p of proxies) {
    const code = p.country || "US";
    if (!hubMap[code]) {
      const geo = GEO_COORDINATES[code] || { lat: p.latitude || 37.7749, lon: p.longitude || -122.4194, city: `${code} Hub` };''',
        '''  for (const p of proxies) {
    const code = String(p.country || "ZZ").toUpperCase();
    const latitude = Number(p.latitude);
    const longitude = Number(p.longitude);
    if (code === "ZZ" || !Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
    if (!hubMap[code]) {
      const geo = GEO_COORDINATES[code] || { lat: latitude, lon: longitude, city: `${code} Hub` };''',
        "skip unknown globe hubs",
    )

    app = replace_once(
        app,
        '''    this.catalog = FALLBACK_CATALOG;
    this.proxies = [...SAMPLE_PROXIES];
    this.globeHubs = [...(GLOBE_HUBS || [])];
    this.stats = INGEST_STATS || {};''',
        '''    this.catalog = { files: [], total_files: 0, total_size: 0, total_size_str: "0 B" };
    this.proxies = [];
    this.globeHubs = [];
    this.stats = {};
    this.fallbackLoaded = false;''',
        "lazy fallback constructor",
    )

    load_anchor = '''  async loadLiveData() {
    this.liveDataState = "loading";'''
    fallback_method = '''  async loadBundledFallback() {
    if (this.fallbackLoaded) return;
    const data = await import("./data.js");
    this.catalog = data.FALLBACK_CATALOG || this.catalog;
    this.proxies = (data.SAMPLE_PROXIES || []).map((proxy) => {
      const rawLatency = proxy?.latency ?? proxy?.ping;
      const measured = rawLatency === null || rawLatency === undefined || rawLatency === "" ? null : Number(rawLatency);
      const latency = Number.isFinite(measured) && measured >= 0 ? measured : null;
      return {
        ...proxy,
        latency,
        ping: latency,
        latency_grade: healthForLatency(latency).grade,
        security_grade: proxy.security_grade || securityGrade(proxy.security),
        geo_source: proxy.geo_source || "legacy-estimate",
        geo_verified: Boolean(proxy.geo_verified)
      };
    });
    this.globeHubs = clusterGlobeHubs(this.proxies);
    this.stats = data.INGEST_STATS || {};
    this.fallbackLoaded = true;
  }

'''+load_anchor
    app = replace_once(app, load_anchor, fallback_method, "lazy fallback method")

    app = replace_once(
        app,
        '''            const measuredLatency = Number(entry.latency_ms ?? entry.latency ?? entry.ping);
            const latency = Number.isFinite(measuredLatency) && measuredLatency >= 0 ? measuredLatency : null;''',
        '''            const rawLatency = entry.latency_ms ?? entry.latency ?? entry.ping;
            const measuredLatency = rawLatency === null || rawLatency === undefined || rawLatency === "" ? null : Number(rawLatency);
            const latency = Number.isFinite(measuredLatency) && measuredLatency >= 0 ? measuredLatency : null;''',
        "preserve missing live latency",
    )
    app = replace_once(
        app,
        '''              latitude: geo.latitude,
              longitude: geo.longitude,
              latency,
              ping: latency,''',
        '''              latitude: geo.latitude,
              longitude: geo.longitude,
              geo_source: geo.geo_source,
              geo_verified: geo.geo_verified,
              security_grade: securityGrade(security),
              latency_grade: healthForLatency(latency).grade,
              latency,
              ping: latency,''',
        "live evidence metadata",
    )
    app = replace_once(
        app,
        '''    } else if (this.liveDataState === "loading") {
      this.liveDataState = "stale";
      this.renderDataStatus();
    }
  }''',
        '''    } else {
      await this.loadBundledFallback();
      if (this.liveDataState === "loading") this.liveDataState = "stale";
      this.renderDataStatus();
    }
  }''',
        "load fallback on live failure",
    )

    app = replace_all_required(app, "Live Proxies", "Published Proxies", "published proxy terminology")
    app = replace_all_required(app, "Explore Live Proxies", "Explore Published Proxies", "published explore terminology") if "Explore Live Proxies" in app else app
    app = replace_all_required(app, "verified proxy endpoints", "published proxy endpoints", "endpoint wording") if "verified proxy endpoints" in app else app
    app = replace_all_required(app, "Live Node Intelligence", "Published Node Inventory", "inventory wording") if "Live Node Intelligence" in app else app
    app = replace_all_required(app, "Live Carrier Latency & Ingress Matrix", "Carrier & Ingress Inventory", "carrier wording") if "Live Carrier Latency & Ingress Matrix" in app else app

    app = replace_once(
        app,
        '''      ready: { cls: "data-status-ready", text: `Live verified snapshot${when ? " · " + when : ""}` },
      stale: { cls: "data-status-stale", text: "Bundled snapshot — live data unavailable" },''',
        '''      ready: { cls: "data-status-ready", text: `Artifact integrity verified${when ? " · " + when : ""}` },
      stale: { cls: "data-status-stale", text: "Bundled snapshot — published data unavailable" },''',
        "status wording",
    )
    app = replace_once(
        app,
        '        ready: { dot: "bg-emerald-500", glow: "bg-emerald-400 opacity-75 animate-ping", text: "PIPELINE ONLINE", tone: "text-emerald-400", frame: "bg-emerald-950/50 border-emerald-800/40" },',
        '        ready: { dot: "bg-emerald-500", glow: "", text: "SNAPSHOT VERIFIED", tone: "text-emerald-400", frame: "bg-emerald-950/50 border-emerald-800/40" },',
        "pipeline evidence wording",
    )
    app = replace_once(
        app,
        '''      const live = this.liveDataState === "ready";
      radarBadge.textContent = live ? "LIVE" : "SAMPLE";''',
        '''      const live = this.liveDataState === "ready";
      radarBadge.textContent = live ? "VERIFIED" : "BUNDLED";''',
        "radar evidence wording",
    )
    app = replace_once(app, 'if (notify) this.showToast("Published data updated");', 'if (notify) this.showToast("Published snapshot updated");', "refresh toast wording")

    old_health = '''  getHealthScore(ping) {
    if (!Number.isFinite(ping) || ping < 0) {
      return { score: null, grade: "—", label: "Unmeasured", color: "text-gray-400 border-gray-700 bg-gray-900" };
    }
    const p = ping;
    if (p <= 45) return { score: 98, grade: "A+", label: "Ultra Fast", color: "text-emerald-400 border-emerald-800/80 bg-emerald-950/60" };
    if (p <= 80) return { score: 91, grade: "A", label: "Fast", color: "text-cyan-400 border-cyan-800/80 bg-cyan-950/60" };
    if (p <= 140) return { score: 82, grade: "B", label: "Stable", color: "text-amber-400 border-amber-800/80 bg-amber-950/60" };
    return { score: 68, grade: "C", label: "Moderate", color: "text-rose-400 border-rose-800/80 bg-rose-950/60" };
  }

  getLatency(node) {
    const value = Number(node?.latency ?? node?.ping);
    return Number.isFinite(value) && value >= 0 ? value : null;
  }'''
    new_health = '''  getHealthScore(ping) {
    return healthForLatency(ping);
  }

  getLatency(node) {
    const raw = node?.latency ?? node?.ping;
    if (raw === null || raw === undefined || raw === "") return null;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 ? value : null;
  }'''
    app = replace_once(app, old_health, new_health, "canonical health scoring")

    old_grades = '''    const grades = [
      { id: "ALL", label: "All Health Grades" },
      { id: "A+", label: "Grade A+ (<35ms)" },
      { id: "A", label: "Grade A (<55ms)" },
      { id: "B+", label: "Grade B+ (Stable)" }
    ];'''
    new_grades = '''    const hasMeasuredLatency = allProxies.some((proxy) => this.getLatency(proxy) !== null);
    if (!hasMeasuredLatency && this.selectedGrade !== "ALL") this.selectedGrade = "ALL";
    const grades = hasMeasuredLatency
      ? [
          { id: "ALL", label: "All Latency Grades" },
          ...HEALTH_GRADES.map((grade) => ({
            id: grade.id,
            label: Number.isFinite(grade.maxLatency)
              ? `Grade ${grade.id} (≤${grade.maxLatency}ms)`
              : `Grade ${grade.id} (>${HEALTH_GRADES[HEALTH_GRADES.length - 2].maxLatency}ms)`
          }))
        ]
      : [{ id: "ALL", label: "Latency unmeasured" }];'''
    app = replace_once(app, old_grades, new_grades, "health filter options")

    app = replace_once(
        app,
        '${flag} ${escapeHTML(node.countryName)} • ${escapeHTML(op)}</span>',
        '${flag} ${escapeHTML(node.countryName || node.country_name || "Unknown")} • ${escapeHTML(op)} <span class="text-[9px] text-gray-500">(${node.geo_verified ? "verified" : node.geo_source === "unknown" ? "unknown" : "estimated"})</span></span>',
        "geo provenance label",
    )

    write(path, app)

    gen_path = "scripts/generate_site_data.py"
    gen = read(gen_path)
    gen = sub_once(
        gen,
        r'''    else:\n        # Balanced hash fallback across global tier-1 sovereign nodes\n        h = sum\(ord\(c\) for c in addr\)\n        pool = \[[\s\S]*?        country, carrier = pool\[h % len\(pool\)\]\n\n    lat, lon, hub_name = GEO_COORDINATES\.get\(country, \(37\.7749, -122\.4194, "Global Hub"\)\)\n    country_name = COUNTRY_NAMES\.get\(country, "International"\)\n    flag = _country_flag\(country\)''',
        '''    else:
        return {
            "country": "ZZ",
            "country_name": "Unknown",
            "flag": "🌐",
            "carrier": "Unverified",
            "org": "Unverified",
            "city": "Unknown",
            "latitude": None,
            "longitude": None,
            "geo_source": "unknown",
            "geo_verified": False,
        }

    lat, lon, hub_name = GEO_COORDINATES[country]
    country_name = COUNTRY_NAMES.get(country, "Unknown")
    flag = _country_flag(country)''',
        "producer unknown geo",
    )
    gen = replace_once(
        gen,
        '''        "longitude": lon,
    }''',
        '''        "longitude": lon,
        "geo_source": "inferred",
        "geo_verified": False,
    }''',
        "producer geo provenance",
    )
    gen = replace_once(
        gen,
        '        grade = "A+" if security == "reality" else ("A" if security == "tls" else "B+")',
        '        security_grade = "A+" if security == "reality" else ("A" if security == "tls" else "B+")',
        "producer security grade name",
    )
    gen = replace_once(
        gen,
        '''            "longitude": geo["longitude"],
            "latency": None,
            "grade": grade,
            "raw_uri": raw''',
        '''            "longitude": geo["longitude"],
            "geo_source": geo["geo_source"],
            "geo_verified": geo["geo_verified"],
            "latency": None,
            "latency_grade": None,
            "security_grade": security_grade,
            "raw_uri": raw''',
        "producer grade split",
    )
    gen = replace_once(
        gen,
        '''    for p in proxies:
        code = p["country"]
        if code not in hub_map:''',
        '''    for p in proxies:
        code = p["country"]
        if code == "ZZ" or not isinstance(p.get("latitude"), (int, float)) or not isinstance(p.get("longitude"), (int, float)):
            continue
        if code not in hub_map:''',
        "producer skip unknown hubs",
    )
    write(gen_path, gen)

    runtime_test = r'''import test from "node:test";
import assert from "node:assert/strict";
import { AppState, HEALTH_GRADES, healthForLatency, resolveGeoAndCarrier, securityGrade } from "../docs/assets/js/app.js";

test("missing latency remains unmeasured instead of becoming zero", () => {
  const app = new AppState();
  assert.equal(app.getLatency({ latency: null, ping: null }), null);
  assert.equal(app.getLatency({}), null);
  assert.equal(healthForLatency(null).grade, "—");
});

test("latency grade labels and runtime thresholds share one source", () => {
  assert.deepEqual(HEALTH_GRADES.map((grade) => grade.id), ["A+", "A", "B", "C"]);
  assert.equal(healthForLatency(45).grade, "A+");
  assert.equal(healthForLatency(46).grade, "A");
  assert.equal(healthForLatency(80).grade, "A");
  assert.equal(healthForLatency(81).grade, "B");
  assert.equal(healthForLatency(141).grade, "C");
});

test("security grade is independent from latency health", () => {
  assert.equal(securityGrade("reality"), "A+");
  assert.equal(securityGrade("tls"), "A");
  assert.equal(securityGrade("none"), "B+");
});

test("unknown endpoints do not receive fabricated geography", () => {
  const geo = resolveGeoAndCarrier("203.0.113.199", "", "");
  assert.equal(geo.country, "ZZ");
  assert.equal(geo.carrier, "Unverified");
  assert.equal(geo.latitude, null);
  assert.equal(geo.longitude, null);
  assert.equal(geo.geo_source, "unknown");
  assert.equal(geo.geo_verified, false);
});
'''
    write("tests/frontend_runtime.test.mjs", runtime_test)

    commit("fix(frontend): make telemetry health and geo evidence truthful")


def wave2_interaction_and_accessibility() -> None:
    globe_path = "docs/assets/js/globe.js"
    globe = read(globe_path)
    globe = replace_once(globe, 'import { GLOBE_HUBS } from "./data.js";\n\n', "", "remove eager globe data import")
    globe = replace_once(
        globe,
        'export function initTelemetryGlobe(canvasId, onNodeSelect, customHubs = null) {',
        'export function initTelemetryGlobe(canvasId, onNodeSelect, customHubs = null, options = {}) {',
        "globe options",
    )
    globe = replace_once(
        globe,
        '''  const sourceHubs = (customHubs && Array.isArray(customHubs) && customHubs.length > 0)
    ? customHubs
    : ((typeof GLOBE_HUBS !== "undefined" && Array.isArray(GLOBE_HUBS) && GLOBE_HUBS.length > 0) ? GLOBE_HUBS : DEFAULT_HUBS);''',
        '''  const sourceHubs = (customHubs && Array.isArray(customHubs) && customHubs.length > 0)
    ? customHubs
    : DEFAULT_HUBS;''',
        "globe fallback source",
    )

    old_gate = '''  // Touch interaction gating for mobile / pointer devices
  let isTouchActive = false;
  canvas.style.touchAction = "pan-y";

  function setTouchInteractive(active) {
    isTouchActive = !!active;
    canvas.style.touchAction = isTouchActive ? "none" : "pan-y";
  }
'''
    new_gate = '''  // Touch interaction gating for coarse pointer devices. The timeout is
  // activity-based and owned by this component so remounts cannot leak stale timers.
  let isTouchActive = false;
  let touchInactivityTimer = null;
  const TOUCH_IDLE_TIMEOUT_MS = 12000;
  canvas.style.touchAction = "pan-y";

  function notifyTouchMode() {
    if (typeof options.onTouchModeChange === "function") options.onTouchModeChange(isTouchActive);
  }

  function scheduleTouchInactivityTimeout() {
    if (touchInactivityTimer) clearTimeout(touchInactivityTimer);
    touchInactivityTimer = null;
    if (!isTouchActive) return;
    touchInactivityTimer = setTimeout(() => setTouchInteractive(false), TOUCH_IDLE_TIMEOUT_MS);
  }

  function noteTouchActivity() {
    if (isTouchActive) scheduleTouchInactivityTimeout();
  }

  function setTouchInteractive(active) {
    isTouchActive = !!active;
    canvas.style.touchAction = isTouchActive ? "none" : "pan-y";
    scheduleTouchInactivityTimeout();
    notifyTouchMode();
  }
'''
    globe = replace_once(globe, old_gate, new_gate, "globe inactivity ownership")

    globe = replace_once(
        globe,
        '''  function onPointerDown(e) {
    if (e.pointerType === "touch" && !isTouchActive) {''',
        '''  function onPointerDown(e) {
    if (e.pointerType === "touch") noteTouchActivity();
    if (e.pointerType === "touch" && !isTouchActive) {''',
        "pointerdown activity",
    )
    globe = replace_once(
        globe,
        '''  function onPointerMove(e) {
    if (isDragging) {''',
        '''  function onPointerMove(e) {
    if (e.pointerType === "touch" && isDragging) noteTouchActivity();
    if (isDragging) {''',
        "pointermove activity",
    )
    globe = replace_once(
        globe,
        '''  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);''',
        '''  function onPointerCancel(e) {
    isDragging = false;
    velX = 0;
    velY = reduceMotion ? 0 : 0.0032;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch (err) {}
  }

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerCancel);''',
        "separate pointercancel",
    )
    globe = replace_once(
        globe,
        '''      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();''',
        '''      cancelAnimationFrame(rafId);
      if (touchInactivityTimer) clearTimeout(touchInactivityTimer);
      touchInactivityTimer = null;
      resizeObserver.disconnect();
      intersectionObserver.disconnect();''',
        "destroy timer cleanup",
    )
    globe = replace_once(
        globe,
        '      canvas.removeEventListener("pointercancel", onPointerUp);',
        '      canvas.removeEventListener("pointercancel", onPointerCancel);',
        "pointercancel cleanup",
    )
    write(globe_path, globe)

    app_path = "docs/assets/js/app.js"
    app = read(app_path)
    app = replace_all_required(
        app,
        'class="flex items-center justify-center gap-1.5 p-2 sm:px-3.5 sm:py-2 min-h-[44px] min-w-[44px]',
        'class="hidden sm:flex items-center justify-center gap-1.5 p-2 sm:px-3.5 sm:py-2 min-h-[44px] min-w-[44px]',
        "compact mobile header tools",
        minimum=2,
    )
    app = replace_once(
        app,
        'class="absolute bottom-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-auto md:hidden"',
        'class="absolute bottom-3 left-3 right-3 z-10 hidden items-center justify-between pointer-events-auto"',
        "coarse pointer gate class",
    )
    app = replace_once(
        app,
        '                aria-label="Toggle Interactive 3D Mode"\n              >',
        '                aria-label="Toggle Interactive 3D Mode"\n                aria-pressed="false"\n              >',
        "globe aria pressed",
    )

    old_touch_handler_pattern = r'''    const touchBtn = document\.getElementById\("btn-globe-touch-toggle"\);\n    touchBtn\?\.addEventListener\("click", \(\) => \{[\s\S]*?    \}\);\n\n    document\.getElementById\("hero-copy-sub"\)'''
    new_touch_handler = '''    const touchGate = document.getElementById("globe-touch-gate");
    const touchBtn = document.getElementById("btn-globe-touch-toggle");
    const hasCoarsePointer = typeof window !== "undefined" && window.matchMedia?.("(any-pointer: coarse)")?.matches;
    if (touchGate) touchGate.classList.toggle("hidden", !hasCoarsePointer);
    touchBtn?.addEventListener("click", () => {
      if (!this.globeInstance) return;
      this.globeInstance.setTouchInteractive?.(!this.globeInstance.isTouchInteractive?.());
    });
    this.syncGlobeTouchControl(this.globeInstance?.isTouchInteractive?.() || false);

    document.getElementById("hero-copy-sub")'''
    app = sub_once(app, old_touch_handler_pattern, new_touch_handler, "replace app-level globe timeout")

    mount_anchor = '''  mountGlobe() {
    this.globeInstance?.destroy?.();'''
    mount_with_sync = '''  syncGlobeTouchControl(active) {
    const touchBtn = document.getElementById("btn-globe-touch-toggle");
    const label = document.getElementById("globe-touch-label");
    if (!touchBtn) return;
    const enabled = Boolean(active);
    touchBtn.setAttribute("aria-pressed", enabled ? "true" : "false");
    if (label) label.textContent = enabled ? "Exit 3D Mode" : "Explore 3D Globe";
    touchBtn.classList.toggle("bg-cyan-500", enabled);
    touchBtn.classList.toggle("text-gray-950", enabled);
    touchBtn.classList.toggle("border-cyan-400", enabled);
    touchBtn.classList.toggle("bg-gray-950/90", !enabled);
    touchBtn.classList.toggle("text-cyan-300", !enabled);
  }

'''+mount_anchor
    app = replace_once(app, mount_anchor, mount_with_sync, "globe UI sync method")
    app = replace_once(
        app,
        '''    this.globeInstance = initTelemetryGlobe("telemetry-globe-canvas", (hub) => {
      this.selectedCountry = hub.code;
      this.renderFilterBar();
      this.renderNodes();
      this.switchPageTab("proxies", true);
      this.showToast(`Filtered by ${escapeHTML(hub.name)} (${escapeHTML(hub.code)})`);
    }, this.globeHubs);''',
        '''    this.globeInstance = initTelemetryGlobe("telemetry-globe-canvas", (hub) => {
      this.selectedCountry = hub.code;
      this.renderFilterBar();
      this.renderNodes();
      this.switchPageTab("proxies", true);
      this.showToast(`Filtered by ${escapeHTML(hub.name)} (${escapeHTML(hub.code)})`);
    }, this.globeHubs, {
      onTouchModeChange: (active) => this.syncGlobeTouchControl(active)
    });
    this.syncGlobeTouchControl(this.globeInstance?.isTouchInteractive?.() || false);''',
        "mount touch mode callback",
    )

    app = replace_once(app, 'class="text-gray-300 truncate max-w-[170px] select-all">${escapeHTML(node.server)}:${node.port}', 'class="technical-ltr text-gray-300 truncate max-w-[170px] select-all">${escapeHTML(node.server)}:${node.port}', "endpoint bidi")
    app = replace_once(app, 'class="text-cyan-300 truncate max-w-[170px] select-all">${escapeHTML(node.sni)}', 'class="technical-ltr text-cyan-300 truncate max-w-[170px] select-all">${escapeHTML(node.sni)}', "sni bidi")
    app = replace_once(app, 'class="text-gray-400 font-mono text-[10px]">${escapeHTML(displayUUID)}', 'class="technical-ltr text-gray-400 font-mono text-[10px]">${escapeHTML(displayUUID)}', "credential bidi")
    app = replace_once(app, 'class="text-[10px] font-mono text-gray-500 truncate" title="${escapeHTML(link.display)}"', 'class="technical-ltr text-[10px] font-mono text-gray-500 truncate" title="${escapeHTML(link.display)}"', "artifact link bidi")
    write(app_path, app)

    runtime = read("tests/frontend_runtime.test.mjs")
    runtime += r'''

test("globe module owns touch inactivity and does not treat cancellation as click", async () => {
  const source = await (await import("node:fs/promises")).readFile(new URL("../docs/assets/js/globe.js", import.meta.url), "utf8");
  assert.match(source, /function onPointerCancel/);
  assert.match(source, /pointercancel", onPointerCancel/);
  assert.doesNotMatch(source, /pointercancel", onPointerUp/);
  assert.match(source, /scheduleTouchInactivityTimeout/);
  assert.match(source, /clearTimeout\(touchInactivityTimer\)/);
});
'''
    write("tests/frontend_runtime.test.mjs", runtime)

    commit("fix(frontend): harden coarse-pointer globe interaction and accessibility")


def wave3_i18n_and_delivery() -> None:
    i18n_path = "docs/assets/js/i18n.js"
    i18n = read(i18n_path)
    i18n = replace_once(i18n, 'const regionMatch = source.match(/^(\\d+)\\s+Regions$/i);', 'const regionMatch = source.match(/^(\\d+)\\s+Regions$/);', "reachable uppercase region pattern")

    additions = {
        "fa": {
            "Published Proxies": "پروکسی‌های منتشرشده",
            "Published Node Inventory": "فهرست گره‌های منتشرشده",
            "Artifact integrity verified": "یکپارچگی فایل منتشرشده تأیید شد",
            "SNAPSHOT VERIFIED": "نسخه منتشرشده تأیید شد",
            "VERIFIED": "تأییدشده",
            "BUNDLED": "نسخه محلی",
            "Published snapshot updated": "نسخه منتشرشده به‌روزرسانی شد",
            "Latency unmeasured": "تأخیر اندازه‌گیری نشده",
            "All Latency Grades": "همه رتبه‌های تأخیر",
            "Unknown": "نامشخص",
            "Unverified": "تأییدنشده",
            "estimated": "تخمینی",
            "verified": "تأییدشده",
            "unknown": "نامشخص",
        },
        "zh-CN": {
            "Published Proxies": "已发布代理",
            "Published Node Inventory": "已发布节点清单",
            "Artifact integrity verified": "发布文件完整性已验证",
            "SNAPSHOT VERIFIED": "快照已验证",
            "VERIFIED": "已验证",
            "BUNDLED": "内置快照",
            "Published snapshot updated": "发布快照已更新",
            "Latency unmeasured": "延迟未测量",
            "All Latency Grades": "全部延迟等级",
            "Unknown": "未知",
            "Unverified": "未验证",
            "estimated": "估算",
            "verified": "已验证",
            "unknown": "未知",
        },
        "ru": {
            "Published Proxies": "Опубликованные прокси",
            "Published Node Inventory": "Опубликованный список узлов",
            "Artifact integrity verified": "Целостность опубликованного снимка подтверждена",
            "SNAPSHOT VERIFIED": "СНИМОК ПРОВЕРЕН",
            "VERIFIED": "ПРОВЕРЕНО",
            "BUNDLED": "ВСТРОЕННЫЙ СНИМОК",
            "Published snapshot updated": "Опубликованный снимок обновлён",
            "Latency unmeasured": "Задержка не измерена",
            "All Latency Grades": "Все классы задержки",
            "Unknown": "Неизвестно",
            "Unverified": "Не проверено",
            "estimated": "оценка",
            "verified": "проверено",
            "unknown": "неизвестно",
        },
    }
    for locale, mapping in additions.items():
        marker = f"  {locale}: {{\n"
        payload = "".join(f"    {json.dumps(key, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)},\n" for key, value in mapping.items())
        i18n = replace_once(i18n, marker, marker + payload, f"{locale} new translations")

    observer_pattern = r'''    this\.observer = new MutationObserver\(\(mutations\) => \{[\s\S]*?    this\.observer\.observe\(document\.documentElement, \{\n      attributes: true,\n      attributeFilter: \["aria-label", "title", "placeholder"\],\n      characterData: true,\n      childList: true,\n      subtree: true\n    \}\);'''
    observer_replacement = '''    this.observer = new MutationObserver((mutations) => {
      if (this.isTranslating) return;
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          this.isTranslating = true;
          try { this.translateTree(node); } finally { this.isTranslating = false; }
        }
      }
    });
    this.observer.observe(document.documentElement, {
      childList: true,
      subtree: true
    });'''
    i18n = sub_once(i18n, observer_pattern, observer_replacement, "lightweight i18n observer")
    write(i18n_path, i18n)

    app_path = "docs/assets/js/app.js"
    app = read(app_path)
    app = replace_once(app, '<span class="truncate max-w-[280px]">${escapeHTML(msg)}</span>', '<span class="truncate max-w-[280px]">${escapeHTML(i18n.translate(msg))}</span>', "translate runtime toasts")
    write(app_path, app)

    updater_path = "scripts/update_frontend.py"
    updater = read(updater_path)
    updater = sub_once(
        updater,
        r'''  <!-- Tailwind CSS 3\.4 CDN with Dark Mode Class Support -->\n  <script src="https://cdn\.tailwindcss\.com"></script>\n  <script>[\s\S]*?  </script>\n\n''',
        '  <link rel="stylesheet" href="assets/css/tailwind.css">\n\n',
        "remove Tailwind runtime config",
    )
    updater = replace_once(updater, '  <!-- Progressive Tailwind CDN -->\n  <script src="https://cdn.tailwindcss.com/3.4.17" defer></script>\n', '', "remove progressive Tailwind CDN")
    updater = replace_once(
        updater,
        '  <!-- Checked-in standalone bundle. Supported delivery mode is HTTP/HTTPS. -->\n  <script src="assets/js/bundle.js"></script>\n\n  <!-- Resilient Non-Module Fallback -->\n  <script>\n    if (typeof AppState === \'undefined\') {\n      console.warn(\'[HUNTX] Bundle loading fallback...\');\n    }\n  </script>\n',
        '  <!-- Native ES-module entrypoint; fallback data is lazy-loaded on demand. -->\n  <script type="module" src="assets/js/app.js"></script>\n',
        "native module entrypoint",
    )
    updater = replace_all_required(updater, "Live Proxies", "Published Proxies", "index proxy terminology")
    updater = replace_once(updater, '<!-- TAB 2 PANEL: Live Proxies Stream Grid -->', '<!-- TAB 2 PANEL: Published Proxies Stream Grid -->', "tab comment wording") if '<!-- TAB 2 PANEL: Live Proxies Stream Grid -->' in updater else updater

    safe_anchor = '''    /* Safe-area inset support for mobile screens */
    body {
      padding-bottom: env(safe-area-inset-bottom, 0px);
    }
'''
    safe_replacement = safe_anchor + '''
    #toast-container {
      bottom: max(1.5rem, calc(0.75rem + env(safe-area-inset-bottom, 0px))) !important;
      padding-left: env(safe-area-inset-left, 0px);
      padding-right: env(safe-area-inset-right, 0px);
    }

    #data-status-pill {
      bottom: max(12px, calc(8px + env(safe-area-inset-bottom, 0px))) !important;
      left: max(12px, calc(8px + env(safe-area-inset-left, 0px))) !important;
    }

    .technical-ltr,
    code,
    pre {
      direction: ltr;
      unicode-bidi: plaintext;
      text-align: left;
    }

    #page-tabs-nav .nav-tab-btn {
      scroll-snap-align: start;
    }
    #page-tabs-nav > div {
      scroll-snap-type: x proximity;
    }
    @media (max-width: 639px) {
      #page-tabs-nav .no-scrollbar {
        scrollbar-width: thin;
      }
      #page-tabs-nav .no-scrollbar::-webkit-scrollbar {
        display: block;
        height: 3px;
      }
    }
'''
    updater = replace_once(updater, safe_anchor, safe_replacement, "safe area and bidi CSS")

    updater = sub_once(
        updater,
        r'''def write_index\(\):[\s\S]*?\n\ndef legacy_bundle\(\):[\s\S]*?\n\nif __name__ == "__main__":[\s\S]*$''',
        '''def build_index_content(root: Path | None = None) -> str:
    import json
    project_root = root or Path(__file__).resolve().parents[1]
    proxies_count = 0
    artifacts_count = 0
    try:
        data_path = project_root / "docs" / "assets" / "js" / "data.js"
        if data_path.exists():
            data_js = data_path.read_text(encoding="utf-8")
            proxies_count = data_js.count('"id": "px-')
            m_stat = re.search(r'"total_production_nodes":\\s*(\\d+)', data_js)
            if m_stat:
                proxies_count = int(m_stat.group(1))
        catalog_path = project_root / "docs" / "catalog.json"
        if catalog_path.exists():
            cat = json.loads(catalog_path.read_text(encoding="utf-8"))
            if isinstance(cat, dict) and isinstance(cat.get("files"), list):
                artifacts_count = len(cat["files"])
    except Exception:
        pass
    return INDEX_HTML.replace("{{PROXIES_COUNT}}", str(proxies_count)).replace("{{ARTIFACTS_COUNT}}", str(artifacts_count))


def write_index(root: Path | None = None) -> None:
    project_root = root or Path(__file__).resolve().parents[1]
    content = build_index_content(project_root)
    output = project_root / "docs" / "index.html"
    output.write_text(content, encoding="utf-8")
    print(f"Generated {output}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    if sys.argv[1:] == ["--check"]:
        expected = build_index_content(root)
        actual = (root / "docs" / "index.html").read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit("Frontend index is stale; run scripts/update_frontend.py and commit docs/index.html.")
        if (root / "docs" / "assets" / "js" / "bundle.js").exists():
            raise SystemExit("Legacy bundle.js must not be checked in; native modules are the production entrypoint.")
        print("Frontend index is current and legacy bundle is absent.")
        raise SystemExit(0)
    write_index(root)
''',
        "remove legacy bundler",
        flags=re.MULTILINE,
    )
    write(updater_path, updater)

    write(
        "package.json",
        json.dumps(
            {
                "name": "huntx-static-dashboard",
                "private": True,
                "scripts": {"build:css": "tailwindcss -i docs/assets/css/input.css -o docs/assets/css/tailwind.css --minify"},
                "devDependencies": {"tailwindcss": "3.4.17"},
            },
            indent=2,
        ) + "\n",
    )
    write(
        "tailwind.config.cjs",
        '''module.exports = {
  darkMode: "class",
  content: [
    "./docs/index.html",
    "./docs/assets/js/**/*.js",
    "./scripts/update_frontend.py"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Plus Jakarta Sans", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"]
      }
    }
  },
  plugins: []
};
''',
    )
    write("docs/assets/css/input.css", "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")

    sw_path = "docs/sw.js"
    sw = read(sw_path)
    sw = replace_once(sw, "const CACHE_NAME = 'huntx-cache-v3.0';", "const CACHE_NAME = 'huntx-cache-v4.0';", "service worker cache version")
    sw = replace_once(
        sw,
        '''  './catalog.json',
  './assets/js/bundle.js',
  './assets/js/decoder.js',
  './assets/js/wasm_exec.js',''',
        '''  './catalog.json',
  './assets/css/tailwind.css',
  './assets/js/app.js',
  './assets/js/globe.js',
  './assets/js/i18n.js',
  './assets/js/qrcode.js',
  './assets/js/decoder.js',
  './assets/js/wasm_exec.js',''',
        "service worker module graph",
    )
    sw = replace_once(sw, "    || path.endsWith('/assets/js/bundle.js')", "    || path.endsWith('/assets/js/app.js')\n    || path.endsWith('/assets/css/tailwind.css')", "service worker deployment shell")
    write(sw_path, sw)

    bundle = ROOT / "docs" / "assets" / "js" / "bundle.js"
    if bundle.exists():
        bundle.unlink()
    generated_manifest = ROOT / "huntx-generated-files.txt"
    if generated_manifest.exists():
        lines = [line for line in generated_manifest.read_text(encoding="utf-8").splitlines() if "docs/assets/js/bundle.js" not in line]
        generated_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    run("python", "scripts/update_frontend.py")
    run("npm", "install", "--package-lock-only", "--ignore-scripts")
    run("npm", "ci", "--ignore-scripts")
    run("npm", "run", "build:css")

    tests_path = "tests/test_frontend_delivery.py"
    tests = read(tests_path)
    tests = sub_once(
        tests,
        r'''def test_checked_in_bundle_matches_frontend_modules\(\) -> None:[\s\S]*?\n\n\ndef test_service_worker_uses_network_first_for_deployment_shell''',
        '''def test_checked_in_index_matches_frontend_generator() -> None:
    builder = _load_frontend_builder()
    expected = builder.build_index_content(ROOT)
    published = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert published == expected
    assert 'src="assets/js/bundle.js"' not in published
    assert 'type="module" src="assets/js/app.js"' in published
    assert 'cdn.tailwindcss.com' not in published
    assert 'assets/css/tailwind.css' in published
    assert not (ROOT / "docs" / "assets" / "js" / "bundle.js").exists()


def test_service_worker_uses_network_first_for_deployment_shell''',
        "delivery test native modules",
    )
    tests = replace_once(tests, 'assert "(freshReleaseData || deploymentShell) ? networkFirst(event.request)" in worker', 'assert "(freshReleaseData || deploymentShell) ? networkFirst(event.request)" in worker\n    assert "assets/js/app.js" in worker\n    assert "assets/css/tailwind.css" in worker\n    assert "assets/js/bundle.js" not in worker', "service worker assertions")
    tests = replace_once(tests, '    assert builder.MODULE_ORDER.index("i18n.js") < builder.MODULE_ORDER.index("app.js")', '    html = builder.build_index_content(ROOT)\n    assert \'type="module" src="assets/js/app.js"\' in html\n    assert \'import { i18n } from "./i18n.js";\' in (ROOT / "docs" / "assets" / "js" / "app.js").read_text(encoding="utf-8")', "remove module order test")
    write(tests_path, tests)

    runtime = read("tests/frontend_runtime.test.mjs")
    runtime += r'''

test("delivery uses native modules and lazy fallback data", async () => {
  const fs = await import("node:fs/promises");
  const appSource = await fs.readFile(new URL("../docs/assets/js/app.js", import.meta.url), "utf8");
  const html = await fs.readFile(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.doesNotMatch(appSource, /from "\.\/data\.js"/);
  assert.match(appSource, /await import\("\.\/data\.js"\)/);
  assert.match(html, /type="module" src="assets\/js\/app\.js"/);
  assert.doesNotMatch(html, /cdn\.tailwindcss\.com/);
});
'''
    write("tests/frontend_runtime.test.mjs", runtime)

    commit("perf(frontend): ship compiled CSS and lazy native modules")


def wave4_ci_dependencies_and_docs() -> None:
    dep_path = ".github/dependabot.yml"
    dep = read(dep_path)
    go_entries = '''

  - package-ecosystem: gomod
    directory: "/"
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: Europe/Helsinki
    groups:
      go-runtime:
        patterns:
          - "*"
    open-pull-requests-limit: 5

  - package-ecosystem: gomod
    directory: "/src/huntx/connectors/v2ray_collector"
    schedule:
      interval: weekly
      day: monday
      time: "06:15"
      timezone: Europe/Helsinki
    groups:
      collector-go-runtime:
        patterns:
          - "*"
    open-pull-requests-limit: 5
'''
    if 'package-ecosystem: gomod' not in dep:
        dep = dep.rstrip() + go_entries + "\n"
    write(dep_path, dep)

    run("go", "get", "golang.org/x/net@v0.58.0", cwd="src/huntx/connectors/v2ray_collector")
    run("go", "mod", "tidy", cwd="src/huntx/connectors/v2ray_collector")

    prod_path = ".github/workflows/huntx.yml"
    prod = read(prod_path)
    nested_block = '''          go test -race ./...
          go vet ./...
          (
            cd src/huntx/connectors/v2ray_collector
            go test -race ./...
            go vet ./...
            go run golang.org/x/vuln/cmd/govulncheck@v1.7.0 ./...
          )'''
    if "govulncheck@v1.7.0" not in prod:
        prod = replace_once(prod, '''          go test -race ./...
          go vet ./...''', nested_block, "production nested Go gate")
    write(prod_path, prod)

    final_pr_validation = '''name: pull-request-validation

on:
  workflow_dispatch:
  pull_request:
    paths:
      - ".github/workflows/**"
      - "configs/**"
      - "docs/**"
      - "go.mod"
      - "go.sum"
      - "package.json"
      - "package-lock.json"
      - "tailwind.config.cjs"
      - "deploy/**"
      - "cmd/**"
      - "internal/**"
      - "pyproject.toml"
      - "requirements*.txt"
      - "scripts/**"
      - "src/**"
      - "tests/**"
  push:
    branches:
      - "fix/**"
      - "agent/**"
      - "codex/**"
    paths:
      - ".github/workflows/**"
      - "configs/**"
      - "docs/**"
      - "go.mod"
      - "go.sum"
      - "package.json"
      - "package-lock.json"
      - "tailwind.config.cjs"
      - "deploy/**"
      - "cmd/**"
      - "internal/**"
      - "pyproject.toml"
      - "requirements*.txt"
      - "scripts/**"
      - "src/**"
      - "tests/**"

concurrency:
  group: pull-request-validation-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  validate:
    name: quality-gate
    runs-on: ubuntu-24.04
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 1
          persist-credentials: false

      - name: Validate workflow YAML syntax
        run: |
          set -euo pipefail
          ruby -e '
            require "yaml"
            paths = Dir[".github/workflows/*.{yml,yaml}"].sort
            abort "No workflow files found" if paths.empty?
            paths.each { |path| YAML.load_file(path) }
          '

      - uses: actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e # v7.0.0
        with:
          go-version-file: go.mod
          cache: true

      - name: Go quality gate
        run: |
          set -euo pipefail
          formatting="$(gofmt -l .)"
          test -z "$formatting" || {
            printf 'Unformatted Go files:\n%s\n' "$formatting"
            exit 1
          }
          go test -race ./...
          go vet ./...
          go build ./cmd/huntx-tools
          go build ./cmd/huntx-engine
          go build ./cmd/huntx-daemon
          go build ./cmd/huntx-probe
          (
            cd src/huntx/connectors/v2ray_collector
            go test -race ./...
            go vet ./...
            go run golang.org/x/vuln/cmd/govulncheck@v1.7.0 ./...
          )

      - name: Validate fleet deployment manifests
        run: |
          set -euo pipefail
          docker build -f deploy/Dockerfile.daemon .
          docker build -f deploy/Dockerfile.probe .
          curl -fsSL https://get.helm.sh/helm-v3.17.3-linux-amd64.tar.gz -o helm.tar.gz
          echo "ee88b3c851ae6466a3de507f7be73fe94d54cbf2987cbaa3d1a3832ea331f2cd  helm.tar.gz" | sha256sum -c -
          tar -xzf helm.tar.gz
          helm_args=(
            --set-string daemon.controlToken=ci-control-token
            --set-file daemon.nodesJson=deploy/helm/huntx-fleet/ci-nodes.json
            --set-string orchestratorBearerToken=ci-orchestrator-token
            --set-string orchestratorUrl=https://receiver.invalid/api/vantage/report
            --set-string daemon.image.tag=ci
            --set-string image.tag=ci
          )
          ./linux-amd64/helm lint deploy/helm/huntx-fleet "${helm_args[@]}"
          ./linux-amd64/helm template huntx deploy/helm/huntx-fleet "${helm_args[@]}" >/dev/null

      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4
        with:
          node-version: "22"
          cache: npm

      - name: Frontend runtime and production asset gate
        run: |
          set -euo pipefail
          npm ci --ignore-scripts
          npm run build:css
          git diff --exit-code -- docs/assets/css/tailwind.css
          node --experimental-default-type=module --test tests/frontend_runtime.test.mjs
          python scripts/update_frontend.py --check

      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            requirements.txt
            requirements-ci.txt
            pyproject.toml

      - name: Python quality gate
        run: |
          set -euo pipefail
          python -m pip install --require-hashes --prefer-binary -r requirements.txt
          python -m pip install --prefer-binary -r requirements-ci.txt
          python -m pip install --no-deps -e .
          python -m pip check
          python -m compileall -q -j 0 src tests scripts
          python -m flake8 src/huntx tests scripts --count --statistics
          python -m mypy src/huntx
          python -m pytest -q -m "not perf" --strict-config --strict-markers --durations=20 --junitxml=pytest-results.xml
'''
    write(".github/workflows/pr-validation.yml", final_pr_validation)

    for doc_path in ["README.md", "docs/USER_GUIDE.md", "docs/DEVELOPMENT.md"]:
        target = ROOT / doc_path
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8")
        text = text.replace("WCAG 2.2 AA compliant >=44px", "44px touch targets, exceeding the WCAG 2.2 AA minimum")
        target.write_text(text, encoding="utf-8")

    temp = ROOT / "scripts" / "pr88_remediation.py"
    if temp.exists():
        temp.unlink()

    commit("ci: cover frontend runtime, nested Go module, and dependency security")


def final_local_validation() -> None:
    run("python", "scripts/update_frontend.py", "--check")
    run("npm", "ci", "--ignore-scripts")
    run("npm", "run", "build:css")
    run("git", "diff", "--exit-code", "--", "docs/assets/css/tailwind.css")
    run("node", "--experimental-default-type=module", "--test", "tests/frontend_runtime.test.mjs")
    run("go", "test", "-race", "./...", cwd="src/huntx/connectors/v2ray_collector")
    run("go", "vet", "./...", cwd="src/huntx/connectors/v2ray_collector")
    run("go", "run", "golang.org/x/vuln/cmd/govulncheck@v1.7.0", "./...", cwd="src/huntx/connectors/v2ray_collector")


if __name__ == "__main__":
    run("git", "config", "user.name", "huntx-pr88-remediation")
    run("git", "config", "user.email", "actions@users.noreply.github.com")
    wave1_data_truth()
    wave2_interaction_and_accessibility()
    wave3_i18n_and_delivery()
    wave4_ci_dependencies_and_docs()
    final_local_validation()
