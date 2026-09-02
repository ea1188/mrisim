/*
 * Assignments — pure logic for owner-assigned work (owner sub-project C). UMD like
 * class_insight.js: window.Assignments in the browser, module.exports under Node.
 * Builds the assignable catalog from the shared curriculum + quiz categories, and
 * derives completion from the existing `activity` table. No DOM, no network.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Assignments = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function humanize(id) {
    return String(id || "").replace(/[-_]+/g, " ")
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  // Assignable catalog, shared by the owner picker and the learner status surfaces.
  function catalog(lessonsData, quizData) {
    var curriculum = (lessonsData && lessonsData.curriculum) || [];
    var modules = [], lessons = [];
    curriculum.forEach(function (m) {
      var mlessons = (m.lessons || []).slice();
      modules.push({ ref: m.title, label: m.title, lessons: mlessons });
      mlessons.forEach(function (t) { lessons.push({ ref: t, label: t, module: m.title }); });
    });
    var cats = (quizData && quizData.categories) || [];
    var quizzes = cats.map(function (c) { return { ref: c.id, label: c.name || humanize(c.id) }; });
    return { modules: modules, lessons: lessons, quizzes: quizzes };
  }

  function _labelOf(cat, kind, ref) {
    var list = kind === "module" ? cat.modules : kind === "quiz" ? cat.quizzes : cat.lessons;
    for (var i = 0; i < (list || []).length; i++) { if (list[i].ref === ref) return list[i].label; }
    return ref;
  }
  function _moduleLessons(cat, ref) {
    var mods = (cat && cat.modules) || [];
    for (var i = 0; i < mods.length; i++) { if (mods[i].ref === ref) return mods[i].lessons || []; }
    return null;   // unknown module
  }

  // Mastery-check pass threshold (percent). Mirrors CourseLogic.PASS_PCT; kept as a
  // local constant so this module stays dependency-free.
  var MASTERY_PASS = 80;

  // Earliest created_at where the student's activity matches (kind, ref); null if never.
  function _firstDone(activity, kind, ref) {
    var at = null;
    (activity || []).forEach(function (a) {
      if (a.kind === kind && a.ref === ref && (at == null || a.created_at < at)) at = a.created_at;
    });
    return at;
  }

  // Earliest PASSING mastery_check for a module (score/total >= MASTERY_PASS); null
  // if never passed. mastery_check is logged on every attempt (pass or fail), so the
  // score must be checked, not just the event's presence.
  function _firstMasteryPass(activity, ref) {
    var at = null;
    (activity || []).forEach(function (a) {
      if (a.kind !== "mastery_check" || a.ref !== ref) return;
      var pct = a.total ? (100 * a.score / a.total) : a.score;
      if (pct >= MASTERY_PASS && (at == null || a.created_at < at)) at = a.created_at;
    });
    return at;
  }

  // Earliest of two nullable timestamps (null sinks).
  function _earliest(x, y) {
    if (x == null) return y;
    if (y == null) return x;
    return x < y ? x : y;
  }

  // done/doneAt for ONE assignment against ONE student's activity.
  function _statusOne(a, activity, cat) {
    if (a.kind === "lesson") {
      var l = _firstDone(activity, "lesson_complete", a.ref);
      return { done: l != null, doneAt: l };
    }
    if (a.kind === "quiz") {
      var q = _firstDone(activity, "quiz_attempt", a.ref);
      return { done: q != null, doneAt: q };
    }
    // Module: done when EITHER the mastery check is passed OR every lesson is
    // complete. doneAt is whichever came first.
    var masteryAt = _firstMasteryPass(activity, a.ref);
    var lessons = _moduleLessons(cat, a.ref);
    var lessonsAt = null;
    if (lessons && lessons.length) {
      var latest = null, allDone = true;
      for (var i = 0; i < lessons.length; i++) {
        var d = _firstDone(activity, "lesson_complete", lessons[i]);
        if (d == null) { allDone = false; break; }
        if (latest == null || d > latest) latest = d;
      }
      if (allDone) lessonsAt = latest;
    }
    var doneAt = _earliest(masteryAt, lessonsAt);
    return { done: doneAt != null, doneAt: doneAt };
  }

  // Order rows by due date (earliest first); no-due-date rows sink to the bottom,
  // and same-due rows fall back to label so the order is stable, not insertion order.
  function _byDueThenLabel(x, y) {
    if (x.dueAt !== y.dueAt) {
      if (!x.dueAt) return 1;
      if (!y.dueAt) return -1;
      return x.dueAt < y.dueAt ? -1 : 1;
    }
    return String(x.label).localeCompare(String(y.label));
  }

  function studentStatus(assignments, activity, cat) {
    cat = cat || { modules: [], lessons: [], quizzes: [] };
    return (assignments || []).map(function (a) {
      var s = _statusOne(a, activity, cat);
      return {
        id: a.id, kind: a.kind, ref: a.ref,
        label: _labelOf(cat, a.kind, a.ref),
        dueAt: a.due_at || null,
        done: s.done, doneAt: s.doneAt,
      };
    }).sort(_byDueThenLabel);
  }

  function classCompletion(assignments, roster, activity, cat) {
    cat = cat || { modules: [], lessons: [], quizzes: [] };
    var byStudent = {};
    (activity || []).forEach(function (a) {
      (byStudent[a.student_id] || (byStudent[a.student_id] = [])).push(a);
    });
    var members = (roster || []).map(function (r) { return r.student_id; });
    var nameById = {};
    (roster || []).forEach(function (r) {
      nameById[r.student_id] = (r.profiles && r.profiles.display_name) || "(unnamed)";
    });
    return (assignments || []).map(function (a) {
      var doneCount = 0, missing = [];
      members.forEach(function (sid) {
        if (_statusOne(a, byStudent[sid] || [], cat).done) doneCount++;
        else missing.push(nameById[sid]);
      });
      return {
        id: a.id, kind: a.kind, ref: a.ref,
        label: _labelOf(cat, a.kind, a.ref),
        dueAt: a.due_at || null,
        doneCount: doneCount, total: members.length,
        missing: missing,
      };
    }).sort(_byDueThenLabel);
  }

  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function dueLabel(dueAt, now) {
    if (!dueAt) return null;
    var d = new Date(dueAt);
    if (isNaN(d.getTime())) return null;
    var n = now ? new Date(now) : new Date();
    return { text: "due " + MON[d.getMonth()] + " " + d.getDate(), overdue: d.getTime() < n.getTime() };
  }

  return {
    catalog: catalog, studentStatus: studentStatus,
    classCompletion: classCompletion, dueLabel: dueLabel,
  };
});
