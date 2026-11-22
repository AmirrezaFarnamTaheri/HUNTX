import test from "node:test";
import assert from "node:assert/strict";
import {
  CORE_PROTOCOLS, normalizeDirection, normalizeSubscriptionIndex,
  subscriptionHref, filterProtocols
} from "../docs/assets/js/subscription-hub.js";

function fixture() {
  const hash = "a".repeat(64);
  return {
    schema_version: 1,
    scope: "all_time_cumulative",
    health_status: "historical_unverified",
    latest_by: "first_seen",
    generated_at: "2026-11-21T10:00:00Z",
    limit_per_protocol: 200,
    protocol_limits: { vless: 150, shadowsocks: 150 },
    protocols: Object.fromEntries(
      CORE_PROTOCOLS.map((name) => [name, {
        count: name === "vless" ? 100 : name === "vmess" ? 12 : 0,
        file: name + ".txt", base64_file: name + "_base64.txt", sha256: hash
      }])
    ),
    aggregate: { count: 112, file: "all.txt", base64_file: "all_base64.txt", sha256: hash }
  };
}

test("every requested proxy protocol has an independent, named subscription", () => {
  assert.deepEqual(CORE_PROTOCOLS, [
    "vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2",
    "socks", "http", "shadowsocks", "shadowsocksr", "tuic",
    "wireguard", "ssh", "shadowtls", "naive", "juicity",
    "mieru", "warp", "dns", "dnstt"
  ]);
  assert.ok(!CORE_PROTOCOLS.includes("others"));
});

test("normalizes historical metadata without inventing health or node counts", () => {
  const directory = normalizeSubscriptionIndex(fixture());
  assert.equal(directory.aggregate.count, 112);
  assert.equal(directory.categories.length, 20);
  assert.equal(directory.categories.find((c) => c.name === "vless").count, 100);
  assert.equal(directory.categories.find((c) => c.name === "vmess").count, 12);
  assert.equal(directory.categories.find((c) => c.name === "dns").count, 0);
  assert.equal(directory.healthStatus, "historical_unverified");
  assert.equal(directory.latestBy, "first_seen");
  assert.equal(directory.limit, 200);
  assert.equal(directory.categories.find((c) => c.name === "vless").limit, 150);
  assert.equal(directory.categories.find((c) => c.name === "vmess").limit, 200);
});

test("new protocol families appear separately, not under an Others group", () => {
  const index = fixture();
  index.protocols["reality-layer"] = {
    count: 7, file: "reality-layer.txt",
    base64_file: "reality-layer_base64.txt", sha256: "b".repeat(64)
  };
  index.aggregate.count = 119; // Exact union after the new independent category.
  const directory = normalizeSubscriptionIndex(index);
  assert.equal(directory.categories.at(-1).name, "reality-layer");
  assert.equal(directory.categories.at(-1).count, 7);
  assert.ok(!directory.categories.some((c) => c.name === "others"));
});

test("rejects path-injection and impossible count metadata", () => {
  const wrongPath = fixture();
  wrongPath.protocols.vless.file = "../../secret.txt";
  assert.throws(() => normalizeSubscriptionIndex(wrongPath), /file|path|invalid/i);
  const tooMany = fixture();
  tooMany.protocols.vmess.count = 201;
  assert.throws(() => normalizeSubscriptionIndex(tooMany), /count|limit|invalid/i);
  const unknownScope = fixture();
  unknownScope.health_status = "live";
  assert.throws(() => normalizeSubscriptionIndex(unknownScope), /historical|invalid/i);
});

test("rejects aggregate totals that do not equal all selected protocol counts", () => {
  const undercount = fixture();
  undercount.aggregate.count = 111;
  assert.throws(() => normalizeSubscriptionIndex(undercount), /aggregate|count|invalid/i);
  const overcount = fixture();
  overcount.aggregate.count = 113;
  assert.throws(() => normalizeSubscriptionIndex(overcount), /aggregate|count|invalid/i);
});

test("safe, deterministic URLs cover per-protocol and aggregate formats", () => {
  assert.equal(subscriptionHref("vless"), "subscriptions/latest/vless.txt");
  assert.equal(subscriptionHref("vless", "base64"), "subscriptions/latest/vless_base64.txt");
  assert.equal(subscriptionHref("all"), "subscriptions/latest/all.txt");
  assert.equal(subscriptionHref("all", "base64"), "subscriptions/latest/all_base64.txt");
  assert.equal(subscriptionHref("index", "json"), "subscriptions/latest/index.json");
  assert.throws(() => subscriptionHref("../secret"), /protocol|invalid/i);
});

test("search and available-only filtering work without reordering protocols", () => {
  const categories = normalizeSubscriptionIndex(fixture()).categories;
  assert.deepEqual(filterProtocols(categories, "v", "all").map((x) => x.name),
    ["vless", "vmess", "naive"]);
  assert.deepEqual(filterProtocols(categories, "", "available").map((x) => x.name),
    ["vless", "vmess"]);
  assert.equal(filterProtocols(categories, "no-such-protocol", "all").length, 0);
});

test("three saved visual directions have a safe deterministic default", () => {
  assert.equal(normalizeDirection("signal"), "signal");
  assert.equal(normalizeDirection("ledger"), "ledger");
  assert.equal(normalizeDirection("orbit"), "orbit");
  assert.equal(normalizeDirection("<script>"), "signal");
  assert.equal(normalizeDirection(null), "signal");
});

test("extension labels cannot resolve inherited Object.prototype properties", () => {
  const data = fixture();
  data.protocols.constructor = {
    count: 1,
    file: "constructor.txt",
    base64_file: "constructor_base64.txt",
    sha256: "c".repeat(64)
  };
  data.aggregate.count += 1;
  const categories = normalizeSubscriptionIndex(data).categories;
  const extension = categories.find((item) => item.name === "constructor");
  assert.equal(extension.label, "constructor");
  assert.equal(extension.limit, 200, "prototype properties cannot override caps");
  assert.deepEqual(filterProtocols(categories, "constructor").map((item) => item.name),
    ["constructor"]);
});
