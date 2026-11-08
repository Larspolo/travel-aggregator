// ==UserScript==
// @name         travel-aggregator: eurostar.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.0
// @description  Send the Eurostar search results (NewBookingSearch responses) to travel-aggregator.
// @match        https://www.eurostar.com/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to eurostar.com (P1).
// Each search is a full page load, so the script runs at document start (#954).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "eurostar.com";
  const PARSER_VERSION = "1.0.0";
  const HOST = "site-api.eurostar.com";
  const PATH = "/gateway";
  const OPERATION = "NewBookingSearch";

  // The GraphQL query text is long and has no search data: only the operation and its variables are sent.
  const withoutQuery = (body) => {
    if (!body || typeof body !== "object" || body.operationName !== OPERATION) return null;
    return { operationName: body.operationName, variables: body.variables };
  };

  const countRaw = (raw) => {
    const outbound = raw && raw.response && raw.response.data && raw.response.data.journeySearch
      && raw.response.data.journeySearch.outbound;
    return outbound && Array.isArray(outbound.journeys) ? outbound.journeys.length : 0;
  };

  core.watch(core.urlTest((u) => u.hostname === HOST && u.pathname === PATH), ({ url, method, body, text }) => {
    const request = withoutQuery(core.parseJson(body));
    if (!request) return;
    const response = core.parseJson(text);
    if (!response || !response.data || !response.data.journeySearch) return;
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: { method, body: request }, response },
      countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
