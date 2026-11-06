// travel-aggregator userscript core: a floating status panel in a Shadow DOM.
// It reads and writes no page data (P1, P5). It uses GM_* functions only through TACore.gm.
(function (root) {
  "use strict";
  if (root.TACore) return;

  const gm = {
    getValue: (key, fallback) =>
      typeof GM_getValue === "function" ? GM_getValue(key, fallback) : fallback,
    setValue: (key, value) => {
      if (typeof GM_setValue === "function") GM_setValue(key, value);
    },
    request: (details) =>
      typeof GM_xmlhttpRequest === "function" ? GM_xmlhttpRequest(details) : undefined,
    menu: (name, fn) => {
      if (typeof GM_registerMenuCommand === "function") GM_registerMenuCommand(name, fn);
    },
  };
  const RETRY_MS = 60000;

  const STYLE = `
    :host { all: initial; }
    .panel { position: fixed; right: 12px; bottom: 12px; z-index: 2147483647;
      font: 13px/1.4 system-ui, sans-serif; padding: 6px 10px; border-radius: 6px;
      background: #f4f4f4; color: #222; border: 1px solid #999; box-shadow: 0 2px 6px rgba(0,0,0,.3); }
    .panel.ok { background: #e7f6e7; border-color: #2e7d32; color: #1b5e20; }
    .panel.error { background: #fdecea; border-color: #c62828; color: #b71c1c; font-weight: bold; }
    .panel.info { background: #e8f0fe; border-color: #1a73e8; color: #0d47a1; }
  `;

  function createPanel() {
    const host = document.createElement("div");
    host.id = "ta-core-panel";
    const shadow = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    const box = document.createElement("div");
    box.className = "panel info";
    box.setAttribute("role", "status");
    box.textContent = "travel-aggregator ready";
    shadow.append(style, box);
    (document.body || document.documentElement).appendChild(host);
    return {
      host,
      setStatus(text, kind) {
        box.className = "panel " + (["ok", "error", "info"].includes(kind) ? kind : "info");
        box.textContent = String(text);
      },
      text: () => box.textContent,
      kind: () => box.className.replace("panel ", ""),
    };
  }

  const panel = createPanel();
  const config = () => ({
    server: String(gm.getValue("server", "") || "").replace(/\/+$/, ""),
    token: String(gm.getValue("token", "") || ""),
  });
  const loadQueue = () => {
    const q = gm.getValue("queue", []);
    return Array.isArray(q) ? q : [];
  };
  const count = (payload) => (payload && Array.isArray(payload.offers) ? payload.offers.length : 0);
  let busy = false;

  // POST one payload to the configured server only (P1). Resolves "ok", "retry" or "drop".
  function post(payload) {
    const { server, token } = config();
    if (!/^https?:\/\//.test(server)) {
      panel.setStatus("Set the server URL in the menu", "error");
      return Promise.resolve("retry");
    }
    return new Promise((resolve) => {
      const fail = () => { panel.setStatus("Send failed: kept in the queue", "error"); resolve("retry"); };
      gm.request({
        method: "POST",
        url: server + "/api/ingest",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        data: JSON.stringify(payload),
        onload: (r) => {
          if (r.status >= 200 && r.status < 300) { core.sent(count(payload)); resolve("ok"); }
          else if (r.status === 401) { panel.setStatus("Check the API token", "error"); resolve("retry"); }
          else if (r.status >= 500) fail();
          else { panel.setStatus(`Send rejected (${r.status}): payload dropped`, "error"); resolve("drop"); }
        },
        onerror: fail,
        ontimeout: fail,
      });
    });
  }

  // Send the queue oldest first; stop at the first failure so the order stays.
  async function flush() {
    if (busy) return;
    busy = true;
    try {
      let q = loadQueue();
      while (q.length) {
        const result = await post(q[0]);
        if (result === "retry") break;
        q = loadQueue().slice(1);
        gm.setValue("queue", q);
      }
    } finally {
      busy = false;
    }
  }

  const core = {
    gm,
    panel,
    report(n) { panel.setStatus(`Captured ${n} offers`, "info"); },
    sent(n) { panel.setStatus(`Captured ${n} offers → sent ✓`, "ok"); },
    queue: loadQueue,
    flush,
    send(payload) {
      gm.setValue("queue", loadQueue().concat([payload]));
      return flush();
    },
  };
  root.TACore = core;
  gm.menu("Set server URL", () => {
    const v = root.prompt("travel-aggregator server URL", config().server);
    if (v !== null) gm.setValue("server", v.trim());
  });
  gm.menu("Set API token", () => {
    const v = root.prompt("travel-aggregator API token", "");
    if (v !== null) gm.setValue("token", v.trim());
  });
  flush();
  setInterval(flush, RETRY_MS);
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
