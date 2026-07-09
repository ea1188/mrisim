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

  function isAttempted(entry) {
    return !!entry && typeof entry.total === "number" && entry.total > 0;
  }

  // progress = mrisim_quiz_progress_v1: { categoryId: { best, total, runs } }
  function readiness(progress) {
    var prog = progress || {};
    var categories = ARRT_BLUEPRINT.map(function (c) {
      var right = 0, asked = 0, attempted = 0;
      c.members.forEach(function (m) {
        var e = prog[m];
        if (!isAttempted(e)) return;
        attempted += 1;
        right += (typeof e.best === "number" ? e.best : 0);
        asked += e.total;
      });
      return {
        key: c.key, name: c.name, scored: c.scored, weight: c.weight, note: c.note || null,
        accuracy: asked > 0 ? right / asked : null,
        coverage: c.members.length ? attempted / c.members.length : 0,
        attempted: attempted, memberCount: c.members.length,
      };
    });
    var projected = 0, coverage = 0;
    categories.forEach(function (c) {
      projected += (c.accuracy || 0) * c.weight;
      coverage += c.coverage * c.weight;
    });
    return { categories: categories, projected: projected, coverage: coverage };
  }

  return { ARRT_BLUEPRINT: ARRT_BLUEPRINT, readiness: readiness };
});
