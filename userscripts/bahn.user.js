// ==UserScript==
// @name         travel-aggregator: bahn.de
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.1.0
// @description  Send the bahn.de search results (fahrplan and recon responses) to travel-aggregator.
// @match        https://www.bahn.de/*
// @match        https://int.bahn.de/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to bahn.de (P1).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "bahn.de";
  const PARSER_VERSION = "1.0.0";
  const PATHS = ["/web/api/angebote/fahrplan", "/web/api/angebote/recon"];

  const countRaw = (raw) => {
    const r = raw && raw.response;
    return r && Array.isArray(r.verbindungen) ? r.verbindungen.length : 0;
  };

  core.watch(core.urlTest((u) => PATHS.includes(u.pathname)), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    if (!response || !Array.isArray(response.verbindungen)) return;
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: core.parseJson(body), response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
