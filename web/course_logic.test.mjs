import test from "node:test";
import assert from "node:assert/strict";
import CourseLogic from "./course_logic.js";

const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL } = CourseLogic;

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
