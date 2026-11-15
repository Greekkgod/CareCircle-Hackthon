/**
 * CareCircle Progressive Web App Service Worker
 * Provides offline caching for application shell, static assets,
 * and caches today's medication schedule for resilient offline senior access.
 */

const STATIC_CACHE = "carecircle-static-v4";
const API_CACHE = "carecircle-api-v4";

const STATIC_ASSETS = [
  "/",
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/icons/icon.svg",
  "/manifest.webmanifest"
];

// Install: precache static shell assets and immediately skip waiting
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean up outdated cache buckets and claim clients immediately
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== STATIC_CACHE && key !== API_CACHE) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Strategy for shell and API requests
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // 1. API Calls (Medications & Appointments Schedule)
  if (url.pathname.startsWith("/api/")) {
    if (event.request.method === "GET") {
      // Network-first with API cache fallback for offline schedule access
      event.respondWith(
        fetch(event.request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              const clone = networkResponse.clone();
              caches.open(API_CACHE).then((cache) => {
                cache.put(event.request, clone);
              });
            }
            return networkResponse;
          })
          .catch(async () => {
            const cached = await caches.match(event.request);
            if (cached) {
              return cached;
            }
            return new Response(
              JSON.stringify({
                offline: true,
                message: "Offline mode. Showing cached medication schedule.",
                data: []
              }),
              {
                status: 200,
                headers: { "Content-Type": "application/json" }
              }
            );
          })
      );
      return;
    }

    // For POST/PATCH mutations when offline: pass through or handle client queue
    return;
  }

  // 2. Static Assets: Network-first, cache fallback (ensures updates are live immediately)
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(STATIC_CACHE).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return networkResponse;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) {
          return cached;
        }
        return new Response("Offline mode. Asset not in cache.", { status: 503 });
      })
  );
});
