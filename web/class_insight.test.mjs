import { test } from "node:test";
import assert from "node:assert/strict";
import CI from "./class_insight.js";

const roster = [
  { student_id: "s1", profiles: { display_name: "Ada" } },
  { student_id: "s2", profiles: { display_name: "Bo" } },
  { student_id: "s3", profiles: {} }, // unnamed, no activity
];
const activity = [
  { student_id: "s1", kind: "quiz_attempt", ref: "safety", score: 6, total: 10, created_at: "2026-07-01T10:00:00Z" },
  { student_id: "s1", kind: "quiz_attempt", ref: "safety", score: 9, total: 10, created_at: "2026-07-02T10:00:00Z" },
  { student_id: "s1", kind: "quiz_attempt", ref: "flow", score: 5, total: 10, created_at: "2026-07-03T10:00:00Z" },
  { student_id: "s1", kind: "lesson_complete", ref: "Lesson A", score: null, total: null, created_at: "2026-07-01T09:00:00Z" },
  { student_id: "s1", kind: "lesson_complete", ref: "Lesson A", score: null, total: null, created_at: "2026-07-04T09:00:00Z" },
  { student_id: "s2", kind: "quiz_attempt", ref: "safety", score: 2, total: 10, created_at: "2026-07-01T10:00:00Z" },
  { student_id: "s2", kind: "quiz_attempt", ref: "safety", score: 3, total: 10, created_at: "2026-07-05T10:00:00Z" },
  { student_id: "s2", kind: "quiz_attempt", ref: "zero", score: 0, total: 0, created_at: "2026-07-06T10:00:00Z" },
];

test("perStudent aggregates best/latest/attempts and distinct lessons", () => {
  const rows = CI.perStudent(roster, activity);
  const a = rows.find((r) => r.studentId === "s1");
  assert.equal(a.name, "Ada");
  assert.equal(a.topics.safety.attempts, 2);
  assert.equal(a.topics.safety.best, 90);
  assert.equal(a.topics.safety.latest, 90); // 2026-07-02 is latest of the two safety runs
  assert.equal(a.lessonsDone, 1); // "Lesson A" twice = 1 distinct
  assert.equal(a.quizRuns, 3);
  assert.equal(a.bestPct, 90);
  assert.equal(a.weakestTopic, "flow"); // 50 < 90
  assert.equal(a.lastActive, "2026-07-04T09:00:00Z");
});

test("struggling flags a topic retaken >= struggleAttempts still below passPct", () => {
  const rows = CI.perStudent(roster, activity);
  assert.equal(rows.find((r) => r.studentId === "s2").struggling, true); // safety 2 attempts, best 30 < 80
  assert.equal(rows.find((r) => r.studentId === "s1").struggling, false); // safety passed; flow only 1 attempt
});

test("a roster member with no activity is all zeros", () => {
  const rows = CI.perStudent(roster, activity);
  const c = rows.find((r) => r.studentId === "s3");
  assert.equal(c.name, "(unnamed)");
  assert.equal(c.quizRuns, 0);
  assert.equal(c.lessonsDone, 0);
  assert.equal(c.bestPct, null);
  assert.equal(c.struggling, false);
});

test("total==0 quiz row counts as a run but not for scoring", () => {
  const s2 = CI.perStudent(roster, activity).find((r) => r.studentId === "s2");
  assert.equal(s2.quizRuns, 3);
  assert.equal(s2.topics.zero.best, null);
  assert.equal(s2.topicsPassed, 0);
});

test("coverage blends lessons and topics passed over totals; 0 on empty denom", () => {
  const a = CI.perStudent(roster, activity).find((r) => r.studentId === "s1");
  // lessonsDone 1 + topicsPassed 1 (safety 90>=80; flow 50 no) = 2; totals 40+8=48 -> round(100*2/48)=4
  assert.equal(CI.coverage(a, { lessons: 40, topics: 8 }), 4);
  assert.equal(CI.coverage(a, { lessons: 0, topics: 0 }), 0);
});

test("classStats averages and picks up to 3 weakest topics ascending", () => {
  const rows = CI.perStudent(roster, activity);
  const st = CI.classStats(rows, { lessons: 40, topics: 8 });
  assert.equal(st.members, 3);
  // flow avgBest 50 (s1 only) < safety avgBest 60 (90,30) -> flow is weakest, first
  assert.equal(st.weakestTopics[0].topic, "flow");
  assert.equal(st.weakestTopics[0].avgBest <= st.weakestTopics[st.weakestTopics.length - 1].avgBest, true);
});

test("mastery_check counts distinct modules passed; mock_exam tracks best", () => {
  const roster2 = [{ student_id: "m1", profiles: { display_name: "Cy" } }];
  const acts = [
    // module "Safety": fails then passes -> mastered once (best 90 >= 80)
    { student_id: "m1", kind: "mastery_check", ref: "Safety", score: 60, total: 100, created_at: "2026-07-01T00:00:00Z" },
    { student_id: "m1", kind: "mastery_check", ref: "Safety", score: 90, total: 100, created_at: "2026-07-02T00:00:00Z" },
    // module "Physics": best 70 < 80 -> attempted but NOT mastered
    { student_id: "m1", kind: "mastery_check", ref: "Physics", score: 70, total: 100, created_at: "2026-07-03T00:00:00Z" },
    // two mock exams -> best is the higher
    { student_id: "m1", kind: "mock_exam", ref: "mock", score: 30, total: 60, created_at: "2026-07-04T00:00:00Z" },
    { student_id: "m1", kind: "mock_exam", ref: "mock", score: 48, total: 60, created_at: "2026-07-05T00:00:00Z" },
  ];
  const row = CI.perStudent(roster2, acts)[0];
  assert.equal(row.modulesMastered, 1);          // Safety mastered, Physics not
  assert.equal(row.bestMockPct, 80);             // 48/60 = 80 beats 30/60 = 50
  assert.equal(row.lastActive, "2026-07-05T00:00:00Z");
  const st = CI.classStats([row], { lessons: 10, topics: 4 });
  assert.equal(st.avgMockPct, 80);
});

test("toCSV emits the exact header and escapes commas and quotes", () => {
  const rows = CI.perStudent(
    [{ student_id: "x", profiles: { display_name: 'De, "Q"' } }],
    [{ student_id: "x", kind: "quiz_attempt", ref: "t", score: 8, total: 10, created_at: "2026-07-01T00:00:00Z" }]
  );
  const csv = CI.toCSV(rows, { lessons: 10, topics: 4 });
  const lines = csv.split("\n");
  assert.equal(lines[0], '"Member","Practice coverage %","Best score %","Modules mastered","Best mock %","Lessons done","Weakest topic","Struggling","Last active"');
  assert.ok(lines[1].startsWith('"De, ""Q"""')); // comma preserved, quotes doubled
});
