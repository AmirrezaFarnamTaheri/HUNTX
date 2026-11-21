import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  normalizeSubscriptionIndex, subscriptionPaths, filterProtocolEntries
} from "../docs/assets/js/subscription-hub.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

const valid = {
  schema_version: 1,
  scope: "all_time_cumulative",
  health_status: "historical_unverified",
  generated_at: "2026-11-21T00:00:00Z",
  limit_per_protocol: 100,
  protocols: {
    vless: { count: 100, file: "vless.txt", base64_file: "vless_base64.txt" },
    trojan: { count: 6, file: "trojan.txt", base64_file: "trojan_base64.txt" },
    anytls: { count: 0, file: "anytls.txt", base64_file: "anytls_base64.txt" }
  },
  aggregate: { count: 106, file: "all.txt", base64_file: "all_base64.txt" }
};

test("subscription hub reads only historical, capped, trusted file metadata", () => {
  const result = normalizeSubscriptionIndex(valid);
  assert.equal(result.total, 106);
  assert.equal(result.limit, 100);
  assert.equal(result.entries.length, 3);
  assert.equal(result.entries.find((r) => r.name === "vless").count, 100);
  assert.equal(result.entries.find((r) => r.name === "anytls").count, 0);
  assert.equal(result.generatedAt, "2026-11-21T00:00:00Z");
  assert.equal(result.trust, "historical_unverified");
  for (const malicious of [
    { ...valid, scope: "verified_live" },
    { ...valid, health_status: "verified" },
    { ...valid, limit_per_protocol: 0 },
    { ...valid, protocols: { "../admin": { count: 1, file: "../admin.txt" } } },
    { ...valid, protocols: { vless: { count: 101 } } },
    { ...valid, protocols: { vless: { count: 1, file: "trojan.txt" } } },
    { ...valid, aggregate: { count: 9999, file: "all.txt", base64_file: "all_base64.txt" } }
  ]) {
    assert.throws(() => normalizeSubscriptionIndex(malicious), TypeError);
  }
});

test("subscription links use only safe same-project paths, not catalog redirects", () => {
  const urls = subscriptionPaths("vless");
  assert.equal(urls.plain, "subscriptions/latest/vless.txt");
  assert.equal(urls.base64, "subscriptions/latest/vless_base64.txt");
  assert.deepEqual(subscriptionPaths("all"), {
    plain: "subscriptions/latest/all.txt",
    base64: "subscriptions/latest/all_base64.txt"
  });
  for (const unsafe of ["../x", "x/y", "vless?foo", "a b", "☂", "https://evil.example"]) {
    assert.throws(() => subscriptionPaths(unsafe), TypeError);
  }
});

test("protocol search supports case-insensitive filtering and empty categories", () => {
  const entries = normalizeSubscriptionIndex(valid).entries;
  assert.equal(filterProtocolEntries(entries, "VLE").map((x) => x.name).join(","), "vless");
  assert.equal(filterProtocolEntries(entries, "").length, 3);
  assert.deepEqual(filterProtocolEntries(entries, "not-a-protocol"), []);
  assert.equal(filterProtocolEntries(entries, "anytls")[0].count, 0);
});

test("generated markup preserves five workspaces and mounts subscriptions before downloads", async () => {
  const [generated, template, worker, css, ux] = await Promise.all([
    read("../docs/index.html"),
    read("../scripts/update_frontend.py"),
    read("../docs/sw.js"),
    read("../docs/assets/css/subscription-hub.css"),
    read("../UX-CONTRACT.md")
  ]);
  for (const page of [generated, template]) {
    assert.match(page, /id="subscription-hub"/);
    assert.match(page, /id="subscription-hub-status"/);
    assert.match(page, /id="subscription-protocol-search"/);
    assert.match(page, /id="subscription-hub-retry"/);
    assert.match(page, /assets\/js\/subscription-hub\.js/);
    assert.match(page, /assets\/css\/subscription-hub\.css/);
    assert.ok(page.indexOf('id="subscription-hub"') < page.indexOf('id="artifacts-section"'));
    for (const name of ["radar", "proxies", "studio", "decoder", "artifacts"]) {
      assert.match(page, new RegExp('data-tab-target="' + name + '"'));
    }
  }
  assert.match(worker, /assets\/js\/subscription-hub\.js/);
  assert.match(worker, /assets\/css\/subscription-hub\.css/);
  assert.match(worker, /\/subscriptions\/latest\//);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /forced-colors: active/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media\s*\(max-width:/);
  assert.doesNotMatch(css, /@import|url\(https?:\/\//i);
  assert.match(ux, /historical_unverified/);
});
