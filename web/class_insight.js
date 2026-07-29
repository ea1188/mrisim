/*
 * ClassInsight — pure aggregation of formative class activity for the owner
 * dashboard. UMD like join_link.js: window.ClassInsight in the browser,
 * module.exports under Node. No DOM, no network.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ClassInsight = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var DEFAULTS = { passPct: 80, struggleAttempts: 2 };

  function pct(score, total) { return total ? (100 * score) / total : null; }

  function perStudent(roster, activity, opts) {
    opts = opts || {};
    var passPct = opts.passPct == null ? DEFAULTS.passPct : opts.passPct;
    var struggleAttempts = opts.struggleAttempts == null ? DEFAULTS.struggleAttempts : opts.struggleAttempts;

    var byStudent = {};
    (activity || []).forEach(function (a) {
      (byStudent[a.student_id] || (byStudent[a.student_id] = [])).push(a);
    });

    return (roster || []).map(function (r) {
      var acts = byStudent[r.student_id] || [];
      var topics = {};   // ref -> { best, latest, latestAt, attempts }
      var lessons = {};
      var masteredBest = {};   // premium module title -> best mastery-check %
      var bestMock = null;     // best mock-exam %
      var quizRuns = 0;
      var lastActive = null;

      acts.forEach(function (a) {
        if (!lastActive || a.created_at > lastActive) lastActive = a.created_at;
        if (a.kind === "quiz_attempt") {
          quizRuns++;
          var t = topics[a.ref] || (topics[a.ref] = { best: null, latest: null, latestAt: null, attempts: 0 });
          t.attempts++;
          var p = pct(a.score, a.total);
          if (p != null) {
            if (t.best == null || p > t.best) t.best = p;
            if (t.latestAt == null || a.created_at > t.latestAt) { t.latest = p; t.latestAt = a.created_at; }
          }
        } else if (a.kind === "lesson_complete") {
          lessons[a.ref] = true;
        } else if (a.kind === "mastery_check") {
          var mp = pct(a.score, a.total);
          if (mp != null && (masteredBest[a.ref] == null || mp > masteredBest[a.ref])) masteredBest[a.ref] = mp;
        } else if (a.kind === "mock_exam") {
          var ep = pct(a.score, a.total);
          if (ep != null && (bestMock == null || ep > bestMock)) bestMock = ep;
        }
      });

      var outTopics = {};
      var bestPct = null, weakestTopic = null, weakestBest = null, topicsPassed = 0, struggling = false;
      Object.keys(topics).forEach(function (k) {
        var t = topics[k];
        outTopics[k] = { best: t.best, latest: t.latest, attempts: t.attempts };
        if (t.best != null) {
          if (bestPct == null || t.best > bestPct) bestPct = t.best;
          if (weakestBest == null || t.best < weakestBest) { weakestBest = t.best; weakestTopic = k; }
          if (t.best >= passPct) topicsPassed++;
          else if (t.attempts >= struggleAttempts) struggling = true;
        }
      });

      var modulesMastered = 0;
      Object.keys(masteredBest).forEach(function (k) { if (masteredBest[k] >= passPct) modulesMastered++; });

      return {
        studentId: r.student_id,
        name: (r.profiles && r.profiles.display_name) || "(unnamed)",
        quizRuns: quizRuns,
        lessonsDone: Object.keys(lessons).length,
        topics: outTopics,
        topicsPassed: topicsPassed,
        bestPct: bestPct,
        modulesMastered: modulesMastered,
        bestMockPct: bestMock,
        weakestTopic: weakestTopic,
        lastActive: lastActive,
        struggling: struggling,
      };
    });
  }

  function coverage(row, totals) {
    var denom = ((totals && totals.lessons) || 0) + ((totals && totals.topics) || 0);
    if (!denom) return 0;
    return Math.round((100 * (row.lessonsDone + row.topicsPassed)) / denom);
  }

  function mean(arr) {
    return arr.length ? Math.round(arr.reduce(function (a, b) { return a + b; }, 0) / arr.length) : null;
  }

  function classStats(rows, totals) {
    rows = rows || [];
    var bests = rows.map(function (r) { return r.bestPct; }).filter(function (v) { return v != null; });
    var mocks = rows.map(function (r) { return r.bestMockPct; }).filter(function (v) { return v != null; });
    var covs = rows.map(function (r) { return coverage(r, totals); });
    var agg = {};
    rows.forEach(function (r) {
      Object.keys(r.topics).forEach(function (k) {
        var b = r.topics[k].best;
        if (b == null) return;
        (agg[k] || (agg[k] = [])).push(b);
      });
    });
    var weakestTopics = Object.keys(agg).map(function (k) {
      return { topic: k, avgBest: mean(agg[k]) };
    }).sort(function (a, b) { return a.avgBest - b.avgBest; }).slice(0, 3);
    return {
      members: rows.length,
      avgBestPct: bests.length ? mean(bests) : null,
      avgMockPct: mocks.length ? mean(mocks) : null,
      avgCoverage: covs.length ? mean(covs) : 0,
      weakestTopics: weakestTopics,
    };
  }

  function csvCell(v) {
    v = v == null ? "" : String(v);
    return '"' + v.replace(/"/g, '""') + '"';
  }

  function toCSV(rows, totals) {
    var header = ["Member", "Practice coverage %", "Best score %", "Modules mastered", "Best mock %", "Lessons done", "Weakest topic", "Struggling", "Last active"];
    var lines = [header.map(csvCell).join(",")];
    (rows || []).forEach(function (r) {
      lines.push([
        r.name,
        coverage(r, totals),
        r.bestPct == null ? "" : Math.round(r.bestPct),
        r.modulesMastered,
        r.bestMockPct == null ? "" : Math.round(r.bestMockPct),
        r.lessonsDone,
        r.weakestTopic || "",
        r.struggling ? "yes" : "no",
        r.lastActive || "",
      ].map(csvCell).join(","));
    });
    return lines.join("\n");
  }

  return { perStudent: perStudent, coverage: coverage, classStats: classStats, toCSV: toCSV };
});
