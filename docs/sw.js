// Minimal service worker - just enough for Chrome/Android to consider this
// installable. No offline caching: this page always wants fresh data
// (venue list, live alert rules), so there's nothing worth caching here.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
