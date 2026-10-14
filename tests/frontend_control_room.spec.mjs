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
  await page.locator("#tab-btn-proxies").click();
  await expect(page.locator("#workspace-title")).toHaveText("Find a working proxy");
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
