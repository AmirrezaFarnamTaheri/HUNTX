// Deployment version-skew tests.
//
// HUNTX is a static site behind a service worker. A visitor's browser can hold
// last deployment's modules while the page and entry script are this
// deployment's. When the entry script imports an export the cached module does
// not have, the module graph fails to link and the dashboard never boots.
//
// These tests drive a real browser through "visit, deploy, visit again" against
// a server whose document root is swapped mid-test. They deliberately use the
// real docs/ shell and the real sw.js so they exercise the shipped caching
// logic, not a model of it.

import { test, expect } from "@playwright/test";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_DOCS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "docs");
const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

// A trimmed copy of the caching logic that shipped BEFORE the fix: only the
// entry script and stylesheet were network-first; every other module was
// cache-first with a background refresh. Visitors still running this worker on
// deploy day are the population the boot guard exists to rescue.
const LEGACY_SW = `
const CACHE_NAME = 'huntx-cache-v4.0';
const ASSETS = ['./', './index.html', './assets/js/app.js', './assets/js/decoder.js', './assets/css/tailwind.css'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then(async (c) => {
    await Promise.all(ASSETS.map(async (a) => c.put(a, await fetch(a, { cache: 'reload' }))));
    await self.skipWaiting();
  }));
});
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const path = new URL(event.request.url).pathname;
  const shell = event.request.mode === 'navigate' || path.endsWith('/index.html')
    || path.endsWith('/assets/js/app.js') || path.endsWith('/assets/css/tailwind.css');
  if (shell) {
    event.respondWith(fetch(event.request).then(async (r) => {
      if (r && r.ok) (await caches.open(CACHE_NAME)).put(event.request, r.clone());
      return r;
    }).catch(() => caches.match(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then((cached) => {
    if (cached) return cached;
    return fetch(event.request).then(async (r) => {
      if (r && r.status === 200) (await caches.open(CACHE_NAME)).put(event.request, r.clone());
      return r;
    });
  }));
});
`;

/** Copy only what the service worker precaches, not the 150 MB of artifacts. */
function copyShell(dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const file of ["index.html", "architecture.html", "catalog.json", "manifest.json", "sw.js"]) {
    fs.copyFileSync(path.join(REPO_DOCS, file), path.join(dest, file));
  }
  fs.cpSync(path.join(REPO_DOCS, "assets"), path.join(dest, "assets"), { recursive: true });
}

/** Simulate a new deployment: the entry script now imports a new decoder export. */
function applyDeploy(dest, { exportExists }) {
  const decoder = path.join(dest, "assets/js/decoder.js");
  const app = path.join(dest, "assets/js/app.js");
  if (exportExists) {
    fs.appendFileSync(decoder, '\nexport const __deployProbe = "new";\n');
  }
  const original = fs.readFileSync(app, "utf8");
  fs.writeFileSync(
    app,
    'import { __deployProbe } from "./decoder.js";\nglobalThis.__deployProbe = __deployProbe;\n' + original
  );
}

/** A server whose document root can be swapped between visits. */
function startSwitchableServer() {
  let root = null;
  const server = http.createServer((req, res) => {
    let pathname = decodeURIComponent(req.url.split("?")[0]);
    if (pathname.endsWith("/")) pathname += "index.html";
    const file = path.join(root, pathname);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
      "cache-control": "no-cache",
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({
        url: `http://127.0.0.1:${server.address().port}/`,
        serve: (dir) => {
          root = dir;
        },
        close: () => new Promise((done) => server.close(done)),
      });
    });
  });
}

async function withDeployments(t, { legacyServiceWorker = false, exportExists = true }, body) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "huntx-skew-"));
  const before = path.join(tmp, "before");
  const after = path.join(tmp, "after");
  copyShell(before);
  copyShell(after);
  if (legacyServiceWorker) {
    // Deploy N-1 shipped with the old worker. Deploy N ships the fixed one.
    fs.writeFileSync(path.join(before, "sw.js"), LEGACY_SW);
  }
  applyDeploy(after, { exportExists });

  const site = await startSwitchableServer();
  try {
    await body({ site, before, after });
  } finally {
    await site.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

async function firstVisit(page, site, before) {
  site.serve(before);
  await page.goto(site.url);
  // Wait for the worker to take control, then reload so this visit is served by it.
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await page.waitForTimeout(1500);
  await page.reload();
  await page.waitForTimeout(1000);
}

test("a deploy that adds a module export does not break a returning visitor", async ({ browser }, testInfo) => {
  await withDeployments(testInfo, {}, async ({ site, before, after }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await firstVisit(page, site, before);
    expect(pageErrors, "the first deployment must boot cleanly").toEqual([]);

    site.serve(after);
    await page.reload();
    await page.waitForFunction(() => globalThis.__deployProbe === "new", null, { timeout: 15_000 });

    expect(pageErrors, "returning visitor hit a module version skew").toEqual([]);
    await context.close();
  });
});

test("the boot guard rescues a visitor still running the legacy worker", async ({ browser }, testInfo) => {
  await withDeployments(testInfo, { legacyServiceWorker: true }, async ({ site, before, after }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    let navigations = 0;
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) navigations += 1;
    });

    await firstVisit(page, site, before);
    navigations = 0;

    // The legacy worker serves the new entry script alongside the OLD cached
    // decoder.js. Without the guard this is the dashboard-fails-to-boot case.
    site.serve(after);
    await page.reload();

    await page.waitForFunction(() => globalThis.__deployProbe === "new", null, { timeout: 20_000 });
    expect(navigations, "recovery should cost exactly one extra reload").toBeLessThanOrEqual(2);
    await context.close();
  });
});

test("a genuinely broken deploy fails visibly instead of reloading forever", async ({ browser }, testInfo) => {
  await withDeployments(testInfo, { exportExists: false }, async ({ site, before, after }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    let navigations = 0;
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) navigations += 1;
    });
    page.on("pageerror", () => {});

    await firstVisit(page, site, before);
    navigations = 0;

    site.serve(after);
    await page.reload();
    // Long enough for a reload loop to show itself many times over.
    await page.waitForTimeout(6000);

    expect(navigations, "the guard must attempt recovery at most once per session").toBeLessThanOrEqual(3);
    await context.close();
  });
});
