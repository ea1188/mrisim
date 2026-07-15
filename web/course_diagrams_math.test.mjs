import test from "node:test";
import assert from "node:assert/strict";
import Math2 from "./course_diagrams_math.js";

const { mz, mxy, t2star, classifyWeighting, sample, TISSUES, DIAGRAM_MAP } = Math2;

test("mz recovers from 0 toward 1", () => {
  assert.equal(mz(0, 500), 0);
  assert.ok(Math.abs(mz(500, 500) - 0.6321) < 1e-3);   // one time-constant ~63.2%
  assert.ok(mz(5000, 500) > 0.99);
});

test("mxy decays from 1 toward 0", () => {
  assert.equal(mxy(0, 90), 1);
  assert.ok(Math.abs(mxy(90, 90) - 0.3679) < 1e-3);     // one time-constant ~36.8%
  assert.ok(mxy(900, 90) < 0.01);
});

test("t2star is always shorter than T2 and approaches T2 as T2prime grows", () => {
  assert.ok(t2star(90, 30) < 90);
  assert.ok(t2star(90, 1e6) > 89.9);
});

test("classifyWeighting maps the four corners", () => {
  assert.equal(classifyWeighting(400, 15), "T1");   // short TR, short TE
  assert.equal(classifyWeighting(2500, 90), "T2");  // long TR, long TE
  assert.equal(classifyWeighting(2500, 15), "PD");  // long TR, short TE
  assert.equal(classifyWeighting(400, 90), "mixed");// short TR, long TE
});

test("classifyWeighting treats a mid-range TR as mixed", () => {
  assert.equal(classifyWeighting(1000, 15), "mixed");
});

test("sample returns n+1 points spanning [0, tMax]", () => {
  const pts = sample((t) => t, 100, 10);
  assert.equal(pts.length, 11);
  assert.deepEqual(pts[0], [0, 0]);
  assert.deepEqual(pts[10], [100, 100]);
});

test("data tables are well-formed", () => {
  assert.ok(TISSUES.length >= 4);
  for (const ti of TISSUES) {
    assert.ok(ti.id && ti.label && ti.t1 > 0 && ti.t2 > 0);
  }
  const titles = Object.keys(DIAGRAM_MAP);
  assert.ok(titles.includes("What makes an image T1 weighted?"));
  assert.deepEqual(DIAGRAM_MAP["What makes an image T1 weighted?"], ["t1-recovery"]);
  assert.deepEqual(DIAGRAM_MAP["Why is fluid bright on a T2 weighted image?"], ["t2-decay"]);
  assert.deepEqual(DIAGRAM_MAP["How does spin echo differ from gradient echo?"], ["t2-vs-t2star"]);
  assert.deepEqual(DIAGRAM_MAP["Contrast & weighting: the exam synthesis"], ["tr-te-weighting"]);
});
