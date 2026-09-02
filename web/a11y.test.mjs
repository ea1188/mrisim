import { test } from "node:test";
import assert from "node:assert/strict";
import A11y from "./a11y.js";

test("speakable expands MRI jargon with word boundaries", () => {
  assert.equal(A11y.speakable("T2-weighted, TR 3500 ms and TE 100 ms at 3T"),
    "T two-weighted, T R 3500 milliseconds and T E 100 milliseconds at 3 tesla");
  assert.equal(A11y.speakable("T2* decay on GRE"), "T two star decay on gradient echo");
  // no false positives inside words
  assert.equal(A11y.speakable("STIRRED and Trees"), "STIRRED and Trees");
});

test("speakable handles symbols and empty input", () => {
  assert.equal(A11y.speakable("flip 30° ± 5"), "flip 30 degrees plus or minus 5");
  assert.equal(A11y.speakable(null), "");
});

test("describeScan builds alt text from a render setup", () => {
  assert.equal(A11y.describeScan({
    region: "Knee", orientation: "sagittal",
    params: { sequence: "Inversion Recovery", TR: 4000, TE: 40, TI: 150, field_strength: "1.5T" },
  }), "Sagittal knee inversion recovery image at 1.5 tesla, TR 4000, TE 40, TI 150 milliseconds");
  assert.equal(A11y.describeScan(null), "MRI scan image");
});

test("describeScan notes fat saturation", () => {
  const s = A11y.describeScan({ region: "Knee", orientation: "sagittal",
    params: { sequence: "Spin Echo", TR: 3000, TE: 20, fatsat_enabled: true } });
  assert.ok(s.includes("with fat saturation"));
});

test("speech API no-ops under Node", () => {
  assert.equal(A11y.speak("hello"), false);
  assert.equal(A11y.speaking(), false);
  A11y.stop();
});

// --- TTS quality: chunking, voice preference, prosody ------------------------
test("chunks splits at sentences and caps run-ons at commas", () => {
  const c = A11y.chunks("Short one. Another short one!");
  assert.deepEqual(c, ["Short one.", "Another short one!"]);
  const long = "A very long clause that keeps going, " + "and adds more detail, ".repeat(8) + "then ends.";
  const parts = A11y.chunks(long, 120);
  assert.ok(parts.length > 1);
  assert.ok(parts.every((p) => p.length <= 121));
});

test("pickVoice prefers saved, then known-good, then any English", () => {
  const vs = [
    { name: "Robot Default", lang: "en-US" },
    { name: "Google US English", lang: "en-US" },
    { name: "Samantha", lang: "en-US" },
    { name: "Autre", lang: "fr-FR" },
  ];
  assert.equal(A11y.pickVoice(vs, "Samantha").name, "Samantha");
  assert.equal(A11y.pickVoice(vs, null).name, "Google US English");
  assert.equal(A11y.pickVoice([{ name: "Only", lang: "en-GB" }], "Gone").name, "Only");
  assert.equal(A11y.pickVoice([], null), null);
});

test("speakable turns parentheticals and dashes into comma breaths", () => {
  assert.equal(A11y.speakable("Fat is bright (short T1) — muscle is not."),
    "Fat is bright, short T one, muscle is not.");
});

test("refresh is a safe no-op when idle or under Node", () => {
  A11y.refresh();
  assert.equal(A11y.speaking(), false);
});

test("speakable expands compound MRI units", () => {
  assert.equal(A11y.speakable("SAR limit 2 W/kg, gradients 45 mT/m"),
    "specific absorption rate limit 2 watts per kilogram, gradients 45 millitesla per meter");
  assert.equal(A11y.speakable("bandwidth 130 Hz/px at 128 MHz"),
    "bandwidth 130 hertz per pixel at 128 megahertz");
});

test("speakable spells device acronyms", () => {
  assert.equal(A11y.speakable("a DBS with a B1+rms condition"),
    "a D B S with a B one plus R M S condition");
});

// --- read-along: sentencePlan must mirror the spoken chunk stream ------------
test("sentencePlan counts align with chunking the full spoken text", () => {
  const title = "RF heating and coil safety";
  const blocks = ["The RF field deposits energy. SAR tracks it.", "Burns cluster at loops and skin contact points."];
  const keypoints = ["Keep cables straight", "Use pads between skin and bore."];
  const worked = ["Compute SAR for a 70 kg patient. It doubles with B1."];
  const hooks = ["SAR scales with the square of B1"];
  const traps = ["Whole body SAR limit is 2 W/kg in normal mode."];
  const plan = A11y.sentencePlan(title, blocks, keypoints, worked, hooks, traps);
  let spoken = title + ". " + blocks.join(" ");
  keypoints.forEach((k) => { spoken += " Key point: " + k + "."; });
  spoken += " Worked example. " + worked.join(" ");
  hooks.forEach((k) => { spoken += " Memory hook: " + k + "."; });
  traps.forEach((k) => { spoken += " Exam trap: " + k + "."; });
  assert.equal(plan.total, A11y.chunks(spoken).length);
  assert.equal(plan.workedHeader.count, 1);
  assert.deepEqual(plan.workedBlocks.map((b) => b.count), [2]);
  assert.equal(plan.traps[0].count, 1);
  assert.equal(plan.title.start, 0);
  assert.deepEqual(plan.blocks.map((b) => b.count), [2, 1]);
  assert.equal(plan.keypoints[0].count, 1);
});

test("sentencePlan tolerates empty parts", () => {
  const plan = A11y.sentencePlan("Title", [], []);
  assert.equal(plan.total, 1);
  assert.deepEqual(plan.blocks, []);
});

test("seekChunk and position are safe no-ops when idle or under Node", () => {
  A11y.seekChunk(3);
  assert.deepEqual(A11y.position(), { index: -1, total: 0 });
});
