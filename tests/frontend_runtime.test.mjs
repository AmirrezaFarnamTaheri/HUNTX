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

test("Cloudflare anycast keeps provider evidence without invented geography", () => {
  const geo = resolveGeoAndCarrier("104.21.12.34", "", "");
  assert.equal(geo.country, "ZZ");
  assert.equal(geo.carrier, "Cloudflare Anycast");
  assert.equal(geo.org, "Cloudflare");
  assert.equal(geo.latitude, null);
  assert.equal(geo.longitude, null);
  assert.equal(geo.geo_source, "anycast-provider");
});


test("globe module owns touch inactivity and does not treat cancellation as click", async () => {
  const source = await (await import("node:fs/promises")).readFile(new URL("../docs/assets/js/globe.js", import.meta.url), "utf8");
  assert.match(source, /function onPointerCancel/);
  assert.match(source, /pointercancel", onPointerCancel/);
  assert.doesNotMatch(source, /pointercancel", onPointerUp/);
  assert.match(source, /scheduleTouchInactivityTimeout/);
  assert.match(source, /clearTimeout\(touchInactivityTimer\)/);
  assert.match(source, /const sourceHubs = Array\.isArray\(customHubs\) \? customHubs : DEFAULT_HUBS/);
  assert.doesNotMatch(source, /customHubs\.length > 0/);
  assert.match(source, /function onPointerUp\(e\) \{\r?\n {4}if \(e\.pointerType === "touch"\) noteTouchActivity\(\);/);
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


test("region localization distinguishes badge casing", async () => {
  const { i18n } = await import("../docs/assets/js/i18n.js");
  assert.equal(i18n.translate("5 Regions", "ru"), "5 регионов");
  assert.equal(i18n.translate("5 REGIONS", "ru"), "5 РЕГИОНОВ");
});


// Converter input must survive decoding before client-specific serialization.
test("decoder preserves UTF-8 names and subscription payloads", async () => {
  const { decodeProxyURI, extractAllURIs } = await import("../docs/assets/js/decoder.js");
  const name = "Тегеран σταν 東京";
  const uri = "vmess://" + Buffer.from(JSON.stringify({ ps: name, add: "example.com", port: 443, id: "test-id" })).toString("base64");
  assert.equal(decodeProxyURI(uri).name, name);
  const line = "trojan://password@example.com:443#" + name;
  assert.deepEqual(extractAllURIs(Buffer.from(line.replaceAll(" ", "%20")).toString("base64")), [line.replaceAll(" ", "%20")]);
});

test("Shadowsocks preserves colon-containing and empty passwords", async () => {
  const { decodeProxyURI } = await import("../docs/assets/js/decoder.js");
  for (const password of ["pass:word:123", ""]) {
    const auth = "aes-256-gcm:" + password;
    for (const uri of [
      "ss://" + Buffer.from(auth).toString("base64") + "@example.com:8388",
      "ss://" + Buffer.from(auth + "@example.com:8388").toString("base64")
    ]) {
      const node = decodeProxyURI(uri);
      assert.equal(node.password, password);
      assert.equal(node.cipher, "aes-256-gcm");
      assert.equal(node.server, "example.com");
    }
  }
});

test("VLESS flow reaches the Sing-box outbound", async () => {
  const { decodeProxyURI, nodeToSingboxOutbound } = await import("../docs/assets/js/decoder.js");
  const uri = "vless://test-id@example.com:443?security=tls&flow=xtls-rprx-vision";
  assert.equal(nodeToSingboxOutbound(decodeProxyURI(uri)).flow, "xtls-rprx-vision");
  assert.equal(decodeProxyURI("vless://test-id@example.com:443").flow, "");
});

test("Sing-box config references only outbounds it declares", async () => {
  // The shipped backend emits hijack-dns for DNS and no rule sets; the client-side
  // preview must be equally self-contained so clients never reject the config.
  const { decodeProxyURI, buildSingboxConfig } = await import("../docs/assets/js/decoder.js");
  const nodes = [
    decodeProxyURI("vless://test-id@example.com:443?security=tls&flow=xtls-rprx-vision#n1"),
    decodeProxyURI("trojan://password@example.com:443#n2"),
  ];
  const config = buildSingboxConfig(nodes);
  const tags = new Set(config.outbounds.map((o) => o.tag));
  // Every route rule outbound target must exist (dns hijack needs no target).
  for (const rule of config.route.rules) {
    if (Object.prototype.hasOwnProperty.call(rule, "outbound")) {
      assert.ok(tags.has(rule.outbound), `route rule targets undeclared outbound: ${rule.outbound}`);
    }
  }
  assert.ok(tags.has(config.route.final), "route.final must name a declared outbound");
  // No undeclared rule sets (the backend ships none)."
  const json = JSON.stringify(config);
  assert.equal(json.includes("rule_set"), false, "config must not reference undeclared rule sets");
  assert.equal(json.includes("dns-out"), false, "dns hijack must not reference an undeclared dns-out outbound");
  assert.ok(config.route.rules.some((r) => r.protocol === "dns" && r.action === "hijack-dns"));
  assert.ok(config.route.rules.some((r) => r.ip_is_private === true));
});

test("VLESS and Trojan query paths are decoded exactly once", async () => {
  const { decodeProxyURI } = await import("../docs/assets/js/decoder.js");
  for (const scheme of ["vless", "trojan"]) {
    const base = scheme + "://credential@example.com:443";
    assert.equal(decodeProxyURI(base + "?type=ws&path=%2Fapi%252Fws%3Fmode%3Dreal").path, "/api%2Fws?mode=real");
    assert.equal(decodeProxyURI(base).path, "");
  }
});

test("an integrity-verified empty release is authoritative", async (t) => {
  const app = Object.create(AppState.prototype);
  // The Go site generator emits exactly this shape for a verified empty
  // release: intentional_empty with a null files list and no artifacts.
  const catalog = {
    intentional_empty: true,
    schema_version: 1,
    generated_at: "2026-09-17T00:00:00Z",
    release_manifest: "artifacts/release/manifest.json",
    total_files: 0,
    total_size: 0,
    files: null,
  };
  t.mock.method(globalThis, "fetch", async () => ({ ok: true, json: async () => catalog }));
  app.renderDataStatus = () => {};
  let usedFallback = false;
  app.loadBundledFallback = async () => { usedFallback = true; };
  await app.loadLiveData();
  assert.equal(usedFallback, false, "bundled sample data must not back a verified empty release");
  assert.equal(app.liveDataState, "ready");
  assert.equal(app.catalog, catalog);
  assert.deepEqual(app.proxies, []);
  assert.deepEqual(app.globeHubs, []);
});

test("fallback is restored after bundled to live to unavailable transition", async (t) => {
  const app = Object.create(AppState.prototype);
  app.renderDataStatus = () => {};
  await app.loadBundledFallback();
  const bundledCatalog = app.catalog;
  const bundledProxies = structuredClone(app.proxies);
  const catalog = { files: [{ filename: "all_sources.npvt.decoded.json", path: "artifacts/release/live.json", sha256: "b".repeat(64) }] };
  let available = true;
  t.mock.method(globalThis, "fetch", async () => ({ ok: available, json: async () => catalog }));
  app.loadVerifiedJsonArtifact = async () => ({ entries: [{ protocol: "vless", address: "example.com", tag: "live" }] });
  await app.loadLiveData();
  assert.equal(app.liveDataState, "ready");
  assert.equal(app.catalog, catalog);
  available = false;
  await app.loadLiveData();
  assert.equal(app.liveDataState, "stale");
  assert.equal(app.catalog, bundledCatalog);
  assert.deepEqual(app.proxies, bundledProxies);
});
