// HUNTX ServiceWorker — Offline Cache-First Architecture
const CACHE_NAME = 'huntx-cache-v2.8';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './architecture.html',
  './catalog.json',
  './assets/js/bundle.js',
  './assets/js/decoder.js',
  './assets/js/wasm_exec.js',
  './assets/js/rule-studio.js',
  './assets/huntx_engine.wasm',
  './manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
        console.warn('[HUNTX-SW] Cache prefetch partial warning:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((k) => {
          if (k !== CACHE_NAME) {
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
  // Published feeds must not lag behind their catalog after a deployment.
  const freshReleaseData = path.endsWith('/catalog.json') || path.includes('/artifacts/release/');
  event.respondWith(
    freshReleaseData ? fetch(event.request).then((response) => {
      if (response && response.ok) caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
      return response;
    }).catch(() => caches.match(event.request)) :
    caches.match(event.request).then((cached) => {
      if (cached) {
        // Return cached and update in background
        fetch(event.request).then((resp) => {
          if (resp && resp.status === 200) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
        }).catch(() => {});
        return cached;
      }
      return fetch(event.request).then((resp) => {
        if (!resp || resp.status !== 200 || resp.type !== 'basic') {
          return resp;
        }
        const copy = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return resp;
      });
    }).catch(() => event.request.mode === 'navigate'
      ? caches.match('./index.html')
      : new Response('Offline resource unavailable', { status: 503, statusText: 'Service Unavailable' }))
  );
});
