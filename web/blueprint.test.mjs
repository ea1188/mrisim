import { test } from "node:test";
import assert from "node:assert/strict";
import B from "./blueprint.js";

const KNOWN_CATEGORIES = [
  "sequences", "pathology", "perfusion", "artifacts",
  "anatomy", "image-quality", "safety", "patient-care",
];

test("blueprint integrity: scored sums to 200, weights to 1.0, 8 categories mapped once", () => {
  const scored = B.ARRT_BLUEPRINT.reduce((s, c) => s + c.scored, 0);
  assert.equal(scored, 200);
  const weight = B.ARRT_BLUEPRINT.reduce((s, c) => s + c.weight, 0);
  assert.ok(Math.abs(weight - 1.0) < 1e-9, `weights sum to ${weight}`);
  const members = B.ARRT_BLUEPRINT.flatMap((c) => c.members).sort();
  assert.deepEqual(members, [...KNOWN_CATEGORIES].sort());
});

test("blueprint pins each ARRT category's scored count and weight (guards against silent drift)", () => {
  // From the ARRT MRI Content Specifications (Board Approved Jan 2024, impl Feb 1 2025):
  // 200 scored items. Pinned individually so a compensating edit that keeps the sum at
  // 200 (e.g. moving items between Safety and Image Production) still fails this test.
  const EXPECTED = {
    "Image Production": { scored: 106, weight: 0.53 },
    Procedures: { scored: 57, weight: 0.285 },
    Safety: { scored: 21, weight: 0.105 },
    "Patient Care": { scored: 16, weight: 0.08 },
  };
  assert.equal(B.ARRT_BLUEPRINT.length, Object.keys(EXPECTED).length);
  for (const cat of B.ARRT_BLUEPRINT) {
    const exp = EXPECTED[cat.name];
    assert.ok(exp, `unexpected category ${cat.name}`);
    assert.equal(cat.scored, exp.scored, `${cat.name} scored`);
    assert.ok(Math.abs(cat.weight - exp.weight) < 1e-9, `${cat.name} weight`);
    // weight is the exam share of the 200 scored items
    assert.ok(Math.abs(cat.weight - cat.scored / 200) < 1e-9, `${cat.name} weight matches scored/200`);
  }
});

test("blueprint is ordered by weight descending (Image Production first)", () => {
  assert.equal(B.ARRT_BLUEPRINT[0].name, "Image Production");
  const w = B.ARRT_BLUEPRINT.map((c) => c.weight);
  for (let i = 1; i < w.length; i++) assert.ok(w[i] <= w[i - 1]);
});

test("Procedures carries the honesty note; single-member categories carry none", () => {
  const proc = B.ARRT_BLUEPRINT.find((c) => c.name === "Procedures");
  assert.match(proc.note, /Positioning, coils, and protocol are practiced in Protocol Planning/);
  const safety = B.ARRT_BLUEPRINT.find((c) => c.name === "Safety");
  assert.ok(!safety.note);
});

test("empty progress: every category not-started, overall zero", () => {
  const r = B.readiness({});
  assert.equal(r.projected, 0);
  assert.equal(r.coverage, 0);
  r.categories.forEach((c) => {
    assert.equal(c.accuracy, null);
    assert.equal(c.coverage, 0);
    assert.equal(c.attempted, 0);
  });
});

test("full progress: per-category accuracy and weighted overall match hand math", () => {
  const progress = {
    sequences: { best: 8, total: 10, runs: 1 },
    "image-quality": { best: 6, total: 10, runs: 1 },
    artifacts: { best: 5, total: 10, runs: 1 },
    perfusion: { best: 1, total: 10, runs: 1 },
    pathology: { best: 7, total: 10, runs: 1 },
    anatomy: { best: 3, total: 10, runs: 1 },
    safety: { best: 9, total: 10, runs: 1 },
    "patient-care": { best: 8, total: 10, runs: 1 },
  };
  const r = B.readiness(progress);
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.ok(Math.abs(ip.accuracy - 0.5) < 1e-9);   // (8+6+5+1)/(40) = 0.5
  assert.equal(ip.coverage, 1);                     // 4 of 4 members
  const proc = r.categories.find((c) => c.key === "procedures");
  assert.ok(Math.abs(proc.accuracy - 0.5) < 1e-9);  // (7+3)/20
  // projected = .5*.53 + .5*.285 + .9*.105 + .8*.08 = 0.566
  assert.ok(Math.abs(r.projected - 0.566) < 1e-9);
  assert.ok(Math.abs(r.coverage - 1.0) < 1e-9);
});

test("partial: only one member of Image Production attempted", () => {
  const r = B.readiness({ sequences: { best: 8, total: 10, runs: 1 } });
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.ok(Math.abs(ip.accuracy - 0.8) < 1e-9);   // only sequences counted
  assert.equal(ip.coverage, 0.25);                  // 1 of 4 members
  assert.equal(ip.attempted, 1);
  assert.ok(Math.abs(r.projected - 0.8 * 0.53) < 1e-9);
});

test("unattempted category contributes null accuracy and 0 to projected", () => {
  const r = B.readiness({ safety: { best: 9, total: 10, runs: 1 } });
  const pc = r.categories.find((c) => c.key === "patient-care");
  assert.equal(pc.accuracy, null);
  const safety = r.categories.find((c) => c.key === "safety");
  assert.ok(Math.abs(r.projected - safety.accuracy * 0.105) < 1e-9);
});

test("thin sample reads as high accuracy but low coverage", () => {
  const r = B.readiness({ artifacts: { best: 3, total: 3, runs: 1 } });
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.equal(ip.accuracy, 1);
  assert.equal(ip.coverage, 0.25);
});

test("readiness tolerates missing/garbage progress", () => {
  assert.doesNotThrow(() => B.readiness(undefined));
  assert.doesNotThrow(() => B.readiness(null));
  // a member with total 0 or missing is not attempted
  const r = B.readiness({ safety: { best: 0, total: 0, runs: 2 } });
  assert.equal(r.categories.find((c) => c.key === "safety").accuracy, null);
});
