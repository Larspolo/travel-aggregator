// travel-aggregator userscript core: a floating status panel in a Shadow DOM.
// It reads and writes no page data (P1, P5). It uses GM_* functions only through TACore.gm.
// Make CORE_VERSION higher with each change of this file (the server adds it to the @version of each script).
const CORE_VERSION = 16;
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

  // The design tokens of app.css (#621, #1067), copied: the panel loads no CSS or font from a server (P1, P5).
  const STYLE = `
    :host { all: initial; color-scheme: light dark;
      --surface: #ffffff; --surface-2: #f8f8fa; --text: #17171c; --muted: #5d5d68; --line: #e3e3e8;
      --accent: #5145d6; --accent-text: #ffffff; --accent-soft: #eeedfd;
      --good: #187a35; --info: #0a64c9; --warn: #9a4f00; --danger: #c4302b;
      --shadow: 0 1px 2px rgb(16 16 24 / .05), 0 4px 12px rgb(16 16 24 / .08);
      --ring: 0 0 0 3px rgb(81 69 214 / .22); --radius: 8px;
      --font: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
    @media (prefers-color-scheme: dark) {
      :host { --surface: #15151a; --surface-2: #1b1b21; --text: #ececf0; --muted: #9b9ba6; --line: #2a2a31;
        --accent: #8f87ff; --accent-text: #0c0c0f; --accent-soft: #23214a;
        --good: #43c164; --info: #5eaaff; --warn: #e3a03f; --danger: #f47067;
        --shadow: 0 4px 12px rgb(0 0 0 / .5); --ring: 0 0 0 3px rgb(143 135 255 / .3); }
    }
    .panel, .controls, .ask { position: fixed; right: 12px; z-index: 2147483647; box-sizing: border-box;
      max-width: min(440px, calc(100vw - 24px)); font: 12.5px/1.4 var(--font); color: var(--text);
      background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
      box-shadow: var(--shadow); }
    .panel { bottom: 12px; padding: 6px 10px 6px 12px; border-left: 4px solid var(--info); cursor: pointer;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .panel.ok { border-left-color: var(--good); }
    .panel.info { border-left-color: var(--info); }
    .panel.warn { border-left-color: var(--warn); }
    .panel.error { border-left-color: var(--danger); color: var(--danger); font-weight: 600; }
    .controls { bottom: 48px; display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; padding: 8px 10px; }
    .ask { bottom: 48px; display: flex; gap: 6px; align-items: center; padding: 8px 10px; }
    .ask:not([hidden]) ~ .controls { display: none; }
    [hidden], .collapsed .controls, .collapsed .ask { display: none !important; }
    label { display: inline-flex; gap: 4px; align-items: center; color: var(--muted); }
    select, input:not([type=checkbox]) { font: inherit; color: var(--text); background: var(--surface-2);
      border: 1px solid var(--line); border-radius: 6px; padding: 3px 6px; min-width: 0; }
    input[type=checkbox] { accent-color: var(--accent); margin: 0; }
    button { font: inherit; font-weight: 500; color: var(--text); background: var(--surface-2); cursor: pointer;
      border: 1px solid var(--line); border-radius: 6px; padding: 3px 9px; }
    button:hover { background: var(--accent-soft); }
    button.send, button.ask-save { color: var(--accent-text); background: var(--accent); border-color: var(--accent); }
    button:focus-visible, select:focus-visible, input:focus-visible { outline: none; box-shadow: var(--ring); }
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
      <label><input type="checkbox" class="autotrip"> auto-select trip</label>
      <button type="button" class="send">Send</button>
      <button type="button" class="set-server">Server URL</button>
      <button type="button" class="set-token">API token</button>`;
    // One inline form for the questions of the panel (#1066): a browser dialog blocks Playwright and agent tools.
    const form = document.createElement("form");
    form.className = "ask";
    form.hidden = true;
    form.innerHTML = `<label><span class="ask-label"></span> <input class="ask-input"></label>
      <button type="submit" class="ask-save">Save</button>
      <button type="button" class="ask-cancel">Cancel</button>`;
    const input = form.querySelector(".ask-input");
    let answer = null;
    const close = (value) => {
      form.hidden = true;
      const done = answer;
      answer = null;
      if (done) done(value);
    };
    form.addEventListener("submit", (e) => { e.preventDefault(); close(input.value); });
    form.querySelector(".ask-cancel").addEventListener("click", () => close(null));
    input.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); close(null); } });
    // A click on the status line hides or shows the controls (#1067): the panel must not cover the buttons of the site.
    const wrap = document.createElement("div");
    const fold = (on) => { wrap.classList.toggle("collapsed", on); gm.setValue("collapsed", on); };
    wrap.classList.toggle("collapsed", gm.getValue("collapsed", false) === true);
    box.title = "Show or hide the travel-aggregator controls";
    box.addEventListener("click", () => fold(!wrap.classList.contains("collapsed")));
    wrap.append(form, controls, box);
    shadow.append(style, wrap);
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
      autotrip: controls.querySelector(".autotrip"),
      sendButton: controls.querySelector(".send"),
      serverButton: controls.querySelector(".set-server"),
      tokenButton: controls.querySelector(".set-token"),
      setStatus(text, kind) {
        box.className = "panel " + (["ok", "error", "info", "warn"].includes(kind) ? kind : "info");
        box.textContent = String(text);
      },
      // Show the form; resolve with the text at "Save" or Enter, with null at "Cancel" or Escape.
      ask(label, value, type) {
        close(null);
        form.querySelector(".ask-label").textContent = String(label);
        input.type = type || "text";
        input.value = String(value || "");
        form.hidden = false;
        if (wrap.classList.contains("collapsed")) fold(false);
        input.focus();
        return new Promise((resolve) => { answer = resolve; });
      },
      text: () => box.textContent,
      kind: () => box.className.replace("panel ", ""),
      collapsed: () => wrap.classList.contains("collapsed"),
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
  // The queue as status text (#1664): "3 captures wait (oldest 12 min)", "1 capture waits". The age comes from the
  // oldest item with a valid captured_at; an item without one counts but gives no age.
  const queueText = () => {
    const q = loadQueue();
    const n = q.length;
    const times = q.map((item) => Date.parse(item && item.captured_at)).filter((t) => Number.isFinite(t));
    const age = times.length ? ` (oldest ${Math.max(0, Math.floor((Date.now() - Math.min(...times)) / 60000))} min)` : "";
    return n === 1 ? `1 capture waits${age}` : `${n} captures wait${age}`;
  };
  const tripId = () => {
    const id = Number(gm.getValue("trip", 0));
    return Number.isInteger(id) && id > 0 ? id : null;
  };
  const autoSend = () => gm.getValue("autosend", true) !== false;
  // "Auto-select trip" (#721): the server stores a capture into the trip that matches it (auto_trip, #719).
  const autoTrip = () => gm.getValue("autotrip", true) !== false;
  // The trip that the last response suggested (#720); the next "+ new trip" uses it. Null when there is none.
  let suggestion = null;
  // The offers of a payload; a raw capture asks the counter of its site userscript (core.countRaw).
  const count = (payload) => {
    if (!payload) return 0;
    if (Array.isArray(payload.offers) && payload.offers.length) return payload.offers.length;
    if (payload.raw !== undefined && typeof core.countRaw === "function") {
      try { return Number(core.countRaw(payload.raw)) || 0; } catch (e) { return 0; }
    }
    return 0;
  };
  // The warning of the ingest response (#557): the offers do not match the trip. Null when there is none.
  const warningOf = (r) => {
    const w = responseOf(r).warning;
    return w ? String(w) : null;
  };
  // The best offer of the trip (#881) as a suffix of the sent text: "" when the response has none.
  // Whole euros show without decimals ("€182"); other totals show 2 decimals ("€165.50").
  function bestOf(resp) {
    const best = resp && resp.best;
    if (!best || typeof best !== "object" || typeof best.total !== "string") return "";
    if (!/^\d+(\.\d+)?$/.test(best.total)) return "";
    const amount = Number(best.total).toFixed(2).replace(/\.00$/, "");
    return ` · Best of trip: €${amount}${best.new === true ? " (new)" : ""}`;
  }
  // The parsed ingest response; {} when it is not a JSON object.
  function responseOf(r) {
    try {
      const v = JSON.parse(String(r.responseText || "{}"));
      return v && typeof v === "object" ? v : {};
    } catch (e) {
      return {};
    }
  }
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
      const fail = () => { panel.setStatus(`Send failed: ${queueText()}, kept in the queue`, "error"); resolve("retry"); };
      gm.request({
        method: "POST",
        url: server + "/api/ingest",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        data: JSON.stringify(payload),
        onload: (r) => {
          if (r.status >= 200 && r.status < 300) { core.sent(count(payload), warningOf(r), responseOf(r)); resolve("ok"); }
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
    const suggested = suggestion;
    const title = await panel.ask("Title of the new trip", suggested ? String(suggested.title || "") : "");
    if (title === null || !title.trim()) return;
    suggestion = null;
    const trip = await trips("POST", Object.assign({}, suggested || {}, { title: title.trim() }));
    if (!trip || !trip.id) return;
    addOption(trip);
    panel.select.value = String(trip.id);
    gm.setValue("trip", trip.id);
  }

  panel.select.addEventListener("change", () => gm.setValue("trip", Number(panel.select.value) || 0));
  panel.newTrip.addEventListener("click", newTrip);
  panel.autotrip.checked = autoTrip();
  panel.autotrip.addEventListener("change", () => gm.setValue("autotrip", panel.autotrip.checked));
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
  // The text of a response or a request body: a string, JSON, a Blob, an ArrayBuffer (or a view) or URLSearchParams.
  const asText = (v) => {
    try {
      if (v === null || v === undefined || typeof v === "string") return Promise.resolve(v === undefined ? null : v);
      if (typeof Blob !== "undefined" && v instanceof Blob) return v.text();
      if (v instanceof ArrayBuffer || ArrayBuffer.isView(v)) return Promise.resolve(new TextDecoder().decode(v));
      if (typeof URLSearchParams !== "undefined" && v instanceof URLSearchParams) return Promise.resolve(String(v));
      if (typeof FormData !== "undefined" && v instanceof FormData) return Promise.resolve(null);
      return Promise.resolve(JSON.stringify(v));
    } catch (e) { return Promise.resolve(null); }
  };
  let hooked = false;
  // For the diagnosis of a missed capture (#1072): the time of the hook, the responses it saw, and if the page had
  // wrapped XMLHttpRequest before it.
  const probe = { at: null, seen: 0, nativeXhr: true };
  const notify = (url, method, body, text) => {
    probe.seen += 1;
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
    probe.at = root.performance && root.performance.now ? root.performance.now() : null;
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
      try { probe.nativeXhr = /\[native code\]/.test(Function.prototype.toString.call(XHR.send)); } catch (e) { /* */ }
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
            // A page can ask for a blob or an arraybuffer, and send a Blob or URLSearchParams (#1072): decode them.
            Promise.all([asText(this.responseType === "" || this.responseType === "text"
              ? this.responseText : this.response), asText(body)])
              .then(([text, b]) => notify(this.__taUrl, this.__taMethod, b, text), () => {});
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
    // A URL test of a site: true when the URL passes test(u) for its URL object u. A relative URL is relative to the
    // base of the document: bahn.de has `<base href="/web/">` and requests `api/angebote/fahrplan` (#528).
    urlTest: (test) => (url) => {
      const base = (root.document && root.document.baseURI) || root.location.href;
      try { return Boolean(test(new URL(String(url), base))); } catch (e) { return false; }
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
    sent(n, warning, response) {
      const resp = response || {};
      if (resp.suggestion && typeof resp.suggestion === "object") {
        suggestion = resp.suggestion;  // #720: no trip matches; "+ new trip" fills in this trip
        panel.setStatus(`Captured ${n} offers → sent ✓. No trip matches: + new trip`, "warn");
        return;
      }
      const id = Number(resp.trip_id);
      if (Number.isInteger(id) && id > 0 && id !== tripId()) {
        // #721: the server chose another trip: select it in the dropdown
        if (!Array.from(panel.select.options).some((o) => o.value === String(id))) {
          addOption({ id, title: resp.trip_title || `Trip ${id}` });
        }
        panel.select.value = String(id);
        gm.setValue("trip", id);
        panel.setStatus(`Captured ${n} offers → sent to ${resp.trip_title || `trip ${id}`} ✓${bestOf(resp)}`, "ok");
        return;
      }
      const best = bestOf(resp);
      // #945: the travelers warning of the server ("These offers are for 1 traveler; the trip has 2") as it is
      if (warning && resp.mismatch === "travelers") {
        const text = warning.charAt(0).toLowerCase() + warning.slice(1);
        panel.setStatus(`Captured ${n} offers → sent ✓, but ${text}${best}`, "warn");
      } else if (warning) panel.setStatus(`Captured ${n} offers → sent ✓, but these offers do not match the trip${best}`, "warn");
      else panel.setStatus(`Captured ${n} offers → sent ✓${best}`, "ok");
    },
    queue: loadQueue,
    flush,
    loadTrips,
    newTrip,
    tripId,
    // Queue one payload for the chosen trip; send it now only when auto-send is on.
    send(payload) {
      const id = tripId();
      const item = Object.assign({}, payload, id ? { trip_id: id } : {}, autoTrip() ? { auto_trip: true } : {});
      gm.setValue("queue", loadQueue().concat([item]));
      if (!autoSend()) {
        panel.setStatus(`Captured ${count(item)} offers: ${queueText()}, press Send`, "info");
        return Promise.resolve();
      }
      return flush();
    },
  };
  root.TACore = core;
  // A missed capture (#1072): the resource timing of the browser (a local list, no request, P1) shows the requests of
  // the page that a watcher accepts. When the hook saw none of them, the panel tells why.
  core.diagnose = () => {
    if (probe.seen || probe.at === null || !root.performance || !root.performance.getEntriesByType) return null;
    const missed = root.performance.getEntriesByType("resource").filter((e) => accepted(e.name)
      && (e.initiatorType === "xmlhttprequest" || e.initiatorType === "fetch"));
    if (!missed.length) return null;
    const early = missed.filter((e) => e.startTime < probe.at).length;
    const start = (probe.at / 1000).toFixed(2);
    const text = early
      ? `Missed ${early} search responses: they came before the script started (${start} s)`
      : `Missed ${missed.length} search responses: ${probe.nativeXhr ? "the hook did not see them" : "the page wrapped XMLHttpRequest first"} (start ${start} s)`;
    panel.setStatus(text, "warn");
    return text;
  };
  const later = () => setTimeout(core.diagnose, 3000);
  if (root.document && root.document.readyState === "complete") later();
  else root.addEventListener("load", later);
  // The panel has the settings too (#536): the Tampermonkey menu is hidden in the extension popup.
  const setServer = async () => {
    const v = await panel.ask("travel-aggregator server URL", config().server, "url");
    if (v !== null) { gm.setValue("server", v.trim()); loadTrips(); }
  };
  const setToken = async () => {
    const v = await panel.ask("travel-aggregator API token", "", "password");
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
