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

  // Spin-echo signal magnitude at time t: the irreversible T2 decay times the
  // reversible inhomogeneity dephasing that a 180 pulse at TE/2 refocuses. Before
  // the pulse the reversible phase grows with t; after it, it unwinds toward TE,
  // so the echo at t=TE is fully refocused and peaks on the true-T2 envelope
  // (exp(-TE/T2)), while at TE/2 the signal sits on the faster T2* curve.
  function spinEchoSignal(t, T2, T2prime, TE) {
    var rev = t <= TE / 2 ? t : Math.abs(t - TE);
    return Math.exp(-t / T2) * Math.exp(-rev / T2prime);
  }

  // Ernst angle (radians): the flip angle that maximizes spoiled-GRE signal at a given TR/T1.
  function ernstAngle(TR, T1) { return Math.acos(Math.exp(-TR / T1)); }

  // Spoiled gradient-echo steady-state signal vs flip angle alpha (radians).
  function spoiledGreSignal(alpha, TR, T1) {
    var e1 = Math.exp(-TR / T1);
    return Math.sin(alpha) * (1 - e1) / (1 - Math.cos(alpha) * e1);
  }

  // Inversion-recovery longitudinal magnetization: starts at -1 after the 180, recovers to +1.
  function irMz(t, T1) { return 1 - 2 * Math.exp(-t / T1); }

  // Inversion time that nulls a tissue (irMz crosses zero).
  function nullTI(T1) { return T1 * Math.LN2; }

  // Diffusion-weighted signal: mono-exponential decay with b-value and ADC.
  function dwiSignal(b, ADC) { return Math.exp(-b * ADC); }

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

  // Apparent diffusion coefficients (mm^2/s), 1.5 T teaching approximations.
  var ADCS = [
    { id: "restricted", label: "Restricted (stroke)", adc: 0.0006 },
    { id: "normal", label: "Normal tissue", adc: 0.0010 },
    { id: "free", label: "Free water (CSF)", adc: 0.0030 },
  ];

  // Diagram id(s) shown inside each premium education card, keyed by exact title.
  var DIAGRAM_MAP = {
    "Relaxation: T1 spin-lattice and T2 spin-spin": ["t1-recovery", "t2-decay"],
    "Dephasing, T2 vs T2*, and the spin-echo refocusing pulse": ["t2-vs-t2star"],
    "TR, TE, TI, and flip angle: setting image contrast": ["tr-te-weighting"],
    "Flip angle: the Ernst angle and the SAR trade-off": ["ernst-angle"],
    "Fat suppression: STIR, spectral, Dixon and water excitation": ["ir-nulling"],
    "Diffusion in disease: stroke, abscess and cellular tumors": ["dwi-bvalue"],
  };

  return { mz: mz, mxy: mxy, t2star: t2star, spinEchoSignal: spinEchoSignal,
    ernstAngle: ernstAngle, spoiledGreSignal: spoiledGreSignal, irMz: irMz, nullTI: nullTI,
    dwiSignal: dwiSignal, classifyWeighting: classifyWeighting, sample: sample,
    TISSUES: TISSUES, ADCS: ADCS, DIAGRAM_MAP: DIAGRAM_MAP };
});
