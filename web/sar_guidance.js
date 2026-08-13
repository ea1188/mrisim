/*
 * SAR guidance — pure logic for the simulator's SAR-limit warning. UMD like
 * feedback.js / assignments.js: window.SarGuidance in the browser, module.exports
 * under Node. Given the CURRENT estimated head SAR and the acquisition params, it
 * returns the concrete parameter changes that each, on their own, bring SAR back
 * under the limit. Works from sar_head directly so it stays field-aware and can
 * never drift from the number the engine displays. No DOM, no network.
 *
 * SAR ∝ flip_angle² · (1/TR) · sequence_factor, so scaling FA by √(limit/sar) or
 * TR by sar/limit lands exactly on the limit.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SarGuidance = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var LIMIT = 3.2;              // FDA head-SAR limit (W/kg), matches estimate_sar
  var TR_CEILING = 10000;       // don't advise a TR beyond this (impractical)

  // Relative RF factor per sequence — mirrors presets.estimate_sar's seq_factors,
  // keyed by the web display names. Unlisted sequences default to 1.0.
  var SEQ_FACTORS = {
    "Spin Echo": 1.5,
    "Inversion Recovery": 2.0,
    "Diffusion (DWI)": 1.5,
    "Gradient Echo": 0.5,
    "Echo Planar (EPI)": 0.5,
  };
  // Low-SAR sequences we're willing to suggest switching TO, lowest first.
  var LOWER_SEQ_CANDIDATES = ["Gradient Echo", "Echo Planar (EPI)"];

  function factorOf(seq) {
    return Object.prototype.hasOwnProperty.call(SEQ_FACTORS, seq) ? SEQ_FACTORS[seq] : 1.0;
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // opts: { flip_angle, TR, sequence, sar_head, limit? }
  function sarGuidance(opts) {
    opts = opts || {};
    var limit = opts.limit || LIMIT;
    var sar = Number(opts.sar_head) || 0;
    var fa = Number(opts.flip_angle) || 0;
    var tr = Number(opts.TR) || 0;
    var seq = opts.sequence;

    var over = sar > limit;
    var out = { over: over, limit: limit, ratio: sar / limit, maxSafeFa: null, minSafeTr: null, lowerSeqOptions: [] };
    if (!over) return out;

    // Flip angle: scale by √(limit/sar); clamp to a usable integer below current FA.
    if (fa > 0) {
      var target = Math.round(fa * Math.sqrt(limit / sar));
      out.maxSafeFa = clamp(target, 1, Math.max(1, Math.floor(fa) - 1));
    }
    // TR: scale by sar/limit; only offer if it stays practical.
    if (tr > 0) {
      var trTarget = Math.ceil(tr * (sar / limit));
      out.minSafeTr = trTarget <= TR_CEILING ? trTarget : null;
    }
    // Sequence: suggest lower-SAR sequences whose factor change alone gets under.
    var fCur = factorOf(seq);
    LOWER_SEQ_CANDIDATES.forEach(function (cand) {
      if (cand === seq) return;
      var fNew = factorOf(cand);
      if (fNew < fCur && sar * (fNew / fCur) <= limit) out.lowerSeqOptions.push(cand);
    });
    return out;
  }

  return { LIMIT: LIMIT, TR_CEILING: TR_CEILING, SEQ_FACTORS: SEQ_FACTORS, sarGuidance: sarGuidance };
});
