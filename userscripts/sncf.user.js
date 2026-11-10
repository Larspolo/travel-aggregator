// ==UserScript==
// @name         travel-aggregator: sncf-connect.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.1.0
// @description  Send the SNCF Connect search results (itineraries responses) to travel-aggregator.
// @match        https://www.sncf-connect.com/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to sncf-connect.com (P1).
// The request body keeps only `schedule` and `mainJourney`: the other keys hold a session id (P5).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "sncf-connect.com";
  const PARSER_VERSION = "1.0.0";
  const HOST = "www.sncf-connect.com";
  const PATH = "/bff/api/v1/itineraries";
  const KEEP = ["schedule", "mainJourney"];

  const countRaw = (raw) => {
    const r = raw && raw.response;
    const ld = r && r.longDistance;
    const props = ld && ld.proposals && Array.isArray(ld.proposals.proposals) ? ld.proposals.proposals : [];
    return props.filter((p) => p && p.status && p.status.isBookable).length;
  };

  const searchOnly = (body) => {
    const parsed = core.parseJson(body);
    if (!parsed || typeof parsed !== "object") return null;
    const out = {};
    KEEP.forEach((k) => { if (k in parsed) out[k] = parsed[k]; });
    return out;
  };

  // No offers seen (#1757): the results page of the site.
  core.resultsPage((u) => u.hostname === HOST && u.pathname.startsWith("/app/home/shop/results/"), SOURCE, PARSER_VERSION);
  core.watch(core.urlTest((u) => u.hostname === HOST && u.pathname === PATH), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    const ld = response && response.longDistance;
    if (!ld || !ld.proposals || !Array.isArray(ld.proposals.proposals)) return;
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: searchOnly(body), response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
