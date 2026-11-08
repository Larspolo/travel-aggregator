// ==UserScript==
// @name         travel-aggregator: thetrainline.com
// @namespace    https://github.com/Larspolo/travel-aggregator
// @version      1.0.0
// @description  Send the Trainline search results (journey search responses) to travel-aggregator.
// @match        https://www.thetrainline.com/*
// @match        https://thetrainline.com/*
// @run-at       document-start
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      *
// @require      https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/core.js
// ==/UserScript==
// It only reads the responses that the page itself gets: it sends no request to thetrainline.com (P1).
(function (root) {
  "use strict";
  const core = root.TACore;
  if (!core) return;
  const SOURCE = "thetrainline.com";
  const PARSER_VERSION = "1.0.0";
  const HOST = "www.thetrainline.com";
  const PATH = "/api/journey-search/";

  // The request body names each passenger; the date of birth is personal data and is not sent (P5).
  const withoutBirthDates = (text) => {
    const body = core.parseJson(text);
    if (!body || typeof body !== "object") return null;
    if (Array.isArray(body.passengers)) {
      body.passengers = body.passengers.map((p) => {
        const copy = Object.assign({}, p);
        delete copy.dateOfBirth;
        return copy;
      });
    }
    return body;
  };

  const countRaw = (raw) => {
    const js = raw && raw.response && raw.response.data && raw.response.data.journeySearch;
    return js && js.journeys ? Object.keys(js.journeys).length : 0;
  };

  core.watch(core.urlTest((u) => u.hostname === HOST && u.pathname === PATH), ({ url, method, body, text }) => {
    const response = core.parseJson(text);
    if (!response || !response.data || !response.data.journeySearch) return;
    const request = withoutBirthDates(body);
    core.capture(SOURCE, PARSER_VERSION, { url, method, request: request && { method, body: request }, response },
      countRaw);
  });
})(typeof unsafeWindow !== "undefined" ? unsafeWindow : window);
