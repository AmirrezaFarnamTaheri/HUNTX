import test from "node:test";
import assert from "node:assert/strict";
import { AppState, HEALTH_GRADES, healthForLatency, resolveGeoAndCarrier, securityGrade } from "../docs/assets/js/app.js";

test("missing latency remains unmeasured instead of becoming zero", () => {
  const getLatency = AppState.prototype.getLatency;
  assert.equal(getLatency.call({}, { latency: null, ping: null }), null);
  assert.equal(getLatency.call({}, {}), null);
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


test("globe module owns touch inactivity and does not treat cancellation as click", async () => {
  const source = await (await import("node:fs/promises")).readFile(new URL("../docs/assets/js/globe.js", import.meta.url), "utf8");
  assert.match(source, /function onPointerCancel/);
  assert.match(source, /pointercancel", onPointerCancel/);
  assert.doesNotMatch(source, /pointercancel", onPointerUp/);
  assert.match(source, /scheduleTouchInactivityTimeout/);
  assert.match(source, /clearTimeout\(touchInactivityTimer\)/);
});


test("delivery uses native modules and lazy fallback data", async () => {
  const fs = await import("node:fs/promises");
  const appSource = await fs.readFile(new URL("../docs/assets/js/app.js", import.meta.url), "utf8");
  const html = await fs.readFile(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.doesNotMatch(appSource, /from "\.\/data\.js"/);
  assert.match(appSource, /await import\("\.\/data\.js"\)/);
  assert.match(html, /type="module" src="assets\/js\/app\.js"/);
  assert.doesNotMatch(html, /cdn\.tailwindcss\.com/);
});


test("responsive shell is offline-safe and respects reduced motion", async () => {
  const fs = await import("node:fs/promises");
  const appSource = await fs.readFile(new URL("../docs/assets/js/app.js", import.meta.url), "utf8");
  const html = await fs.readFile(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.match(appSource, /prefers-reduced-motion: reduce/);
  assert.match(appSource, /btn-header-tools/);
  assert.match(appSource, /aria-expanded/);
  assert.doesNotMatch(html, /fonts\.googleapis\.com|fonts\.gstatic\.com/);
});

test("runtime localization covers dynamic user feedback", async () => {
  const { i18n } = await import("../docs/assets/js/i18n.js");
  assert.notEqual(i18n.translate("Filtered proxies for operator: Example", "fa"), "Filtered proxies for operator: Example");
  assert.notEqual(i18n.translate("Loaded 42 active nodes into converter", "zh-CN"), "Loaded 42 active nodes into converter");
  assert.notEqual(i18n.translate("Deduplication complete: 9 unique nodes.", "ru"), "Deduplication complete: 9 unique nodes.");
});
