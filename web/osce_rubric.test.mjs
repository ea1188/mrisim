// Rubric fixtures run against the REAL generated targets (web/osce.json), so a
// regeneration that shifts a band or angle re-validates every verdict here.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const Rubric = require("./osce_rubric.js");
const DATA = JSON.parse(readFileSync(new URL("./osce.json", import.meta.url), "utf8"));

const byId = Object.fromEntries(DATA.scenarios.map((s) => [s.id, s]));
const R = DATA.regions;

function verdicts(result) {
  return Object.fromEntries(result.criteria.map((c) => [c.id, c.verdict]));
}

// One queue item: acquired series with params/plan defaulted sensibly.
function item(preset, orientation, over = {}) {
  return {
    preset, acquired: true,
    params: { n_slices: 15, slice_thickness: 5, slice_gap: 0, ...(over.params || {}) },
    plan: { orientation, slice: null, tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100, ...(over.plan || {}) },
  };
}

// --- lumbar radiculopathy --------------------------------------------------
const LUMBAR = byId["lumbar-radiculopathy"];
const T = Object.fromEntries(LUMBAR.criteria.filter((c) => c.target).map((c) => [c.id, c.target]));

function lumbarIdeal() {
  return [
    item("Spine T1 Sagittal", "sagittal", { params: { n_slices: 20, slice_thickness: 8 } }),
    item("Spine T2 Sagittal", "sagittal", { params: { n_slices: 20, slice_thickness: 8 } }),
    item("Spine STIR", "sagittal", { params: { TI: 265 } }),
    item("Spine Axial T2", "axial", {
      params: { n_slices: 26, slice_thickness: 7 },
      plan: { tilt: Math.round(T["ax-angle"].tilt_deg), slice: 82 },
    }),
  ];
}

test("lumbar: the ideal protocol earns full credit on every criterion", () => {
  const r = Rubric.grade(LUMBAR, lumbarIdeal(), R);
  const v = verdicts(r);
  for (const c of LUMBAR.criteria) assert.equal(v[c.id], "pass", c.id);
  assert.equal(r.pct, 100);
});

test("lumbar: unangled axial is partial, opposite tilt fails", () => {
  // target 8.2 with bands 5/10: tilt 0 is 8.2 off (partial), tilt -5 is 13.2 off (fail)
  const sub = lumbarIdeal();
  sub[3].plan.tilt = 0;
  assert.equal(verdicts(Rubric.grade(LUMBAR, sub, R))["ax-angle"], "partial");
  sub[3].plan.tilt = -5;
  assert.equal(verdicts(Rubric.grade(LUMBAR, sub, R))["ax-angle"], "fail");
});

test("lumbar: default mid slice misses L4-L5 (stack must move down)", () => {
  const sub = lumbarIdeal();
  sub[3].plan.slice = null;   // planner default = mid = 111, band is 77..88
  const v = verdicts(Rubric.grade(LUMBAR, sub, R));
  assert.equal(v["ax-slice"], "fail");
});

test("lumbar: a small centred stack covers L4-L5 only (partial coverage)", () => {
  const sub = lumbarIdeal();
  sub[3].params = { n_slices: 12, slice_thickness: 5 };   // 30mm slab
  const v = verdicts(Rubric.grade(LUMBAR, sub, R));
  assert.equal(v["ax-coverage"], "partial");
  sub[3].params = { n_slices: 4, slice_thickness: 5 };    // 10mm slab
  assert.equal(verdicts(Rubric.grade(LUMBAR, sub, R))["ax-coverage"], "fail");
});

test("lumbar: skipping the axial fails it and everything graded on it", () => {
  const sub = lumbarIdeal().slice(0, 3);
  const v = verdicts(Rubric.grade(LUMBAR, sub, R));
  assert.equal(v["acq-ax-t2"], "fail");
  assert.equal(v["ax-angle"], "fail");
  assert.equal(v["ax-slice"], "fail");
  assert.equal(v["ax-coverage"], "fail");
  assert.equal(v["acq-t1-sag"], "pass");   // the rest is unaffected
});

test("lumbar: acquiring post-Gd loses the contrast-stewardship points", () => {
  const sub = lumbarIdeal().concat([item("Spine T1 Post-Gd", "sagittal")]);
  const v = verdicts(Rubric.grade(LUMBAR, sub, R));
  assert.equal(v["no-gd"], "fail");
});

test("lumbar: STIR TI bands (derived from tissue_db fat T1)", () => {
  const sub = lumbarIdeal();
  const cases = [[265, "pass"], [200, "partial"], [150, "fail"], [400, "fail"]];
  for (const [ti, want] of cases) {
    sub[2].params.TI = ti;
    assert.equal(verdicts(Rubric.grade(LUMBAR, sub, R))["stir-ti"], want, `TI ${ti}`);
  }
});

