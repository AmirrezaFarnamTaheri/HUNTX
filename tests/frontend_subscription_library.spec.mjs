import { test, expect } from "@playwright/test";

const sha256 = "a".repeat(64);
const protocols = Object.fromEntries([
  ["vless", 100], ["vmess", 12], ["anytls", 1], ["wireguard", 0], ["future-protocol", 2]
].map(([name, count]) => [
  name,
  { count, file: name + ".txt", base64_file: name + "_base64.txt", sha256 }
]));
const index = {
  schema_version: 1,
  scope: "all_time_cumulative",
  health_status: "historical_unverified",
  generated_at: "2026-11-21T10:00:00Z",
  latest_by: "first_seen",
  limit_per_protocol: 200,
    protocol_limits: { vless: 150, shadowsocks: 150 },
  protocols,
  aggregate: { count: 115, file: "all.txt", base64_file: "all_base64.txt", sha256 }
};

async function localOnly(page, offline = false) {
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) return route.abort();
    if (url.pathname.endsWith("/subscriptions/latest/index.json")) {
      return offline ? route.fulfill({ status: 503, body: "Offline" }) : route.fulfill({
        status: 200, contentType: "application/json", body: JSON.stringify(index)
      });
    }
    return route.continue();
  });
}

test("hub renders a truthful aggregate, all categories, and direct subscription downloads", async ({ page }) => {
  await localOnly(page);
  await page.goto("/subscriptions.html");
  await expect(page.getByRole("heading", { name: /subscription library/i })).toBeVisible();
  await expect(page.locator("#aggregate-count")).toHaveText("115");
  await expect(page.locator("#protocol-count")).toHaveText("5");
  await expect(page.locator("#protocol-grid .protocol-card")).toHaveCount(5);
  await expect(page.locator("#subscription-trust")).toContainText(/historical/i);
  await expect(page.locator("#master-text-download")).toHaveAttribute("href", "subscriptions/latest/all.txt");
  await expect(page.locator("#master-base64-download")).toHaveAttribute("href", "subscriptions/latest/all_base64.txt");
  const vless = page.locator("[data-protocol-card='vless']");
  await expect(vless).toContainText("100");
  await expect(vless.getByRole("link", { name: /plain text/i })).toHaveAttribute("href",
    "subscriptions/latest/vless.txt");
  await expect(vless.getByRole("link", { name: /base64/i })).toHaveAttribute("href",
    "subscriptions/latest/vless_base64.txt");
});

test("search/filter and three visual directions are keyboard operable", async ({ page }) => {
  await localOnly(page);
  await page.goto("/subscriptions.html");
  const search = page.locator("#subscription-search");
  await search.focus();
  await page.keyboard.type("wire");
  await expect(page.locator("#protocol-grid .protocol-card")).toHaveCount(1);
  await page.getByRole("checkbox", { name: /available only/i }).check();
  await expect(page.locator("#protocol-grid .protocol-card")).toHaveCount(0);
  await expect(page.locator("#protocol-result-summary")).toContainText(/no matching/i);
  await page.locator("#clear-subscription-search").click();
  await expect(search).toHaveValue("");
  await page.getByRole("checkbox", { name: /available only/i }).uncheck();

  const canvas = page.getByRole("button", { name: /canvas/i });
  await canvas.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-design", "canvas");
  await expect(canvas).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: /ledger/i }).click();
  await expect(page.locator("html")).toHaveAttribute("data-design", "ledger");
  await page.getByRole("button", { name: /signal/i }).click();
  await expect(page.locator("html")).toHaveAttribute("data-design", "signal");
});

test("unavailable index is an honest recoverable error, not a fake empty or healthy feed", async ({ page }) => {
  await localOnly(page, true);
  await page.goto("/subscriptions.html");
  await expect(page.locator("#subscription-status")).toContainText(/unavailable/i);
  await expect(page.locator("#aggregate-count")).toHaveText("—");
  await expect(page.locator("#protocol-grid .protocol-card")).toHaveCount(0);
  await expect(page.locator("#subscription-retry")).toBeVisible();
  await expect(page.locator("#subscription-status")).not.toContainText(/verified live/i);
});

for (const width of [320, 375, 768, 1024, 1440]) {
  test(`hub remains usable at ${width}px without horizontal page overflow`, async ({ page }) => {
    await page.setViewportSize({ width, height: 820 });
    await localOnly(page);
    await page.goto("/subscriptions.html");
    await expect(page.locator("#protocol-grid .protocol-card").first()).toBeVisible();
    const widths = await page.evaluate(() => ({
      document: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth
    }));
    expect(widths.document).toBeLessThanOrEqual(widths.viewport + 1);
    await expect(page.getByRole("link", { name: /dashboard/i }).first()).toBeVisible();
  });
}

test("dashboard exposes a persistent subscription entry without replacing legacy workspaces", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator("#tab-btn-radar")).toBeVisible();
  await expect(page.locator("#tab-btn-artifacts")).toBeVisible();
  const nav = page.getByRole("link", { name: /browse protocol subscriptions/i });
  await expect(nav).toHaveAttribute("href", "subscriptions.html");
  await nav.click();
  await expect(page).toHaveURL(/\/subscriptions\.html$/);
  await expect(page.getByRole("heading", { name: /subscription library/i })).toBeVisible();
});
