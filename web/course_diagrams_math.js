/* Pure, DOM-free physics for the course diagrams. Shared by course_diagrams.js
 * (browser) and the node unit test. No DOM, no globals beyond the export.
 * UMD: attaches window.CourseDiagramsMath in the browser, module.exports under node. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CourseDiagramsMath = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Longitudinal magnetization recovered by time t (fraction of equilibrium).
  function mz(t, T1) { return 1 - Math.exp(-t / T1); }

  // Transverse magnetization remaining at time t (fraction of the post-90 peak).
  function mxy(t, T2) { return Math.exp(-t / T2); }

  // Effective transverse decay including static field inhomogeneity (T2prime).
  function t2star(T2, T2prime) { return 1 / (1 / T2 + 1 / T2prime); }

  // TR/TE thresholds (ms), 1.5 T teaching values.
  var TR_SHORT = 700, TR_LONG = 1500, TE_SHORT = 35, TE_LONG = 80;

  function classifyWeighting(tr, te) {
    var trShort = tr < TR_SHORT, trLong = tr >= TR_LONG;
    var teShort = te < TE_SHORT, teLong = te >= TE_LONG;
    if (trShort && teShort) return "T1";
    if (trLong && teLong) return "T2";
    if (trLong && teShort) return "PD";
    return "mixed"; // short TR + long TE, or any mid-range combination
  }

  // Evenly sample fn over [0, tMax] into n+1 [t, v] points.
  function sample(fn, tMax, n) {
    var pts = [];
    for (var i = 0; i <= n; i++) {
      var t = (tMax * i) / n;
      pts.push([t, fn(t)]);
    }
    return pts;
  }

  // Representative 1.5 T relaxation constants (ms). Teaching approximations.
  var TISSUES = [
    { id: "fat", label: "Fat", t1: 260, t2: 80 },
    { id: "wm", label: "White matter", t1: 510, t2: 90 },
    { id: "gm", label: "Gray matter", t1: 760, t2: 100 },
    { id: "csf", label: "CSF", t1: 2400, t2: 1400 },
  ];

  // Diagram id(s) shown inside each premium education card, keyed by exact title.
  var DIAGRAM_MAP = {
    "What makes an image T1 weighted?": ["t1-recovery"],
    "Why is fluid bright on a T2 weighted image?": ["t2-decay"],
    "How does spin echo differ from gradient echo?": ["t2-vs-t2star"],
    "Contrast & weighting: the exam synthesis": ["tr-te-weighting"],
  };

  return { mz: mz, mxy: mxy, t2star: t2star, classifyWeighting: classifyWeighting,
    sample: sample, TISSUES: TISSUES, DIAGRAM_MAP: DIAGRAM_MAP };
});
