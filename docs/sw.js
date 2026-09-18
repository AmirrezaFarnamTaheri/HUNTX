// HUNTX ServiceWorker — offline fallback with deployment-aware freshness.
const CACHE_NAME = 'huntx-cache-v5.0';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './architecture.html',
  './catalog.json',
  './assets/css/tailwind.css',
  './assets/js/boot-guard.js',
  './assets/js/app.js',
  './assets/js/globe.js',
  './assets/js/i18n.js',
  './assets/js/qrcode.js',
  './assets/js/decoder.js',
  './assets/js/rule-studio.js',
  './manifest.json'
  // Deliberately absent: assets/huntx_engine.wasm (2.6 MB) and wasm_exec.js.
  // No page loads them today, so precaching them made every first visit
  // download 2.6 MB for nothing -- and because install fails if any entry
  // fails, a slow connection could break offline support for a feature that
  // does not exist. If a WASM worker is wired up later, cache it on first use
  // (the runtime cache-first path below does this) or add it back here.
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      const results = await Promise.allSettled(ASSETS_TO_CACHE.map(async (asset) => {
        const response = await fetch(asset, { cache: 'reload' });
        if (!response.ok) throw new Error(`Cache prefetch failed: ${asset} (${response.status})`);
        await cache.put(asset, response);
      }));
      const failed = results.filter((result) => result.status === 'rejected');
      if (failed.length) {
        await caches.delete(CACHE_NAME);
        throw new Error(`[HUNTX-SW] Cache prefetch failed for ${failed.length} required asset(s)`);
      }
      await self.skipWaiting();
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((k) => {
          if (k.startsWith('huntx-cache-') && k !== CACHE_NAME) {
            return caches.delete(k);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const path = new URL(event.request.url).pathname;
  // Published feeds and the deployment shell must not lag after a deployment.
  const freshReleaseData = path.endsWith('/catalog.json')
    || path.includes('/artifacts/release/')
    // data.js is the bundled telemetry snapshot; serving it cache-first showed
    // returning visitors the previous run's numbers for one whole visit.
    || path.endsWith('/assets/js/data.js');
  // Every first-party script and stylesheet is part of the shell, not just the
  // entry point. app.js imports decoder.js, globe.js, i18n.js and qrcode.js as
  // ES modules; if those were served cache-first while app.js was fetched fresh,
  // a deploy that adds an export produced a new app.js importing from an old
  // cached module -- "does not provide an export named ..." -- and the
  // dashboard failed to boot for that visit. Code must never version-skew, so
  // all of it is network-first. Binary assets (wasm) stay cache-first.
  const deploymentShell = event.request.mode === 'navigate'
    || path.endsWith('/index.html')
    || path.endsWith('/manifest.json')
    || path.endsWith('/sw.js')
    || /\/assets\/(js|css)\/[^/]+\.(js|css)$/.test(path);
  const networkFirst = (request) => fetch(request).then(async (response) => {
    if (response && response.ok) {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    }
    return response;
  }).catch(() => caches.match(request));
  event.respondWith(
    (freshReleaseData || deploymentShell) ? networkFirst(event.request).then((response) => {
      if (response) return response;
      if (event.request.mode === 'navigate') {
        return caches.match('./index.html').then((fallback) => fallback || new Response('Offline dashboard unavailable', { status: 503, statusText: 'Service Unavailable' }));
      }
      return new Response('Offline resource unavailable', { status: 503, statusText: 'Service Unavailable' });
    }) :
    caches.match(event.request).then((cached) => {
      if (cached) {
        // Return cached and update in background
        event.waitUntil(fetch(event.request).then(async (resp) => {
          if (resp && resp.status === 200) {
            const copy = resp.clone();
            const cache = await caches.open(CACHE_NAME);
            await cache.put(event.request, copy);
          }
        }).catch(() => {}));
        return cached;
      }
      return fetch(event.request).then(async (resp) => {
        if (!resp || resp.status !== 200 || resp.type !== 'basic') {
          return resp;
        }
        const copy = resp.clone();
        const cache = await caches.open(CACHE_NAME);
        await cache.put(event.request, copy);
        return resp;
      });
    }).catch(() => event.request.mode === 'navigate'
      ? caches.match('./index.html')
      : new Response('Offline resource unavailable', { status: 503, statusText: 'Service Unavailable' }))
  );
});
