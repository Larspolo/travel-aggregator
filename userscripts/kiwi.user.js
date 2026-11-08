// ==UserScript==
// @name         travel-aggregator: kiwi.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.3.0
// @description  Send the Kiwi.com search results (SearchOneWayItinerariesQuery and SearchReturnItinerariesQuery responses) to travel-aggregator.
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
// It sends the currency of the request, the number of adults, children and infants, and the response body, and no
// other request value (no serverToken, no session id).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "kiwi.com";
  const PARSER_VERSION = "1.2.0";
  const HOST = "api.skypicker.com";
  const PATH = "/umbrella/v2/graphql";
  // A one-way search and a return search (#1004: the default search of Kiwi.com is a return trip).
  const FEATURES = new Set(["SearchOneWayItinerariesQuery", "SearchReturnItinerariesQuery"]);
  const resultsOf = (response) => {
    const d = response && response.data;
    if (!d) return null;
    return d.onewayItineraries || d.returnItineraries || null;
  };

  const countRaw = (raw) => {
    const r = raw && raw.response;
    const o = resultsOf(r);
    return o && Array.isArray(o.itineraries) ? o.itineraries.length : 0;
  };
  const currencyOf = (request) => {
    const v = request && request.variables;
    const c = v && v.options && v.options.currency;
    return typeof c === "string" && c ? c.toLowerCase() : null;
  };
  const passengersOf = (request) => {
    const s = request && request.variables && request.variables.search;
    const p = s && s.passengers;
    if (!p || typeof p !== "object") return null;
    return { adults: p.adults, children: p.children, infants: p.infants };
  };
  const isSearch = (u) => u.host === HOST && u.pathname === PATH && FEATURES.has(u.searchParams.get("featureName"));

  core.watch(core.urlTest(isSearch), ({ body, text }) => {
    const response = core.parseJson(text);
    if (!resultsOf(response)) return;
    const request = core.parseJson(body);
    const currency = currencyOf(request);
    if (!currency) return;
    const raw = { currency, response };
    const passengers = passengersOf(request);
    if (passengers) raw.passengers = passengers;
    core.capture(SOURCE, PARSER_VERSION, raw, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
