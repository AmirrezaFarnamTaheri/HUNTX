import test from "node:test";
import assert from "node:assert/strict";
import {
  decodeProxyURI,
  extractAllURIs,
  isProxyURILine,
  convertProxyBatch,
  PROXY_URI_SCHEMES
} from "../docs/assets/js/decoder.js";
import { pickSubscriptionArtifact, AppState } from "../docs/assets/js/app.js";

// The pipeline can emit any scheme in src/huntx/core/router.py::_PROXY_SCHEMES.
// The extractor used to carry a hand-written ten-entry list, so a conversion of
// the published feed silently lost every socks://, ssr://, hysteria://,
// wireguard://, anytls:// and warp:// node. "Import all proxies" that quietly
// returns a subset is worse than a visible failure.
const PIPELINE_SCHEMES = [
  "vmess", "vless", "trojan", "ss", "ssr",
  "hysteria2+realm+http", "hysteria2+realm", "hysteria2", "hy2", "hysteria",
  "tuic", "wireguard", "wg",
  "socks", "socks5", "socks4", "socks4a",
  "anytls", "juicity", "mieru", "mierus", "warp",
  "shadowtls", "naive+https", "naive+quic",
  "ssh", "dns", "dnstt"
];

test("the URI extractor recognises every scheme the pipeline can emit", () => {
  for (const scheme of PIPELINE_SCHEMES) {
    assert.ok(PROXY_URI_SCHEMES.includes(scheme), `missing scheme ${scheme}`);
    assert.ok(isProxyURILine(`${scheme}://user@host:443#node`), `${scheme}:// is not recognised`);
  }
});

test("http and https are not share links", () => {
  // They match ordinary web links, so only an authenticated CONNECT proxy
  // should ever be collected.
  assert.equal(isProxyURILine("https://example.com/page"), false);
  assert.equal(isProxyURILine("http://cdn.example.com/x"), false);
});

test("a share link is matched at the start of the line, not anywhere inside it", () => {
  const uri = "vless://uuid@example.com:443?host=proxy.example.com&sni=http://cdn.example.com#node";
  assert.equal(isProxyURILine(uri), true);
  // A substring scan for http:// used to shred this line at the first "http://".
  assert.deepEqual(extractAllURIs(uri), [uri]);
});

test("every line of a feed is collected, with nothing dropped", () => {
  const feed = [
    "vless://a@example.com:443#vless-1",
    "socks://MTExOjExMQ@198.51.100.1:11310#socks-1",
    "socks5://198.51.100.2:1080#socks5-1",
    "ssr://token@198.51.100.3:443#ssr-1",
    "warp://key@198.51.100.4:2408#warp-1",
    "wireguard://key@198.51.100.5:51820#wg-1"
  ].join("\n");
  const extracted = extractAllURIs(feed);
  assert.equal(extracted.length, feed.split("\n").length);
  // The two schemes the old list missed are the point of this test.
  assert.ok(extracted.some((u) => u.startsWith("socks://")));
  assert.ok(extracted.some((u) => u.startsWith("ssr://")));
  assert.ok(extracted.some((u) => u.startsWith("warp://")));
  assert.ok(extracted.some((u) => u.startsWith("wireguard://")));
});

test("a pasted base64 subscription expands to every node, not one", () => {
  const lines = [
    "vless://a@example.com:443#vless-1",
    "trojan://secret@198.51.100.6:443#trojan-1",
    "hysteria2://pw@198.51.100.7:8443#hy2-1"
  ];
  const body = Buffer.from(lines.join("\n"), "utf8").toString("base64");
  const decoded = decodeProxyURI(body);
  assert.equal(decoded.protocol, "subscription");
  assert.equal(decoded.lines.length, lines.length);
  assert.equal(extractAllURIs(decoded.raw).length, lines.length);
});

test("the batch converter turns a pasted subscription into a full config", () => {
  const lines = Array.from({ length: 25 }, (_, i) => `vless://id${i}@198.51.100.${i + 1}:443#vless-${i + 1}`);
  const body = Buffer.from(lines.join("\n"), "utf8").toString("base64");
  const singbox = JSON.parse(convertProxyBatch(body, "singbox"));
  const proxies = singbox.outbounds.filter((o) => o.type === "vless");
  assert.equal(proxies.length, lines.length);
  // The round trip back to a subscription body preserves every node.
  const rebuilt = Buffer.from(convertProxyBatch(body, "b64sub"), "base64").toString("utf8");
  assert.equal(rebuilt.trim().split("\n").length, lines.length);
});

