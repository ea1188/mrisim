/* OSCE rubric engine: grades a submitted protocol against a scenario from
 * web/osce.json. Pure module, no DOM, no fetch; UMD so the browser planner and
 * node --test share it.
 *
 * grade(scenario, submission, regions) ->
 *   { criteria: [{id, label, verdict, points, max, feedback}], points, max, pct }
 *
 * submission: [{preset, acquired, params, plan}] — one entry per queue item.
 *   params: engine params (TR, TE, TI, b_value, n_slices, slice_thickness,
 *           slice_gap, acq3d, n_partitions).
 *   plan:   {orientation, slice, tilt, rot, inplane_off, fov_pct} — slice may
 *           be null (the planner's "mid" default).
 * regions: web/osce.json's regions map ({shape:[nz,ny,nx], voxel_mm}).
 *
 * Geometry mirrors the engine exactly: slice indexes the orientation's fixed
 * scout axis (axial 0, coronal 1, sagittal 2, oblique.scout_band's convention);
 * slab half-coverage is (n*thickness + (n-1)*gap)/2 mm over voxel_mm, matching
 * web_adapter.render_scout. Every numeric target in the scenario was derived
 * from atlas geometry by scripts/derive_osce_targets.py, never hand-tuned.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.OsceRubric = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var ACQ_AXIS = { axial: 0, coronal: 1, sagittal: 2 };

  function findAcquired(submission, preset) {
    for (var i = submission.length - 1; i >= 0; i--) {
      var it = submission[i];
      if (it.preset === preset && it.acquired) return it;
    }
    return null;
  }

  function inBand(v, band) { return v >= band[0] && v <= band[1]; }

  // Covered range along the acquisition axis, in voxels: centre from the plan's
  // slice (or the adapter's mid default), half-extent from the slab maths.
  function coveredRange(item, axis, region) {
    var p = item.params || {}, pl = item.plan || {};
    var shape = region.shape;
    var c = (pl.slice != null && ACQ_AXIS[pl.orientation] === axis)
      ? pl.slice : Math.floor(shape[axis] / 2);
    var halfMm;
    if (p.acq3d) halfMm = ((p.n_partitions || 16) * region.voxel_mm) / 2;
    else {
      var n = Math.max(1, Math.min(32, p.n_slices || 1));
      var thk = p.slice_thickness || 5, gap = p.slice_gap || 0;
      halfMm = (n * thk + Math.max(0, n - 1) * gap) / 2;
    }
    var halfVox = halfMm / region.voxel_mm;
    return [c - halfVox, c + halfVox];
  }

  var GRADERS = {
    acquired: function (c, submission) {
      return findAcquired(submission, c.preset) ? "pass" : "fail";
    },
    not_acquired: function (c, submission) {
      return findAcquired(submission, c.preset) ? "fail" : "pass";
    },
    angulation: function (c, submission) {
      var it = findAcquired(submission, c.preset);
      if (!it || !it.plan) return "fail";
      var t = c.target;
      var err = Math.max(Math.abs((it.plan.tilt || 0) - t.tilt_deg),
                         Math.abs((it.plan.rot || 0) - t.rot_deg));
      if (err <= t.full_deg) return "pass";
      if (err <= t.partial_deg) return "partial";
      return "fail";
    },
    slice: function (c, submission, regions, scenario) {
      var it = findAcquired(submission, c.preset);
      if (!it || !it.plan) return "fail";
      var region = regions[scenario.region], t = c.target;
      var sl = it.plan.slice != null ? it.plan.slice
        : Math.floor(region.shape[t.axis] / 2);
      return sl >= t.lo && sl <= t.hi ? "pass" : "fail";
    },
    coverage: function (c, submission, regions, scenario) {
      var it = findAcquired(submission, c.preset);
      if (!it) return "fail";
      var t = c.target;
      var cov = coveredRange(it, t.axis, regions[scenario.region]);
      if (cov[0] <= t.full[0] && cov[1] >= t.full[1]) return "pass";
      if (cov[0] <= t.partial[0] && cov[1] >= t.partial[1]) return "partial";
      return "fail";
    },
    param: function (c, submission) {
      var it = findAcquired(submission, c.preset);
      if (!it || !it.params) return "fail";
      var v = it.params[c.param];
      if (v == null || !isFinite(v)) return "fail";
      var band = c.band || c.target;   // authored band, or derived (null_ti)
      if (inBand(v, band.full)) return "pass";
      if (inBand(v, band.partial)) return "partial";
      return "fail";
    },
  };

  function grade(scenario, submission, regions) {
    var out = [], points = 0, max = 0;
    scenario.criteria.forEach(function (c) {
      var fn = GRADERS[c.type];
      var verdict = fn ? fn(c, submission, regions, scenario) : "fail";
      var got = verdict === "pass" ? c.points
        : verdict === "partial" ? Math.ceil(c.points / 2) : 0;
      points += got; max += c.points;
      var fb = c.feedback[verdict] || c.feedback.fail;
      out.push({ id: c.id, label: c.label, verdict: verdict,
                 points: got, max: c.points, feedback: fb });
    });
    return { criteria: out, points: points, max: max,
             pct: max ? Math.round(100 * points / max) : 0 };
  }

  return { grade: grade, ACQ_AXIS: ACQ_AXIS };
});
