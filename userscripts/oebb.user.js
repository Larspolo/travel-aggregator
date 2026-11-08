// ==UserScript==
// @name         travel-aggregator: oebbtickets.at
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.1.0
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
  const PARSER_VERSION = "1.1.0";
  const HOST = "shop.oebbtickets.at";
  // The search (connections) and the fares of one connection (offers). Both are POST requests with a JSON body.
  const TIMETABLE = "/api/hafas/v4/timetable";
  const PRICES = "/api/offer/v1/prices";
  const PATHS = new Set([TIMETABLE, "/api/offer/v6/offers", PRICES]);
  // The timetables of the page: the prices of their connections come later with GET PRICES (#1050).
  const timetables = [];

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

  const pathOf = (url) => {
    try { return new URL(String(url), root.location.href).pathname; } catch (e) { return ""; }
  };

  // Send the timetable whose connections have the ids of the prices response, with the prices.
  const onPrices = (response) => {
    const prices = {};
    for (const o of Array.isArray(response.offers) ? response.offers : []) {
      if (!o || o.offerError || o.price === undefined || o.price === null || !o.connectionId) continue;
      prices[o.connectionId] = String(o.price);
    }
    const ids = Object.keys(prices);
    if (!ids.length) return;
    for (let i = timetables.length - 1; i >= 0; i--) {
      const t = timetables[i];
      const own = new Set(t.response.connections.map((c) => c && c.id));
      if (!ids.some((id) => own.has(id))) continue;
      timetables.splice(i, 1);
      core.capture(SOURCE, PARSER_VERSION, { url: t.url, method: t.method, request: t.request,
        response: t.response, prices }, countRaw);
      return;
    }
  };

  core.watch(core.urlTest(isSource), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    if (!response || typeof response !== "object") return;
    const path = pathOf(url);
    if (path === PRICES) {
      if (String(method || "GET").toUpperCase() === "GET") onPrices(response);
      return;
    }
    const request = core.parseJson(body);
    if (path === TIMETABLE) {
      // A timetable alone gives only rejects: keep it until its prices come.
      if (Array.isArray(response.connections)) timetables.push({ url, method, request, response });
      if (timetables.length > 10) timetables.shift();
      return;
    }
    core.capture(SOURCE, PARSER_VERSION, { url, method, request, response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
