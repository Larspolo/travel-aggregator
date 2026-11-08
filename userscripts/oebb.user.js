// ==UserScript==
// @name         travel-aggregator: oebbtickets.at
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.0
// @description  Send the ÖBB search results (timetable and fare responses of shop.oebbtickets.at) to travel-aggregator.
// @match        https://shop.oebbtickets.at/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to oebbtickets.at (P1).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "oebbtickets.at";
  const PARSER_VERSION = "1.0.0";
  const HOST = "shop.oebbtickets.at";
  // The search (connections) and the fares of one connection (offers). Both are POST requests with a JSON body.
  const PATHS = new Set(["/api/hafas/v4/timetable", "/api/offer/v6/offers"]);

  const countRaw = (raw) => {
    const r = raw && raw.response;
    if (!r) return 0;
    if (Array.isArray(r.connections)) return r.connections.length;
    const sections = Array.isArray(r.offerSections) ? r.offerSections : [];
    return sections.reduce((n, s) => {
      const classes = s && Array.isArray(s.travelClasses) ? s.travelClasses : [];
      return n + classes.reduce((m, c) => m + (c && Array.isArray(c.offers) ? c.offers.length : 0), 0);
    }, 0);
  };

  const isSource = (u) => u.hostname === HOST && PATHS.has(u.pathname);

  core.watch(core.urlTest(isSource), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    if (!response || typeof response !== "object") return;
    const request = core.parseJson(body);
    core.capture(SOURCE, PARSER_VERSION, { url, method, request, response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
