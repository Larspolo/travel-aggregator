// ==UserScript==
// @name         travel-aggregator: flixbus.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.1.1
// @description  Send the Flixbus search results (search service responses) to travel-aggregator.
// @match        https://*.flixbus.at/*
// @match        https://*.flixbus.be/*
// @match        https://*.flixbus.bg/*
// @match        https://*.flixbus.ca/*
// @match        https://*.flixbus.ch/*
// @match        https://*.flixbus.co.uk/*
// @match        https://*.flixbus.com/*
// @match        https://*.flixbus.com.br/*
// @match        https://*.flixbus.cz/*
// @match        https://*.flixbus.de/*
// @match        https://*.flixbus.dk/*
// @match        https://*.flixbus.ee/*
// @match        https://*.flixbus.es/*
// @match        https://*.flixbus.fi/*
// @match        https://*.flixbus.fr/*
// @match        https://*.flixbus.gr/*
// @match        https://*.flixbus.hr/*
// @match        https://*.flixbus.hu/*
// @match        https://*.flixbus.ie/*
// @match        https://*.flixbus.in/*
// @match        https://*.flixbus.it/*
// @match        https://*.flixbus.lt/*
// @match        https://*.flixbus.lv/*
// @match        https://*.flixbus.nl/*
// @match        https://*.flixbus.no/*
// @match        https://*.flixbus.pl/*
// @match        https://*.flixbus.pt/*
// @match        https://*.flixbus.ro/*
// @match        https://*.flixbus.rs/*
// @match        https://*.flixbus.se/*
// @match        https://*.flixbus.si/*
// @match        https://*.flixbus.sk/*
// @match        https://*.flixbus.com.ua/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to flixbus.com (P1).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "flixbus.com";
  const PARSER_VERSION = "1.0.0";
  const HOST = "global.api.flixbus.com";
  const PATH = "/search/service/v4/search";

  const countRaw = (raw) => {
    const r = raw && raw.response;
    const trips = r && Array.isArray(r.trips) ? r.trips : [];
    return trips.reduce((n, t) => n + (t && t.results ? Object.keys(t.results).length : 0), 0);
  };

  core.watch(core.urlTest((u) => u.hostname === HOST && u.pathname === PATH), ({ url, method, text }) => {
    const response = core.parseJson(text);
    if (!response || !Array.isArray(response.trips)) return;
    // The search is a GET with its parameters in the URL: the body is empty.
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: null, response }, countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
