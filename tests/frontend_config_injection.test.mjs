// Regression tests for the profile serializers.
//
// Node metadata reaches HUNTX from public channels. The Clash, Surge, Loon and
// Quantumult X emitters write that metadata into config files that users load
// into a proxy client, and those formats are line- and delimiter-oriented with
// no escaping of their own. A value carrying a newline or a delimiter must
// never be able to introduce a directive the user did not ask for.

import test from "node:test";
import assert from "node:assert/strict";
import {
  yamlQuote,
  iniValue,
  iniTag,
  clashProxyToYAML,
  nodeToClashProxy,
  nodeToSurgeProxy,
  nodeToLoonProxy,
  nodeToQXServer,
  buildClashMetaYAML,
  buildSurgeConfig,
  buildLoonConfig,
  buildQXConfig,
} from "../docs/assets/js/decoder.js";

/** A name that tries to close its YAML scalar and open a new mapping key. */
const YAML_BREAKOUT = 'evil"\nrules:\n  - MATCH,DIRECT\nx: "';

/** A name that tries to end its directive line and start another. */
const LINE_BREAKOUT = "evil\nProxy = attacker, 10.0.0.1, 1080";

function vlessNode(overrides = {}) {
  return {
    protocol: "vless",
    name: "clean-node",
    server: "example.invalid",
    port: 443,
    uuid: "11111111-2222-3333-4444-555555555555",
    security: "tls",
    sni: "example.invalid",
    transport: "tcp",
    ...overrides,
  };
}

test("yamlQuote escapes quotes, backslashes and newlines", () => {
  assert.equal(yamlQuote("plain"), '"plain"');
  assert.equal(yamlQuote('say "hi"'), '"say \\"hi\\""');
  assert.equal(yamlQuote("a\\b"), '"a\\\\b"');
  assert.equal(yamlQuote("line1\nline2"), '"line1\\nline2"');
  assert.equal(yamlQuote("tab\there"), '"tab\\there"');
});

test("yamlQuote renders nullish input as an empty scalar", () => {
  assert.equal(yamlQuote(undefined), '""');
  assert.equal(yamlQuote(null), '""');
});

test("yamlQuote escapes remaining control characters", () => {
  assert.equal(yamlQuote("a\u0000b"), '"a\\x00b"');
  assert.equal(yamlQuote("a\u001bb"), '"a\\x1bb"');
});