test("Sing-box, Xray and Clash feeds are valid node subscriptions", () => {
  const jsonFeeds = [
    { filename: "all_sources_singbox.json", path: "p/s", tags: ["release", "subscription", "singbox", "json-nodes", "multi-node"] },
    { filename: "all_sources_xray.json", path: "p/x", tags: ["release", "subscription", "xray", "json-nodes", "multi-node"] },
    { filename: "all_sources_clash.yaml", path: "p/c", tags: ["release", "subscription", "clash", "mihomo", "yaml-nodes", "multi-node"] }
  ];

  const jsonChoice = pickSubscriptionArtifact(jsonFeeds);
  assert.ok(jsonChoice);
  assert.equal(jsonChoice.filename, "all_sources_singbox.json");

  const clashOnly = pickSubscriptionArtifact([jsonFeeds[2]]);
  assert.ok(clashOnly);
  assert.equal(clashOnly.filename, "all_sources_clash.yaml");

  const withBase64 = [...jsonFeeds, { filename: "all_sources_base64.txt", path: "p/b", tags: ["release", "subscription", "base64", "multi-node"] }];
  assert.equal(pickSubscriptionArtifact(withBase64).filename, "all_sources_base64.txt");
});

test("the dashboard resolves its subscription link from the published catalog", () => {
  assert.ok(AppState.prototype.resolveSubscriptionArtifact, "catalog-driven resolver is wired");
  const resolved = AppState.prototype.resolveSubscriptionArtifact.call(
    { catalog: { files: [{ filename: "a_base64.txt", path: "p/b", tags: ["release", "subscription", "base64"] }] } }
  );
  assert.equal(resolved.label, "Base64");
  assert.equal(AppState.prototype.resolveSubscriptionArtifact.call({ catalog: { files: [] } }), null);
});

test("SOCKS links decode with their real credentials, not an opaque blob", () => {
  const encoded = Buffer.from("111:111", "utf8").toString("base64");
  const node = decodeProxyURI(`socks://${encoded}@47.76.229.132:11310#socks-1`);
  assert.equal(node.protocol, "socks");
  assert.equal(node.version, "5");
  assert.equal(node.username, "111");
  assert.equal(node.password, "111");
  assert.equal(node.server, "47.76.229.132");
  assert.equal(node.port, 11310);

  const literal = decodeProxyURI("socks5://alice:hunter2@198.51.100.7:1080#s5");
  assert.equal(literal.username, "alice");
  assert.equal(literal.password, "hunter2");

  const anonymous = decodeProxyURI("socks5://198.51.100.4:1080#open");
  assert.equal(anonymous.username, "");
  assert.equal(anonymous.password, "");

  assert.equal(decodeProxyURI("socks4://u:p@h:1080#v4").version, "4");
});

test("a scheme the converter cannot model is reported, never faked into a raw node", () => {
  for (const scheme of ["wireguard", "warp", "anytls", "tuic"]) {
    const node = decodeProxyURI(`${scheme}://key@198.51.100.9:51820#${scheme}-1`);
    assert.equal(node.protocol, scheme, `${scheme} lost its identity`);
    assert.equal(node.supported, false);
    assert.equal(node.name, `${scheme}-1`);
  }
});

test("converting a mixed feed emits real outbounds and no invented raw ones", () => {
  const encoded = Buffer.from("111:111", "utf8").toString("base64");
  const feed = [
    "vless://a@example.com:443#vless-1",
    "trojan://secret@198.51.100.6:443#trojan-1",
    `socks://${encoded}@198.51.100.1:11310#socks-1`,
    "warp://key@198.51.100.4:2408#warp-1"
  ].join(String.fromCharCode(10));
  const singbox = JSON.parse(convertProxyBatch(feed, "singbox"));
  const tags = singbox.outbounds.map((o) => o.tag).filter(Boolean);
  assert.ok(tags.includes("vless-1"));
  assert.ok(tags.includes("trojan-1"));
  assert.ok(tags.includes("socks-1"), "the SOCKS node must survive as a real outbound");
  // warp is unsupported here, so it is dropped rather than emitted as a node
  // of an invented type that no client could load.
  assert.ok(!tags.includes("warp-1"));
  assert.ok(!singbox.outbounds.some((o) => o.type === "raw"));
});

test("a payload of only unsupported links fails loudly", () => {
  assert.throws(
    () => convertProxyBatch("warp://k@198.51.100.4:2408#warp-1", "singbox"),
    /does not model/
  );
});
