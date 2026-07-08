import test from "node:test";
import assert from "node:assert/strict";
import CourseLogic from "./course_logic.js";

const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL, rankModulesByDiagnostic, diagnosticStudyNext, reviewOnMiss, reviewOnCorrect, dueCount, mergeProgress, isCourseComplete, remainingStudyOrder, pacePerWeek } = CourseLogic;

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

test("reviewOnMiss resets to box 0 due-now and increments misses", () => {
  assert.deepEqual(reviewOnMiss(undefined, 1000), { box: 0, due: 1000, misses: 1, lastSeen: 1000 });
  assert.deepEqual(reviewOnMiss({ box: 2, misses: 1 }, 5000), { box: 0, due: 5000, misses: 2, lastSeen: 5000 });
});

test("reviewOnCorrect advances box, widens due (1/3/7 days), then graduates", () => {
  const D = 86400000;
  assert.deepEqual(reviewOnCorrect(undefined, 0), { box: 1, due: 1 * D, misses: 0, lastSeen: 0 });
  assert.deepEqual(reviewOnCorrect({ box: 1, misses: 2 }, 0), { box: 2, due: 3 * D, misses: 2, lastSeen: 0 });
  assert.deepEqual(reviewOnCorrect({ box: 2, misses: 2 }, 0), { box: 3, due: 7 * D, misses: 2, lastSeen: 0 });
  assert.equal(reviewOnCorrect({ box: 3, misses: 2 }, 0), null);
});

test("dueCount counts only entries with due <= now", () => {
  assert.equal(dueCount({ a: { due: 100 }, b: { due: 300 }, c: { due: 200 } }, 200), 2);
  assert.equal(dueCount({}, 999), 0);
});

test("mergeProgress unions curriculum + read, keeps higher quiz seen", () => {
  const local = { mrisim_curriculum: ["a", "b"], mrisim_course_read_v1: { x: true }, mrisim_course_quiz_v1: { M: { seen: 5, right: 3 } } };
  const remote = { mrisim_curriculum: ["b", "c"], mrisim_course_read_v1: { y: true }, mrisim_course_quiz_v1: { M: { seen: 8, right: 2 } } };
  const m = mergeProgress(local, remote);
  assert.deepEqual(m.mrisim_curriculum.slice().sort(), ["a", "b", "c"]);
  assert.deepEqual(Object.keys(m.mrisim_course_read_v1).sort(), ["x", "y"]);
  assert.deepEqual(m.mrisim_course_quiz_v1.M, { seen: 8, right: 2 });
});

test("mergeProgress mastery: passed OR, max bestPct/attempts/ts", () => {
  const m = mergeProgress(
    { mrisim_course_mastery_v1: { M: { passed: false, bestPct: 60, attempts: 1, ts: 10 } } },
    { mrisim_course_mastery_v1: { M: { passed: true, bestPct: 90, attempts: 3, ts: 5 } } });
  assert.deepEqual(m.mrisim_course_mastery_v1.M, { passed: true, bestPct: 90, attempts: 3, ts: 10 });
});

test("mergeProgress exam higher bestPct; diagnostic later ts; review later lastSeen", () => {
  const m = mergeProgress(
    { mrisim_course_exam_v1: { bestPct: 70 }, mrisim_course_diagnostic_v1: { ts: 100, order: ["a"] }, mrisim_course_review_v1: { q: { box: 1, lastSeen: 50 } } },
    { mrisim_course_exam_v1: { bestPct: 85 }, mrisim_course_diagnostic_v1: { ts: 200, order: ["b"] }, mrisim_course_review_v1: { q: { box: 0, lastSeen: 80 } } });
  assert.equal(m.mrisim_course_exam_v1.bestPct, 85);
  assert.deepEqual(m.mrisim_course_diagnostic_v1.order, ["b"]);
  assert.deepEqual(m.mrisim_course_review_v1.q, { box: 0, lastSeen: 80 });
});

test("mergeProgress passes through one-sided keys and handles empties", () => {
  assert.deepEqual(mergeProgress({}, {}), {});
  assert.deepEqual(mergeProgress({ mrisim_curriculum: ["a"] }, {}), { mrisim_curriculum: ["a"] });
  assert.deepEqual(mergeProgress({}, { mrisim_course_exam_v1: { bestPct: 50 } }).mrisim_course_exam_v1, { bestPct: 50 });
});

test("isCourseComplete requires all mastered and exam >= 80", () => {
  assert.equal(isCourseComplete(["mastered", "mastered"], 80), true);
  assert.equal(isCourseComplete(["mastered", "mastered"], 79), false);
  assert.equal(isCourseComplete(["mastered", "progress"], 95), false);
  assert.equal(isCourseComplete([], 100), false);
  assert.equal(isCourseComplete(["mastered"], null), false);
});

test("mergeProgress completed record keeps the earlier at", () => {
  const m = mergeProgress(
    { mrisim_course_completed_v1: { at: 200, examPct: 90 } },
    { mrisim_course_completed_v1: { at: 100, examPct: 82 } });
  assert.deepEqual(m.mrisim_course_completed_v1, { at: 100, examPct: 82 });
  assert.deepEqual(mergeProgress({ mrisim_course_completed_v1: { at: 5 } }, {}).mrisim_course_completed_v1, { at: 5 });
});

test("remainingStudyOrder: diagnostic weakest-first, mastered dropped, rest appended in module order", () => {
  const modules = [{ title: "A", status: "mastered" }, { title: "B", status: "progress" }, { title: "C", status: "not-started" }, { title: "D", status: "review" }];
  assert.deepEqual(remainingStudyOrder(modules, ["A", "C", "B"]), ["C", "B", "D"]);
});

test("remainingStudyOrder: no diagnostic falls back to module order; all mastered gives []", () => {
  assert.deepEqual(remainingStudyOrder([{ title: "A", status: "progress" }, { title: "B", status: "not-started" }], null), ["A", "B"]);
  assert.deepEqual(remainingStudyOrder([{ title: "A", status: "mastered" }], ["A"]), []);
});

test("pacePerWeek: math, past date null, zero remaining null, sub-week rounds to 1 week", () => {
  const now = 0, D = 86400000;
  assert.deepEqual(pacePerWeek(8, 28 * D, now), { weeks: 4, perWeek: 2 });
  assert.equal(pacePerWeek(4, -D, now), null);
  assert.equal(pacePerWeek(0, 28 * D, now), null);
  assert.deepEqual(pacePerWeek(3, 2 * D, now), { weeks: 1, perWeek: 3 });
});
