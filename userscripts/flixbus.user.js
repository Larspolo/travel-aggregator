// ==UserScript==
// @name         travel-aggregator: flixbus.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.1
// @description  Send the Flixbus search results (search service responses) to travel-aggregator.
// @match        https://*.flixbus.nl/*
// @match        https://*.flixbus.com/*
// @match        https://*.flixbus.de/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to flixbus.com (P1).
(function (root) {
  "use strict";
  const SOURCE = "flixbus.com";
  const PARSER_VERSION = "1.0.0";
  const HOST = "global.api.flixbus.com";
  const PATH = "/search/service/v4/search";

  const isSearch = (url) => {
    try {
      const u = new URL(String(url), root.location.href);
      return u.hostname === HOST && u.pathname === PATH;
    } catch (e) { return false; }
  };
  const parseJson = (text) => {
    if (typeof text !== "string" || !text) return null;
    try { return JSON.parse(text); } catch (e) { return null; }
  };
  const countRaw = (raw) => {
    const r = raw && raw.response;
    const trips = r && Array.isArray(r.trips) ? r.trips : [];
    return trips.reduce((n, t) => n + (t && t.results ? Object.keys(t.results).length : 0), 0);
  };

  function capture(url, method, responseText) {
    const response = parseJson(responseText);
    if (!response || !Array.isArray(response.trips)) return;
    const core = root.TACore;
    if (!core) return;
    core.countRaw = countRaw;
    // The search is a GET with its parameters in the URL: the body is empty.
    const raw = { url: String(url), method: String(method || "GET").toUpperCase(), request: null, response };
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
      return promise.then((res) => {
        try { res.clone().text().then((t) => capture(url, method, t), () => {}); } catch (e) { /* ignore */ }
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
    XHR.send = function () {
      if (isSearch(this.__taUrl)) {
        this.addEventListener("load", () => {
          const t = this.responseType;
          const text = !t || t === "text" ? this.responseText : t === "json" ? JSON.stringify(this.response) : null;
          capture(this.__taUrl, this.__taMethod, text);
        });
      }
      return send.apply(this, arguments);
    };
  }
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
