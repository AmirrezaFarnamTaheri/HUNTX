import { test, expect } from "@playwright/test";

const INDEX = {
  schema_version: 1,
  scope: "all_time_cumulative",
  health_status: "historical_unverified",
  generated_at: "2026-11-21T00:00:00Z",
  limit_per_protocol: 100,
  protocols: {
    vless: { count: 100, file: "vless.txt", base64_file: "vless_base64.txt" },
    trojan: { count: 5, file: "trojan.txt", base64_file: "trojan_base64.txt" },
    anytls: { count: 0, file: "anytls.txt", base64_file: "anytls_base64.txt" }
  },
  aggregate: { count: 105, file: "all.txt", base64_file: "all_base64.txt" }
};

async function mockIndex(page, ready = () => true) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) return route.abort();
    if (url.pathname.endsWith("/subscriptions/latest/index.json")) {
      return route.fulfill(ready()
        ? { status: 200, contentType: "application/json", body: JSON.stringify(INDEX) }
        : { status: 404, contentType: "application/json", body: "{}" });
    }
    return route.continue();
  });
}

test("subscription hub shows the master, protocol feeds and historical provenance", async ({ page }) => {
  await mockIndex(page);
  await page.goto("/#artifacts");
  await expect(page.locator("#subscription-hub-title")).toBeVisible();
  await expect(page.locator("#subscription-hub-status")).toContainText("not a live connectivity test");
  await expect(page.locator("#subscription-summary")).toContainText("3 protocol feeds");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(3);
  const master = page.locator(".sub-feature-primary");
  await expect(master).toContainText("105 unique historical configurations");
  await expect(master.locator("a", { hasText: "Plain-text feed" })).toHaveAttribute(
    "href", /subscriptions\/latest\/all\.txt$/
  );
  await expect(master.locator("a", { hasText: "Base64 feed" })).toHaveAttribute(
    "href", /subscriptions\/latest\/all_base64\.txt$/
  );
  await expect(page.locator(".sub-feature-release")).toContainText("current-run release");
  await expect(page.locator(".sub-protocol-card", { hasText: "anytls" })).toContainText(
    "No archived connections"
  );
  await page.locator("#subscription-protocol-search").fill("VLE");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(1);
  await expect(page.locator(".sub-protocol-card")).toContainText("vless");
  await page.getByRole("button", { name: "Clear protocol search" }).click();
  await expect(page.locator("#subscription-protocol-search")).toBeFocused();
  await expect(page.locator(".sub-protocol-card")).toHaveCount(3);
});

test("subscription directory retries unavailable historical index without hiding existing downloads", async ({ page }) => {
  let ready = false;
  await mockIndex(page, () => ready);
  await page.goto("/#artifacts");
  await expect(page.locator("#subscription-hub-status")).toContainText("not available");
  await expect(page.locator("#artifacts-section")).toBeVisible();
  ready = true;
  await page.getByRole("button", { name: "Retry loading subscriptions" }).click();
  await expect(page.locator(".sub-protocol-card")).toHaveCount(3);
  await expect(page.locator("#subscription-hub-status")).toHaveAttribute("data-state", "ready");
});

for (const width of [320, 375, 768, 1440]) {
  test(`subscription discovery remains usable without horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await mockIndex(page);
    await page.goto("/#artifacts");
    await expect(page.locator(".sub-protocol-card")).toHaveCount(3);
    const measurement = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
      grid: document.getElementById("subscription-protocol-grid").getBoundingClientRect()
    }));
    expect(measurement.document).toBeLessThanOrEqual(measurement.viewport + 1);
    expect(measurement.grid.right).toBeLessThanOrEqual(width + 1);
    if (width === 375) {
      await page.screenshot({
        path: "test-results/subscriptions-phone.png", fullPage: true, animations: "disabled"
      });
    }
  });
}

test("subscription discovery respects light theme and keyboard navigation", async ({ page }) => {
  await mockIndex(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Browse subscriptions and downloads" }).click();
  await expect(page.locator("#tab-btn-artifacts")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(3);
  await page.locator("#btn-toggle-theme").click();
  await expect(page.locator("html")).toHaveClass(/light/);
  await page.locator("#subscription-protocol-search").focus();
  await page.keyboard.type("trojan");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(1);
  await page.screenshot({
    path: "test-results/subscriptions-light.png", fullPage: true, animations: "disabled"
  });
});
