// The service worker of the price-drop messages by Web Push (#514). The server sends JSON: title, body, url.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(self.registration.showNotification(data.title || "travel-aggregator", {
    body: data.body || "",
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data && event.notification.data.url || "/", self.location.origin);
  // only a page of this app: the URL comes from the server, but a wrong origin must not open
  const target = url.origin === self.location.origin ? url.href : self.location.origin + "/";
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const client of list) {
      if (client.url === target && "focus" in client) return client.focus();
    }
    return self.clients.openWindow(target);
  }));
});

// The Upcoming page offline (#963): network first for the navigations to /upcoming; the last good copy and the
// static files of its layout stay in one cache. All other requests go to the network unchanged.
const CACHE = "upcoming-v1";
const PAGE = "/upcoming";
const STATIC = ["/static/app.css", "/static/icons.svg", "/static/offline.js", "/static/fonts/inter-regular.woff2",
  "/static/fonts/inter-medium.woff2", "/static/fonts/inter-semibold.woff2", "/static/fonts/inter-bold.woff2"];
const OFFLINE = "<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width\">" +
  "<link rel=stylesheet href=/static/app.css><title>Offline – travel-aggregator</title>" +
  "<main><h1>Upcoming</h1><p class=muted>No saved journeys: open Upcoming once with a network.</p></main>";

// only a 200 that is not a redirect (for example to /login) goes into the cache; a page with "no-store" (the one
// view of the calendar link, #1407) never does
const keep = (response) => response.status === 200 && !response.redirected && response.type === "basic" &&
  !(response.headers.get("Cache-Control") || "").includes("no-store");

const savePage = (response) => caches.open(CACHE).then((cache) => cache.put(PAGE, response));

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(STATIC)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// offline.js asks for a copy after the first online visit (that visit had no service worker yet)
self.addEventListener("message", (event) => {
  if (event.data !== "save-upcoming") return;
  event.waitUntil(fetch(PAGE, { credentials: "same-origin" })
    .then((response) => (keep(response) ? savePage(response) : null)).catch(() => {}));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== "GET") return;
  if (event.request.mode === "navigate" && url.pathname === PAGE) {
    event.respondWith(fetch(event.request).then((response) => {
      if (keep(response)) event.waitUntil(savePage(response.clone()));
      return response;
    }).catch(() => caches.match(PAGE).then((hit) => hit ||
      new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8" } }))));
  } else if (STATIC.includes(url.pathname)) {
    // the network first, so that a new app.css shows at once; the cache only when the network fails
    event.respondWith(fetch(event.request).catch(() => caches.match(url.pathname).then((hit) => hit || Response.error())));
  }
});
