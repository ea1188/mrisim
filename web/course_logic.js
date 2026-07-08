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

  var DAY_MS = 86400000;
  var REVIEW_INTERVALS_DAYS = [1, 3, 7];   // days added at box 1, 2, 3

  // A missed question: reset to box 0, due immediately, misses incremented.
  function reviewOnMiss(entry, now) {
    return { box: 0, due: now, misses: (entry && entry.misses ? entry.misses : 0) + 1, lastSeen: now };
  }

  // A correct answer during a review session: advance the box and widen the due date;
  // return null once it graduates past the last interval (remove it from the queue).
  function reviewOnCorrect(entry, now) {
    var box = (entry && entry.box ? entry.box : 0) + 1;
    if (box > REVIEW_INTERVALS_DAYS.length) return null;
    return { box: box, due: now + REVIEW_INTERVALS_DAYS[box - 1] * DAY_MS,
      misses: (entry && entry.misses ? entry.misses : 0), lastSeen: now };
  }

  // How many entries in the review map are due now.
  function dueCount(map, now) {
    var n = 0, k;
    for (k in map) { if (Object.prototype.hasOwnProperty.call(map, k) && map[k] && map[k].due <= now) n += 1; }
    return n;
  }

  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
    rankModulesByDiagnostic: rankModulesByDiagnostic,
    diagnosticStudyNext: diagnosticStudyNext,
    reviewOnMiss: reviewOnMiss,
    reviewOnCorrect: reviewOnCorrect,
    dueCount: dueCount,
  };
});
