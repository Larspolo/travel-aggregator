// travel-aggregator userscript core: a floating status panel in a Shadow DOM.
// It reads and writes no page data (P1, P5). It uses GM_* functions only through TACore.gm.
// Make CORE_VERSION higher with each change of this file (the server adds it to the @version of each script).
const CORE_VERSION = 6;
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
    info: () => (typeof GM_info === "object" && GM_info ? GM_info : {}),
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
    .controls { position: fixed; right: 12px; bottom: 48px; z-index: 2147483647; display: flex; gap: 6px;
      align-items: center; font: 13px/1.4 system-ui, sans-serif; padding: 6px 10px; border-radius: 6px;
      background: #f4f4f4; color: #222; border: 1px solid #999; }
    .controls select, .controls button { font: inherit; }
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
    const controls = document.createElement("div");
    controls.className = "controls";
    controls.innerHTML = `<label>Attach to trip: <select class="trip"></select></label>
      <button type="button" class="new-trip">+ new trip</button>
      <label><input type="checkbox" class="autosend"> auto-send</label>
      <button type="button" class="send">Send</button>
      <button type="button" class="set-server">Server URL</button>
      <button type="button" class="set-token">API token</button>`;
    shadow.append(style, controls, box);
    // At document-start the page can have no root element yet (#155): mount when it comes.
    const mount = () => (document.body || document.documentElement).appendChild(host);
    if (document.documentElement) mount();
    else {
      const watch = new MutationObserver(() => {
        if (document.documentElement) { watch.disconnect(); mount(); }
      });
      watch.observe(document, { childList: true });
    }
    return {
      host,
      select: controls.querySelector(".trip"),
      newTrip: controls.querySelector(".new-trip"),
      autosend: controls.querySelector(".autosend"),
      sendButton: controls.querySelector(".send"),
      serverButton: controls.querySelector(".set-server"),
      tokenButton: controls.querySelector(".set-token"),
      setStatus(text, kind) {
        box.className = "panel " + (["ok", "error", "info"].includes(kind) ? kind : "info");
        box.textContent = String(text);
      },
      text: () => box.textContent,
      kind: () => box.className.replace("panel ", ""),
    };
  }

  const panel = createPanel();
  // With no server set, the server that installed the script (#392): the origin of its @downloadURL, when it is https
  // and not GitHub. A server that the owner sets keeps priority.
  const defaultServer = () => {
    try {
      const u = new URL(String(gm.info().script?.downloadURL || ""));
      return u.protocol === "https:" && u.hostname !== "raw.githubusercontent.com" ? u.origin : "";
    } catch (e) {
      return "";
    }
  };
  const config = () => ({
    server: String(gm.getValue("server", "") || defaultServer()).replace(/\/+$/, ""),
    token: String(gm.getValue("token", "") || ""),
  });
  const loadQueue = () => {
    const q = gm.getValue("queue", []);
    return Array.isArray(q) ? q : [];
  };
  const tripId = () => {
    const id = Number(gm.getValue("trip", 0));
    return Number.isInteger(id) && id > 0 ? id : null;
  };
  const autoSend = () => gm.getValue("autosend", true) !== false;
  // The offers of a payload; a raw capture asks the counter of its site userscript (core.countRaw).
  const count = (payload) => {
    if (!payload) return 0;
    if (Array.isArray(payload.offers) && payload.offers.length) return payload.offers.length;
    if (payload.raw !== undefined && typeof core.countRaw === "function") {
      try { return Number(core.countRaw(payload.raw)) || 0; } catch (e) { return 0; }
    }
    return 0;
  };
  let busy = false;

  // POST one payload to the configured server only (P1). Resolves "ok", "retry" or "drop".
  function post(payload) {
    const { server, token } = config();
    if (!/^https?:\/\//.test(server)) {
      panel.setStatus('Set the server URL: press "Server URL"', "error");
      return Promise.resolve("retry");
    }
    if (!payload || !payload.trip_id) {
      panel.setStatus("Choose a trip in the panel", "error");
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
          else if (r.status === 429) { panel.setStatus("Server busy: kept in the queue", "error"); resolve("retry"); }
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

  // GET or POST /api/trips on the configured server only (P1). Resolves the parsed JSON or null.
  function trips(method, body) {
    const { server, token } = config();
    if (!/^https?:\/\//.test(server)) return Promise.resolve(null);
    return new Promise((resolve) => {
      gm.request({
        method,
        url: server + "/api/trips" + (method === "GET" ? "?status=planning" : ""),
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        data: body === undefined ? undefined : JSON.stringify(body),
        onload: (r) => {
          if (r.status < 200 || r.status >= 300) {
            panel.setStatus(`Trips request failed (${r.status})`, "error");
            return resolve(null);
          }
          try { resolve(JSON.parse(r.responseText)); } catch (e) { resolve(null); }
        },
        onerror: () => { panel.setStatus("Trips request failed", "error"); resolve(null); },
        ontimeout: () => { panel.setStatus("Trips request failed", "error"); resolve(null); },
      });
    });
  }

  function addOption(trip) {
    const opt = document.createElement("option");
    opt.value = String(trip.id);
    opt.textContent = String(trip.title);
    panel.select.appendChild(opt);
  }

  async function loadTrips() {
    const list = await trips("GET");
    if (!Array.isArray(list)) return;
    panel.select.replaceChildren();
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "(choose)";
    panel.select.appendChild(empty);
    list.forEach(addOption);
    const id = tripId();
    panel.select.value = id && list.some((t) => t.id === id) ? String(id) : "";
  }

  async function newTrip() {
    const title = root.prompt("Title of the new trip", "");
    if (title === null || !title.trim()) return;
    const trip = await trips("POST", { title: title.trim() });
    if (!trip || !trip.id) return;
    addOption(trip);
    panel.select.value = String(trip.id);
    gm.setValue("trip", trip.id);
  }

  panel.select.addEventListener("change", () => gm.setValue("trip", Number(panel.select.value) || 0));
  panel.newTrip.addEventListener("click", newTrip);
  panel.autosend.checked = autoSend();
  panel.autosend.addEventListener("change", () => {
    gm.setValue("autosend", panel.autosend.checked);
    if (panel.autosend.checked) flush();
  });
  panel.sendButton.addEventListener("click", () => flush());

  const parseJson = (text) => {
    if (typeof text !== "string" || !text) return null;
    try { return JSON.parse(text); } catch (e) { return null; }
  };

  // One hook of fetch and XMLHttpRequest for all site userscripts. It only reads the responses that the page itself
  // gets (P1). Each watcher gets {url, method, body, text} of a response whose URL it accepts.
  const watchers = [];
  let hooked = false;
  const notify = (url, method, body, text) => {
    const r = { url: String(url), method: String(method || "GET").toUpperCase(),
      body: typeof body === "string" ? body : null, text };
    watchers.forEach((w) => {
      try { if (w.accepts(url)) w.onResponse(r); } catch (e) { /* a site error does not stop the others */ }
    });
  };
  const accepted = (url) => watchers.some((w) => { try { return w.accepts(url); } catch (e) { return false; } });
  function hook() {
    if (hooked) return;
    hooked = true;
    const origFetch = root.fetch;
    if (typeof origFetch === "function") {
      root.fetch = function (input, init) {
        const promise = origFetch.apply(this, arguments);
        const url = input && typeof input === "object" && "url" in input ? input.url : input;
        if (!accepted(url)) return promise;
        const method = (init && init.method) || (input && input.method) || "GET";
        const body = init && typeof init.body === "string" ? init.body : null;
        return promise.then((res) => {
          try { res.clone().text().then((t) => notify(url, method, body, t), () => {}); } catch (e) { /* ignore */ }
          return res;
        });
      };
    }
    const XHR = root.XMLHttpRequest && root.XMLHttpRequest.prototype;
    if (XHR) {
      const open = XHR.open;
      const send = XHR.send;
      XHR.open = function (method, url) {
        this.__taMethod = method;
        this.__taUrl = url;
        return open.apply(this, arguments);
      };
      XHR.send = function (body) {
        if (accepted(this.__taUrl)) {
          this.addEventListener("load", () => {
            const t = this.responseType;
            const text = !t || t === "text" ? this.responseText : t === "json" ? JSON.stringify(this.response) : null;
            notify(this.__taUrl, this.__taMethod, body, text);
          });
        }
        return send.apply(this, arguments);
      };
    }
  }

  const core = {
    gm,
    countRaw: null,
    parseJson,
    // A URL test of a site: true when the URL (relative to the page) passes test(u) for its URL object u.
    urlTest: (test) => (url) => {
      try { return Boolean(test(new URL(String(url), root.location.href))); } catch (e) { return false; }
    },
    // Watch the responses whose URL passes accepts(url); onResponse gets {url, method, body, text}.
    watch(accepts, onResponse) {
      watchers.push({ accepts, onResponse });
      hook();
    },
    // Report and send one raw capture of a site (the server parser of the source reads raw).
    capture(source, parserVersion, raw, countRaw) {
      core.countRaw = countRaw;
      core.report(countRaw(raw));
      return core.send({ source, parser_version: parserVersion, captured_at: new Date().toISOString(),
        page_url: root.location.href, raw });
    },
    server: () => config().server,
    panel,
    report(n) { panel.setStatus(`Captured ${n} offers`, "info"); },
    sent(n) { panel.setStatus(`Captured ${n} offers → sent ✓`, "ok"); },
    queue: loadQueue,
    flush,
    loadTrips,
    newTrip,
    tripId,
    // Queue one payload for the chosen trip; send it now only when auto-send is on.
    send(payload) {
      const id = tripId();
      const item = id ? Object.assign({}, payload, { trip_id: id }) : payload;
      gm.setValue("queue", loadQueue().concat([item]));
      if (!autoSend()) {
        panel.setStatus(`Captured ${count(item)} offers: ${loadQueue().length} waiting, press Send`, "info");
        return Promise.resolve();
      }
      return flush();
    },
  };
  root.TACore = core;
  // The panel has the settings too (#536): the Tampermonkey menu is hidden in the extension popup.
  const setServer = () => {
    const v = root.prompt("travel-aggregator server URL", config().server);
    if (v !== null) { gm.setValue("server", v.trim()); loadTrips(); }
  };
  const setToken = () => {
    const v = root.prompt("travel-aggregator API token", "");
    if (v !== null) { gm.setValue("token", v.trim()); loadTrips(); }
  };
  panel.serverButton.addEventListener("click", setServer);
  panel.tokenButton.addEventListener("click", setToken);
  gm.menu("Set server URL", setServer);
  gm.menu("Set API token", setToken);
  gm.menu("Add this website", () => {
    root.open(config().server.replace(/\/+$/, "") + "/sources/new?site=" + encodeURIComponent(root.location.host), "_blank");
  });
  loadTrips();
  if (autoSend()) flush();
  setInterval(() => { if (autoSend()) flush(); }, RETRY_MS);
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
