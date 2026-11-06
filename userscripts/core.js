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
  };

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
  root.TACore = {
    gm,
    panel,
    report(count) { panel.setStatus(`Captured ${count} offers`, "info"); },
    sent(count) { panel.setStatus(`Captured ${count} offers → sent ✓`, "ok"); },
  };
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
