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
