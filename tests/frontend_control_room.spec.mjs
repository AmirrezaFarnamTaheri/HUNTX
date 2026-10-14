import { test, expect } from "@playwright/test";

async function localOnly(page) {
  await page.route("**/*", async (route) => {
    const host = new URL(route.request().url()).hostname;
    return ["127.0.0.1", "localhost"].includes(host) ? route.continue() : route.abort();
  });
}

test("desktop dashboard uses a stable operation rail with separate work surface", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await localOnly(page);
  await page.goto("/");
  const nav = page.locator("#page-tabs-nav");
  const main = page.locator("#dashboard-main");
  await expect(page.locator("#workspace-title")).toHaveText("Network overview");
  await expect(page.locator(".rail-intro")).toBeVisible();
  await expect(nav).toHaveCSS("position", "fixed");
  const rail = await nav.boundingBox();
  const content = await main.boundingBox();
  expect(rail).toBeTruthy();
  expect(content).toBeTruthy();
  expect(content.x).toBeGreaterThanOrEqual(rail.x + rail.width - 1);
  await expect(page.getByRole("link", { name: /fix connection/i })).toBeVisible();
});

test("workspace navigation updates context and primary action without losing tab behavior", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator("#hero-section .radar-overview")).toBeVisible();
  await page.locator("#tab-btn-proxies").click();
  await expect(page.locator("#workspace-title")).toHaveText("Explore published proxies");
  await expect(page.locator("#tab-panel-proxies")).toBeVisible();
  await page.locator("#workspace-action").click();
  await expect(page.locator("#tab-btn-artifacts")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#workspace-title")).toHaveText("Published feeds");
  await page.locator("#tab-btn-decoder").click();
  await expect(page.locator("#workspace-title")).toHaveText("Inspect a configuration");
});

