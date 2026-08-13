import { test } from "node:test";
import assert from "node:assert/strict";
import S from "./sar_guidance.js";

// SAR ∝ flip_angle^2 / TR (holding sequence fixed). Given a known sar_head at
// (fa, tr), the sar after moving one lever scales predictably — used to check the
// suggested targets actually land under the limit.
function sarAfterFa(sar0, fa0, fa1) { return sar0 * (fa1 / fa0) ** 2; }
function sarAfterTr(sar0, tr0, tr1) { return sar0 * (tr0 / tr1); }

test("under the limit → over:false and no targets", () => {
  const g = S.sarGuidance({ flip_angle: 90, TR: 4000, sequence: "Spin Echo", sar_head: 2.1 });
  assert.equal(g.over, false);
  assert.equal(g.maxSafeFa, null);
  assert.equal(g.minSafeTr, null);
  assert.deepEqual(g.lowerSeqOptions, []);
});

test("max safe flip angle brings SAR to ~the limit and is below current FA", () => {
  const g = S.sarGuidance({ flip_angle: 120, TR: 500, sequence: "Spin Echo", sar_head: 5.0 });
  assert.equal(g.over, true);
  assert.ok(g.maxSafeFa >= 1 && g.maxSafeFa < 120);
  // applying the suggested FA should sit at or just under the 3.2 limit
  assert.ok(sarAfterFa(5.0, 120, g.maxSafeFa) <= 3.2 + 0.15);
});

test("min safe TR brings SAR under the limit", () => {
  const g = S.sarGuidance({ flip_angle: 90, TR: 500, sequence: "Spin Echo", sar_head: 5.0 });
  assert.ok(g.minSafeTr > 500);
  assert.ok(sarAfterTr(5.0, 500, g.minSafeTr) <= 3.2 + 1e-6);
});

test("max safe FA is clamped to >= 1 even for a huge overage", () => {
  const g = S.sarGuidance({ flip_angle: 10, TR: 200, sequence: "Inversion Recovery", sar_head: 40 });
  assert.ok(g.maxSafeFa >= 1);
  assert.ok(g.maxSafeFa < 10);
});

test("impractical TR (beyond ceiling) is dropped", () => {
  // sar/limit huge → TR target above TR_CEILING → null
  const g = S.sarGuidance({ flip_angle: 90, TR: 800, sequence: "Inversion Recovery", sar_head: 60 });
  assert.equal(g.minSafeTr, null);
});

test("from Spin Echo when far over, suggests GRE and EPI; never the current seq", () => {
  const g = S.sarGuidance({ flip_angle: 90, TR: 500, sequence: "Spin Echo", sar_head: 4.0 });
  // SE factor 1.5 → GRE/EPI 0.5 scales sar by 1/3 = 1.33 < 3.2 → both offered
  assert.deepEqual(g.lowerSeqOptions.sort(), ["Echo Planar (EPI)", "Gradient Echo"]);
  assert.ok(!g.lowerSeqOptions.includes("Spin Echo"));
});

test("no sequence option when switching alone can't get under", () => {
  // SE 1.5 → 0.5 scales by 1/3; need sar/3 <= 3.2 → sar <= 9.6. At sar=12 none qualify.
  const g = S.sarGuidance({ flip_angle: 90, TR: 300, sequence: "Spin Echo", sar_head: 12 });
  assert.deepEqual(g.lowerSeqOptions, []);
});

test("already a low-SAR sequence → no lower sequence to suggest", () => {
  const g = S.sarGuidance({ flip_angle: 70, TR: 8, sequence: "Gradient Echo", sar_head: 4.0 });
  assert.deepEqual(g.lowerSeqOptions, []);
  assert.ok(g.maxSafeFa < 70);   // FA lever still offered
});

test("exactly at the limit is not 'over'", () => {
  const g = S.sarGuidance({ flip_angle: 90, TR: 500, sequence: "Spin Echo", sar_head: 3.2 });
  assert.equal(g.over, false);
});
