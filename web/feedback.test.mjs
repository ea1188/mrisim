import { test } from "node:test";
import assert from "node:assert/strict";
import F from "./feedback.js";

test("buildPayload rejects an all-empty form", () => {
  const r = F.buildPayload({});
  assert.equal(r.ok, false);
  assert.match(r.error, /at least one/i);
});

test("buildPayload builds a full valid row and always stamps the cohort", () => {
  const r = F.buildPayload({
    recommend: "9", prepared: "4", pace: "about_right", workload: "too_heavy",
    useful_simulator: "5", useful_planner: "3", useful_quiz: "4",
    useful_lessons: "5", useful_reference: "2",
    hardest_module: "m6", helped_most: "the simulator", improve: "more images", other: "",
  });
  assert.equal(r.ok, true);
  assert.equal(r.payload.cohort, "2026-08");
  assert.equal(r.payload.recommend, 9);          // numbers, not strings
  assert.equal(r.payload.prepared, 4);
  assert.equal(r.payload.pace, "about_right");
  assert.equal(r.payload.hardest_module, "m6");
  assert.equal(r.payload.helped_most, "the simulator");
  assert.equal(r.payload.improve, "more images");
  assert.ok(!("other" in r.payload));            // blank text is omitted
});

test("buildPayload omits unanswered fields (partial submission is fine)", () => {
  const r = F.buildPayload({ recommend: "10" });
  assert.equal(r.ok, true);
  assert.deepEqual(r.payload, { cohort: "2026-08", recommend: 10 });
});

test("buildPayload rejects out-of-range numerics", () => {
  assert.equal(F.buildPayload({ recommend: "11" }).ok, false);
  assert.equal(F.buildPayload({ prepared: "0" }).ok, false);
  assert.equal(F.buildPayload({ useful_quiz: "6" }).ok, false);
  assert.equal(F.buildPayload({ recommend: "3.5" }).ok, false);  // non-integer
});

test("buildPayload rejects unknown enum / module values", () => {
  assert.equal(F.buildPayload({ pace: "warp_speed" }).ok, false);
  assert.equal(F.buildPayload({ workload: "", hardest_module: "m99" }).ok, false);
});

test("buildPayload accepts 'none' as hardest_module", () => {
  const r = F.buildPayload({ hardest_module: "none" });
  assert.equal(r.ok, true);
  assert.equal(r.payload.hardest_module, "none");
});

test("buildPayload trims and caps free text at TEXT_CAP", () => {
  const long = "x".repeat(F.TEXT_CAP + 500);
  const r = F.buildPayload({ improve: "  hello  ", other: long });
  assert.equal(r.ok, true);
  assert.equal(r.payload.improve, "hello");                 // trimmed
  assert.equal(r.payload.other.length, F.TEXT_CAP);         // capped
});

test("buildPayload honors a cohort override", () => {
  const r = F.buildPayload({ recommend: "8" }, { cohort: "2027-01" });
  assert.equal(r.payload.cohort, "2027-01");
});

test("MODULES cover the 10 core modules with stable keys", () => {
  assert.equal(F.MODULES.length, 10);
  assert.deepEqual(F.MODULES.map((m) => m.key), ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10"]);
  assert.ok(F.MODULE_KEYS.includes("none"));
});
