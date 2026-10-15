{% autoescape off %}// Masroofi service worker, rendered by expenses.views.pwa_views.service_worker.
//
// It caches static files (CSS, JavaScript, icons) and the offline page, nothing else.
// Pages, the API, the admin, account pages and receipt images always go to the
// network and are never stored, because they contain the user's data.

const CACHE = "masroofi-static-{{ version }}";
const OFFLINE_URL = {{ offline_url }};
const PRECACHE = {{ precache }};
const STATIC_PREFIX = {{ static_prefix }};
const NEVER_CACHE = {{ never_cache }};

function isCacheable(url) {
    return url.origin === self.location.origin
        && url.pathname.startsWith(STATIC_PREFIX)
        && !NEVER_CACHE.some((prefix) => url.pathname.startsWith(prefix));
}

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    // Remove the caches of older versions of this worker.
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key.startsWith("masroofi-") && key !== CACHE).map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") return;
    const url = new URL(request.url);

    if (request.mode === "navigate") {
        // Pages: always from the network and never stored. Offline, show the offline page.
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
        return;
    }

    if (!isCacheable(url)) return; // the browser handles it as if there were no service worker

    // Static files: network first so a new version is used at once, the cached copy when offline.
    event.respondWith(
        fetch(request)
            .then((response) => {
                const type = response.headers.get("Content-Type") || "";
                if (response.ok && response.type === "basic" && !type.includes("text/html")) {
                    const copy = response.clone();
                    caches.open(CACHE).then((cache) => cache.put(request, copy));
                }
                return response;
            })
            .catch(() => caches.match(request))
    );
});
{% endautoescape %}
