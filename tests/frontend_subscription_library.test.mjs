import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";

import {
  REQUIRED_PROTOCOLS,
  parseSubscriptionIndex,
  filterProtocols,
  subscriptionURL
} from "../docs/assets/js/subscription-library.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
const hash = "a".repeat(64);

function fixture() {
  return {
    schema_version: 1,
    scope: "all_time_cumulative",
    health_status: "historical_unverified",
    latest_by: "first_seen",
    generated_at: "2026-11-21T10:00:00Z",
    limit_per_protocol: 100,
    protocols: {
      vless: { count: 100, file: "vless.txt", base64_file: "vless_base64.txt", sha256: hash },
      trojan: { count: 8, file: "trojan.txt", base64_file: "trojan_base64.txt", sha256: hash },
      wireguard: { count: 0, file: "wireguard.txt", base64_file: "wireguard_base64.txt", sha256: hash },
      "future-protocol": { count: 2, file: "future-protocol.txt", base64_file: "future-protocol_base64.txt", sha256: hash }
    },
    aggregate: { count: 110, file: "all.txt", base64_file: "all_base64.txt", sha256: hash }
  };
}

test("subscription hub recognises all 20 named protocols without an Others bucket", () => {
  assert.equal(REQUIRED_PROTOCOLS.length, 20);
  for (const name of ["vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2",
    "socks", "http", "shadowsocks", "shadowsocksr", "tuic", "wireguard",
    "ssh", "shadowtls", "naive", "juicity", "mieru", "warp", "dns", "dnstt"]) {
    assert.ok(REQUIRED_PROTOCOLS.includes(name), name);
  }
  assert.ok(!REQUIRED_PROTOCOLS.includes("others"));
});

test("read historical manifest safely without implying that proxies are verified", () => {
  const index = parseSubscriptionIndex(fixture());
  assert.equal(index.total, 110);
  assert.equal(index.protocolCount, 4);
  assert.equal(index.scope, "historical_unverified");
  assert.equal(index.records[0].name, "vless");
  assert.equal(index.records.find((record) => record.name === "wireguard").count, 0);
  assert.equal(index.records.at(-1).name, "future-protocol");
});

test("rejects missing or mismatched first-seen ordering metadata", () => {
  const wrong = fixture();
  wrong.latest_by = "last_seen";
  assert.throws(() => parseSubscriptionIndex(wrong), /historical|invalid/i);
  const missing = fixture();
  delete missing.latest_by;
  assert.throws(() => parseSubscriptionIndex(missing), /historical|invalid/i);
});

test("search and available-only toggle compose without hiding future protocol categories", () => {
  const records = parseSubscriptionIndex(fixture()).records;
  assert.deepEqual(filterProtocols(records, "TROJ", false).map((x) => x.name), ["trojan"]);
  assert.deepEqual(filterProtocols(records, "wire", true).map((x) => x.name), []);
  assert.deepEqual(filterProtocols(records, "future", true).map((x) => x.name), ["future-protocol"]);
  assert.equal(filterProtocols(records, "", false).length, 4);
});

test("construct absolute same-origin URLs without accepting an untrusted path", () => {
  const root = "https://example.github.io/HUNTX/subscriptions.html";
  assert.equal(subscriptionURL("vless", "text", root),
    "https://example.github.io/HUNTX/subscriptions/latest/vless.txt");
  assert.equal(subscriptionURL("all", "base64", root),
    "https://example.github.io/HUNTX/subscriptions/latest/all_base64.txt");
  assert.equal(subscriptionURL("index", "json", root),
    "https://example.github.io/HUNTX/subscriptions/latest/index.json");
  assert.throws(() => subscriptionURL("../private", "text", root), /protocol/i);
  assert.throws(() => subscriptionURL("vless", "yaml", root), /format/i);
});

test("reject malformed, mislabeled and impossible feed metadata instead of fabricating counts", () => {
  const bad = fixture();
  bad.protocols.vless.count = 101;
  assert.throws(() => parseSubscriptionIndex(bad), /count/i);

  const foreign = fixture();
  foreign.protocols["../escape"] = { count: 1 };
  assert.throws(() => parseSubscriptionIndex(foreign), /protocol/i);

  const stale = fixture();
  stale.health_status = "verified";
  assert.throws(() => parseSubscriptionIndex(stale), /historical/i);

  const inconsistent = fixture();
  inconsistent.aggregate.count = 109;
  assert.throws(() => parseSubscriptionIndex(inconsistent), /aggregate/i);

  const renamed = fixture();
  renamed.protocols.vless.file = "redirect.txt";
  assert.throws(() => parseSubscriptionIndex(renamed), /file/i);
});

test("dedicated hub is linked from dashboard and preserved generator", async () => {
  const [page, index, generator, worker] = await Promise.all([
    read("../docs/subscriptions.html"),
    read("../docs/index.html"),
    read("../scripts/update_frontend.py"),
    read("../docs/sw.js")
  ]);
  assert.match(page, /data-design="signal"/);
  assert.match(page, /id="protocol-grid"/);
  assert.match(page, /id="subscription-search"/);
  assert.match(page, /assets\/js\/subscription-library\.js/);
  assert.match(page, /assets\/css\/subscription-library\.css/);
  assert.match(page, /index\.html#artifacts/);
  for (const source of [index, generator]) {
    assert.match(source, /href="subscriptions\.html"/);
  }
  for (const asset of ["assets/css/subscription-library.css", "assets/js/subscription-library.js"]) {
    assert.ok(worker.includes(asset), asset);
  }
  // Standalone HTML is an offline-capable shell, while the metadata is network-only.
  assert.match(worker, /['"]\.\/subscriptions\.html['"]/);
  assert.match(worker, /event\.request\.mode === 'navigate'/);
  assert.ok(worker.includes("path.includes('/subscriptions/latest/')"));
});

test("service worker does not accept cached metadata as an online subscription index", async () => {
  const worker = await read("../docs/sw.js");
  const handlers = new Map();
  const cached = new Response(JSON.stringify(fixture()), {
    status: 200, headers: { "content-type": "application/json" }
  });
  let online = true;
  let cacheWrites = 0;
  runInNewContext(worker, {
    self: { addEventListener(name, callback) { handlers.set(name, callback); } },
    caches: {
      match: async () => cached.clone(),
      open: async () => ({
        put: async () => { cacheWrites += 1; }
      })
    },
    fetch: async () => {
      if (!online) throw new TypeError("Offline");
      return new Response(JSON.stringify(fixture()), { status: 200 });
    },
    Response, URL
  });

  const request = new Request("https://example.invalid/HUNTX/subscriptions/latest/index.json");
  const simulateFetch = async () => {
    let result;
    handlers.get("fetch")({ request, respondWith(response) { result = response; } });
    return result;
  };

  assert.equal((await simulateFetch()).status, 200, "Online metadata should remain readable");
  assert.equal(cacheWrites, 0, "Historical index is not cached as fresh data");
  online = false;
  const response = await simulateFetch();
  assert.equal(response.status, 503, "Cached index must not be used after network failure");
});
