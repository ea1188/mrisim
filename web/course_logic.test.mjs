import test from "node:test";
import assert from "node:assert/strict";
import CourseLogic from "./course_logic.js";

const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL, rankModulesByDiagnostic, diagnosticStudyNext } = CourseLogic;

test("constants match the spec", () => {
  assert.equal(PASS_PCT, 80);
  assert.equal(CHECK_N, 8);
  assert.equal(MIN_POOL, 4);
});

test("not-started when nothing done, seen, or attempted", () => {
  assert.equal(deriveModuleStatus(0, 5, 0, 0, false), "not-started");
});

test("progress when some subs done but mastery not passed", () => {
  assert.equal(deriveModuleStatus(2, 5, 3, 0, false), "progress");
});

test("review when mastery attempted but not passed", () => {
  assert.equal(deriveModuleStatus(5, 5, 8, 1, false), "review");
});

test("mastered when passed and every sub done", () => {
  assert.equal(deriveModuleStatus(5, 5, 8, 1, true), "mastered");
});

test("passed but not all subs done stays progress, not mastered", () => {
  assert.equal(deriveModuleStatus(4, 5, 8, 1, true), "progress");
});

test("pass boundary is 80 percent inclusive", () => {
  assert.equal(79 >= PASS_PCT, false);
  assert.equal(80 >= PASS_PCT, true);
});

test("rankModulesByDiagnostic orders weakest-first; absent module counts as 1.0; curriculum tiebreak", () => {
  const per = { B: { asked: 2, right: 0 }, C: { asked: 2, right: 1 }, A: { asked: 2, right: 2 } };
  // B acc 0, C acc 0.5, A acc 1.0, D absent -> 1.0; A before D by curriculum order.
  assert.deepEqual(rankModulesByDiagnostic(per, ["A", "B", "C", "D"]), ["B", "C", "A", "D"]);
});

test("rankModulesByDiagnostic treats asked=0 as accuracy 1.0", () => {
  assert.deepEqual(rankModulesByDiagnostic({ A: { asked: 0, right: 0 } }, ["A", "B"]), ["A", "B"]);
});

test("diagnosticStudyNext returns first non-mastered title in order", () => {
  assert.equal(diagnosticStudyNext(["B", "C", "A"], { B: "mastered", C: "progress", A: "not-started" }), "C");
});

test("diagnosticStudyNext returns null when all mastered", () => {
  assert.equal(diagnosticStudyNext(["A", "B"], { A: "mastered", B: "mastered" }), null);
});

test("diagnosticStudyNext returns null for empty order", () => {
  assert.equal(diagnosticStudyNext([], {}), null);
});
