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

  function _num(x) { return typeof x === "number" && !isNaN(x) ? x : 0; }
  function _has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function _keysUnion(a, b) {
    var keys = {}, k; a = a || {}; b = b || {};
    for (k in a) { if (_has(a, k)) keys[k] = 1; }
    for (k in b) { if (_has(b, k)) keys[k] = 1; }
    return keys;
  }
  function _arrUnion(a, b) {
    var out = (a || []).slice(), seen = {};
    out.forEach(function (x) { seen[x] = 1; });
    (b || []).forEach(function (x) { if (!seen[x]) { seen[x] = 1; out.push(x); } });
    return out;
  }
  function _mapUnion(a, b) {
    var out = {}, k; a = a || {}; b = b || {};
    for (k in a) { if (_has(a, k)) out[k] = a[k]; }
    for (k in b) { if (_has(b, k) && !(k in out)) out[k] = b[k]; }
    return out;
  }
  function _mergeQuiz(a, b) {
    var out = {}, keys = _keysUnion(a, b), k; a = a || {}; b = b || {};
    for (k in keys) {
      var ra = a[k], rb = b[k];
      out[k] = (!rb) ? ra : (!ra) ? rb : (_num(rb.seen) > _num(ra.seen) ? rb : ra);
    }
    return out;
  }
  function _mergeMastery(a, b) {
    var out = {}, keys = _keysUnion(a, b), k; a = a || {}; b = b || {};
    for (k in keys) {
      var ra = a[k] || {}, rb = b[k] || {};
      out[k] = { passed: !!(ra.passed || rb.passed),
        bestPct: Math.max(_num(ra.bestPct), _num(rb.bestPct)),
        attempts: Math.max(_num(ra.attempts), _num(rb.attempts)),
        ts: Math.max(_num(ra.ts), _num(rb.ts)) };
    }
    return out;
  }
  function _mergeReview(a, b) {
    var out = {}, keys = _keysUnion(a, b), k; a = a || {}; b = b || {};
    for (k in keys) {
      var ra = a[k], rb = b[k];
      out[k] = (!rb) ? ra : (!ra) ? rb : (_num(rb.lastSeen) > _num(ra.lastSeen) ? rb : ra);
    }
    return out;
  }
  function _higher(a, b, field) {
    if (!a) return b; if (!b) return a;
    return _num(b[field]) > _num(a[field]) ? b : a;
  }

  // Merge two course-progress states (each keyed by the seven storage keys) so that
  // progress only ever increases. Keys present on one side pass through unchanged.
  function mergeProgress(local, remote) {
    local = local || {}; remote = remote || {};
    var out = {}, k;
    for (k in local) { if (_has(local, k)) out[k] = local[k]; }
    for (k in remote) { if (_has(remote, k) && !(k in out)) out[k] = remote[k]; }
    if ("mrisim_curriculum" in out) out.mrisim_curriculum = _arrUnion(local.mrisim_curriculum, remote.mrisim_curriculum);
    if ("mrisim_course_read_v1" in out) out.mrisim_course_read_v1 = _mapUnion(local.mrisim_course_read_v1, remote.mrisim_course_read_v1);
    if ("mrisim_course_quiz_v1" in out) out.mrisim_course_quiz_v1 = _mergeQuiz(local.mrisim_course_quiz_v1, remote.mrisim_course_quiz_v1);
    if ("mrisim_premium_topic_progress_v1" in out) out.mrisim_premium_topic_progress_v1 = _mergeQuiz(local.mrisim_premium_topic_progress_v1, remote.mrisim_premium_topic_progress_v1);
    if ("mrisim_course_exam_v1" in out) out.mrisim_course_exam_v1 = _higher(local.mrisim_course_exam_v1, remote.mrisim_course_exam_v1, "bestPct");
    if ("mrisim_course_mastery_v1" in out) out.mrisim_course_mastery_v1 = _mergeMastery(local.mrisim_course_mastery_v1, remote.mrisim_course_mastery_v1);
    if ("mrisim_course_diagnostic_v1" in out) out.mrisim_course_diagnostic_v1 = _higher(local.mrisim_course_diagnostic_v1, remote.mrisim_course_diagnostic_v1, "ts");
    if ("mrisim_course_review_v1" in out) out.mrisim_course_review_v1 = _mergeReview(local.mrisim_course_review_v1, remote.mrisim_course_review_v1);
    if ("mrisim_course_completed_v1" in out) out.mrisim_course_completed_v1 = _earlier(local.mrisim_course_completed_v1, remote.mrisim_course_completed_v1, "at");
    return out;
  }

  // Decide, at boot, which course-progress state to persist for the signed-in user,
  // given who owns the device-global local blob. The local blob carries no user id of
  // its own, so a stamped owner is passed in. Same owner => this is the user's own data
  // from another device: union it monotonically with the server copy. Different or
  // absent owner => the local blob belongs to someone else on a shared device (or is
  // untrusted): DISCARD it and use the server copy alone (or an empty slate when the
  // user has no server row yet), so account B never inherits or overwrites account A.
  // Returns { state, sameOwner }; the caller writes `state` locally and pushes it up.
  function reconcileBootProgress(storedOwner, currentUser, local, remote) {
    var sameOwner = !!currentUser && storedOwner === currentUser;
    if (sameOwner) return { state: mergeProgress(local || {}, remote || {}), sameOwner: true };
    return { state: remote || {}, sameOwner: false };
  }

  var COMPLETE_EXAM_PCT = 80;  // best-mock threshold for course completion

  // Complete = every module status is "mastered" AND the best practice exam >= COMPLETE_EXAM_PCT.
  function isCourseComplete(statuses, bestExamPct) {
    if (!statuses || !statuses.length) return false;
    for (var i = 0; i < statuses.length; i++) { if (statuses[i] !== "mastered") return false; }
    return typeof bestExamPct === "number" && bestExamPct >= COMPLETE_EXAM_PCT;
  }
  // Keep the object with the smaller field value (null-safe; one-sided returns the present one).
  function _earlier(a, b, field) {
    if (!a) return b; if (!b) return a;
    return _num(a[field]) <= _num(b[field]) ? a : b;
  }

  // Non-mastered module titles in recommended study order: diagnostic weakest-first where available
  // (order = the diagnostic order array or null), then any remaining non-mastered in module order.
  // modules = [{ title, status }].
  function remainingStudyOrder(modules, order) {
    modules = modules || [];
    var statusByTitle = {}, remaining = [];
    modules.forEach(function (m) { statusByTitle[m.title] = m.status; if (m.status !== "mastered") remaining.push(m.title); });
    if (!order || !order.length) return remaining;
    var out = [], seen = {};
    order.forEach(function (t) { if (statusByTitle[t] && statusByTitle[t] !== "mastered") { out.push(t); seen[t] = 1; } });
    remaining.forEach(function (t) { if (!seen[t]) out.push(t); });
    return out;
  }

  // Weeks until target and modules/week needed to finish `remaining` modules by targetMs.
  // Returns null when nothing remains or the target is not in the future.
  function pacePerWeek(remaining, targetMs, nowMs) {
    if (!remaining || remaining <= 0) return null;
    var ms = targetMs - nowMs;
    if (!(ms > 0)) return null;
    var weeks = Math.max(1, Math.ceil(ms / (7 * 86400000)));
    return { weeks: weeks, perWeek: Math.ceil(remaining / weeks) };
  }

  // The first lesson title of a module (for the study rail's "open in simulator"
  // deep-link), or null when the module has no lessons.
  function firstLesson(mod) {
    return (mod && mod.lessons && mod.lessons.length) ? mod.lessons[0] : null;
  }

  // Previous/next module in curriculum order (by title), null at either end.
  function topicNav(curriculum, mod) {
    var i = -1;
    for (var k = 0; k < curriculum.length; k++) {
      if (curriculum[k].title === (mod && mod.title)) { i = k; break; }
    }
    if (i < 0) return { prev: null, next: null };
    return {
      prev: i > 0 ? curriculum[i - 1] : null,
      next: i < curriculum.length - 1 ? curriculum[i + 1] : null,
    };
  }

  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    firstLesson: firstLesson, topicNav: topicNav,
    deriveModuleStatus: deriveModuleStatus,
    rankModulesByDiagnostic: rankModulesByDiagnostic,
    diagnosticStudyNext: diagnosticStudyNext,
    reviewOnMiss: reviewOnMiss,
    reviewOnCorrect: reviewOnCorrect,
    dueCount: dueCount,
    mergeProgress: mergeProgress,
    reconcileBootProgress: reconcileBootProgress,
    isCourseComplete: isCourseComplete,
    remainingStudyOrder: remainingStudyOrder, pacePerWeek: pacePerWeek,
  };
});
