/* Pure, DOM-free course logic shared by course.js (browser) and the node unit test.
 * No localStorage, no DOM — just decisions over plain values, so it is unit-testable.
 * UMD: attaches window.CourseLogic in the browser, module.exports under node. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CourseLogic = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var PASS_PCT = 80;   // mastery-check pass threshold, percent
  var CHECK_N = 8;     // questions drawn per mastery check
  var MIN_POOL = 4;    // below this many questions, a module hides its mastery check

  // Per-module status tier from plain progress counts.
  // doneCount   = completed subsections (reads + lessons + mastery)
  // subTotal    = total subsections in the module
  // quizSeen    = questions answered anywhere in the module
  // masteryAttempts / masteryPassed = mastery-check state
  function deriveModuleStatus(doneCount, subTotal, quizSeen, masteryAttempts, masteryPassed) {
    if (doneCount === 0 && quizSeen === 0 && masteryAttempts === 0) return "not-started";
    if (masteryAttempts > 0 && !masteryPassed) return "review";
    if (masteryPassed && subTotal > 0 && doneCount === subTotal) return "mastered";
    return "progress";
  }

  // Rank all module titles weakest-first by diagnostic accuracy (right/asked). A module absent
  // from perModule or with asked===0 counts as accuracy 1.0 so it does not jump ahead of
  // genuinely weak modules. Ties keep original curriculum order (stable).
  function rankModulesByDiagnostic(perModule, curriculumTitles) {
    perModule = perModule || {};
    var rows = curriculumTitles.map(function (t, i) {
      var rec = perModule[t];
      var acc = (rec && rec.asked) ? rec.right / rec.asked : 1;
      return { title: t, acc: acc, i: i };
    });
    rows.sort(function (a, b) { return a.acc - b.acc || a.i - b.i; });
    return rows.map(function (x) { return x.title; });
  }

  // First title in `order` whose status is not "mastered"; null if none (or order empty).
  function diagnosticStudyNext(order, statusByTitle) {
    order = order || [];
    statusByTitle = statusByTitle || {};
    for (var i = 0; i < order.length; i++) {
      if (statusByTitle[order[i]] !== "mastered") return order[i];
    }
    return null;
  }

  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
    rankModulesByDiagnostic: rankModulesByDiagnostic,
    diagnosticStudyNext: diagnosticStudyNext,
  };
});
