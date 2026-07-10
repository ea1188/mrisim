/*
 * Blueprint — pure logic mapping the course's quiz categories onto the official
 * ARRT MRI content categories and computing weighted registry readiness. UMD like
 * assignments.js: window.Blueprint in the browser, module.exports under Node.
 * Numbers are verbatim from the ARRT MRI Content Specifications (Board Approved
 * January 2024, implementation February 1, 2025): 200 scored questions.
 * No DOM, no network.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Blueprint = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Ordered by exam weight, descending, so the render mirrors where the exam's mass sits.
  var ARRT_BLUEPRINT = [
    { key: "image-production", name: "Image Production", scored: 106, weight: 0.530,
      members: ["sequences", "image-quality", "artifacts", "perfusion"] },
    { key: "procedures", name: "Procedures", scored: 57, weight: 0.285,
      members: ["pathology", "anatomy"],
      note: "Covers pathology and anatomy. Positioning, coils, and protocol are practiced in Protocol Planning." },
    { key: "safety", name: "Safety", scored: 21, weight: 0.105,
      members: ["safety"] },
    { key: "patient-care", name: "Patient Care", scored: 16, weight: 0.080,
      members: ["patient-care"] },
  ];

  // Premium quiz topic -> ARRT category key. Audited against the quiz topic-count
  // rebalance: every premium topic maps to exactly one category. Names that also
  // appear as free members (image-quality, pathology, safety, patient-care) are a
  // SEPARATE question bank here, so they count as their own practiceable source.
  var PREMIUM_MAP = {
    "instrumentation": "image-production",
    "pulse-sequences": "image-production",
    "data-acquisition": "image-production",
    "contrast-weighting": "image-production",
    "image-quality": "image-production",
    "flow-artifacts": "image-production",
    "fat-suppression": "image-production",
    "three-d-recon": "image-production",
    "procedures-anatomy": "procedures",
    "procedures-protocols": "procedures",
    "procedures-vascular": "procedures",
    "pathology": "procedures",
    "safety": "safety",
    "patient-care": "patient-care",
    "contrast-agents": "patient-care",
  };

  function isAttempted(entry) {            // free store: { best, total, runs }
    return !!entry && typeof entry.total === "number" && entry.total > 0;
  }
  function isAttemptedPremium(entry) {     // premium store: { right, seen }
    return !!entry && typeof entry.seen === "number" && entry.seen > 0;
  }

  // freeProgress   = mrisim_quiz_progress_v1:            { freeCategory: { best, total, runs } }
  // premiumProgress = mrisim_premium_topic_progress_v1:  { premiumTopic: { right, seen } }
  // Omit premiumProgress for the legacy free-only model (denominators unchanged).
  // Supply it (even {}) to blend the premium bank into each category's accuracy and
  // coverage, with premium topics added to the coverage denominator.
  function readiness(freeProgress, premiumProgress) {
    var prog = freeProgress || {};
    var blend = premiumProgress !== undefined && premiumProgress !== null;
    var prem = premiumProgress || {};
    var premByCat = {};                    // category key -> [premium topics], computed once
    Object.keys(PREMIUM_MAP).forEach(function (t) {
      (premByCat[PREMIUM_MAP[t]] = premByCat[PREMIUM_MAP[t]] || []).push(t);
    });
    var categories = ARRT_BLUEPRINT.map(function (c) {
      var right = 0, asked = 0, attempted = 0, slots = c.members.length;
      c.members.forEach(function (m) {
        var e = prog[m];
        if (!isAttempted(e)) return;
        attempted += 1;
        right += (typeof e.best === "number" ? e.best : 0);
        asked += e.total;
      });
      if (blend) {
        var topics = premByCat[c.key] || [];
        slots += topics.length;
        topics.forEach(function (t) {
          var e = prem[t];
          if (!isAttemptedPremium(e)) return;
          attempted += 1;
          right += (typeof e.right === "number" ? e.right : 0);
          asked += e.seen;
        });
      }
      return {
        key: c.key, name: c.name, scored: c.scored, weight: c.weight, note: c.note || null,
        accuracy: asked > 0 ? right / asked : null,
        coverage: slots ? attempted / slots : 0,
        attempted: attempted, memberCount: slots,
      };
    });
    var projected = 0, coverage = 0;
    categories.forEach(function (c) {
      projected += (c.accuracy || 0) * c.weight;
      coverage += c.coverage * c.weight;
    });
    return { categories: categories, projected: projected, coverage: coverage };
  }

  return { ARRT_BLUEPRINT: ARRT_BLUEPRINT, PREMIUM_MAP: PREMIUM_MAP, readiness: readiness };
});
