// ==UserScript==
// @name         travel-aggregator: nsinternational.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.0
// @description  Send the NS International search results (traveloffers responses) to travel-aggregator.
// @match        https://www.nsinternational.com/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to nsinternational.com (P1).
(function (root) {
  "use strict";
  const SOURCE = "nsinternational.com";
  const PARSER_VERSION = "1.0.0";
  const PATH = "/api/v2/sales/traveloffers/search";

  const isSearch = (url) => {
    try { return new URL(String(url), root.location.href).pathname === PATH; } catch (e) { return false; }
  };
  const parseJson = (text) => {
    if (typeof text !== "string" || !text) return null;
    try { return JSON.parse(text); } catch (e) { return null; }
  };
  const countRaw = (raw) => {
    const r = raw && raw.response;
    const d = r && r.data;
    return d && Array.isArray(d.travelOffers) ? d.travelOffers.length : 0;
  };

  function capture(url, method, requestBody, responseText) {
    const response = parseJson(responseText);
    if (!response || !response.data || !Array.isArray(response.data.travelOffers)) return;
    const core = root.TACore;
    if (!core) return;
    core.countRaw = countRaw;
    const raw = { url: String(url), method: String(method || "GET").toUpperCase(),
      request: parseJson(requestBody), response };
    core.report(countRaw(raw));
    core.send({ source: SOURCE, parser_version: PARSER_VERSION, captured_at: new Date().toISOString(),
      page_url: root.location.href, raw });
  }

  const origFetch = root.fetch;
  if (typeof origFetch === "function") {
    root.fetch = function (input, init) {
      const promise = origFetch.apply(this, arguments);
      const url = input && typeof input === "object" && "url" in input ? input.url : input;
      if (!isSearch(url)) return promise;
      const method = (init && init.method) || (input && input.method) || "GET";
      const body = init && typeof init.body === "string" ? init.body : null;
      return promise.then((res) => {
        try { res.clone().text().then((t) => capture(url, method, body, t), () => {}); } catch (e) { /* ignore */ }
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
      if (isSearch(this.__taUrl)) {
        this.addEventListener("load", () => {
          const t = this.responseType;
          const text = !t || t === "text" ? this.responseText : t === "json" ? JSON.stringify(this.response) : null;
          capture(this.__taUrl, this.__taMethod, typeof body === "string" ? body : null, text);
        });
      }
      return send.apply(this, arguments);
    };
  }
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
