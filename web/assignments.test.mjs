import { test } from "node:test";
import assert from "node:assert/strict";
import A from "./assignments.js";

const lessonsData = {
  curriculum: [
    { title: "1 · Basics", lessons: ["What is MRI", "T1 vs T2"] },
    { title: "2 · Safety", lessons: ["Zones", "Screening"] },
  ],
};
const quizData = { categories: [{ id: "safety" }, { id: "image-quality", name: "Image Quality" }] };

test("catalog builds modules, lessons (with owning module), and humanized quiz labels", () => {
  const cat = A.catalog(lessonsData, quizData);
  assert.equal(cat.modules.length, 2);
  assert.deepEqual(cat.modules[0].lessons, ["What is MRI", "T1 vs T2"]);
  assert.equal(cat.lessons.length, 4);
  assert.deepEqual(cat.lessons[0], { ref: "What is MRI", label: "What is MRI", module: "1 · Basics" });
  assert.equal(cat.quizzes[0].label, "Safety");            // humanized from id
  assert.equal(cat.quizzes[1].label, "Image Quality");     // explicit name wins
});

test("catalog tolerates empty / missing inputs", () => {
  const cat = A.catalog({}, undefined);
  assert.deepEqual(cat, { modules: [], lessons: [], quizzes: [] });
});

test("studentStatus: lesson done uses earliest matching lesson_complete", () => {
  const cat = A.catalog(lessonsData, quizData);
  const assignments = [{ id: "a1", kind: "lesson", ref: "Zones", due_at: null }];
  const activity = [
    { kind: "lesson_complete", ref: "Zones", created_at: "2026-07-03T00:00:00Z" },
    { kind: "lesson_complete", ref: "Zones", created_at: "2026-07-01T00:00:00Z" },
    { kind: "lesson_complete", ref: "Other", created_at: "2026-07-02T00:00:00Z" },
  ];
  const s = A.studentStatus(assignments, activity, cat)[0];
  assert.equal(s.done, true);
  assert.equal(s.doneAt, "2026-07-01T00:00:00Z");
  assert.equal(s.label, "Zones");
});

test("studentStatus: quiz done on any quiz_attempt for the topic", () => {
  const cat = A.catalog(lessonsData, quizData);
  const s = A.studentStatus(
    [{ id: "a2", kind: "quiz", ref: "safety", due_at: null }],
    [{ kind: "quiz_attempt", ref: "safety", created_at: "2026-07-05T00:00:00Z" }],
    cat
  )[0];
  assert.equal(s.done, true);
  assert.equal(s.doneAt, "2026-07-05T00:00:00Z");
});

test("studentStatus: module done needs ALL its lessons; doneAt is the latest", () => {
  const cat = A.catalog(lessonsData, quizData);
  const asg = [{ id: "a3", kind: "module", ref: "1 · Basics", due_at: null }];
  const partial = A.studentStatus(asg, [
    { kind: "lesson_complete", ref: "What is MRI", created_at: "2026-07-01T00:00:00Z" },
  ], cat)[0];
  assert.equal(partial.done, false);          // "T1 vs T2" not done
  assert.equal(partial.doneAt, null);
  const full = A.studentStatus(asg, [
    { kind: "lesson_complete", ref: "What is MRI", created_at: "2026-07-01T00:00:00Z" },
    { kind: "lesson_complete", ref: "T1 vs T2", created_at: "2026-07-04T00:00:00Z" },
  ], cat)[0];
  assert.equal(full.done, true);
  assert.equal(full.doneAt, "2026-07-04T00:00:00Z");   // latest of the two
});

test("studentStatus: module done on a PASSING mastery_check even with no lessons complete", () => {
  const cat = A.catalog(lessonsData, quizData);
  const asg = [{ id: "a3", kind: "module", ref: "1 · Basics", due_at: null }];
  const s = A.studentStatus(asg, [
    { kind: "mastery_check", ref: "1 · Basics", score: 80, total: 100, created_at: "2026-07-05T00:00:00Z" },
  ], cat)[0];
  assert.equal(s.done, true);
  assert.equal(s.doneAt, "2026-07-05T00:00:00Z");
});

