// The buttons of Web Push on the settings page (#514): subscribe this browser with the VAPID public key, or remove it.
(() => {
  const box = document.getElementById("push");
  if (!box) return;
  const status = document.getElementById("push-status");
  const on = document.getElementById("push-on");
  const off = document.getElementById("push-off");
  const key = box.dataset.key;
  const csrf = box.dataset.csrf;
  const say = (text) => { status.textContent = text; };

  if (!key) { on.disabled = off.disabled = true; return; }
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    on.disabled = off.disabled = true;
    // iOS Safari in a browser tab sets navigator.standalone to false: Web Push works only from the Home Screen app (#798)
    say(navigator.standalone === false
      ? "On an iPhone or iPad, Web Push works only in the app on the Home Screen: tap Share, then \"Add to Home Screen\", and open the app from there."
      : "This browser has no Web Push.");
    return;
  }

  const bytes = (b64) => {
    const raw = atob((b64 + "=".repeat((4 - b64.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  };
  const send = (url, sub) => fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(sub.toJSON()),
  }).then((r) => { if (!r.ok) throw new Error("the server answered " + r.status); return r.json(); });

  const ready = () => navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready);

  ready().then((reg) => reg.pushManager.getSubscription()).then((sub) => {
    if (sub) say("Push is on on this device.");
  }).catch(() => {});

  on.addEventListener("click", () => {
    say("Wait…");
    Notification.requestPermission().then((permission) => {
      if (permission !== "granted") throw new Error("the browser does not allow notifications");
      return ready();
    }).then((reg) => reg.pushManager.getSubscription().then((sub) => sub ||
      reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) })))
      .then((sub) => send("/settings/push", sub))
      .then(() => say("Push is on on this device."))
      .catch((e) => say("Push is not on: " + e.message));
  });

  off.addEventListener("click", () => {
    ready().then((reg) => reg.pushManager.getSubscription()).then((sub) => {
      if (!sub) return null;
      return send("/settings/push/delete", sub).then(() => sub.unsubscribe());
    }).then(() => say("Push is off on this device."))
      .catch((e) => say("Push is not off: " + e.message));
  });
})();
