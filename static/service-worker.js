/* Creative Video Studio — Service Worker
 * Strategy:
 *   static assets  → cache-first  (serve instantly, update in background)
 *   API calls      → network-first (always try live data, cache as fallback)
 *   navigation     → network-first, fallback to cached shell
 *
 * Bump CACHE_VERSION to force a full cache refresh on next app load.
 */

const CACHE_VERSION = 'v1';
const CACHE_NAME    = `video-studio-${CACHE_VERSION}`;

const PRECACHE_ASSETS = [
  '/',
  '/static/index.html',
  '/static/app.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable-192.png',
];

const OFFLINE_FALLBACK_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Creative Video Studio — Offline</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      background: #1a1108; color: #f9e8d2;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      text-align: center; padding: 2rem;
    }
    .icon { font-size: 4rem; margin-bottom: 1.5rem; }
    h1 { font-size: 1.5rem; color: #e8a76a; margin-bottom: 0.75rem; }
    p  { color: #963f16; font-size: 0.95rem; line-height: 1.6; max-width: 320px; }
    .retry {
      margin-top: 2rem;
      background: #d07020; color: #fff;
      border: none; border-radius: 8px;
      padding: 12px 28px; font-size: 1rem;
      font-weight: 600; cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="icon">🎬</div>
  <h1>You're Offline</h1>
  <p>Creative Video Studio needs a connection to generate videos and sync with Notion. Reconnect to continue.</p>
  <button class="retry" onclick="location.reload()">Try Again</button>
</body>
</html>`;


// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // Pre-cache known static assets (ignore individual failures)
      await Promise.allSettled(
        PRECACHE_ASSETS.map((url) =>
          cache.add(url).catch((err) =>
            console.warn(`[SW] Pre-cache failed for ${url}:`, err)
          )
        )
      );
      // Store the offline fallback HTML
      await cache.put(
        '/__offline',
        new Response(OFFLINE_FALLBACK_HTML, {
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        })
      );
    })
  );
  // Activate new SW immediately without waiting for old clients to close
  self.skipWaiting();
});


// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('video-studio-') && k !== CACHE_NAME)
          .map((k) => {
            console.log(`[SW] Deleting old cache: ${k}`);
            return caches.delete(k);
          })
      )
    )
  );
  // Take control of all open clients immediately
  self.clients.claim();
});


// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // ── API calls: network-first ──────────────────────────────────────────────
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithCache(request));
    return;
  }

  // ── Service worker / manifest: network only ───────────────────────────────
  if (
    url.pathname === '/service-worker.js' ||
    url.pathname.endsWith('manifest.json')
  ) {
    event.respondWith(fetch(request));
    return;
  }

  // ── Output files (generated videos/audio): network only ──────────────────
  if (url.pathname.startsWith('/output/')) {
    event.respondWith(fetch(request).catch(() => offlineFallback(request)));
    return;
  }

  // ── Static assets & navigation: stale-while-revalidate ───────────────────
  event.respondWith(staleWhileRevalidate(request));
});


// ── Strategies ────────────────────────────────────────────────────────────────

async function networkFirstWithCache(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response.ok) {
      // Only cache GET responses for potential offline fallback
      if (request.method === 'GET') {
        cache.put(request, response.clone());
      }
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    // Return a JSON error so the app can handle it gracefully
    return new Response(
      JSON.stringify({ error: 'offline', detail: 'No network connection' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  const networkFetch = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  // Return cached immediately; update cache in background
  if (cached) {
    networkFetch.catch(() => {}); // fire-and-forget background update
    return cached;
  }

  // Nothing cached — wait for network
  const networkResponse = await networkFetch;
  if (networkResponse) return networkResponse;
  return offlineFallback(request);
}

async function offlineFallback(request) {
  // For navigation requests return the offline HTML page
  if (request.mode === 'navigate') {
    const cache = await caches.open(CACHE_NAME);
    return (await cache.match('/__offline')) ||
      new Response('Offline', { status: 503 });
  }
  return new Response('Offline', { status: 503 });
}


// ── Background Sync (optional — queued API retries) ───────────────────────────
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-generation-status') {
    event.waitUntil(syncGenerationStatus());
  }
});

async function syncGenerationStatus() {
  // When connectivity returns, notify all clients to refresh job statuses
  const clients = await self.clients.matchAll({ type: 'window' });
  clients.forEach((client) =>
    client.postMessage({ type: 'SYNC_STATUS' })
  );
}


// ── Push notifications (optional) ────────────────────────────────────────────
self.addEventListener('push', (event) => {
  const data = event.data?.json() ?? {};
  event.waitUntil(
    (async () => {
      try {
        await self.registration.showNotification(data.title || 'Creative Video Studio', {
          body: data.body || 'Your video is ready!',
          icon: '/static/icons/icon-192.png',
          badge: '/static/icons/icon-192.png',
          data: data.url ? { url: data.url } : {},
        });
      } catch (err) {
        console.warn('[SW] showNotification failed:', err);
      }
    })()
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        const existing = clients.find((c) => c.url === url && 'focus' in c);
        if (existing) return existing.focus();
        return self.clients.openWindow(url);
      })
  );
});
