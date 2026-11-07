// ==UserScript==
// @name         travel-aggregator: kiwi.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.0
// @description  Send the Kiwi.com search results (SearchOneWayItinerariesQuery responses) to travel-aggregator.
// @match        https://www.kiwi.com/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to kiwi.com or skypicker.com (P1).
// It sends the currency of the request and the response body, and no request value (no serverToken, no session id).
(function (root) {
  "use strict";
  const SOURCE = "kiwi.com";
  const PARSER_VERSION = "1.0.0";
  const HOST = "api.skypicker.com";
  const PATH = "/umbrella/v2/graphql";
  const FEATURE = "SearchOneWayItinerariesQuery";

  const isSearch = (url) => {
    try {
      const u = new URL(String(url), root.location.href);
      return u.host === HOST && u.pathname === PATH && u.searchParams.get("featureName") === FEATURE;
    } catch (e) { return false; }
  };
  const parseJson = (text) => {
    if (typeof text !== "string" || !text) return null;
    try { return JSON.parse(text); } catch (e) { return null; }
  };
  const countRaw = (raw) => {
    const r = raw && raw.response;
    const o = r && r.data && r.data.onewayItineraries;
    return o && Array.isArray(o.itineraries) ? o.itineraries.length : 0;
  };
  const currencyOf = (request) => {
    const v = request && request.variables;
    const c = v && v.options && v.options.currency;
    return typeof c === "string" && c ? c.toLowerCase() : null;
  };

  function capture(requestBody, responseText) {
    const response = parseJson(responseText);
    if (!response || !response.data || !response.data.onewayItineraries) return;
    const currency = currencyOf(parseJson(requestBody));
    const core = root.TACore;
    if (!core || !currency) return;
    core.countRaw = countRaw;
    const raw = { currency, response };
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
      const body = init && typeof init.body === "string" ? init.body : null;
      return promise.then((res) => {
        try { res.clone().text().then((t) => capture(body, t), () => {}); } catch (e) { /* ignore */ }
        return res;
      });
    };
  }

  const XHR = root.XMLHttpRequest && root.XMLHttpRequest.prototype;
  if (XHR) {
    const open = XHR.open;
    const send = XHR.send;
    XHR.open = function (method, url) {
      this.__taUrl = url;
      return open.apply(this, arguments);
    };
    XHR.send = function (body) {
      if (isSearch(this.__taUrl)) {
        this.addEventListener("load", () => {
          const t = this.responseType;
          const text = !t || t === "text" ? this.responseText : t === "json" ? JSON.stringify(this.response) : null;
          capture(typeof body === "string" ? body : null, text);
        });
      }
      return send.apply(this, arguments);
    };
  }
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
