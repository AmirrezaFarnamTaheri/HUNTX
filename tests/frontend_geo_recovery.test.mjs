import test from "node:test";
import assert from "node:assert/strict";
import {
  AppState,
  clusterGlobeHubs,
  getRegionPresentation,
  normalizeDecodedProxyInput,
} from "../docs/assets/js/app.js";

test("live decoder retains VMess endpoints embedded in decoded.add", () => {
  const entry = {
    protocol: "vmess", raw: "vmess://synthetic-base64",
    decoded: {
      v: "2", ps: "🇩🇪 Synthetic VMess", add: "edge.example.com",
      port: "8443", id: "11111111-2222-4333-8444-555555555555",
      net: "ws", tls: "tls", host: "cdn.example.com", sni: "tls.example.com",
    },
  };
  const result = normalizeDecodedProxyInput(entry, 7);
  assert.equal(result.proto, "vmess");
  assert.equal(result.tag, entry.decoded.ps);
  assert.equal(result.host, "edge.example.com");
  assert.equal(result.port, 8443);
  assert.equal(result.params.type, "ws");
  assert.equal(result.params.security, "tls");
  assert.equal(result.user, entry.decoded.id);
});

test("live artifact mapping displays VMess instead of silently dropping it", async t => {
  const app = Object.create(AppState.prototype);
  app.renderDataStatus = () => {};
  app.loadVerifiedJsonArtifact = async () => ({
    entries: [{
      protocol: "vmess", raw: "vmess://synthetic-only",
      decoded: {
        ps: "vmess-fixture", add: "vmess.example.com", port: "443",
        id: "11111111-2222-4333-8444-555555555555", net: "grpc",
        tls: "tls", sni: "cdn.example.com",
      },
    }],
  });
  t.mock.method(globalThis, "fetch", async () => ({
    ok: true, json: async () => ({
      generated_at: "2099-01-01T00:00:00Z",
      files: [{ filename: "all_sources.json", path: "artifacts/release/all_sources.json", sha256: "a".repeat(64) }],
    }),
  }));
  await app.loadLiveData();
  assert.equal(app.liveDataState, "ready");
  assert.equal(app.proxies.length, 1);
  assert.equal(app.proxies[0].protocol, "vmess");
  assert.equal(app.proxies[0].server, "vmess.example.com");
  assert.equal(app.proxies[0].name, "vmess-fixture");
  assert.equal(app.proxies[0].security, "tls");
  assert.equal(app.proxies[0].transport, "grpc");
});

test("TLS-implied and UDP-only proxy modes stay accurate in live view", () => {
  for (const protocol of ["trojan", "hysteria2", "tuic", "anytls"]) {
    const connection = normalizeDecodedProxyInput({ protocol, address: "edge.example.com", port: 443 }, 0);
    assert.equal(connection.proto, protocol);
    assert.equal(connection.defaultSecurity, "tls");
    if (["hysteria2", "tuic"].includes(protocol)) assert.equal(connection.defaultTransport, "udp");
  }
});

test("country attribution without measured coordinates must not fabricate globe city pins", () => {
  const known = {
    country: "DE", country_name: "Germany",
    geo_verified: true, geo_source: "server-country-pddl",
    latitude: null, longitude: null, latency: 12,
  };
  assert.equal(getRegionPresentation(known).confidence, "provider");
  assert.deepEqual(clusterGlobeHubs([known]), []);
  assert.deepEqual(clusterGlobeHubs([{...known,latitude:"",longitude:""}]), []);
});

test("globe uses verified observation coordinates, not hard-coded city hubs", () => {
  const hubs = clusterGlobeHubs([{
    country: "NL", country_name: "Netherlands", geo_verified: true,
    geo_source: "ip-api", latitude: 52.08, longitude: 4.31, latency: 30,
  }]);
  assert.equal(hubs.length, 1);
  assert.equal(hubs[0].lat, 52.08);
  assert.equal(hubs[0].lon, 4.31);
  assert.match(hubs[0].name, /Netherlands/);
  assert.doesNotMatch(hubs[0].name, /Amsterdam/);
  assert.equal(hubs[0].count, 1);
});
