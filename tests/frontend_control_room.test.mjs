import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { WORKSPACES, resolveWorkspace } from "../docs/assets/js/control-room.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("control room defines a complete, explicit workspace navigation contract", () => {
  const expected = ["radar", "proxies", "studio", "decoder", "artifacts"];
  assert.deepEqual(Object.keys(WORKSPACES), expected);
  for (const key of expected) {
    assert.ok(WORKSPACES[key].title.length >= 8);
    assert.ok(WORKSPACES[key].description.length >= 30);
    assert.ok(WORKSPACES[key].action.label.length >= 6);
    assert.ok(["tab", "link"].includes(WORKSPACES[key].action.type));
  }
  assert.equal(resolveWorkspace("unrecognized"), WORKSPACES.radar);
  assert.equal(resolveWorkspace("proxies"), WORKSPACES.proxies);
});

test("generated frontend uses the same offline-safe control room shell as the template", async () => {
  const [generated, template, css, worker] = await Promise.all([
    read("../docs/index.html"),
    read("../scripts/update_frontend.py"),
    read("../docs/assets/css/control-room.css"),
    read("../docs/sw.js")
  ]);
  for (const source of [generated, template]) {
    assert.match(source, /assets\/css\/control-room\.css/);
    assert.match(source, /assets\/js\/control-room\.js/);
    assert.match(source, /id="workspace-masthead"/);
    assert.match(source, /class="rail-intro"/);
    assert.match(source, /id="workspace-action"/);
    assert.match(source, /id="workspace-title"/);
  }
  assert.match(worker, /assets\/css\/control-room\.css/);
  assert.match(worker, /assets\/js\/control-room\.js/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /forced-colors: active/);
  assert.doesNotMatch(css, /@import|url\(https?:\/\//i);
});

test("Atlas v2 design layer is generated, offline-cached and exposes real studio actions", async () => {
  const [generated, template, stylesheet, worker, application] = await Promise.all([
    read("../docs/index.html"),
    read("../scripts/update_frontend.py"),
    read("../docs/assets/css/atlas-v2.css"),
    read("../docs/sw.js"),
    read("../docs/assets/js/app.js")
  ]);
  for (const source of [generated, template]) {
    assert.match(source, /assets\/css\/atlas-v2\.css/);
    assert.match(source, /<span>Subscription Studio<\/span>/);
  }
  assert.match(worker, /assets\/css\/atlas-v2\.css/);
  assert.match(stylesheet, /\.measurement-bar/);
  assert.match(stylesheet, /\.studio-feed-grid/);
  assert.match(stylesheet, /prefers-reduced-motion: reduce/);
  assert.match(stylesheet, /forced-colors: active/);
  assert.doesNotMatch(stylesheet, /@import|url\(https?:\/\//i);
  assert.match(application, /id="advanced-filters"/);
  assert.match(application, /id="studio-start-builder"/);
  assert.match(application, /this\.openSubscriptionBuilderModal\(\)/);
});
