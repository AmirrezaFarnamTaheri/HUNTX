import { test, expect } from "@playwright/test";
import { wcagAuditInPage } from "./lib/wcag_audit.mjs";

async function isolateLocalPage(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      await route.continue();
    } else {
      await route.abort();
    }
  });
}

for (const width of [320, 375, 640, 768, 1024, 1280]) {
  test(`header is usable without clipping at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await isolateLocalPage(page);
    await page.goto("/");
    await expect(page.locator("#main-header")).toBeVisible();
    const metrics = await page.locator("#main-header").evaluate((header) => {
      const visible = [...header.querySelectorAll("button, select, a")]
        .filter((el) => {
          const style = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
        })
        .map((el) => {
          const rect = el.getBoundingClientRect();
          return { left: rect.left, right: rect.right };
        });
      return {
        scrollWidth: header.scrollWidth,
        clientWidth: header.clientWidth,
        minLeft: Math.min(...visible.map((item) => item.left)),
        maxRight: Math.max(...visible.map((item) => item.right))
      };
    });
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
    expect(metrics.minLeft).toBeGreaterThanOrEqual(-1);
    expect(metrics.maxRight).toBeLessThanOrEqual(width + 1);

    const tools = page.locator("#btn-header-tools");
    await expect(tools).toBeVisible();
    await expect(tools).toHaveAttribute("aria-expanded", "false");
    await tools.click();
    await expect(page.locator("#header-tools-menu")).toBeVisible();
    await expect(tools).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("#header-tools-menu")).toBeHidden();
    await expect(tools).toHaveAttribute("aria-expanded", "false");
  });
}

test("coarse-pointer tablet gets an explicit, stateful globe gate", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1024, height: 900 },
    hasTouch: true,
    isMobile: true,
    deviceScaleFactor: 1
  });
  const page = await context.newPage();
  await isolateLocalPage(page);
  await page.goto("/");
  expect(await page.evaluate(() => matchMedia("(any-pointer: coarse)").matches)).toBe(true);
  const gate = page.locator("#globe-touch-gate");
  const button = page.locator("#btn-globe-touch-toggle");
  await expect(gate).toBeVisible();
  await expect(button).toHaveAttribute("aria-pressed", "false");
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await context.close();
});

test("Persian locale updates semantics while technical data remains LTR", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  const selector = page.locator("#language-selector");
  await selector.selectOption("fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(selector).toHaveAttribute("aria-label", "زبان");
  await expect(selector).toHaveAttribute("title", "زبان");
  const direction = await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.className = "technical-ltr";
    probe.textContent = "1.2.3.4:443 / abc-def";
    document.body.appendChild(probe);
    return getComputedStyle(probe).direction;
  });
  expect(direction).toBe("ltr");
});

test("mobile tabs expose horizontal scrolling rather than hiding overflow affordance", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  const scroller = page.locator("#page-tabs-nav > div");
  const metrics = await scroller.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    scrollbarWidth: getComputedStyle(el).scrollbarWidth
  }));
  expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
  expect(metrics.scrollbarWidth).not.toBe("none");
  const moved = await scroller.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
    return el.scrollLeft;
  });
  expect(Math.abs(moved)).toBeGreaterThan(0);
});


test("checksum-valid empty release renders no bundled endpoints", async ({ page }) => {
  const { createHash } = await import("node:crypto");
  const artifact = JSON.stringify({ total: 0, protocols: {}, entries: [] });
  const sha256 = createHash("sha256").update(artifact).digest("hex");
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await isolateLocalPage(page);
  await page.route("**/catalog.json", (route) => route.fulfill({
    json: { files: [{ filename: "all_sources.npvt.decoded.json", path: "artifacts/release/empty-test.json", sha256 }] }
  }));
  await page.route("**/artifacts/release/empty-test.json", (route) => route.fulfill({
    contentType: "application/json", body: artifact
  }));
  await page.goto("/#proxies");
  await expect(page.locator("#data-status-pill")).toContainText("Artifact integrity verified");
  await expect(page.locator("#tab-count-proxies, #tab-proxies-count-badge")).toHaveText("0");
  await expect(page.locator("#nodes-grid")).toContainText("No proxy endpoints match");
  expect(errors).toEqual([]);
});


test("protocol inspector preserves names, credentials, flow and encoded paths", async ({ page }) => {
  await isolateLocalPage(page);
  await page.goto("/#decoder");
  const input = page.locator("#decoder-single-input");
  const output = page.locator("#inspector-output");
  const vmess = "vmess://" + Buffer.from(JSON.stringify({ ps: "Тегеран 東京", add: "example.com", port: 443, id: "test-id" })).toString("base64");
  await input.fill(vmess);
  await page.locator("#btn-run-inspect").click();
  await expect(output).toContainText("Тегеран 東京");
  await input.fill("ss://" + Buffer.from("aes-256-gcm:pass:word:123").toString("base64") + "@example.com:8388");
  await page.locator("#btn-run-inspect").click();
  await expect(output).toContainText("pass:word:123");
  await input.fill("vless://test-id@example.com:443?flow=xtls-rprx-vision&type=ws&path=%2Fapi%252Fws");
  await page.locator("#btn-run-inspect").click();
  await expect(output).toContainText("xtls-rprx-vision");
  await expect(output).toContainText("/api%2Fws");
});


test("radar keeps diagnostics in the first desktop viewport and active tabs visibly focused", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await isolateLocalPage(page);
  await page.route("**/catalog.json", route => route.fulfill({ json: { files: [] } }));
  await page.goto("/");
  await expect(page.locator(".radar-summary h1")).toBeVisible();
  await expect(page.locator(".radar-description")).toContainText("Artifact checksums do not verify connectivity");
  const diagnostics = await page.locator("#radar-diagnostics").boundingBox();
  expect(diagnostics.y).toBeLessThan(600);
  for (const theme of ["dark", "light"]) {
    await page.evaluate(theme => { document.documentElement.className = theme; }, theme);
    const tab = page.locator("#tab-btn-radar");
    await tab.focus();
    await expect(tab).toHaveCSS("outline-style", "solid");
    await expect(tab).toHaveCSS("outline-width", "2px");
    await expect(tab).toHaveCSS("box-shadow", "none");
  }
});


test("keyboard users can skip navigation and dismiss feeds back to their trigger", async ({ page }) => {
  await isolateLocalPage(page);
  await page.goto("/");
  await expect(page.locator(".radar-summary h1")).toBeVisible();
  const skip = page.getByRole("link", { name: "Skip to dashboard" });
  await skip.focus();
  await expect(skip).toBeVisible();
  await skip.press("Enter");
  await expect(page.locator("#dashboard-main")).toBeFocused();
  await page.locator("#tab-btn-radar").focus();
  await page.keyboard.press("b");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("#tab-btn-radar")).toBeFocused();
});

test("subscription dialog metadata remains readable and fits narrow screens", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  await expect(page.locator(".radar-summary h1")).toBeVisible();
  await page.locator("#tab-btn-radar").focus();
  await page.keyboard.press("b");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const metrics = await dialog.evaluate(el => {
    const sizes = [...el.querySelectorAll("*")]
      .filter(node => node.getBoundingClientRect().width > 0 && [...node.childNodes].some(child => child.nodeType === 3 && child.textContent.trim()))
      .map(node => parseFloat(getComputedStyle(node).fontSize));
    return { smallest: Math.min(...sizes), width: el.scrollWidth, viewport: innerWidth };
  });
  expect(metrics.smallest).toBeGreaterThanOrEqual(12);
  expect(metrics.width).toBeLessThanOrEqual(metrics.viewport);
});


test("artifact QR closure does not hide subsequent dialogs", async ({ page }) => {
  await isolateLocalPage(page);
  await page.route("**/catalog.json", route => route.fulfill({ json: { files: [] } }));
  await page.goto("/");
  await expect(page.locator(".radar-summary h1")).toBeVisible();
  await page.locator("#tab-btn-radar").focus();
  await page.evaluate(() => window.huntxApp.openArtifactQRModal({
    filename: "sample.txt", path: "artifacts/release/sample.txt", description: "Local test fixture"
  }));
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close QR Modal", exact: true }).click();
  await expect(page.locator("#tab-btn-radar")).toBeFocused();
  await page.keyboard.press("b");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("#tab-btn-radar")).toBeFocused();
});

test("globe hub labels never overlap across rotation", async ({ page }) => {
  // Seven of the eleven built-in demo hubs sit within a few degrees of each
  // other in Europe; without collision rejection their two-line tags stack
  // into one unreadable blob.
  await page.setViewportSize({ width: 1280, height: 900 });
  await isolateLocalPage(page);
  await page.route("**/catalog.json", (route) => route.fulfill({ json: { files: [] } }));
  await page.goto("/");
  const globe = await page.evaluateHandle(async () => {
    const { initTelemetryGlobe } = await import("./assets/js/globe.js");
    const host = document.createElement("div");
    host.style.cssText = "position:fixed;left:0;top:0;width:640px;height:640px;z-index:99999;";
    const canvas = document.createElement("canvas");
    canvas.id = "audit-globe-canvas";
    canvas.style.cssText = "width:640px;height:640px;display:block;";
    host.appendChild(canvas);
    document.body.appendChild(host);
    return initTelemetryGlobe("audit-globe-canvas", null, null, {});
  });
  // Sample the placed label boxes while the globe auto-rotates and verify no
  // two boxes in a single frame ever intersect.
  let overlaps = 0;
  let maxVisible = 0;
  for (let i = 0; i < 8; i++) {
    await page.waitForTimeout(150);
    const rects = await page.evaluate((g) => g.getLabelRects(), globe);
    maxVisible = Math.max(maxVisible, rects.length);
    for (let a = 0; a < rects.length; a++) {
      for (let b = a + 1; b < rects.length; b++) {
        const p = rects[a], q = rects[b];
        if (p.x < q.x + q.w && p.x + p.w > q.x && p.y < q.y + q.h && p.y + p.h > q.y) overlaps += 1;
      }
    }
  }
  expect(overlaps).toBe(0);
  // The crowded cluster still renders: crowding is resolved by layout, not
  // by hiding every tag.
  expect(maxVisible).toBeGreaterThan(1);
  await page.evaluate((g) => g.destroy(), globe);
});

test("dashboard keeps WCAG 2.2 AA contrast and control semantics on every tab", async ({ page }) => {
  // Locks the floor fixed by the 2026-09-18 audit: text clears 4.5:1 (3:1 when
  // large), every interactive element has an accessible name and a visible
  // focus indicator, and a control with no text label carries a 3:1 indicator.
  // Criteria live in tests/lib/wcag_audit.mjs so the harness and this test
  // share one definition.
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await isolateLocalPage(page);
  await page.route("**/catalog.json", (route) => route.fulfill({ json: { files: [] } }));
  await page.goto("/");
  await expect(page.locator(".radar-summary h1")).toBeVisible();
  const findings = [];
  let checked = 0;
  for (const pass of [{ theme: "dark", width: 1280 }, { theme: "light", width: 1280 }, { theme: "dark", width: 320 }]) {
    await page.setViewportSize({ width: pass.width, height: 900 });
    await page.evaluate((t) => { document.documentElement.className = t; }, pass.theme);
    for (const tab of ["#radar", "#proxies", "#studio", "#decoder", "#artifacts"]) {
      await page.evaluate((t) => { location.hash = t; }, tab);
      await page.waitForTimeout(350);
      const res = await page.evaluate(wcagAuditInPage);
      findings.push(...res.findings);
      checked += res.checked.text + res.checked.controls;
    }
  }
  // Coverage guard: the audit must have measured real rendered content rather
  // than silently no-op'ing on a page that failed to render.
  expect(checked).toBeGreaterThan(1000);
  const serious = findings.filter((f) => f.level === "serious");
  expect(serious).toEqual([]);
});

test("node grid reveals progressively and keeps appended cards interactive", async ({ page }) => {
  // One card per node is the heaviest render on the dashboard, so only the
  // first window is painted and the rest stream in as the sentinel scrolls
  // into view. Counts, exports and the raw-URI feed still see the whole list.
  // The bundled 735-node snapshot exercises the reveal; a live release small
  // enough to fit one window has nothing to stream and skips it.
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await isolateLocalPage(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  // No decoded artifact on the live catalog -> the bundled snapshot is used.
  await page.route("**/catalog.json", (route) => route.fulfill({ json: { files: [] } }));
  await page.goto("/#proxies");
  await expect(page.locator("#data-status-pill")).toContainText("Bundled snapshot");

  const cards = page.locator("#nodes-grid .proxy-card");
  await expect(cards.first()).toBeVisible();

  const initial = await cards.count();
  expect(initial).toBe(60);                       // NODES_INITIAL

  const sentinel = page.locator("#nodes-grid-sentinel");
  await expect(sentinel).toBeVisible();
  const sentinelText = (await sentinel.textContent()) ?? "";
  const remaining = Number(sentinelText.match(/\d+/)?.[0] ?? 0);
  expect(remaining).toBeGreaterThan(0);           // more nodes wait off-screen

  // Scrolling the marker into view appends the next window without dropping
  // the cards already on screen.
  await sentinel.scrollIntoViewIfNeeded();
  await expect(cards).toHaveCount(initial + 60);  // NODES_INCREMENT

  // A card that scrolled in is bound, not inert: its copy action answers.
  await cards.nth(initial + 5).locator(".btn-copy-node").click();
  await expect(page.locator(".toast-pill").first()).toBeVisible();

  expect(errors).toEqual([]);
});