test("yamlQuote output never contains a raw newline", () => {
  const quoted = yamlQuote(YAML_BREAKOUT);
  assert.ok(!quoted.includes("\n"), "quoted scalar must stay on one line");
  assert.equal(quoted.match(/(?<!\\)"/g).length, 2, "only the delimiters are unescaped quotes");
});

test("iniValue strips control characters and commas", () => {
  assert.equal(iniValue("a\nb"), "ab");
  assert.equal(iniValue("a\r\nb"), "ab");
  assert.equal(iniValue("a,b"), "a_b");
  assert.equal(iniValue("a,b", { allowComma: true }), "a,b");
  assert.equal(iniValue(undefined), "");
});

test("iniTag also neutralizes the directive separator", () => {
  assert.equal(iniTag("a=b"), "a_b");
  assert.equal(iniTag("a,b=c"), "a_b_c");
  assert.equal(iniTag("  "), "huntx-node", "an empty tag would produce a nameless directive");
  assert.equal(iniTag("\n"), "huntx-node");
});

test("clash yaml keeps a hostile node name inside its scalar", () => {
  const yaml = buildClashMetaYAML([vlessNode({ name: YAML_BREAKOUT })]);
  assert.ok(!yaml.includes("\nrules:\n  - MATCH,DIRECT"), "must not inject a rules block");
  // The profile has exactly one rules section: the one the builder writes.
  assert.equal(yaml.match(/^rules:$/gm).length, 1);
});

test("clash yaml quotes the server and preserves the websocket Host header", () => {
  const proxy = nodeToClashProxy(
    vlessNode({ transport: "ws", path: "/a b", host: "front.invalid" })
  );
  const entry = clashProxyToYAML(proxy);
  assert.match(entry, /server: "example\.invalid"/);
  assert.match(entry, /path: "\/a b"/);
  assert.match(entry, /Host: "front\.invalid"/, "the Host header must survive serialization");
});

test("clash yaml emits a numeric port even when the port arrives as text", () => {
  const entry = clashProxyToYAML(nodeToClashProxy(vlessNode({ port: "8443" })));
  assert.match(entry, /port: 8443$/m);
  const bad = clashProxyToYAML(nodeToClashProxy(vlessNode({ port: "not-a-port" })));
  assert.match(bad, /port: 0$/m);
});

test("clashProxyToYAML tolerates a missing proxy", () => {
  assert.equal(clashProxyToYAML(null), "");
  assert.equal(clashProxyToYAML(undefined), "");
});

for (const [label, emitter] of [
  ["surge", nodeToSurgeProxy],
  ["loon", nodeToLoonProxy],
  ["quantumult x", nodeToQXServer],
]) {
  test(`${label} directive stays on a single line for a hostile name`, () => {
    const line = emitter(vlessNode({ name: LINE_BREAKOUT }));
    assert.ok(!line.includes("\n"), `${label} emitted a second line`);
  });

  test(`${label} directive stays on a single line for hostile transport metadata`, () => {
    const line = emitter(
      vlessNode({ transport: "ws", path: "/p\nProxy = attacker, 10.0.0.1, 1080", host: "h\nx" })
    );
    assert.ok(!line.includes("\n"), `${label} emitted a second line`);
  });

  test(`${label} tolerates a missing node`, () => {
    assert.equal(emitter(null), "");
  });
}

test("surge and loon labels cannot introduce an extra field", () => {
  const hostile = vlessNode({ name: "a, tls=false" });
  assert.ok(!nodeToSurgeProxy(hostile).startsWith("a,"));
  assert.ok(!nodeToLoonProxy(hostile).startsWith("a,"));
});

test("loon quoting cannot be terminated early by an embedded quote", () => {
  const line = nodeToLoonProxy(vlessNode({ uuid: 'aaa", udp=false, x="' }));
  assert.ok(!line.includes('"'.repeat(1) + ", udp=false"), "quote was not neutralized");
  // Field quotes must remain balanced.
  assert.equal(line.match(/"/g).length % 2, 0);
});

test("whole-profile builders stay injection free", () => {
  const hostile = [vlessNode({ name: LINE_BREAKOUT, host: "h\nx", transport: "ws" })];
  for (const [label, build] of [
    ["surge", buildSurgeConfig],
    ["loon", buildLoonConfig],
    ["qx", buildQXConfig],
  ]) {
    const text = build(hostile);
    assert.ok(
      !text.includes("Proxy = attacker"),
      `${label} profile contains an injected directive`
    );
  }
});

test("surge group references use iniTag to prevent line injection", () => {
  const hostile = [vlessNode({ name: LINE_BREAKOUT })];
  const text = buildSurgeConfig(hostile);
  const groupSection = text.slice(text.indexOf("[Proxy Group]"));
  assert.ok(!groupSection.includes("\nProxy = attacker"), "group reference was not escaped");
  // Verify the reference is present and normalized.
  assert.ok(groupSection.includes(iniTag(LINE_BREAKOUT)), "normalized tag not found");
});

test("loon group references use iniTag to prevent line injection", () => {
  const hostile = [vlessNode({ name: LINE_BREAKOUT })];
  const text = buildLoonConfig(hostile);
  const groupSection = text.slice(text.indexOf("[Proxy Group]"));
  assert.ok(!groupSection.includes("\nProxy = attacker"), "group reference was not escaped");
  assert.ok(groupSection.includes(iniTag(LINE_BREAKOUT)), "normalized tag not found");
});

test("qx policy references use iniTag to prevent line injection", () => {
  const hostile = [vlessNode({ name: LINE_BREAKOUT })];
  const text = buildQXConfig(hostile);
  const policySection = text.slice(text.indexOf("[policy]"));
  assert.ok(!policySection.includes("\nProxy = attacker"), "policy reference was not escaped");
  assert.ok(policySection.includes(iniTag(LINE_BREAKOUT)), "normalized tag not found");
});
