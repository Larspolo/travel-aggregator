// The Upcoming page offline (#963): register the service worker and ask it to save a copy of this page.
(() => {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready)
    .then((reg) => { if (reg.active) reg.active.postMessage("save-upcoming"); }).catch(() => {});
})();
