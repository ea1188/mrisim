/* MRISim service worker — offline support + CDN resilience, designed to be safe.
 *
 * Strategy (deliberately conservative, because a service worker persists in the
 * visitor's browser across visits):
 *
 *   • App shell (HTML / app.js / styles.css / worker.js, and navigations):
 *     NETWORK-FIRST. Online visitors ALWAYS get the latest code; the cache is only
 *     a fallback when the network is unavailable. This is what removes the usual
 *     "a bad service worker bricks returning users" risk — we never serve stale
 *     shell code to someone who is online.
 *
 *   • Immutable, versioned assets — the Pyodide runtime + wheels on the CDN, and
 *     the build-id-busted engine/anatomy (mrisim_src.zip?v=…, data/*.npy?v=…):
 *     CACHE-FIRST. Their URLs change when their content changes (pinned Pyodide
 *     version, content wheel names, BUILD_ID query), so caching can't go stale.
 *     This gives offline-after-first-load and survives CDN hiccups.
 *
 *   • Everything else: passthrough to the network.
 *
 * Kill-switch: if this SW ever misbehaves, deploy a replacement sw.js whose
 * install/activate calls caches.keys()→delete and self.registration.unregister().
 * Because the shell is network-first and the browser re-checks sw.js on every
 * navigation, online visitors pick up that replacement on their next visit.
 */
"use strict";

const CACHE = "mrisim-v36";                 // bump when this file's caching logic changes
const SHELL = [
  "./", "index.html", "simulator.html", "app.js", "styles.css", "theme.css", "worker.js", "logo.png", "lessons.json",
  "data/brain_slice.bin",
  "protocol.html", "protocol.js", "quiz.html", "quiz.js", "quiz.json", "tour.js",
  // Optional accounts layer + paid course (config.js may be absent — allSettled tolerates it).
  "config.js", "accounts.js", "account.html", "account.js", "course.html", "course.js",
  "course_diagrams_math.js", "course_diagrams.js",
  "reference.html", "reference.js",
];

self.addEventListener("install", (event) => {
  // Precache the shell so the very first offline reload works; never fail install
  // if a file is momentarily unavailable.
  event.waitUntil(
    caches.open(CACHE)
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Is this a big, immutable, versioned asset we can safely cache forever?
function isImmutable(url) {
  if (url.hostname === "cdn.jsdelivr.net") return true;          // Pyodide runtime + wheels
  if (url.pathname.endsWith(".npy")) return true;                // anatomy (build-id busted)
  if (url.pathname.endsWith("mrisim_src.zip")) return true;      // engine (build-id busted)
  if (url.pathname.endsWith(".whl") || url.pathname.endsWith(".wasm")) return true;
  return false;
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const resp = await fetch(request);
  if (resp && (resp.ok || resp.type === "opaque")) {
    const cache = await caches.open(CACHE);
    cache.put(request, resp.clone());
  }
  return resp;
}

async function networkFirst(request) {
  try {
    const resp = await fetch(request);
    if (resp && resp.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;     // never touch non-GET
  const url = new URL(request.url);

  if (isImmutable(url)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  // App shell + navigations: network-first (cache only as an offline fallback).
  if (request.mode === "navigate" || url.origin === self.location.origin) {
    event.respondWith(networkFirst(request));
  }
  // Anything else: default network handling (no respondWith).
});
