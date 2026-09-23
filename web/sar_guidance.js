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
    var out = { over: over, limit: limit, ratio: sar / limit, maxSafeFa: null, minSafeTr: null,
      maxSafeSlices: null, lowerSeqOptions: [] };
    if (!over) return out;
    // Slice count: SAR scales linearly with the stack, so the largest stack
    // that fits under the limit is floor(n * limit/sar). Only meaningful when
    // a multi-slice stack is prescribed.
    var n = Number(opts.n_slices) || 0;
    if (n > 1) {
      var ns = Math.floor(n * (limit / sar));
      if (ns >= 1 && ns < n) out.maxSafeSlices = ns;
    }

    // Flip angle: only the excitation term scales with FA² — the refocusing
    // train and inversion are fixed cost (mirrors estimate_sar). When the
    // fixed part alone keeps SAR over the limit, no flip reduction can help
    // and no advice is offered (true on a real console for TSE/IR).
    if (fa > 0) {
      var fa2 = Math.pow(fa / 90, 2);
      var train = Math.max(1, Number(opts.etl) ||
        ((seq === "FSE / TSE" || seq === "Inversion Recovery") ? 16 : 1));
      var refoc = train > 1 ? train * Math.pow(150 / 90, 2) : 4.0;
      var fixed = 0;
      if (seq === "Spin Echo" || seq === "FSE / TSE" || seq === "Diffusion (DWI)") fixed = refoc;
      else if (seq === "Inversion Recovery") fixed = 4.0 + refoc;
      var wCur = fa2 + fixed;
      var fa2Target = wCur * (limit / sar) - fixed;
      out.maxSafeFa = fa2Target > 0
        ? clamp(Math.floor(90 * Math.sqrt(fa2Target)), 1, Math.max(1, Math.floor(fa) - 1))
        : null;
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
