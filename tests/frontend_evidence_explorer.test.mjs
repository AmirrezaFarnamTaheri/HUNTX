import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  AppState, getProxyEvidence, getRegionPresentation, countProxyEvidence,
  displayPublishedName
} from "../docs/assets/js/app.js";

const tcp = { id: "tcp", name: "Node A", protocol: "vless", transport: "ws", server: "a.example.net", port: 443,
  health_evidence: "tcp_connect_only", probe_ok: true, latency: 82, country: "DE",
  country_name: "Germany", geo_verified: false, geo_source: "unverified_country_hint", health_grade: "A+" };
const failed = { ...tcp, id: "failed", name: "Node B", health_evidence: "tcp_failed_from_publish_vantage", probe_ok: false, latency: null };
const authenticated = { ...tcp, id: "auth", name: "Node C", health_evidence: "fresh_authenticated_protocol",
  health_grade: "A", geo_source: "ip-api", geo_verified: true };
const unknown = { ...tcp, id: "unknown", name: "Node D", health_evidence: "", probe_ok: null, latency: null, country: "ZZ" };

test("observation badges distinguish authenticated, TCP-only, failed TCP and unmeasured evidence", () => {
  assert.equal(getProxyEvidence(authenticated).id, "authenticated");
  assert.equal(getProxyEvidence(tcp).id, "tcp");
  assert.equal(getProxyEvidence(tcp).label, "TCP reachable");
  assert.match(getProxyEvidence(tcp).detail, /does not verify proxy authentication/i);
  assert.equal(getProxyEvidence(failed).id, "tcp_failed");
  assert.equal(getProxyEvidence(failed).terminal, false);
  assert.equal(getProxyEvidence(unknown).id, "unmeasured");
  assert.equal(getProxyEvidence({ ...tcp, health_evidence: "", probe_ok: null, health_grade: "A+" }).id, "unmeasured");
});

test("authenticated protocol failures cannot masquerade as failed TCP connects", () => {
  const protocolFailure = { ...authenticated, health_evidence: "failed_authenticated_protocol",
    health_grade: "F", probe_ok: true, latency: 1 };
  assert.equal(getProxyEvidence(protocolFailure).id, "protocol_failed");
  assert.equal(getProxyEvidence(protocolFailure).terminal, false);
  assert.deepEqual(countProxyEvidence([protocolFailure, tcp]), {
    all: 2, authenticated: 0, protocol_failed: 1, tcp: 1, tcp_failed: 0, unmeasured: 0
  });
  const app = Object.create(AppState.prototype);
  assert.notEqual(app.getHealthScore(protocolFailure).grade, "F");
  assert.ok(app.getHealthSortValue(tcp) > app.getHealthSortValue(protocolFailure));
  assert.ok(app.getHealthSortValue(authenticated) > app.getHealthSortValue(tcp));
});

test("hostnames and SNI hints must not fabricate Finland geography", () => {
  const source = { ...tcp, country: "FI", geo_source: "inferred", geo_verified: true };
  assert.equal(getRegionPresentation(source).confidence, "hint");
  assert.equal(getRegionPresentation({ ...tcp, country: "ZZ" }).label, "Unknown region");
});

test("country flags are marked as hints unless accompanied by genuine geo evidence", () => {
  const hint = getRegionPresentation(tcp);
  assert.equal(hint.code, "DE");
  assert.equal(hint.confidence, "hint");
  assert.match(hint.flag, /\?/);
  assert.match(hint.detail, /unverified/i);
  const verified = getRegionPresentation(authenticated);
  assert.equal(verified.confidence, "provider");
  assert.equal(verified.flag, "🇩🇪");
  assert.match(verified.detail, /estimate/i);
  const unlocated = getRegionPresentation(unknown);
  assert.equal(unlocated.code, "ZZ");
  assert.equal(unlocated.flag, "🌐");
  assert.equal(unlocated.confidence, "unknown");
  assert.equal(getRegionPresentation({ ...tcp, country: "", geo_verified: false }).flag, "🌐");
});

test("identity-safe published names preserve existing flag remarks without country duplication", () => {
  const remark = "🇩🇪 DE | VLESS-WS-TLS | AS13335 | abc123def0";
  assert.equal(displayPublishedName(remark, "vless"), remark);
  assert.equal(displayPublishedName("friendly upstream name", "trojan"), "friendly upstream name");
  assert.equal(displayPublishedName("", "hysteria2"), "HYSTERIA2 · Unnamed");
  assert.equal(displayPublishedName(null, "vmess"), "VMESS · Unnamed");
});

test("evidence filters remain independent of grade and country facet", () => {
  const items = [tcp, failed, authenticated, unknown];
  assert.deepEqual(countProxyEvidence(items), { all: 4, authenticated: 1, protocol_failed: 0, tcp: 1, tcp_failed: 1, unmeasured: 1 });
  const app = Object.create(AppState.prototype);
  Object.assign(app, {
    proxies: items, searchQuery: "", selectedProtocol: "ALL", selectedTransport: "ALL", selectedCountry: "ALL",
    selectedOperator: "ALL", selectedGrade: "ALL", selectedSecurity: "ALL", selectedPort: "ALL",
    selectedEvidence: "tcp_failed", sortBy: "name_asc"
  });
  assert.deepEqual(app.getFilteredProxies().map(node => node.id), ["failed"]);
  app.selectedEvidence = "authenticated";
  assert.deepEqual(app.getFilteredProxies().map(node => node.id), ["auth"]);
  app.selectedEvidence = "ALL";
  assert.equal(app.getFilteredProxies().length, 4);
});

test("dashboard surfaces verified measurement meaning and never prefixes published remarks with guessed country", async () => {
  const js = await readFile(new URL("../docs/assets/js/app.js", import.meta.url), "utf8");
  assert.doesNotMatch(js, /name:\s*`\$\{geo\.country\}-\$\{tag\}`/);
  assert.match(js, /id="evidence-overview"/);
  assert.match(js, /class="btn-evidence-filter/);
  assert.match(js, /aria-pressed="\$\{this\.selectedEvidence === option\.id\}"/);
  assert.match(js, /role="status" aria-live="polite"/);
  assert.match(js, /TCP connect does not verify proxy authentication/);
});
