// ==UserScript==
// @name         travel-aggregator: bahn.de
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.3.0
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
  const PARSER_VERSION = "1.2.0";
  const PATHS = ["/web/api/angebote/fahrplan", "/web/api/angebote/recon", "/web/api/angebote/tagesbestpreis"];
  const RESULTS_PATH = "/buchung/fahrplan/suche";

  const countRaw = (raw) => {
    const r = raw && raw.response;
    if (!r) return 0;
    // A recon response (#1678) counts its fares as the parser does: no "Probe " trial, one per name and class,
    // only with a price. A connection with no such fare counts as one.
    const fares = (c) => {
      const seen = new Set();
      for (const a of (c && c.reiseAngebote) || []) {
        const name = String((a && a.name) || "").trim();
        if (name.startsWith("Probe ") || !a.preis || a.preis.betrag == null) continue;
        seen.add(name + "\u0000" + a.klasse);
      }
      return seen.size || 1;
    };
    if (Array.isArray(r.verbindungen)) return r.verbindungen.reduce((n, c) => n + fares(c), 0);
    // A day price response (#1196) counts its intervals that have a price.
    return Array.isArray(r.intervalle) ? r.intervalle.filter((iv) => iv && iv.preis).length : 0;
  };

  // No offers seen (#1756): the results page of bahn.de, with the source and the parser version of this script.
  core.resultsPage((u) => u.pathname === RESULTS_PATH, SOURCE, PARSER_VERSION);
  core.watch(core.urlTest((u) => PATHS.includes(u.pathname)), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    if (!response || !(Array.isArray(response.verbindungen) || Array.isArray(response.intervalle))) return;
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: core.parseJson(body), response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