test("lumbar: narrow sagittal stack clips the foramina", () => {
  const sub = lumbarIdeal();
  sub[1].params = { n_slices: 3, slice_thickness: 4 };    // 12mm midline-only
  assert.equal(verdicts(Rubric.grade(LUMBAR, sub, R))["sag-coverage"], "fail");
  sub[1].params = { n_slices: 12, slice_thickness: 5 };   // 60mm: partial band only
  assert.equal(verdicts(Rubric.grade(LUMBAR, sub, R))["sag-coverage"], "partial");
});

// --- knee internal derangement ----------------------------------------------
const KNEE = byId["knee-internal-derangement"];

function kneeIdeal() {
  return [
    item("Knee T2 FS Axial", "axial"),
    item("Knee PD FS Coronal", "coronal", { params: { TE: 30 } }),
    item("Knee PD Coronal", "coronal", { params: { TE: 30 } }),
    item("Knee PD FSE", "sagittal", {
      params: { n_slices: 28, slice_thickness: 3.5 },
      plan: { slice: 115 },
    }),
    item("Knee T2 Fat-Sat", "sagittal"),
  ];
}

test("knee: the ideal protocol earns full credit", () => {
  const r = Rubric.grade(KNEE, kneeIdeal(), R);
  for (const c of KNEE.criteria) assert.equal(verdicts(r)[c.id], "pass", c.id);
});

test("knee: PD echo time drifting long loses PD weighting", () => {
  const sub = kneeIdeal();
  const cases = [[30, "pass"], [8, "pass"], [50, "partial"], [70, "fail"]];
  for (const [te, want] of cases) {
    sub[1].params.TE = te;
    assert.equal(verdicts(Rubric.grade(KNEE, sub, R))["pd-te"], want, `TE ${te}`);
  }
});

test("knee: skipping the plain PD is called out", () => {
  const sub = kneeIdeal().filter((it) => it.preset !== "Knee PD Coronal");
  assert.equal(verdicts(Rubric.grade(KNEE, sub, R))["acq-pd-nofs"], "fail");
});

// --- brain first seizure ------------------------------------------------------
const BRAIN = byId["brain-first-seizure"];

function brainIdeal() {
  return [
    item("Brain T1 SE", "axial"),
    item("Brain T2 SE", "axial"),
    item("Brain FLAIR", "axial", { params: { TI: 2548 } }),
    item("DWI Stroke", "axial", { params: { b_value: 1000 } }),
  ];
}

test("brain: the ideal seizure protocol earns full credit", () => {
  const r = Rubric.grade(BRAIN, brainIdeal(), R);
  for (const c of BRAIN.criteria) assert.equal(verdicts(r)[c.id], "pass", c.id);
});

test("brain: FLAIR TI off the CSF null degrades and then fails", () => {
  const sub = brainIdeal();
  const cases = [[2548, "pass"], [2000, "partial"], [3300, "fail"], [265, "fail"]];
  for (const [ti, want] of cases) {
    sub[2].params.TI = ti;
    assert.equal(verdicts(Rubric.grade(BRAIN, sub, R))["flair-ti"], want, `TI ${ti}`);
  }
});

test("brain: FLAIR TI is graded against the SUBMITTED TR", () => {
  const sub = brainIdeal();
  sub[2].params.TR = 6000;
  sub[2].params.TI = 2068;            // correctly re-derived null for TR 6000
  assert.equal(verdicts(Rubric.grade(BRAIN, sub, R))["flair-ti"], "pass");
  sub[2].params.TI = 2548;            // stale TI from the TR 9000 preset
  assert.equal(verdicts(Rubric.grade(BRAIN, sub, R))["flair-ti"], "partial");
});

test("brain: DWI b-value bands", () => {
  const sub = brainIdeal();
  const cases = [[1000, "pass"], [600, "partial"], [400, "fail"], [2500, "fail"]];
  for (const [b, want] of cases) {
    sub[3].params.b_value = b;
    assert.equal(verdicts(Rubric.grade(BRAIN, sub, R))["dwi-b"], want, `b ${b}`);
  }
});

test("brain: skipping FLAIR costs the highest-weight criterion", () => {
  const sub = brainIdeal().filter((it) => it.preset !== "Brain FLAIR");
  const r = Rubric.grade(BRAIN, sub, R);
  assert.equal(verdicts(r)["acq-flair"], "fail");
  assert.equal(verdicts(r)["flair-ti"], "fail");
});

// --- scoring mechanics ---------------------------------------------------------
test("partial credit is ceil(points/2) and pct reflects the total", () => {
  const sub = lumbarIdeal();
  sub[3].plan.tilt = 0;                       // 3-point angulation -> partial = 2
  const r = Rubric.grade(LUMBAR, sub, R);
  const ang = r.criteria.find((c) => c.id === "ax-angle");
  assert.equal(ang.points, 2);
  assert.equal(ang.max, 3);
  assert.equal(r.points, r.max - 1);
  assert.equal(r.pct, Math.round(100 * r.points / r.max));
});

test("every criterion carries feedback text for its verdict", () => {
  const r = Rubric.grade(LUMBAR, [], R);      // empty submission: everything fails
  for (const c of r.criteria) {
    assert.equal(typeof c.feedback, "string");
    assert.ok(c.feedback.length > 20, c.id);
  }
});
