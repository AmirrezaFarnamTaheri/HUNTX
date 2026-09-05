// HUNTX ServiceWorker — offline fallback with deployment-aware freshness.
const CACHE_NAME = 'huntx-cache-v4.0';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './architecture.html',
  './catalog.json',
  './assets/css/tailwind.css',
  './assets/js/app.js',
  './assets/js/globe.js',
  './assets/js/i18n.js',
  './assets/js/qrcode.js',
  './assets/js/decoder.js',
  './assets/js/wasm_exec.js',
  './assets/js/rule-studio.js',
  './assets/huntx_engine.wasm',
  './manifest.json'
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
  const freshReleaseData = path.endsWith('/catalog.json') || path.includes('/artifacts/release/');
  const deploymentShell = event.request.mode === 'navigate'
    || path.endsWith('/index.html')
    || path.endsWith('/assets/js/app.js')
    || path.endsWith('/assets/css/tailwind.css')
    || path.endsWith('/sw.js');
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
      if (event.request.mode === 'navigate') return caches.match('./index.html');
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
