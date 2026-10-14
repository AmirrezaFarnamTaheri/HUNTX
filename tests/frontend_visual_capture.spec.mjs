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
    await page.locator(route.includes("#proxies") ? "#tab-panel-proxies" : "#hero-section .radar-overview").waitFor({ state: "visible" });
  }
  await page.evaluate(() => document.fonts?.ready);
  if (!route.startsWith("/network-doctor") && !route.includes("#proxies")) {
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
