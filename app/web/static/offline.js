// The Upcoming page offline (#963): register the service worker and ask it to save a copy of this page.
// The line "Offline: saved at HH:MM" (#965) shows while navigator.onLine is false, in the local time of the browser.
(() => {
  const note = document.querySelector(".offline-note");
  const two = (n) => String(n).padStart(2, "0");
  const show = () => {
    if (!note) return;
    const d = new Date(note.dataset.savedAt);
    if (Number.isNaN(d.getTime())) return;
    note.textContent = `Offline: saved at ${two(d.getHours())}:${two(d.getMinutes())}`;
    note.hidden = false;
  };
  const hide = () => { if (note) note.hidden = true; };
  if (note) {
    window.addEventListener("offline", show);
    window.addEventListener("online", hide);
    if (navigator.onLine === false) show();
  }
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready)
    .then((reg) => { if (reg.active) reg.active.postMessage("save-upcoming"); }).catch(() => {});
})();
