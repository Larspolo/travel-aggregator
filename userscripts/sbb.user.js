// ==UserScript==
// @name         travel-aggregator: sbb.ch
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.0
// @description  Send the SBB connection search results (GraphQL Trips and TripPrices responses) to travel-aggregator.
// @match        https://www.sbb.ch/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to sbb.ch (P1).
// The page asks for the connections (query Trips) and then for their prices (query TripPrices, one response for each
// card): each TripPrices response of the trips of the last Trips response is one capture {..., prices}.
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "sbb.ch";
  const PARSER_VERSION = "1.0.0";
  const HOST = "graphql.www.sbb.ch";

  // Only the GraphQL variables of a request: not the query text (as tests/fixtures/sbb.ch).
  const request = (method, text) => {
    const body = core.parseJson(text);
    const variables = body && typeof body === "object" ? body.variables : null;
    return { method, body: { variables: variables && typeof variables === "object" ? variables : {} } };
  };

  const countRaw = (raw) => {
    const p = raw && raw.prices && raw.prices.response && raw.prices.response.data;
    const list = p && Array.isArray(p.tripPrices) ? p.tripPrices : [];
    return list.reduce((n, t) => n + (Array.isArray(t.tripPrices) ? t.tripPrices.length : 0), 0);
  };

  let trips = null;  // {url, method, request, response, ids} of the last Trips response
  core.watch(core.urlTest((u) => u.hostname === HOST && u.pathname === "/"), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    const data = response && response.data;
    if (!data || typeof data !== "object") return;
    if (data.trips && Array.isArray(data.trips.trips)) {
      trips = { url, method, request: request(method, body), response,
        ids: new Set(data.trips.trips.map((t) => t && t.id)) };
      return;
    }
    if (!trips || !Array.isArray(data.tripPrices) || !data.tripPrices.length) return;
    if (!data.tripPrices.every((t) => t && trips.ids.has(t.tripId))) return;
    core.capture(SOURCE, PARSER_VERSION, { url: trips.url, method: trips.method, request: trips.request,
      response: trips.response, prices: { url, method, request: request(method, body), response } }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
