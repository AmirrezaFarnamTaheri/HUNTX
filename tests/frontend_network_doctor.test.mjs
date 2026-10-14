import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createRecoveryPlan,
  classifyManualOutcome,
  formatSupportSummary,
  summarizeCatalog,
  checkPublishedCatalog
} from "../docs/assets/js/network-doctor.js";

const platforms = ["android", "ios", "desktop"];
const networks = ["wifi", "mobile"];
const symptoms = ["subscription", "timeout", "no_traffic", "tls", "slow", "network_only"];

test("all supported device, network and symptom combinations produce three actionable steps", () => {
  for (const platform of platforms) {
    for (const network of networks) {
      for (const symptom of symptoms) {
        const plan = createRecoveryPlan({ platform, network, symptom });
        assert.equal(plan.actions.length, 3);
        assert.ok(plan.actions.every((item) => item.title && item.description));
        assert.ok(plan.deviceHint);
        assert.match(plan.safety, /TLS|certificate/i);
      }
    }
  }
});

test("network comparison suggests the other network without claiming a repair", () => {
  const wifi = createRecoveryPlan({ platform: "android", network: "wifi", symptom: "network_only" });
  const mobile = createRecoveryPlan({ platform: "ios", network: "mobile", symptom: "timeout" });
  assert.match(wifi.actions[0].title, /mobile data/);
  assert.match(mobile.actions[1].title, /Wi-Fi/);
  assert.doesNotMatch(wifi.actions.map((item) => item.title).join(" "), /verified|revived/i);
});

test("TLS guidance preserves verification and avoids inventing credentials", () => {
  const plan = createRecoveryPlan({ platform: "desktop", network: "wifi", symptom: "tls" });
  const text = JSON.stringify(plan);
  assert.match(text, /Do not disable certificate verification/);
  assert.doesNotMatch(text, /skip-cert-verify|allowInsecure|insecure\s*:\s*true/i);
});

test("unsupported inputs are rejected rather than interpolated into UI", () => {
  assert.throws(() => createRecoveryPlan({ platform: "<img>", network: "wifi", symptom: "tls" }), TypeError);
  assert.throws(() => createRecoveryPlan({ platform: "ios", network: "evil", symptom: "tls" }), TypeError);
  assert.throws(() => createRecoveryPlan({ platform: "ios", network: "wifi", symptom: "evil" }), TypeError);
});

test("manual recovery of the original is not presented as independently verified", () => {
  const outcome = classifyManualOutcome({ originalWorks: "yes" });
  assert.equal(outcome.code, "reported-original");
  assert.equal(outcome.verified, false);
  assert.match(outcome.message, /user.reported/i);
});

test("a working replacement is not presented as revival of the original", () => {
  const outcome = classifyManualOutcome({ originalWorks: "no", alternativeWorks: "yes" });
  assert.equal(outcome.code, "reported-alternative");
  assert.equal(outcome.verified, false);
  assert.match(outcome.message, /original/i);
});

test("disabling TLS verification overrides any claimed success", () => {
  const outcome = classifyManualOutcome({
    originalWorks: "yes", alternativeWorks: "yes", tlsVerificationDisabled: true
  });
  assert.equal(outcome.code, "unsafe");
  assert.equal(outcome.verified, false);
});

test("unknown, invalid, and unconfirmed outcomes cannot be called recovered", () => {
  assert.equal(classifyManualOutcome({}).code, "unresolved");
  assert.equal(classifyManualOutcome({ originalWorks: "no", alternativeWorks: "no" }).verified, false);
  assert.throws(() => classifyManualOutcome({ originalWorks: "maybe" }), TypeError);
  assert.throws(() => classifyManualOutcome({ tlsVerificationDisabled: "false" }), TypeError);
});

test("support summary uses only allowlisted values and omits user secrets", () => {
  const report = formatSupportSummary({
    platform: "ios", network: "wifi", symptom: "timeout",
    originalWorks: "no", alternativeWorks: "yes",
    secret: "my-proxy-credential", ssid: "private-wifi",
    uri: "trojan://password@example.org:443"
  });
  assert.match(report, /self-reported/i);
  assert.match(report, /reported-alternative/);
  assert.doesNotMatch(report, /my-proxy-credential|private-wifi|trojan:\/\/|example.org/);
  assert.throws(() => formatSupportSummary({ platform: "unexpected", network: "wifi", symptom: "timeout" }), TypeError);
});

test("catalog status reports only published metadata, never proxy health", () => {
  const summary = summarizeCatalog({
    generated_at: "2026-10-14T01:25:09Z",
    files: [
      { filename: "all_sources_base64.txt", tags: ["release", "subscription"] },
      { filename: "all_sources.json", tags: ["release", "decoded"] }
    ]
  });
  assert.equal(summary.state, "available");
  assert.equal(summary.subscriptionCount, 1);
  assert.match(summary.message, /not verify.*connectivity/i);
  assert.equal(summary.generatedAt, "2026-10-14T01:25:09Z");
});

test("verified empty release is not mistaken for working subscriptions", () => {
  const summary = summarizeCatalog({ intentional_empty: true, files: [], generated_at: "2026-10-14T00:00:00Z" });
  assert.equal(summary.state, "empty");
  assert.equal(summary.subscriptionCount, 0);
  assert.doesNotMatch(summary.message, /working proxies available/i);
});

test("untrusted catalog structures are rejected", () => {
  assert.throws(() => summarizeCatalog(null), TypeError);
  assert.throws(() => summarizeCatalog({ files: "not-an-array" }), TypeError);
  assert.throws(() => summarizeCatalog({ files: [] }), TypeError);
});

test("catalog fetch is same-origin, uncached and returns an inconclusive state on failure", async () => {
  const calls = [];
  const success = await checkPublishedCatalog({
    fetcher: async (url, options) => {
      calls.push([url, options]);
      return { ok: true, json: async () => ({ files: [{ tags: ["subscription"] }] }) };
    }
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "./catalog.json");
  assert.equal(calls[0][1].cache, "no-store");
  assert.equal(success.state, "available");
  const failure = await checkPublishedCatalog({ fetcher: async () => { throw new Error("offline"); } });
  assert.equal(failure.state, "unavailable");
  assert.equal(failure.subscriptionCount, 0);
});

test("dashboard navigation and generated template both link to Network Doctor", async () => {
  const html = await readFile(new URL("../docs/index.html", import.meta.url), "utf8");
  const generator = await readFile(new URL("../scripts/update_frontend.py", import.meta.url), "utf8");
  const page = await readFile(new URL("../docs/network-doctor.html", import.meta.url), "utf8");
  const worker = await readFile(new URL("../docs/sw.js", import.meta.url), "utf8");
  assert.match(html, /href="network-doctor\.html"/);
  assert.match(generator, /href="network-doctor\.html"/);
  assert.match(page, /id="network-doctor-form"/);
  assert.match(page, /assets\/js\/network-doctor-ui\.js/);
  assert.match(worker, /\.\/network-doctor\.html/);
  assert.match(worker, /\.\/assets\/js\/network-doctor\.js/);
});
