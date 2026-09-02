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
