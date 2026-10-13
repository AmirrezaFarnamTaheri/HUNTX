import { test, expect } from "@playwright/test";

async function localOnly(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(url.hostname)) {
      return route.continue();
    }
    return route.abort();
  });
}

test("observability landing makes evidence and snapshot limitations clear", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  await expect(page.locator(".radar-summary h1")).toBeVisible();
  await expect(page.locator("#evidence-strip")).toBeVisible();
  await expect(page.locator("#evidence-strip")).toContainText("Authenticated");
  await expect(page.locator("#evidence-strip")).toContainText("Unverified");
  await expect(page.locator("#evidence-strip")).toContainText("Unknown location");
  await expect(page.locator(".radar-description")).toContainText("Artifact checksums do not verify connectivity");
  const cards = page.locator("#evidence-strip .evidence-stat");
  await expect(cards).toHaveCount(3);
  for (const card of await cards.all()) {
    const data = await card.locator("[data-evidence-count]").textContent();
    expect(Number.isInteger(Number(data?.replaceAll(",", "")))).toBe(true);
  }
});

test("small-screen search jumps to proxy workspace and focuses query field", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 820 });
  await localOnly(page);
  await page.goto("/");
  const search = page.getByRole("button", { name: "Search published proxies" });
  await expect(search).toBeVisible();
  await search.click();
  await expect(page.locator("#tab-btn-proxies")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#node-quick-search")).toBeFocused();
  await page.keyboard.type("vless");
  await expect(page.locator("#node-quick-search")).toHaveValue("vless");
});

test("filter summaries expose removable, keyboard-operable active filters", async ({ page }) => {
  await localOnly(page);
  await page.goto("/#proxies");
  await page.waitForFunction(() => Boolean(window.huntxApp));
  await page.evaluate(() => {
    const app = window.huntxApp;
    app.selectedProtocol = "VLESS";
    app.searchQuery = "demo";
    app.refreshProxyWorkspace();
  });
  const chips = page.locator("#active-filter-chips");
  await expect(chips).toContainText("VLESS");
  await expect(chips).toContainText("demo");
  const clear = page.getByRole("button", { name: /Remove protocol filter/i });
  await clear.focus();
  await page.keyboard.press("Enter");
  await expect(chips).not.toContainText("VLESS");
  await expect(chips).toContainText("demo");
});

test("radar operator and geo drilldowns work from the keyboard", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  const operator = page.locator(".operator-card[role=button]").first();
  await expect(operator).toBeVisible();
  await operator.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#tab-btn-proxies")).toHaveAttribute("aria-selected", "true");
  await page.locator("#tab-btn-radar").click();
  const country = page.locator(".geo-density-row[role=button]").first();
  if (await country.count()) {
    await country.focus();
    await page.keyboard.press("Space");
    await expect(page.locator("#tab-btn-proxies")).toHaveAttribute("aria-selected", "true");
  }
});

for (const width of [320, 375, 768, 1440]) {
  test(`responsive evidence console avoids horizontal page overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await localOnly(page);
    await page.goto("/");
    await expect(page.locator("#evidence-strip")).toBeVisible();
    const metrics = await page.evaluate(() => ({
      screen: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      cards: [...document.querySelectorAll("#evidence-strip .evidence-stat")].map((node) => {
        const rect = node.getBoundingClientRect();
        return { left: rect.left, right: rect.right };
      }),
    }));
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.screen + 1);
    for (const rect of metrics.cards) {
      expect(rect.left).toBeGreaterThanOrEqual(-1);
      expect(rect.right).toBeLessThanOrEqual(width + 1);
    }
  });
}
