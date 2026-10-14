import { test, expect } from "@playwright/test";

async function localOnly(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(url.hostname)) {
      await route.continue();
    } else {
      await route.abort();
    }
  });
}

test("dashboard offers a discoverable Network Doctor link", async ({ page }) => {
  await localOnly(page);
  await page.goto("/");
  const link = page.getByRole("link", { name: /Fix connection/i });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(/\/network-doctor\.html$/);
  await expect(page.getByRole("heading", { name: /fix your connection/i })).toBeVisible();
});

test("manual wizard is actionable without claiming to have run a proxy test", async ({ page }) => {
  await localOnly(page);
  await page.goto("/network-doctor.html");
  await page.locator("#doctor-platform").selectOption("android");
  await page.locator("#doctor-network").selectOption("wifi");
  await page.locator("#doctor-symptom").selectOption("timeout");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await expect(page.locator("#doctor-actions > li")).toHaveCount(3);
  await expect(page.locator("#doctor-device-hint")).toContainText("VPN");
  await expect(page.locator("#doctor-plan")).toContainText("mobile data");
  await expect(page.locator("#doctor-plan")).toContainText("not");
  await page.locator("#doctor-original").selectOption("no");
  await page.locator("#doctor-alternative").selectOption("yes");
  await page.getByRole("button", { name: "Summarize my result" }).click();
  await expect(page.locator("#doctor-result-title")).toContainText("replacement");
  await expect(page.locator("#doctor-result-detail")).toContainText("original");
  await expect(page.locator("#doctor-report")).toHaveValue(/self-reported/i);
});

test("unsafe TLS change cannot be marked as recovered", async ({ page }) => {
  await localOnly(page);
  await page.goto("/network-doctor.html");
  await page.locator("#doctor-symptom").selectOption("tls");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await expect(page.locator("#doctor-plan")).toContainText("Do not disable certificate verification");
  await page.locator("#doctor-original").selectOption("yes");
  await page.locator("#doctor-tls-disabled").check();
  await page.getByRole("button", { name: "Summarize my result" }).click();
  await expect(page.locator("#doctor-result-title")).toContainText("Unsafe");
  await expect(page.locator("#doctor-result-detail")).toContainText("Restore");
});

test("catalog check shows snapshot metadata rather than claiming proxy health", async ({ page }) => {
  await localOnly(page);
  await page.route("**/catalog.json", async (route) => {
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ files: [{ tags: ["subscription"] }], generated_at: "2026-10-14T01:25:09Z" })
    });
  });
  await page.goto("/network-doctor.html");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await page.getByRole("button", { name: "Check published catalog" }).click();
  await expect(page.locator("#doctor-catalog-status")).toContainText("1 subscription");
  await expect(page.locator("#doctor-catalog-status")).toContainText("not verify");
});

test("small screens keep controls reachable without horizontal page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 850 });
  await localOnly(page);
  await page.goto("/network-doctor.html");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1);
  await expect(page.locator("#doctor-outcome-form")).toBeVisible();
});

test("changing the diagnosis clears a previously reported recovery", async ({ page }) => {
  await localOnly(page);
  await page.goto("/network-doctor.html");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await page.locator("#doctor-original").selectOption("yes");
  await page.getByRole("button", { name: "Summarize my result" }).click();
  await expect(page.locator("#doctor-result")).toBeVisible();
  await page.locator("#doctor-symptom").selectOption("tls");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await expect(page.locator("#doctor-original")).toHaveValue("unknown");
  await expect(page.locator("#doctor-alternative")).toHaveValue("unknown");
  await expect(page.locator("#doctor-result")).toBeHidden();
  await page.locator("#doctor-original").selectOption("yes");
  await page.getByRole("button", { name: "Summarize my result" }).click();
  await page.locator("#doctor-original").selectOption("no");
  await expect(page.locator("#doctor-result")).toBeHidden();
});

test("catalog check warns about stale metadata without calling the proxy healthy", async ({ page }) => {
  await localOnly(page);
  await page.route("**/catalog.json", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      generated_at: "2020-01-01T00:00:00Z",
      files: [{ tags: ["subscription"] }]
    })
  }));
  await page.goto("/network-doctor.html");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await page.getByRole("button", { name: "Check published catalog" }).click();
  const status = page.locator("#doctor-catalog-status");
  await expect(status).toContainText(/stale|outdated/i);
  await expect(status).toContainText(/does not verify proxy connectivity/i);
  await expect(status).toHaveAttribute("data-freshness", "stale");
});

test("a delayed catalog response cannot overwrite a reset diagnosis", async ({ page }) => {
  await localOnly(page);
  let release;
  await page.route("**/catalog.json", async (route) => {
    await new Promise((resolve) => { release = resolve; });
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ generated_at: "2026-10-14T01:25:09Z", files: [{ tags: ["subscription"] }] })
    });
  });
  await page.goto("/network-doctor.html");
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await page.getByRole("button", { name: "Check published catalog" }).click();
  await expect(page.locator("#doctor-catalog-check")).toBeDisabled();
  await expect.poll(() => typeof release).toBe("function");
  await page.getByRole("button", { name: "Start over" }).click();
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  const response = page.waitForResponse((item) => item.url().endsWith("/catalog.json"));
  release();
  await response;
  await page.waitForTimeout(50);
  await expect(page.locator("#doctor-catalog-status")).toContainText("Not checked");
  await expect(page.locator("#doctor-catalog-check")).toBeEnabled();
});
