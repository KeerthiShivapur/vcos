/**
 * VCOS Service Worker
 *
 * Provides:
 * - App Shell caching (static assets)
 * - Runtime caching with stale-while-revalidate
 * - Background sync for offline operations
 * - Push notifications (FCM)
 * - Offline fallback page
 * - Cache management and versioning
 */

const CACHE_VERSION = "vcos-v1.0.0";
const STATIC_CACHE = `vcos-static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `vcos-runtime-${CACHE_VERSION}`;
const OFFLINE_CACHE = `vcos-offline-${CACHE_VERSION}`;

// Assets to cache immediately (App Shell)
const STATIC_ASSETS = [
  "/",
  "/manifest.json",
  "/offline.html",
  "/icon-192.png",
  "/icon-512.png",
];

// API routes that should use network-first strategy
const NETWORK_FIRST_ROUTES = [
  "/api/v1/auth/",
  "/api/v1/realtime/",
  "/api/v1/brain/",
  "/api/v1/intelligence/",
];

// Routes that should use stale-while-revalidate
const STALE_WHILE_REVALIDATE_ROUTES = [
  "/api/v1/company-experience/",
  "/api/v1/dashboard/",
  "/api/v1/meetings/",
  "/api/v1/projects/",
  "/api/v1/tasks/",
  "/api/v1/goals/",
  "/api/v1/people/",
];

// Static assets that can be cached aggressively
const CACHE_FIRST_ROUTES = [
  "/_next/static/",
  "/icons/",
  "/images/",
  "/fonts/",
  "/*.png",
  "/*.jpg",
  "/*.jpeg",
  "/*.svg",
  "/*.webp",
  "/*.woff",
  "/*.woff2",
];

// Install Event - Cache App Shell
self.addEventListener("install", (event) => {
  console.log("[SW] Installing Service Worker v" + CACHE_VERSION);

  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => {
        console.log("[SW] Caching App Shell");
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log("[SW] App Shell cached successfully");
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error("[SW] Failed to cache App Shell:", error);
      }),
  );

  // Force activation
  self.skipWaiting();
});

// Activate Event - Clean up old caches
self.addEventListener("activate", (event) => {
  console.log("[SW] Activating Service Worker v" + CACHE_VERSION);

  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              return (
                name.startsWith("vcos-") &&
                name !== STATIC_CACHE &&
                name !== RUNTIME_CACHE &&
                name !== OFFLINE_CACHE
              );
            })
            .map((name) => {
              console.log("[SW] Deleting old cache:", name);
              return caches.delete(name);
            }),
        );
      })
      .then(() => {
        console.log("[SW] Service Worker activated");
        return self.clients.claim();
      }),
  );
});

// Fetch Event - Handle all network requests
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== "GET") {
    return;
  }

  // Skip chrome-extension and other non-http(s) requests
  if (!url.protocol.startsWith("http")) {
    return;
  }

  // Handle different caching strategies based on route
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirstStrategy(request));
  } else if (isNetworkFirstRoute(url)) {
    event.respondWith(networkFirstStrategy(request));
  } else if (isStaleWhileRevalidateRoute(url)) {
    event.respondWith(staleWhileRevalidateStrategy(request));
  } else {
    // Default: network-first for navigation, cache-first for others
    if (request.mode === "navigate") {
      event.respondWith(networkFirstStrategy(request));
    } else {
      event.respondWith(staleWhileRevalidateStrategy(request));
    }
  }
});

// Message Event - Handle messages from main thread
self.addEventListener("message", (event) => {
  const { type, payload } = event.data;

  switch (type) {
    case "SET_AUTH_TOKEN":
      handleSetAuthToken(payload.token);
      break;
    case "SYNC_OFFLINE_OPERATIONS":
      handleBackgroundSync();
      break;
    case "SKIP_WAITING":
      self.skipWaiting();
      break;
    case "CLEAR_CACHE":
      handleClearCache();
      break;
    case "GET_CACHE_STATUS":
      handleGetCacheStatus(event);
      break;
    default:
      console.log("[SW] Unknown message type:", type);
  }
});

// Background Sync Event
self.addEventListener("sync", (event) => {
  console.log("[SW] Background sync triggered:", event.tag);

  if (event.tag === "offline-operations") {
    event.waitUntil(handleBackgroundSync());
  }
});

// Push Notification Event
self.addEventListener("push", (event) => {
  console.log("[SW] Push notification received");

  if (!event.data) {
    console.log("[SW] Push notification has no data");
    return;
  }

  const data = event.data.json();
  const options = {
    body: data.body || "You have a new notification",
    icon: data.icon || "/icon-192.png",
    badge: data.badge || "/icon-72.png",
    vibrate: data.vibrate || [200, 100, 200],
    data: data.data || {},
    actions: data.actions || [
      { action: "open", title: "Open" },
      { action: "dismiss", title: "Dismiss" },
    ],
    requireInteraction: data.requireInteraction || false,
    silent: data.silent || false,
    tag: data.tag || "vcos-notification",
    renotify: data.renotify || false,
    timestamp: data.timestamp || Date.now(),
  };

  event.waitUntil(
    self.registration.showNotification(data.title || "VCOS", options),
  );
});

// Notification Click Event
self.addEventListener("notificationclick", (event) => {
  console.log("[SW] Notification clicked:", event.action);

  event.notification.close();

  if (event.action === "dismiss") {
    return;
  }

  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        // Check if there's already a window open
        for (const client of clientList) {
          if (client.url.includes(targetUrl) && "focus" in client) {
            return client.focus();
          }
        }
        // Open new window
        return clients.openWindow(targetUrl);
      }),
  );
});

// Notification Close Event
self.addEventListener("notificationclose", (event) => {
  console.log("[SW] Notification closed:", event.notification.tag);

  // Track analytics if needed
  if (event.notification.data?.analytics) {
    // Send analytics event
  }
});

// ==================== Caching Strategies ====================

// Cache First - For static assets
async function cacheFirstStrategy(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cachedResponse = await cache.match(request);

  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.error("[SW] Cache-first fetch failed:", error);
    return new Response("Offline", {
      status: 503,
      statusText: "Service Unavailable",
    });
  }
}

// Network First - For dynamic content (auth, realtime)
async function networkFirstStrategy(request) {
  const cache = await caches.open(RUNTIME_CACHE);

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.log("[SW] Network failed, trying cache:", error);
    const cachedResponse = await cache.match(request);

    if (cachedResponse) {
      return cachedResponse;
    }

    // For navigation requests, return offline page
    if (request.mode === "navigate") {
      return caches.match("/offline.html");
    }

    return new Response("Offline", {
      status: 503,
      statusText: "Service Unavailable",
    });
  }
}

// Stale While Revalidate - For API responses
async function staleWhileRevalidateStrategy(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cachedResponse = await cache.match(request);

  // Fetch fresh data in background
  const fetchPromise = fetch(request)
    .then((networkResponse) => {
      if (networkResponse.ok) {
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    })
    .catch((error) => {
      console.log("[SW] Background fetch failed:", error);
    });

  // Return cached response immediately if available
  if (cachedResponse) {
    // Trigger background update
    fetchPromise;
    return cachedResponse;
  }

  // No cache, wait for network
  try {
    const networkResponse = await fetchPromise;
    return networkResponse;
  } catch (error) {
    console.error("[SW] Stale-while-revalidate failed:", error);

    if (request.mode === "navigate") {
      return caches.match("/offline.html");
    }

    return new Response("Offline", {
      status: 503,
      statusText: "Service Unavailable",
    });
  }
}

// ==================== Route Matchers ====================

function isStaticAsset(url) {
  return CACHE_FIRST_ROUTES.some((route) => {
    if (route.endsWith("/")) {
      return url.pathname.startsWith(route);
    }
    if (route.startsWith("*.")) {
      const ext = route.slice(1);
      return url.pathname.endsWith(ext);
    }
    return url.pathname === route || url.pathname.startsWith(route);
  });
}

function isNetworkFirstRoute(url) {
  return NETWORK_FIRST_ROUTES.some((route) => url.pathname.startsWith(route));
}

function isStaleWhileRevalidateRoute(url) {
  return STALE_WHILE_REVALIDATE_ROUTES.some((route) =>
    url.pathname.startsWith(route),
  );
}

// ==================== Message Handlers ====================

function handleSetAuthToken(token) {
  console.log("[SW] Auth token received");
  // Store token for authenticated requests
  // In practice, you'd use this for authenticated fetch requests
  self.authToken = token;
}

async function handleBackgroundSync() {
  console.log("[SW] Processing background sync for offline-operations");

  try {
    // Get all clients and tell them to sync
    const clients = await self.clients.matchAll({ type: "window" });

    clients.forEach((client) => {
      client.postMessage({
        type: "BACKGROUND_SYNC",
        timestamp: Date.now(),
      });
    });

    // Also try to process any pending IndexedDB operations
    // This would be done by the main thread, but we can notify
    console.log("[SW] Background sync completed");
  } catch (error) {
    console.error("[SW] Background sync failed:", error);
  }
}

async function handleClearCache() {
  console.log("[SW] Clearing all caches");
  const cacheNames = await caches.keys();
  await Promise.all(cacheNames.map((name) => caches.delete(name)));
  console.log("[SW] All caches cleared");
}

async function handleGetCacheStatus(event) {
  const cacheNames = await caches.keys();
  const status = {};

  for (const name of cacheNames) {
    const cache = await caches.open(name);
    const keys = await cache.keys();
    status[name] = {
      entries: keys.length,
    };
  }

  event.ports[0].postMessage({ type: "CACHE_STATUS", payload: status });
}

// ==================== Helper Functions ====================

async function getOfflinePage() {
  const cache = await caches.open(OFFLINE_CACHE);
  return cache.match("/offline.html");
}

// Handle requests when offline
async function handleOfflineRequest(request) {
  const cachedResponse = await caches.match(request);

  if (cachedResponse) {
    return cachedResponse;
  }

  // For navigation, return offline page
  if (request.mode === "navigate") {
    return getOfflinePage();
  }

  return new Response("Offline", {
    status: 503,
    statusText: "Service Unavailable",
    headers: { "Content-Type": "text/plain" },
  });
}

// ==================== Periodic Cleanup ====================

// Periodically clean old cache entries
setInterval(
  async () => {
    const cache = await caches.open(RUNTIME_CACHE);
    const requests = await cache.keys();
    const now = Date.now();
    const MAX_AGE = 7 * 24 * 60 * 60 * 1000; // 7 days

    for (const request of requests) {
      const response = await cache.match(request);
      const dateHeader = response.headers.get("date");

      if (dateHeader) {
        const responseDate = new Date(dateHeader).getTime();
        if (now - responseDate > MAX_AGE) {
          await cache.delete(request);
        }
      }
    }
  },
  24 * 60 * 60 * 1000,
); // Run daily

console.log("[SW] Service Worker loaded v" + CACHE_VERSION);
