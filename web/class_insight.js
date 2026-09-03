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
      var bestOsce = null;     // best OSCE %
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
          if (lessons[a.ref] == null || a.created_at < lessons[a.ref]) lessons[a.ref] = a.created_at;
        } else if (a.kind === "mastery_check") {
          var mp = pct(a.score, a.total);
          if (mp != null && (masteredBest[a.ref] == null || mp > masteredBest[a.ref])) masteredBest[a.ref] = mp;
        } else if (a.kind === "mock_exam") {
          var ep = pct(a.score, a.total);
          if (ep != null && (bestMock == null || ep > bestMock)) bestMock = ep;
        } else if (a.kind === "osce") {
          var op = pct(a.score, a.total);
          if (op != null && (bestOsce == null || op > bestOsce)) bestOsce = op;
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
        mastered: masteredBest,   // module title -> best mastery-check % (all attempts)
        lessons: lessons,         // lesson title -> earliest completion timestamp
        topics: outTopics,
        topicsPassed: topicsPassed,
        bestPct: bestPct,
        modulesMastered: modulesMastered,
        bestMockPct: bestMock,
        bestOscePct: bestOsce,
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

  // One student × one module: "mastered" (passing mastery check), "lessons" (all
  // the module's lessons done), "started" (some lessons or a failed mastery
  // attempt), or "none". Needs a perStudent row + a module {title, lessons:[...]}.
  function moduleStatus(row, mod, passPct) {
    var mastered = row.mastered || {}, done = row.lessons || {};
    if (mastered[mod.title] != null && mastered[mod.title] >= passPct) return "mastered";
    var ls = mod.lessons || [];
    var n = 0;
    for (var i = 0; i < ls.length; i++) if (done[ls[i]] != null) n++;
    if (ls.length && n === ls.length) return "lessons";
    if (n > 0 || mastered[mod.title] != null) return "started";
    return "none";
  }

  // Rows (from perStudent) × modules grid: each student's status per module.
  function moduleMatrix(rows, modules, opts) {
    var passPct = (opts && opts.passPct) || DEFAULTS.passPct;
    return (rows || []).map(function (row) {
      return {
        studentId: row.studentId, name: row.name,
        cells: (modules || []).map(function (m) {
          return {
            module: m.title, status: moduleStatus(row, m, passPct),
            pct: (row.mastered && row.mastered[m.title] != null) ? Math.round(row.mastered[m.title]) : null,
          };
        }),
      };
    });
  }

  // Per-module class rates: how many of the roster mastered / finished the lessons.
  function moduleRates(rows, modules, opts) {
    var passPct = (opts && opts.passPct) || DEFAULTS.passPct;
    var n = (rows || []).length;
    return (modules || []).map(function (m) {
      var mastered = 0, lessonsDone = 0;
      (rows || []).forEach(function (row) {
        var s = moduleStatus(row, m, passPct);
        if (s === "mastered") mastered++;
        if (s === "mastered" || s === "lessons") lessonsDone++;
      });
      return {
        module: m.title, total: n, mastered: mastered, lessonsDone: lessonsDone,
        masteredPct: n ? Math.round((100 * mastered) / n) : 0,
        lessonsPct: n ? Math.round((100 * lessonsDone) / n) : 0,
      };
    });
  }

  // Newest-first labeled activity feed across the whole class (capped).
  function recentActivity(activity, roster, opts) {
    var limit = (opts && opts.limit) || 30;
    var passPct = (opts && opts.passPct) || DEFAULTS.passPct;
    var nameById = {};
    (roster || []).forEach(function (r) {
      nameById[r.student_id] = (r.profiles && r.profiles.display_name) || "(unnamed)";
    });
    return (activity || []).slice().sort(function (a, b) {
      return a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0;
    }).slice(0, limit).map(function (a) {
      var p = pct(a.score, a.total);
      var pt = p == null ? null : Math.round(p);
      var label;
      if (a.kind === "mastery_check") label = (p != null && p >= passPct ? "passed" : "attempted") + " module " + a.ref + (pt != null ? " — " + pt + "%" : "");
      else if (a.kind === "lesson_complete") label = "completed lesson " + a.ref;
      else if (a.kind === "quiz_attempt") label = "quiz " + a.ref + (pt != null ? " — " + pt + "%" : "");
      else if (a.kind === "mock_exam") label = "mock exam" + (pt != null ? " — " + pt + "%" : "");
      else if (a.kind === "osce") label = "OSCE " + a.ref + (pt != null ? " — " + pt + "%" : "");
      else label = a.kind + " " + a.ref;
      return { studentId: a.student_id, name: nameById[a.student_id] || "(unknown)", kind: a.kind, ref: a.ref, pct: pt, at: a.created_at, label: label };
    });
  }

  // Registry-readiness rollup for a class: map each student's per-topic best
  // accuracy through the premium topic -> ARRT category map, average within a
  // category, then weight across ATTEMPTED categories (renormalized) the same
  // way the personal readiness panel does. Formative, not predictive.
  function arrtReadiness(rows, premiumMap, blueprint) {
    var cats = (blueprint || []).map(function (b) { return { key: b.key, weight: b.weight }; });
    var students = (rows || []).map(function (r) {
      var byCat = {};
      Object.keys(r.topics || {}).forEach(function (t) {
        var cat = premiumMap && premiumMap[t];
        if (!cat) return;
        var best = r.topics[t] && r.topics[t].best;
        if (best == null) return;
        (byCat[cat] = byCat[cat] || []).push(best);
      });
      var out = {}, wsum = 0, acc = 0;
      cats.forEach(function (c) {
        var vals = byCat[c.key];
        if (vals && vals.length) {
          var m = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
          out[c.key] = Math.round(m);
          wsum += c.weight;
          acc += c.weight * m;
        } else {
          out[c.key] = null;
        }
      });
      var weakestCat = null, weakestVal = null;
      cats.forEach(function (c) {
        if (out[c.key] != null && (weakestVal == null || out[c.key] < weakestVal)) {
          weakestVal = out[c.key]; weakestCat = c.key;
        }
      });
      return { studentId: r.studentId, name: r.name, cats: out, weakestCat: weakestCat,
               overall: wsum ? Math.round(acc / wsum) : null };
    });
    var classCats = {}, cw = 0, ca = 0;
    cats.forEach(function (c) {
      var vals = students.map(function (s) { return s.cats[c.key]; })
                         .filter(function (v) { return v != null; });
      if (vals.length) {
        var m = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
        classCats[c.key] = Math.round(m);
        cw += c.weight;
        ca += c.weight * m;
      } else {
        classCats[c.key] = null;
      }
    });
    return { students: students,
             "class": { cats: classCats, overall: cw ? Math.round(ca / cw) : null } };
  }

  return {
    perStudent: perStudent, coverage: coverage, classStats: classStats, toCSV: toCSV,
    moduleStatus: moduleStatus, moduleMatrix: moduleMatrix, moduleRates: moduleRates, recentActivity: recentActivity,
    arrtReadiness: arrtReadiness,
  };
});
