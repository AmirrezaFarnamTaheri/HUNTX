import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const output = path.resolve("test-results/ui-review");

async function capture(page, route, file, width, height = 900) {
  await page.setViewportSize({ width, height });
  await page.route("**/*", async (request) => {
    const host = new URL(request.request().url()).hostname;
    return ["127.0.0.1", "localhost"].includes(host) ? request.continue() : request.abort();
  });
  await page.goto(route);
  if (route.startsWith("/network-doctor")) {
    await page.locator("#doctor-title").waitFor();
  } else {
    await page.locator("#filter-bar .workspace-intro").waitFor({ state: "attached" });
    const markers = {
      proxies: "#tab-panel-proxies #node-quick-search",
      studio: "#tab-panel-studio .studio-launch",
      decoder: "#tab-panel-decoder .inspector-workspace",
      artifacts: "#tab-panel-artifacts .artifacts-workspace"
    };
    const hash = route.split("#")[1] || "radar";
    await page.locator(markers[hash] || "#hero-section .radar-overview").waitFor({ state: "visible" });
  }
  await page.evaluate(() => document.fonts?.ready);
  if (!route.startsWith("/network-doctor") && (!route.includes("#") || route.endsWith("#radar"))) {
    // The globe intentionally stops drawing while off-screen. On mobile,
    // bring it into the viewport to obtain a real rendered frame, then
    // return to the page origin for a deterministic full-page capture.
    await page.locator("#telemetry-globe-canvas").scrollIntoViewIfNeeded();
    await page.waitForFunction(() => {
      const canvas = document.getElementById("telemetry-globe-canvas");
      if (!canvas?.width || !canvas?.height) return false;
      const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      for (let i = 3; i < pixels.length; i += 64) {
        if (pixels[i] > 0) return true;
      }
      return false;
    });
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await mkdir(output, { recursive: true });
  await page.screenshot({ path: path.join(output, file), fullPage: true, animations: "disabled" });
}

test("capture dashboard desktop and mobile for visual review", async ({ page }) => {
  await capture(page, "/", "dashboard-desktop-dark.png", 1440);
  await capture(page, "/", "dashboard-mobile-dark.png", 375, 812);
});

test("capture proxy explorer and RTL control room", async ({ page }) => {
  await capture(page, "/#proxies", "proxies-desktop-dark.png", 1440);
  await expect(page.locator("#tab-panel-proxies")).toBeVisible();
  await page.locator("#language-selector").selectOption("fa");
  await page.screenshot({ path: path.join(output, "proxies-desktop-rtl.png"), fullPage: true, animations: "disabled" });
});

test("capture Network Doctor dark, light, guidance and reported-result states", async ({ page }) => {
  await capture(page, "/network-doctor.html", "doctor-desktop-dark.png", 1440);
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "doctor-desktop-guidance-dark.png"), fullPage: true, animations: "disabled" });
  await page.locator("#doctor-theme-toggle").click();
  await page.screenshot({ path: path.join(output, "doctor-desktop-light.png"), fullPage: true, animations: "disabled" });
  await capture(page, "/network-doctor.html", "doctor-mobile-light.png", 375, 812);
  await page.getByRole("button", { name: "Show recovery steps" }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "doctor-mobile-guidance-light.png"), fullPage: true, animations: "disabled" });
  await page.locator("#doctor-original").selectOption("yes");
  await page.getByRole("button", { name: "Summarize my result" }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "doctor-mobile-reported-light.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Remember this manual result" }).click();
  await expect(page.locator("#doctor-recall")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "doctor-mobile-remembered-light.png"), fullPage: true, animations: "disabled" });
  await page.reload();
  await expect(page.locator("#doctor-recall")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "doctor-mobile-recalled-light.png"), fullPage: true, animations: "disabled" });
});

test("capture Atlas v2 subscription studio across desktop, light and phone layouts", async ({ page }) => {
  await capture(page, "/#studio", "atlas-studio-desktop-dark.png", 1440);
  await page.locator("#btn-toggle-theme").click();
  await page.screenshot({ path: path.join(output, "atlas-studio-desktop-light.png"), fullPage: true, animations: "disabled" });
  await capture(page, "/#studio", "atlas-studio-phone-light.png", 375, 812);
  await page.locator("#studio-routing-reference summary").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "atlas-studio-reference-light.png"), fullPage: true, animations: "disabled" });
});

test("capture Atlas v2 proxy explorer with first-viewport results and advanced filters", async ({ page }) => {
  await capture(page, "/#proxies", "atlas-proxies-desktop-dark.png", 1440);
  await page.locator("#advanced-filters summary").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "atlas-proxies-filters-dark.png"), fullPage: true, animations: "disabled" });
  await page.locator("#advanced-filters summary").click();
  await expect(page.locator("#advanced-filters")).not.toHaveAttribute("open");
  await capture(page, "/#proxies", "atlas-proxies-phone-dark.png", 375, 812);
});

test("capture Atlas v2 inspector and artifacts library", async ({ page }) => {
  await capture(page, "/#decoder", "atlas-inspector-desktop-dark.png", 1440);
  await capture(page, "/#artifacts", "atlas-artifacts-desktop-dark.png", 1440);
  await capture(page, "/#artifacts", "atlas-artifacts-phone-dark.png", 375, 812);
});

test("capture all three subscription-library directions with a metadata fixture", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const digest = "a".repeat(64);
  const counts = { vless: 100, vmess: 40, trojan: 8, anytls: 1, wireguard: 0 };
  const protocols = Object.fromEntries(Object.entries(counts).map(([name, count]) => [
    name, { count, file: name + ".txt", base64_file: name + "_base64.txt", sha256: digest }
  ]));
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return route.abort();
    if (url.pathname.endsWith("/subscriptions/latest/index.json")) return route.fulfill({
      contentType: "application/json", status: 200,
      body: JSON.stringify({
        schema_version: 1, scope: "all_time_cumulative",
        health_status: "historical_unverified",
        generated_at: "2026-11-21T10:00:00Z", latest_by: "first_seen",
        limit_per_protocol: 100, protocols,
        aggregate: { count: 149, file: "all.txt", base64_file: "all_base64.txt", sha256: digest }
      })
    });
    return route.continue();
  });

  await page.goto("/subscriptions.html");
  await expect(page.locator("#protocol-grid .protocol-card")).toHaveCount(5);
  await mkdir(output, { recursive: true });
  for (const design of ["signal", "canvas", "ledger"]) {
    await page.locator(`[data-design-option="${design}"]`).click();
    await expect(page.locator("html")).toHaveAttribute("data-design", design);
    await page.screenshot({
      path: path.join(output, `subscription-library-${design}-desktop.png`),
      fullPage: true, animations: "disabled"
    });
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({
    path: path.join(output, "subscription-library-ledger-mobile.png"),
    fullPage: true, animations: "disabled"
  });
});
