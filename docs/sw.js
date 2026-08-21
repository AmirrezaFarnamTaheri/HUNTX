// HUNTX ServiceWorker — Offline Cache-First Architecture
const CACHE_NAME = 'huntx-cache-v2.6';
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
  event.respondWith(
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
    }).catch(() => caches.match('./index.html'))
  );
});
