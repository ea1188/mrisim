import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Math2 from "./course_diagrams_math.js";

const { mz, mxy, t2star, spinEchoSignal, ernstAngle, spoiledGreSignal, irMz, nullTI, dwiSignal, fft1d, fft2d, fftshift2d, snrScanRel, fatWaterSignal, dscSignal, aliasedVelocity, tofSignal, classifyWeighting, sample, TISSUES, ADCS, DIAGRAM_MAP } = Math2;

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

test("spinEchoSignal starts at 1, echoes on the true-T2 envelope, dips to T2* at TE/2", () => {
  const T2 = 100, T2p = 30, TE = 80;
  assert.equal(spinEchoSignal(0, T2, T2p, TE), 1);                       // 90 pulse: full signal
  // echo at TE is fully refocused, so it peaks on the true-T2 curve
  assert.ok(Math.abs(spinEchoSignal(TE, T2, T2p, TE) - Math.exp(-TE / T2)) < 1e-9);
  // at TE/2 the signal has fallen along the faster T2* curve
  const t2s = t2star(T2, T2p);
  assert.ok(Math.abs(spinEchoSignal(TE / 2, T2, T2p, TE) - Math.exp(-(TE / 2) / t2s)) < 1e-9);
  // the spin echo recovers signal a gradient echo (T2*) would have lost by TE
  assert.ok(spinEchoSignal(TE, T2, T2p, TE) > Math.exp(-TE / t2s));
});

test("ernstAngle and spoiledGreSignal: signal peaks at the Ernst angle", () => {
  assert.ok(Math.abs(ernstAngle(500, 500) - Math.acos(1 / Math.E)) < 1e-9);
  const TR = 500, T1 = 500;
  const peak = spoiledGreSignal(ernstAngle(TR, T1), TR, T1);
  for (let deg = 1; deg <= 90; deg++) {
    assert.ok(spoiledGreSignal(deg * Math.PI / 180, TR, T1) <= peak + 1e-9);
  }
});

test("irMz inverts then recovers, nulling at nullTI", () => {
  const T1 = 500;
  assert.equal(irMz(0, T1), -1);
  assert.ok(Math.abs(irMz(nullTI(T1), T1)) < 1e-9);
  assert.ok(irMz(5000, T1) > 0.99);
});

test("dwiSignal: 1 at b=0, faster decay for higher ADC, restricted stays brighter", () => {
  assert.equal(dwiSignal(0, 0.001), 1);
  assert.ok(dwiSignal(1000, 0.003) < dwiSignal(1000, 0.001));
  assert.ok(dwiSignal(1000, 0.0006) > dwiSignal(1000, 0.001));
  assert.ok(ADCS.length === 3 && ADCS[0].adc < ADCS[2].adc);
});

test("fft1d: delta -> constant, inverse round-trips, constant -> DC spike", () => {
  const re = [1, 0, 0, 0], im = [0, 0, 0, 0];
  fft1d(re, im, false);
  for (let i = 0; i < 4; i++) { assert.ok(Math.abs(re[i] - 1) < 1e-9); assert.ok(Math.abs(im[i]) < 1e-9); }
  fft1d(re, im, true);
  const exp = [1, 0, 0, 0];
  for (let i = 0; i < 4; i++) { assert.ok(Math.abs(re[i] - exp[i]) < 1e-9); assert.ok(Math.abs(im[i]) < 1e-9); }
  const cr = [2, 2, 2, 2], ci = [0, 0, 0, 0];
  fft1d(cr, ci, false);
  assert.ok(Math.abs(cr[0] - 8) < 1e-9);
  for (let i = 1; i < 4; i++) { assert.ok(Math.abs(cr[i]) < 1e-9 && Math.abs(ci[i]) < 1e-9); }
});

test("fft2d round-trips an image", () => {
  const N = 4, re = [], im = [];
  for (let i = 0; i < N * N; i++) { re.push((i * 7 % 13) / 13); im.push(0); }
  const re0 = re.slice();
  fft2d(re, im, N, false); fft2d(re, im, N, true);
  for (let i = 0; i < N * N; i++) { assert.ok(Math.abs(re[i] - re0[i]) < 1e-9); assert.ok(Math.abs(im[i]) < 1e-9); }
});

test("fftshift2d is self-inverse and moves DC to center", () => {
  const N = 4, a = [];
  for (let i = 0; i < N * N; i++) a.push(i);
  const a0 = a.slice();
  fftshift2d(a, N); fftshift2d(a, N);
  assert.deepEqual(a, a0);
  const b = [];
  for (let i = 0; i < N * N; i++) b.push(i === 0 ? 1 : 0);
  fftshift2d(b, N);
  assert.equal(b[(N / 2) * N + (N / 2)], 1);
});

test("snrScanRel: baseline 1x; trade-offs move as expected", () => {
  const base = snrScanRel({ slice: 3, matrix: 192, nex: 1, bw: 32 });
  assert.ok(Math.abs(base.snr - 1) < 1e-9 && Math.abs(base.time - 1) < 1e-9);
  assert.ok(Math.abs(snrScanRel({ slice: 6, matrix: 192, nex: 1, bw: 32 }).snr - 2) < 1e-9);
  const fine = snrScanRel({ slice: 3, matrix: 384, nex: 1, bw: 32 });
  assert.ok(Math.abs(fine.snr - 0.25) < 1e-9 && Math.abs(fine.time - 2) < 1e-9);
  assert.ok(Math.abs(snrScanRel({ slice: 3, matrix: 192, nex: 4, bw: 32 }).snr - 2) < 1e-9);
});

