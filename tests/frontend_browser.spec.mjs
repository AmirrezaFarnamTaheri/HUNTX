import { test, expect } from "@playwright/test";

async function isolateLocalPage(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      await route.continue();
    } else {
      await route.abort();
    }
  });
}

for (const width of [320, 375, 640, 768, 1024, 1280]) {
  test(`header is usable without clipping at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await isolateLocalPage(page);
    await page.goto("/");
    await expect(page.locator("#main-header")).toBeVisible();
    const metrics = await page.locator("#main-header").evaluate((header) => {
      const visible = [...header.querySelectorAll("button, select, a")]
        .filter((el) => {
          const style = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
        })
        .map((el) => {
          const rect = el.getBoundingClientRect();
          return { left: rect.left, right: rect.right };
        });
      return {
        scrollWidth: header.scrollWidth,
        clientWidth: header.clientWidth,
        minLeft: Math.min(...visible.map((item) => item.left)),
        maxRight: Math.max(...visible.map((item) => item.right))
      };
    });
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
    expect(metrics.minLeft).toBeGreaterThanOrEqual(-1);
    expect(metrics.maxRight).toBeLessThanOrEqual(width + 1);

    const tools = page.locator("#btn-header-tools");
    await expect(tools).toBeVisible();
    await expect(tools).toHaveAttribute("aria-expanded", "false");
    await tools.click();
    await expect(page.locator("#header-tools-menu")).toBeVisible();
    await expect(tools).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("#header-tools-menu")).toBeHidden();
    await expect(tools).toHaveAttribute("aria-expanded", "false");
  });
}

test("coarse-pointer tablet gets an explicit, stateful globe gate", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1024, height: 900 },
    hasTouch: true,
    isMobile: true,
    deviceScaleFactor: 1
  });
  const page = await context.newPage();
  await isolateLocalPage(page);
  await page.goto("/");
  expect(await page.evaluate(() => matchMedia("(any-pointer: coarse)").matches)).toBe(true);
  const gate = page.locator("#globe-touch-gate");
  const button = page.locator("#btn-globe-touch-toggle");
  await expect(gate).toBeVisible();
  await expect(button).toHaveAttribute("aria-pressed", "false");
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await context.close();
});

test("Persian locale updates semantics while technical data remains LTR", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  const selector = page.locator("#language-selector");
  await selector.selectOption("fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(selector).toHaveAttribute("aria-label", "زبان");
  await expect(selector).toHaveAttribute("title", "زبان");
  const direction = await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.className = "technical-ltr";
    probe.textContent = "1.2.3.4:443 / abc-def";
    document.body.appendChild(probe);
    return getComputedStyle(probe).direction;
  });
  expect(direction).toBe("ltr");
});

test("mobile tabs expose horizontal scrolling rather than hiding overflow affordance", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  const scroller = page.locator("#page-tabs-nav > div");
  const metrics = await scroller.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    scrollbarWidth: getComputedStyle(el).scrollbarWidth
  }));
  expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
  expect(metrics.scrollbarWidth).not.toBe("none");
  const moved = await scroller.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
    return el.scrollLeft;
  });
  expect(Math.abs(moved)).toBeGreaterThan(0);
});