for (const width of [320, 375, 768, 1024]) {
  test(`responsive control room preserves mobile actions and no page overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 820 });
    await localOnly(page);
    await page.goto("/");
    await expect(page.locator("#workspace-title")).toBeVisible();
    await expect(page.locator("#workspace-action")).toBeVisible();
    const measurements = await page.evaluate(() => ({
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      mastheadRight: document.getElementById("workspace-masthead").getBoundingClientRect().right
    }));
    expect(measurements.pageWidth).toBeLessThanOrEqual(measurements.viewportWidth + 1);
    expect(measurements.mastheadRight).toBeLessThanOrEqual(width + 1);
  });
}

test("Persian RTL places operation rail on the right and keeps content separate", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await localOnly(page);
  await page.goto("/");
  await page.locator("#language-selector").selectOption("fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  const nav = await page.locator("#page-tabs-nav").boundingBox();
  const main = await page.locator("#dashboard-main").boundingBox();
  expect(nav.x + nav.width).toBeGreaterThanOrEqual(1439);
  expect(main.x + main.width).toBeLessThanOrEqual(nav.x + 1);
});

test("reduced motion removes control-room entrance animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator("#tab-panel-radar")).toBeVisible();
  await expect(page.locator("#tab-panel-radar")).toHaveCSS("animation-name", "none");
});

test("Network Doctor gives clear progress and keyboard focus after generating steps", async ({ page }) => {
  await localOnly(page);
  await page.goto("/network-doctor.html");
  await expect(page.locator(".doctor-steps [data-step='1']")).toHaveAttribute("aria-current", "step");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await expect(page.locator(".doctor-steps [data-step='2']")).toHaveAttribute("aria-current", "step");
  await expect(page.locator("#plan-heading")).toBeFocused();
  await page.getByRole("button", { name: "Summarize my result" }).click();
  await expect(page.locator(".doctor-steps [data-step='3']")).toHaveAttribute("aria-current", "step");
  await page.getByRole("button", { name: "Start over" }).click();
  await expect(page.locator(".doctor-steps [data-step='1']")).toHaveAttribute("aria-current", "step");
  await expect(page.locator("#doctor-platform")).toBeFocused();
});

test("Network Doctor appearance toggle persists without saving recovery inputs", async ({ page }) => {
  await localOnly(page);
  await page.goto("/network-doctor.html");
  await page.locator("#doctor-symptom").selectOption("tls");
  const toggle = page.locator("#doctor-theme-toggle");
  await toggle.click();
  await expect(page.locator("html")).toHaveClass(/light/);
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  const stored = await page.evaluate(() => Object.keys(localStorage));
  expect(stored).not.toContain("doctor-symptom");
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/light/);
  await expect(page.locator("#doctor-symptom")).toHaveValue("timeout");
});

test("Network Doctor header and steps remain within a narrow phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 820 });
  await localOnly(page);
  await page.goto("/network-doctor.html");
  const geometry = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    header: document.querySelector(".doctor-header").scrollWidth
  }));
  expect(geometry.document).toBeLessThanOrEqual(geometry.viewport + 1);
  expect(geometry.header).toBeLessThanOrEqual(geometry.viewport + 1);
  await expect(page.getByRole("heading", { name: /Fix your connection/i })).toBeVisible();
});

test("artifact search retains keyboard focus and input value after filtered rerender", async ({ page }) => {
  await localOnly(page);
  await page.goto("/#artifacts");
  const search = page.locator("#artifact-search-input");
  await expect(search).toBeVisible();
  await search.fill("clash");
  await page.waitForFunction(() => window.huntxApp?.artifactSearchQuery === "clash");
  await expect(page.locator("#artifact-search-input")).toBeFocused();
  await expect(page.locator("#artifact-search-input")).toHaveValue("clash");
  await expect(page.getByRole("group", { name: "Artifact categories" })).toBeVisible();
});

test("inspector workspace tabs support roving keyboard navigation", async ({ page }) => {
  await localOnly(page);
  await page.goto("/#decoder");
  const inspector = page.locator('.btn-studio-tab[data-tab="inspector"]');
  await expect(inspector).toHaveAttribute("aria-selected", "true");
  await inspector.focus();
  await page.keyboard.press("ArrowRight");
  const converter = page.locator('.btn-studio-tab[data-tab="converter"]');
  await expect(converter).toHaveAttribute("aria-selected", "true");
  await expect(converter).toBeFocused();
  await expect(page.locator("#studio-tab-content")).toHaveAttribute("role", "tabpanel");
  await page.keyboard.press("Home");
  await expect(page.locator('.btn-studio-tab[data-tab="inspector"]')).toBeFocused();
});

test("proxy filters and view controls retain focus after workspace rerenders", async ({ page }) => {
  await localOnly(page);
  await page.goto("/#proxies");
  const transport = page.locator("#select-transport");
  await expect(transport).toBeVisible();
  await transport.focus();
  await transport.selectOption("ALL");
  await expect(page.locator("#select-transport")).toBeFocused();
  const table = page.locator("#btn-view-table");
  await table.click();
  await expect(page.locator("#btn-view-table")).toBeFocused();
  const grid = page.locator("#btn-view-grid");
  await grid.click();
  await expect(page.locator("#btn-view-grid")).toBeFocused();
});

test("artifact category controls remain keyboard-focused after selecting a filter", async ({ page }) => {
  await localOnly(page);
  await page.goto("/#artifacts");
  const category = page.locator('.btn-artifact-tab[data-filter="ALL"]');
  await category.click();
  await expect(page.locator('.btn-artifact-tab[data-filter="ALL"]')).toBeFocused();
  await expect(page.locator('.btn-artifact-tab[data-filter="ALL"]')).toHaveAttribute("aria-pressed", "true");
});

test("radar keeps advanced actions discoverable without clipping the primary actions", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator("#hero-section .radar-overview")).toBeVisible();
  const more = page.locator(".hero-more summary");
  await expect(more).toBeVisible();
  await more.click();
  await expect(page.locator("#hero-open-scanner")).toBeVisible();
  const json = page.locator("#hero-download-json");
  if (await json.getAttribute("hidden") !== null) {
    await expect(json).toHaveAttribute("aria-hidden", "true");
  } else {
    await expect(json).toBeVisible();
  }
});

test("untrusted operator names cannot poison the operator map or inject markup", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator("#hero-section .radar-overview")).toBeVisible();
  const result = await page.evaluate(() => {
    const app = window.huntxApp;
    const original = app.proxies;
    const sample = original[0];
    try {
      app.proxies = [
        { ...sample, carrier: "__proto__", latency: 37, country: "ZZ" },
        { ...sample, carrier: '<img src=x onerror="window.__huntxInjected=1">', latency: 41, country: "ZZ" }
      ];
      app.renderRadarDiagnostics();
      const cards = [...document.querySelectorAll(".operator-card")];
      return {
        count: cards.length,
        nativeButtons: cards.every((card) => card.tagName === "BUTTON"),
        injectedImages: document.querySelectorAll(".operator-card img").length,
        fabricatedLoss: document.getElementById("radar-diagnostics").textContent.includes("Loss: —")
      };
    } finally {
      app.proxies = original;
      delete Object.prototype.count;
    }
  });
  expect(result.count).toBe(2);
  expect(result.nativeButtons).toBe(true);
  expect(result.injectedImages).toBe(0);
  expect(result.fabricatedLoss).toBe(false);
  expect(await page.evaluate(() => window.__huntxInjected)).toBeUndefined();
});

test("phone recovery form appears in the first viewport with legible inputs and optional details", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await localOnly(page);
  await page.goto("/network-doctor.html");
  const formHeading = await page.locator("#setup-heading").boundingBox();
  expect(formHeading.y).toBeLessThan(812);
  const fontSize = await page.locator("#doctor-platform").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(fontSize).toBeGreaterThanOrEqual(16);
  const toggle = page.locator("#doctor-principles-toggle");
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#doctor-principles-content")).toBeVisible();
});

test("phone dashboard keeps both primary routes side by side without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await localOnly(page);
  await page.goto("/");
  const action = await page.locator("#workspace-action").boundingBox();
  const doctor = await page.locator('.workspace-actions a[href="network-doctor.html"]').boundingBox();
  expect(action).toBeTruthy();
  expect(doctor).toBeTruthy();
  expect(Math.abs(action.y - doctor.y)).toBeLessThan(2);
  expect(action.height).toBeGreaterThanOrEqual(44);
  expect(doctor.height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(375);
});

test("operator with no recorded latency displays no synthetic zero or packet-loss data", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator("#hero-section .radar-overview")).toBeVisible();
  await page.evaluate(() => {
    const app = window.huntxApp;
    const baseline = app.proxies[0];
    app.proxies = [{ ...baseline, carrier: "Unmeasured example", latency: null, country: "ZZ" }];
    app.renderRadarDiagnostics();
  });
  const card = page.locator(".operator-card");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("Not measured");
  await expect(card).toContainText("0 samples");
  await expect(card).not.toContainText("0ms");
  await expect(card).not.toContainText("Loss:");
});

test("compact globe actually paints geography instead of an empty canvas", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await localOnly(page);
  await page.goto("/");
  const canvas = page.locator("#telemetry-globe-canvas");
  await expect(canvas).toBeVisible();
  // IntersectionObserver intentionally suspends offscreen animation.
  // Scroll into view to request a frame before asserting painted pixels.
  await canvas.scrollIntoViewIfNeeded();
  await page.waitForFunction(() => {
    const canvas = document.getElementById("telemetry-globe-canvas");
    if (!canvas?.width || !canvas?.height) return false;
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 3; i < pixels.length; i += 64) {
      if (pixels[i] > 0) return true;
    }
    return false;
  });
});
