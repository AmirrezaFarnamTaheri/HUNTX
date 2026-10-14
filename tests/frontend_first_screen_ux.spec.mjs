import { test, expect } from '@playwright/test';

async function localOnly(page) {
  await page.route('**/*', (route) => {
    const host = new URL(route.request().url()).hostname;
    return ['127.0.0.1', 'localhost'].includes(host) ? route.continue() : route.abort();
  });
}

test('published proxy search and results appear in the first desktop viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await localOnly(page);
  await page.goto('/#proxies');
  const search = page.locator('#node-quick-search');
  const results = page.locator('#nodes-grid');
  await expect(search).toBeVisible();
  await expect(results).toBeVisible();
  const searchBox = await search.boundingBox();
  const resultsBox = await results.boundingBox();
  expect(searchBox.y).toBeLessThan(570);
  expect(resultsBox.y).toBeLessThan(900);
  await expect(page.locator('#filter-bar > .proxy-workspace')).toHaveCSS('border-top-width', '0px');
});

test('secondary proxy controls use a stable, keyboard-operable disclosure', async ({ page }) => {
  await localOnly(page);
  await page.goto('/#proxies');
  const advanced = page.locator('#proxy-advanced');
  await expect(advanced).toBeVisible();
  await expect(advanced).not.toHaveAttribute('open');
  const summary = advanced.locator('summary');
  await expect(summary).toContainText('Advanced filters');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(advanced).toHaveAttribute('open', '');
  await expect(page.locator('#select-transport')).toBeVisible();
  const selector = page.locator('#select-transport');
  await selector.focus();
  await selector.selectOption('ALL');
  await expect(page.locator('#select-transport')).toBeFocused();
  await expect(advanced).toHaveAttribute('open', '');
});

test('measurement evidence stays discoverable without consuming the primary workspace', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await localOnly(page);
  await page.goto('/#proxies');
  const mainSearch = page.locator('#node-quick-search');
  const evidence = page.locator('#evidence-overview');
  await expect(evidence).toBeVisible();
  const searchBox = await mainSearch.boundingBox();
  const evidenceBox = await evidence.boundingBox();
  expect(searchBox.y).toBeLessThan(evidenceBox.y);
  await expect(evidence.locator('.btn-evidence-filter')).toHaveCount(6);
  await expect(evidence.locator('details summary')).toContainText('What counts as evidence');
});

test('studio provides real feed downloads and does not present examples as a working builder', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await localOnly(page);
  await page.goto('/#studio');
  await expect(page.locator('#workspace-title')).toHaveText('Get node subscriptions');
  await expect(page.locator('#studio-feed-start')).toBeVisible();
  await expect(page.locator('#studio-feed-start a[data-artifact]')).toHaveCount(2);
  await expect(page.locator('#studio-feed-start a[data-artifact]').first()).toHaveAttribute('download', '');
  const examples = page.locator('#routing-examples');
  await expect(examples).toBeVisible();
  await expect(examples).not.toHaveAttribute('open');
  await expect(examples.locator('.studio-routing-example')).toBeHidden();
  await examples.locator('summary').click();
  await expect(examples.locator('.studio-routing-example')).toBeVisible();
  await expect(examples.locator('.studio-routing-example')).toContainText('Routing Pipeline Flow');
  await page.locator('#studio-customize-proxies').click();
  await expect(page.locator('#tab-btn-proxies')).toHaveAttribute('aria-selected', 'true');
});

for (const width of [375, 768]) {
  test('first-screen explorer and studio remain usable at ' + width + 'px', async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    await localOnly(page);
    await page.goto('/#proxies');
    await expect(page.locator('#node-quick-search')).toBeVisible();
    await expect(page.locator('#proxy-advanced')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await page.goto('/#studio');
    await expect(page.locator('#studio-feed-start')).toBeVisible();
    await expect(page.locator('#routing-examples')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
  });
}
