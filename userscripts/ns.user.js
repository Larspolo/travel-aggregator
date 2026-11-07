// ==UserScript==
// @name         travel-aggregator: nsinternational.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.1.0
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
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "nsinternational.com";
  const PARSER_VERSION = "1.0.0";
  const PATH = "/api/v2/sales/traveloffers/search";

  const countRaw = (raw) => {
    const r = raw && raw.response;
    const d = r && r.data;
    return d && Array.isArray(d.travelOffers) ? d.travelOffers.length : 0;
  };

  core.watch(core.urlTest((u) => u.pathname === PATH), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    if (!response || !response.data || !Array.isArray(response.data.travelOffers)) return;
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: core.parseJson(body), response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