test("studentStatus: a FAILING mastery_check does not mark the module done", () => {
  const cat = A.catalog(lessonsData, quizData);
  const asg = [{ id: "a3", kind: "module", ref: "1 · Basics", due_at: null }];
  const s = A.studentStatus(asg, [
    { kind: "mastery_check", ref: "1 · Basics", score: 70, total: 100, created_at: "2026-07-05T00:00:00Z" },
  ], cat)[0];
  assert.equal(s.done, false);
  assert.equal(s.doneAt, null);
});

test("studentStatus: module doneAt is the EARLIEST of mastery-pass vs all-lessons-done", () => {
  const cat = A.catalog(lessonsData, quizData);
  const asg = [{ id: "a3", kind: "module", ref: "1 · Basics", due_at: null }];
  // mastery passed 07-02; lessons all complete only by 07-04 → done as of the earlier mastery date
  const s = A.studentStatus(asg, [
    { kind: "mastery_check", ref: "1 · Basics", score: 90, total: 100, created_at: "2026-07-02T00:00:00Z" },
    { kind: "lesson_complete", ref: "What is MRI", created_at: "2026-07-01T00:00:00Z" },
    { kind: "lesson_complete", ref: "T1 vs T2", created_at: "2026-07-04T00:00:00Z" },
  ], cat)[0];
  assert.equal(s.done, true);
  assert.equal(s.doneAt, "2026-07-02T00:00:00Z");
});

test("studentStatus: unknown module is not done; unknown ref label falls back to ref", () => {
  const cat = A.catalog(lessonsData, quizData);
  const s = A.studentStatus([{ id: "a4", kind: "module", ref: "9 · Ghost", due_at: null }], [], cat)[0];
  assert.equal(s.done, false);
  assert.equal(s.label, "9 · Ghost");
});

test("classCompletion counts members satisfying each assignment (incl. a member with no activity)", () => {
  const cat = A.catalog(lessonsData, quizData);
  const roster = [{ student_id: "s1" }, { student_id: "s2" }, { student_id: "s3" }];
  const activity = [
    { student_id: "s1", kind: "quiz_attempt", ref: "safety", created_at: "2026-07-01T00:00:00Z" },
    { student_id: "s2", kind: "quiz_attempt", ref: "safety", created_at: "2026-07-02T00:00:00Z" },
    // s3: nothing
  ];
  const c = A.classCompletion([{ id: "a5", kind: "quiz", ref: "safety", due_at: null }], roster, activity, cat)[0];
  assert.equal(c.total, 3);
  assert.equal(c.doneCount, 2);
});

test("studentStatus: rows sort by due date (earliest first), no-due last", () => {
  const cat = A.catalog(lessonsData, quizData);
  const asg = [
    { id: "late", kind: "quiz", ref: "safety", due_at: "2026-08-28T23:59:59Z" },
    { id: "none", kind: "quiz", ref: "image-quality", due_at: null },
    { id: "early", kind: "lesson", ref: "Zones", due_at: "2026-08-07T23:59:59Z" },
  ];
  const rows = A.studentStatus(asg, [], cat);
  assert.deepEqual(rows.map((r) => r.id), ["early", "late", "none"]);
});

test("classCompletion: rows sort by due date (earliest first), no-due last", () => {
  const cat = A.catalog(lessonsData, quizData);
  const roster = [{ student_id: "s1" }];
  const asg = [
    { id: "late", kind: "quiz", ref: "safety", due_at: "2026-08-28T23:59:59Z" },
    { id: "none", kind: "quiz", ref: "image-quality", due_at: null },
    { id: "early", kind: "quiz", ref: "safety", due_at: "2026-08-07T23:59:59Z" },
  ];
  const rows = A.classCompletion(asg, roster, [], cat);
  assert.deepEqual(rows.map((r) => r.id), ["early", "late", "none"]);
});

test("dueLabel: null when no due; overdue flag compares to now", () => {
  assert.equal(A.dueLabel(null, "2026-07-08T00:00:00Z"), null);
  const future = A.dueLabel("2026-07-12T23:59:59Z", "2026-07-08T00:00:00Z");
  assert.equal(future.overdue, false);
  assert.ok(/^due /.test(future.text));
  const past = A.dueLabel("2026-07-05T23:59:59Z", "2026-07-08T00:00:00Z");
  assert.equal(past.overdue, true);
});