test("fatWaterSignal: in-phase at TE=0 and 1/df, opposed at 1/(2df)", () => {
  const df = 220;
  assert.ok(Math.abs(fatWaterSignal(0, 0.5, df) - 1) < 1e-9);
  assert.ok(Math.abs(fatWaterSignal(1000 / df, 0.5, df) - 1) < 1e-6);          // in-phase -> add -> 1
  assert.ok(Math.abs(fatWaterSignal(1000 / (2 * df), 0.5, df)) < 1e-6);        // opposed, equal -> 0
  assert.ok(Math.abs(fatWaterSignal(1000 / (2 * df), 0.3, df) - 0.4) < 1e-6);  // |0.7 - 0.3|
});

test("dscSignal: near-baseline at t=0, a first-pass dip at t=10, deeper for higher depth", () => {
  assert.ok(Math.abs(dscSignal(0, 0.6) - 1) < 0.05);
  assert.ok(dscSignal(10, 0.6) < dscSignal(0, 0.6));
  assert.ok(dscSignal(10, 0.85) < dscSignal(10, 0.4));
});

test("aliasedVelocity wraps true velocity into [-venc, venc]", () => {
  assert.equal(aliasedVelocity(50, 150), 50);     // in range: unchanged
  assert.equal(aliasedVelocity(200, 150), -100);  // above VENC: wraps negative
  assert.equal(aliasedVelocity(-200, 150), 100);  // below -VENC: wraps positive
});

test("tofSignal is the fresh-blood fraction, clamped at 1", () => {
  assert.equal(tofSignal(0, 10), 0);
  assert.equal(tofSignal(5, 10), 0.5);
  assert.equal(tofSignal(20, 10), 1); // clamped
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
  assert.deepEqual(DIAGRAM_MAP["Relaxation: T1 spin-lattice and T2 spin-spin"], ["t1-recovery", "t2-decay"]);
  assert.deepEqual(DIAGRAM_MAP["Dephasing, T2 vs T2*, and the spin-echo refocusing pulse"], ["t2-vs-t2star"]);
  assert.deepEqual(DIAGRAM_MAP["TR, TE, TI, and flip angle: setting image contrast"], ["tr-te-weighting"]);
  assert.deepEqual(DIAGRAM_MAP["Flip angle: the Ernst angle and the SAR trade-off"], ["ernst-angle"]);
  assert.deepEqual(DIAGRAM_MAP["Fat suppression: STIR, spectral, Dixon and water excitation"], ["ir-nulling", "chemical-shift"]);
  assert.deepEqual(DIAGRAM_MAP["Diffusion in disease: stroke, abscess and cellular tumors"], ["dwi-bvalue"]);
  assert.deepEqual(DIAGRAM_MAP["Image quality: SNR, CNR, resolution & the trade-offs"], ["snr-tradeoff"]);
  assert.deepEqual(DIAGRAM_MAP["Data acquisition: k-space, encoding and the Fourier transform"], ["kspace-recon"]);
  assert.deepEqual(DIAGRAM_MAP["Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration"], ["parallel-imaging"]);
  assert.deepEqual(DIAGRAM_MAP["Spatial encoding: slice, phase, and frequency gradients into k-space"], ["kspace-trajectories"]);
  assert.deepEqual(DIAGRAM_MAP["MR image quality: SNR, scan time, and spatial resolution tradeoffs"], ["gibbs-ringing"]);
  assert.deepEqual(DIAGRAM_MAP["Perfusion by DSC: first-pass bolus tracking"], ["dsc-curve"]);
  assert.deepEqual(DIAGRAM_MAP["Arterial spin labeling: perfusion without contrast"], ["asl-subtraction"]);
  assert.deepEqual(DIAGRAM_MAP["Phase contrast MRA and velocity encoding (VENC)"], ["pc-venc"]);
  assert.deepEqual(DIAGRAM_MAP["Time-of-flight MRA: inflow, saturation, and pitfalls"], ["tof-inflow"]);
  assert.deepEqual(DIAGRAM_MAP["The diffusion tensor and fractional anisotropy (FA)"], ["fa-anisotropy"]);
  assert.deepEqual(DIAGRAM_MAP["DTI tractography: mapping white matter tracts"], ["tractography"]);
  // every diagram id is wired exactly once
  const ids = Object.values(DIAGRAM_MAP).reduce((a, v) => a.concat(v), []).sort();
  assert.deepEqual(ids, ["asl-subtraction", "chemical-shift", "dsc-curve", "dwi-bvalue", "ernst-angle", "fa-anisotropy", "gibbs-ringing", "ir-nulling", "kspace-recon", "kspace-trajectories", "parallel-imaging", "pc-venc", "snr-tradeoff", "t1-recovery", "t2-decay", "t2-vs-t2star", "tof-inflow", "tr-te-weighting", "tractography"]);
});

// Guards against the self-referential trap: a DIAGRAM_MAP key that is not a real
// education-card title means attach() (which only runs for kind:"education" cards)
// never fires, so the diagram silently never renders. Cross-check against the
// actual course content, mirroring blueprint.test.mjs.
test("every DIAGRAM_MAP key is a real education-card title", () => {
  const dir = path.dirname(fileURLToPath(import.meta.url));
  const raw = JSON.parse(fs.readFileSync(path.join(dir, "..", "data", "course_content.json"), "utf8"));
  const items = Array.isArray(raw) ? raw : (raw.items || []);
  const eduTitles = new Set(
    items.filter((it) => it.kind === "education")
      .map((it) => (it.body && it.body.title) || it.title)
  );
  const missing = Object.keys(DIAGRAM_MAP).filter((t) => !eduTitles.has(t));
  assert.deepEqual(missing, [], "DIAGRAM_MAP keys are not education-card titles (diagrams would never render): " + missing.join(" | "));
});
