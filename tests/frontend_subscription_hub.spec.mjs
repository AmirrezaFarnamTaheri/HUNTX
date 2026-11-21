import { test, expect } from "@playwright/test";

const protocols = [
  "vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2", "socks",
  "http", "shadowsocks", "shadowsocksr", "tuic", "wireguard", "ssh",
  "shadowtls", "naive", "juicity", "mieru", "warp", "dns", "dnstt"
];

const directory = {
  schema_version: 1, scope: "all_time_cumulative",
  health_status: "historical_unverified", latest_by: "first_seen",
  generated_at: "2026-11-21T10:00:00Z", limit_per_protocol: 100,
  protocols: Object.fromEntries(protocols.map((name) => [name, {
    count: name === "vless" ? 100 : name === "vmess" ? 24 : 0,
    file: name + ".txt", base64_file: name + "_base64.txt", sha256: "a".repeat(64)
  }])),
  aggregate: {
    count: 124, file: "all.txt", base64_file: "all_base64.txt",
    sha256: "a".repeat(64)
  }
};

async function mockDirectory(page, status = 200) {
  await page.route("**/subscriptions/latest/index.json", (route) =>
    route.fulfill({
      status, contentType: "application/json",
      body: status === 200 ? JSON.stringify(directory) : "{}"
    })
  );
}

test("subscription hub exposes all protocols, master feeds, and real counts", async ({ page }) => {
  await mockDirectory(page);
  await page.goto("/#artifacts");
  await expect(page.locator("#subscription-hub")).toBeVisible();
  await expect(page.locator("#sub-feed-status")).toContainText("published");
  await expect(page.locator("#sub-stat-total")).toHaveText("124");
  await expect(page.locator("#sub-stat-types")).toHaveText("20");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(20);
  await expect(page.locator("#sub-protocol-vless")).toContainText("100");
  await expect(page.locator("#sub-protocol-vmess")).toContainText("24");
  await expect(page.locator("#sub-link-all")).toHaveAttribute(
    "href", "subscriptions/latest/all.txt"
  );
  await expect(page.locator("#sub-link-all-base64")).toHaveAttribute(
    "href", "subscriptions/latest/all_base64.txt"
  );
  await expect(page.locator("#sub-protocol-hysteria2 a").first()).toHaveAttribute(
    "href", "subscriptions/latest/hysteria2.txt"
  );
  await expect(page.locator("#subscription-hub")).toContainText("not a live connectivity");
  const search = page.locator("#sub-search");
  await search.fill("shadow");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(3);
  await expect(page.locator("#sub-search-clear")).toBeVisible();
  await page.locator("#sub-search-clear").click();
  await expect(search).toBeFocused();
  await expect(search).toHaveValue("");
  await page.locator("#sub-availability").selectOption("available");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(2);
});

test("unavailable metadata is explicit and never fabricates proxy counts", async ({ page }) => {
  await mockDirectory(page, 404);
  await page.goto("/#artifacts");
  await expect(page.locator("#sub-feed-status")).toContainText("unavailable");
  await expect(page.locator("#sub-stat-total")).toHaveText("—");
  await expect(page.locator("#sub-stat-types")).toHaveText("—");
  await expect(page.locator("#sub-link-all")).toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".sub-protocol-card")).toHaveCount(20);
  await expect(page.locator("#sub-protocol-vless")).toContainText("Awaiting publication");
});

test("three distinctive visual directions persist without breaking light/dark", async ({ page }) => {
  await mockDirectory(page);
  await page.goto("/#artifacts");
  const select = page.locator("#design-direction-select");
  await expect(select).toHaveValue("signal");
  await select.selectOption("ledger");
  await expect(page.locator("html")).toHaveAttribute("data-huntx-direction", "ledger");
  const ledgerColor = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--room-action").trim()
  );
  await select.selectOption("orbit");
  await expect(page.locator("html")).toHaveAttribute("data-huntx-direction", "orbit");
  const orbitColor = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--room-action").trim()
  );
  expect(ledgerColor).not.toBe(orbitColor);
  await page.locator("#btn-toggle-theme").click();
  await expect(page.locator("html")).toHaveClass(/light/);
  await expect(page.locator("html")).toHaveAttribute("data-huntx-direction", "orbit");
  await page.reload();
  await expect(select).toHaveValue("orbit");
  await expect(page.locator("html")).toHaveClass(/light/);
  await expect(page.locator("#tab-panel-artifacts")).toBeVisible();
});

for (const width of [320, 375, 768, 1440]) {
  test("subscription cards reflow and navigation stays operable at " + width + "px", async ({ page }) => {
    await mockDirectory(page);
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/#artifacts");
    await expect(page.locator("#subscription-hub")).toBeVisible();
    const bounds = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
      card: document.querySelector(".sub-protocol-card")?.getBoundingClientRect().right
    }));
    expect(bounds.scroll).toBeLessThanOrEqual(bounds.client + 1);
    expect(bounds.card).toBeLessThanOrEqual(width + 1);
    await page.locator("#tab-btn-proxies").click();
    await expect(page.locator("#tab-panel-proxies")).toBeVisible();
    await page.locator("#tab-btn-artifacts").click();
    await expect(page.locator("#subscription-hub")).toBeVisible();
  });
}
