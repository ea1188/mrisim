/*
 * Course feedback — pure logic for the end-of-course survey. UMD like
 * assignments.js: window.CourseFeedback in the browser, module.exports under Node.
 * Validates the raw form values and builds the anonymous row inserted into the
 * Supabase `course_feedback` table. No DOM, no network, no identity.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.CourseFeedback = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var COHORT = "2026-08";
  var TEXT_CAP = 2000;

  // The 10 core curriculum modules, in order. Stored as a stable key (m1..m10) so
  // re-labeling a module never breaks stored data; label is for the dropdown only.
  var MODULES = [
    { key: "m1", label: "1 · What an MRI image is" },
    { key: "m2", label: "2 · Where contrast comes from" },
    { key: "m3", label: "3 · Making a tissue disappear" },
    { key: "m4", label: "4 · Reading pathology" },
    { key: "m5", label: "5 · Image quality & speed" },
    { key: "m6", label: "6 · How the image is built" },
    { key: "m7", label: "7 · 3D imaging & reconstruction" },
    { key: "m8", label: "8 · Flow, function & artifacts" },
    { key: "m9", label: "9 · Putting it together" },
    { key: "m10", label: "10 · Safety & patient care" },
  ];
  var MODULE_KEYS = MODULES.map(function (m) { return m.key; }).concat("none");

  // field -> [min, max] for the numeric questions.
  var NUMERIC = {
    recommend: [0, 10],
    prepared: [1, 5],
    useful_simulator: [1, 5],
    useful_planner: [1, 5],
    useful_quiz: [1, 5],
    useful_lessons: [1, 5],
    useful_reference: [1, 5],
  };
  var ENUMS = {
    pace: ["too_slow", "about_right", "too_fast"],
    workload: ["too_light", "about_right", "too_heavy"],
  };
  var TEXT_FIELDS = ["helped_most", "improve", "other"];

  function isBlank(v) { return v === undefined || v === null || v === ""; }

  function err(msg) { return { ok: false, error: msg }; }

  // Validate the raw form values and produce the row to insert. Unanswered fields
  // are omitted entirely (so they store as NULL). Returns {ok, payload} or
  // {ok:false, error}. cohort override is for tests / future classes.
  function buildPayload(raw, opts) {
    raw = raw || {};
    var payload = { cohort: (opts && opts.cohort) || COHORT };
    var answered = false;

    for (var f in NUMERIC) {
      if (!Object.prototype.hasOwnProperty.call(NUMERIC, f) || isBlank(raw[f])) continue;
      var n = Number(raw[f]);
      if (!Number.isInteger(n) || n < NUMERIC[f][0] || n > NUMERIC[f][1]) {
        return err("Please pick a valid value for " + f + ".");
      }
      payload[f] = n; answered = true;
    }

    for (var e in ENUMS) {
      if (!Object.prototype.hasOwnProperty.call(ENUMS, e) || isBlank(raw[e])) continue;
      if (ENUMS[e].indexOf(raw[e]) === -1) return err("Please pick a valid value for " + e + ".");
      payload[e] = raw[e]; answered = true;
    }

    if (!isBlank(raw.hardest_module)) {
      if (MODULE_KEYS.indexOf(raw.hardest_module) === -1) return err("Please pick a valid module.");
      payload.hardest_module = raw.hardest_module; answered = true;
    }

    TEXT_FIELDS.forEach(function (t) {
      if (isBlank(raw[t])) return;
      var s = String(raw[t]).trim();
      if (!s) return;
      payload[t] = s.slice(0, TEXT_CAP);
      answered = true;
    });

    if (!answered) return err("Please answer at least one question before submitting.");
    return { ok: true, payload: payload };
  }

  return {
    COHORT: COHORT,
    TEXT_CAP: TEXT_CAP,
    MODULES: MODULES,
    MODULE_KEYS: MODULE_KEYS,
    NUMERIC: NUMERIC,
    ENUMS: ENUMS,
    TEXT_FIELDS: TEXT_FIELDS,
    buildPayload: buildPayload,
  };
});
