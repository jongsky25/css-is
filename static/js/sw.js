/* CSS-IS service worker — Phase 1 (installable PWA + offline app-shell load).
 *
 * Scope: served from "/sw.js" (root) so it controls the whole origin. It does
 * NOT touch submissions — POSTs pass straight through to the network. Offline
 * *capture* (an IndexedDB submit queue) is Phase 2.
 *
 * Bump CACHE_VERSION on every deploy: the `activate` handler deletes any cache
 * whose name differs, so an old app-shell is purged the moment the new SW takes
 * over. Keep this in lockstep with version.py / the ?v= asset tokens.
 */
const CACHE_VERSION = "v1.54-a";
const CACHE_NAME = "css-is-" + CACHE_VERSION;

/* Public app shell. Bare paths (no ?v=) — the versioned asset requests the page
 * actually makes are picked up at runtime by stale-while-revalidate below. */
const PRECACHE = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/search.js",
  "/static/offline.html",
  "/static/img/icons/icon-192.png",
  "/static/img/icons/icon-512.png",
];

/* Only runtime-cache navigations for the public survey surfaces — never the
 * authenticated admin pages (which must always come from the network). */
const PUBLIC_NAV = ["/r/", "/seq", "/e/"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      // addAll is atomic; a single 404 would abort install, so swallow per-item.
      .then((cache) => Promise.all(
        PRECACHE.map((u) => cache.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith("css-is-") && k !== CACHE_NAME)
            .map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function isStaticAsset(url) {
  return url.origin === self.location.origin && url.pathname.startsWith("/static/");
}

function isPublicNav(url) {
  return PUBLIC_NAV.some((p) => url.pathname === p || url.pathname.startsWith(p));
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Phase 1 never intercepts writes — submit goes straight to the server.
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // cross-origin: leave alone

  // Static assets: stale-while-revalidate — instant from cache, refresh behind.
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(req).then((hit) => {
          const network = fetch(req).then((res) => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          }).catch(() => hit);
          return hit || network;
        }))
    );
    return;
  }

  // Navigations: network-first, fall back to a cached page, then the offline
  // shell. Only public survey pages are stored, to bound the cache.
  // NOTE: the Cache API rejects put()/match() on a request whose mode is
  // "navigate", so we key by the URL string (req.url) on both store and lookup.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).then((res) => {
        if (res && res.ok && isPublicNav(url)) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req.url, copy));
        }
        return res;
      }).catch(() =>
        caches.match(req.url).then((hit) => hit || caches.match("/static/offline.html")))
    );
  }
});

/* ── Background Sync (PWA Phase 2) ──────────────────────────────────────────────
 * Flush the offline submission queue even with no tab open (Android/Chrome; iOS
 * has no Background Sync, so the page-side flush in app.js is the universal path).
 * Reads the SAME IndexedDB store app.js writes; server dedup (submission_log,
 * keyed by submission_id baked into each body) makes a double-send harmless. */
const Q_DB = "css_offline", Q_STORE = "queue";

function qOpen() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(Q_DB, 1);
    r.onupgradeneeded = () => {
      const db = r.result;
      if (!db.objectStoreNames.contains(Q_STORE)) db.createObjectStore(Q_STORE, { keyPath: "id" });
    };
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
function qReq(req) { return new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); }); }
function qStore(mode) { return qOpen().then((db) => db.transaction(Q_STORE, mode).objectStore(Q_STORE)); }

async function flushQueue() {
  const all = await qStore("readonly").then((s) => qReq(s.getAll())).catch(() => []);
  for (const it of all) {
    if (it.status === "failed") continue;
    let res;
    try {
      res = await fetch(it.action, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: it.body,
      });
    } catch (_) {
      return;                                    // still offline — stop, sync will fire again
    }
    if (res.ok) {
      await qStore("readwrite").then((s) => s.delete(it.id));
    } else if (res.status >= 400 && res.status < 500) {
      it.status = "failed";                      // permanent (window closed / bad token)
      await qStore("readwrite").then((s) => s.put(it));
    } else {
      return;                                    // 5xx — stop, retry on the next sync
    }
  }
}

self.addEventListener("sync", (event) => {
  if (event.tag === "css-flush") event.waitUntil(flushQueue());
});
