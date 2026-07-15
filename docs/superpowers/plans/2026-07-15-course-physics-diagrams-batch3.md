# Course Physics Diagrams — Batch 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two diagrams with new primitives — an SNR/scan-time trade-off calculator (HTML bars) and a k-space center-vs-periphery widget with real inverse-FFT reconstruction (canvas).

**Architecture:** New pure math in `web/course_diagrams_math.js` (radix-2 FFT + a relative-SNR model, node-tested); two new widget builders in `web/course_diagrams.js` (one HTML-bar, one canvas — neither uses the SVG `makePlot`); two new `DIAGRAM_MAP` keys; CSS in `web/course.html`. No new files; no course.js/sw.js/eslint change.

**Tech Stack:** Vanilla ES2022 classic scripts, HTML/CSS bars, Canvas 2D, `node --test`, ESLint, existing course tokens.

## Global Constraints

- Classic browser scripts; pure module keeps its UMD wrapper.
- UI: no emoji, no pills, no gradients; theme tokens only; **no em dashes in visible strings**. US spelling.
- Do NOT modify read-tracking, PROGRESS_KEYS, buildRail, navigation, course.js, sw.js, eslint.config.mjs.
- Physics are 1.5 T teaching approximations; captions say so.
- No `Co-Authored-By`.
- **Invariant:** every `DIAGRAM_MAP` key MUST be an exact `kind:"education"` `body.title` in `data/course_content.json` (guard test enforces).

---

### Task 1: FFT + SNR math + DIAGRAM_MAP keys + tests

**Files:** Modify `web/course_diagrams_math.js`, `web/course_diagrams_math.test.mjs`

**Interfaces — Produces (pure):** `fft1d(re,im,inverse)`, `fft2d(re,im,N,inverse)`, `fftshift2d(a,N)`, `snrScanRel({slice,matrix,nex,bw})→{snr,time}`, and two new `DIAGRAM_MAP` entries.

- [ ] **Step 1: Write the failing tests**

Extend the destructure on line 6 of `web/course_diagrams_math.test.mjs`:

```js
const { mz, mxy, t2star, spinEchoSignal, ernstAngle, spoiledGreSignal, irMz, nullTI, dwiSignal, fft1d, fft2d, fftshift2d, snrScanRel, classifyWeighting, sample, TISSUES, ADCS, DIAGRAM_MAP } = Math2;
```

Add these tests (after the DWI test):

```js
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
```

Update the DIAGRAM_MAP block in the `"data tables are well-formed"` test — add two `deepEqual`s and change `ids` to nine sorted:

```js
  assert.deepEqual(DIAGRAM_MAP["Image quality: SNR, CNR, resolution & the trade-offs"], ["snr-tradeoff"]);
  assert.deepEqual(DIAGRAM_MAP["Data acquisition: k-space, encoding and the Fourier transform"], ["kspace-recon"]);
  const ids = Object.values(DIAGRAM_MAP).reduce((a, v) => a.concat(v), []).sort();
  assert.deepEqual(ids, ["dwi-bvalue", "ernst-angle", "ir-nulling", "kspace-recon", "snr-tradeoff", "t1-recovery", "t2-decay", "t2-vs-t2star", "tr-te-weighting"]);
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_diagrams_math.test.mjs` → FAIL (undefined fns / missing keys).

- [ ] **Step 3: Implement**

In `web/course_diagrams_math.js`, add after `dwiSignal`:

```js
  // In-place radix-2 Cooley-Tukey FFT; re/im length must be a power of 2. Inverse divides by N.
  function fft1d(re, im, inverse) {
    var n = re.length, i, j, len, s, k;
    for (i = 1, j = 0; i < n; i++) {
      var bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) {
        var tr = re[i]; re[i] = re[j]; re[j] = tr;
        var ti = im[i]; im[i] = im[j]; im[j] = ti;
      }
    }
    for (len = 2; len <= n; len <<= 1) {
      var ang = (inverse ? 2 : -2) * Math.PI / len;
      var wr = Math.cos(ang), wi = Math.sin(ang);
      for (s = 0; s < n; s += len) {
        var cwr = 1, cwi = 0;
        for (k = 0; k < (len >> 1); k++) {
          var a = s + k, b = s + k + (len >> 1);
          var vr = re[b] * cwr - im[b] * cwi, vi = re[b] * cwi + im[b] * cwr;
          re[b] = re[a] - vr; im[b] = im[a] - vi;
          re[a] = re[a] + vr; im[a] = im[a] + vi;
          var ncwr = cwr * wr - cwi * wi;
          cwi = cwr * wi + cwi * wr; cwr = ncwr;
        }
      }
    }
    if (inverse) { for (i = 0; i < n; i++) { re[i] /= n; im[i] /= n; } }
  }

  // 2D FFT of an N x N row-major complex array: transform rows then columns.
  function fft2d(re, im, N, inverse) {
    var rr = new Array(N), ri = new Array(N), x, y;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) { rr[x] = re[y * N + x]; ri[x] = im[y * N + x]; }
      fft1d(rr, ri, inverse);
      for (x = 0; x < N; x++) { re[y * N + x] = rr[x]; im[y * N + x] = ri[x]; }
    }
    var cr = new Array(N), ci = new Array(N);
    for (x = 0; x < N; x++) {
      for (y = 0; y < N; y++) { cr[y] = re[y * N + x]; ci[y] = im[y * N + x]; }
      fft1d(cr, ci, inverse);
      for (y = 0; y < N; y++) { re[y * N + x] = cr[y]; im[y * N + x] = ci[y]; }
    }
  }

  // Swap diagonal quadrants of an N x N array (DC <-> center). Self-inverse for even N.
  function fftshift2d(a, N) {
    var h = N >> 1, x, y, t;
    for (y = 0; y < h; y++) {
      for (x = 0; x < h; x++) {
        var i00 = y * N + x, i11 = (y + h) * N + (x + h);
        t = a[i00]; a[i00] = a[i11]; a[i11] = t;
        var i01 = y * N + (x + h), i10 = (y + h) * N + x;
        t = a[i01]; a[i01] = a[i10]; a[i10] = t;
      }
    }
  }

  // Relative SNR and scan time vs baseline {slice:3, matrix:192, nex:1, bw:32}.
  function snrScanRel(p) {
    var snr = (p.slice / 3) * Math.pow(192 / p.matrix, 2) * Math.sqrt(p.nex / 1) * Math.sqrt(32 / p.bw);
    var time = (p.matrix / 192) * (p.nex / 1);
    return { snr: snr, time: time };
  }
```

Add the two `DIAGRAM_MAP` entries (keep all existing):

```js
    "Image quality: SNR, CNR, resolution & the trade-offs": ["snr-tradeoff"],
    "Data acquisition: k-space, encoding and the Fourier transform": ["kspace-recon"],
```

Extend the return object — add this line inside the returned object literal, alongside the other exports:

```js
    fft1d: fft1d, fft2d: fft2d, fftshift2d: fftshift2d, snrScanRel: snrScanRel,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:web` → PASS (guard test covers the two new education-title keys).

- [ ] **Step 5: Commit**

```bash
git add web/course_diagrams_math.js web/course_diagrams_math.test.mjs
git commit -m "feat(course): batch3 math (radix-2 FFT, fftshift, relative SNR) + map keys"
```

---

### Task 2: SNR / scan-time trade-off widget (HTML bars)

**Files:** Modify `web/course_diagrams.js`, `web/course.html`

**Interfaces:** Consumes `figure`, `el`; `M.snrScanRel`. Produces `BUILDERS["snr-tradeoff"]`.

- [ ] **Step 1: Add the builder**

In `web/course_diagrams.js`, next to the other builders:

```js
  // ---- Widget: SNR / scan-time trade-offs ---- //
  function buildSnrTradeoff() {
    var fig = figure("SNR trade-offs", "Signal-to-noise, resolution and scan time pull against each other. Change a parameter and watch relative SNR and scan time move against the baseline (1.5 T, approximate).");
    var state = { slice: 3, matrix: 192, nex: 1, bw: 32 };
    function bar(label) {
      var fill = el("div", { class: "diag-bar-fill" });
      var track = el("div", { class: "diag-bar-track" }, [fill, el("i", { class: "diag-bar-base" })]);
      var num = el("span", { class: "diag-bar-num" });
      var row = el("div", { class: "diag-bar-row" }, [el("span", { class: "diag-bar-label", text: label }), track, num]);
      return { node: row, set: function (v) {
        var cap = 3;
        fill.style.width = (Math.min(v, cap) / cap * 100) + "%";
        num.textContent = (Math.round(v * 100) / 100) + "x";
        if (v < 1) fill.classList.add("low"); else fill.classList.remove("low");
      } };
    }
    var snrBar = bar("Relative SNR"), timeBar = bar("Relative scan time");
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      var r = M.snrScanRel(state);
      snrBar.set(r.snr); timeBar.set(r.time);
      readout.textContent = "SNR " + (Math.round(r.snr * 100) / 100) + "x, scan time " + (Math.round(r.time * 100) / 100)
        + "x versus baseline (thin slice, coarse matrix, NEX 1, low bandwidth). Bigger voxels and more averages raise SNR; a finer matrix and higher bandwidth lower it.";
    }
    fig.appendChild(snrBar.node);
    fig.appendChild(timeBar.node);
    var controls = el("div", { class: "diag-controls" });
    function group(labelTxt, key, presets) {
      controls.appendChild(el("span", { class: "diag-glabel", text: labelTxt }));
      presets.forEach(function (p) {
        var b = el("button", { type: "button", class: "diag-btn diag-" + key + (p[1] === state[key] ? " on" : ""), text: p[0] });
        b.addEventListener("click", function () {
          state[key] = p[1];
          [].forEach.call(controls.querySelectorAll(".diag-" + key), function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          redraw();
        });
        controls.appendChild(b);
      });
    }
    group("Slice:", "slice", [["Thin", 3], ["Thick", 6]]);
    group("Matrix:", "matrix", [["Coarse", 192], ["Fine", 384]]);
    group("NEX:", "nex", [["1", 1], ["2", 2], ["4", 4]]);
    group("BW:", "bw", [["Low", 32], ["High", 64]]);
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }
```

Register it (keep all prior entries):

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle, "ir-nulling": buildIrNulling, "dwi-bvalue": buildDwiBvalue, "snr-tradeoff": buildSnrTradeoff };
```

- [ ] **Step 2: Add bar CSS to `web/course.html`**

In the `<style>` block, near the other `.diag-*` rules:

```css
    .diag-bar-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; font-size: 12px; color: var(--muted); }
    .diag-bar-label { flex: none; width: 128px; }
    .diag-bar-track { position: relative; flex: 1; height: 10px; background: var(--line); border-radius: 3px; overflow: hidden; }
    .diag-bar-fill { height: 100%; width: 0; background: var(--accent); }
    .diag-bar-fill.low { background: var(--warn); }
    .diag-bar-base { position: absolute; top: 0; bottom: 0; left: 33.33%; width: 1px; background: var(--muted); }
    .diag-bar-num { flex: none; width: 40px; text-align: right; font-variant-numeric: tabular-nums; }
```

And add the fill transition inside the existing `@media (prefers-reduced-motion: no-preference)` block (next to the `.diag-btn` transition):

```css
    .diag-bar-fill { transition: width .2s var(--ease); }
```

- [ ] **Step 3: Lint** — Run: `npm run lint` → clean.

- [ ] **Step 4: Manual smoke** — Load *Image quality: SNR, CNR, resolution & the trade-offs*; toggle each parameter; confirm the SNR bar grows for thick slice / more NEX and shrinks (turns warn) for fine matrix / high BW, the scan-time bar grows for fine matrix / more NEX, and the baseline tick sits at 1/3 of the track.

- [ ] **Step 5: Commit**

```bash
git add web/course_diagrams.js web/course.html
git commit -m "feat(course): SNR and scan-time trade-off diagram"
```

---

### Task 3: k-space reconstruction widget (canvas)

**Files:** Modify `web/course_diagrams.js`, `web/course.html`

**Interfaces:** Consumes `figure`, `el`; `M.fft2d`, `M.fftshift2d`. Produces `BUILDERS["kspace-recon"]`.

- [ ] **Step 1: Add the builder**

In `web/course_diagrams.js`, next to the other builders:

```js
  // ---- Widget: k-space center vs periphery (real reconstruction) ---- //
  function buildKspaceRecon() {
    var fig = figure("k-space", "k-space holds the image's spatial frequencies. The center is low frequency: overall contrast and brightness. The edges are high frequency: fine detail and sharp borders. Keep only part of k-space, inverse-transform, and see what each region carries.");
    var N = 64, img = new Array(N * N), x, y, i;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) {
        var dx = x - N / 2, dy = y - N / 2;
        var v = (dx * dx + dy * dy) < (N * 0.28) * (N * 0.28) ? 0.8 : 0.08;
        if ((x > N * 0.30 && x < N * 0.34) || (y > N * 0.62 && y < N * 0.66)) v = 1.0;
        img[y * N + x] = v;
      }
    }
    var kre = img.slice(), kim = new Array(N * N);
    for (i = 0; i < N * N; i++) kim[i] = 0;
    M.fft2d(kre, kim, N, false);
    M.fftshift2d(kre, N); M.fftshift2d(kim, N);
    var R = N * 0.12;
    var kCanvas = document.createElement("canvas"); kCanvas.width = N; kCanvas.height = N; kCanvas.className = "diag-canvas";
    var iCanvas = document.createElement("canvas"); iCanvas.width = N; iCanvas.height = N; iCanvas.className = "diag-canvas";
    var kctx = kCanvas.getContext("2d"), ictx = iCanvas.getContext("2d");
    var readout = el("div", { class: "diag-readout" });
    function render(mode) {
      var mre = kre.slice(), mim = kim.slice(), p, gx, gy;
      for (gy = 0; gy < N; gy++) {
        for (gx = 0; gx < N; gx++) {
          var rx = gx - N / 2, ry = gy - N / 2, inC = (rx * rx + ry * ry) <= R * R;
          var keep = mode === "full" || (mode === "center" && inC) || (mode === "edges" && !inC);
          if (!keep) { mre[gy * N + gx] = 0; mim[gy * N + gx] = 0; }
        }
      }
      var kdata = kctx.createImageData(N, N), kmag = new Array(N * N), kmax = 0;
      for (p = 0; p < N * N; p++) { kmag[p] = Math.log(1 + Math.sqrt(mre[p] * mre[p] + mim[p] * mim[p])); if (kmag[p] > kmax) kmax = kmag[p]; }
      for (p = 0; p < N * N; p++) { var kg = Math.round(255 * kmag[p] / (kmax || 1)); kdata.data[p * 4] = kg; kdata.data[p * 4 + 1] = kg; kdata.data[p * 4 + 2] = kg; kdata.data[p * 4 + 3] = 255; }
      kctx.putImageData(kdata, 0, 0);
      if (mode !== "full") { kctx.strokeStyle = "#5db0ef"; kctx.lineWidth = 1; kctx.beginPath(); kctx.arc(N / 2, N / 2, R, 0, 2 * Math.PI); kctx.stroke(); }
      var sre = mre.slice(), sim = mim.slice();
      M.fftshift2d(sre, N); M.fftshift2d(sim, N);
      M.fft2d(sre, sim, N, true);
      var idata = ictx.createImageData(N, N), mag = new Array(N * N), imax = 0;
      for (p = 0; p < N * N; p++) { mag[p] = Math.sqrt(sre[p] * sre[p] + sim[p] * sim[p]); if (mag[p] > imax) imax = mag[p]; }
      for (p = 0; p < N * N; p++) { var ig = Math.round(255 * mag[p] / (imax || 1)); idata.data[p * 4] = ig; idata.data[p * 4 + 1] = ig; idata.data[p * 4 + 2] = ig; idata.data[p * 4 + 3] = 255; }
      ictx.putImageData(idata, 0, 0);
      readout.textContent = mode === "center" ? "Center only (low-pass): full contrast returns but the image is blurred, fine detail is gone."
        : mode === "edges" ? "Edges only (high-pass): only sharp borders survive, overall contrast is gone."
        : "Full k-space: the complete image.";
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [kCanvas, el("figcaption", { class: "diag-canvas-cap", text: "k-space" })]));
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [iCanvas, el("figcaption", { class: "diag-canvas-cap", text: "image" })]));
    fig.appendChild(stage);
    var controls = el("div", { class: "diag-controls" });
    [["Center (low-pass)", "center"], ["Edges (high-pass)", "edges"], ["Full", "full"]].forEach(function (pr) {
      var b = el("button", { type: "button", class: "diag-btn" + (pr[1] === "full" ? " on" : ""), text: pr[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on");
        render(pr[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    render("full");
    return fig;
  }
```

Register it (completes all nine):

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle, "ir-nulling": buildIrNulling, "dwi-bvalue": buildDwiBvalue, "snr-tradeoff": buildSnrTradeoff, "kspace-recon": buildKspaceRecon };
```

- [ ] **Step 2: Add canvas CSS to `web/course.html`**

```css
    .diag-kspace { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-start; }
    .diag-canvas-wrap { margin: 0; text-align: center; }
    .diag-canvas { width: 140px; height: 140px; image-rendering: pixelated; border: 1px solid var(--line-2); border-radius: 4px; background: #000; display: block; }
    .diag-canvas-cap { font-size: 11px; color: var(--muted); margin-top: 4px; }
```

- [ ] **Step 3: Lint** — Run: `npm run lint` → clean.

- [ ] **Step 4: Manual smoke** — Load *Data acquisition: k-space, encoding and the Fourier transform*; confirm Full shows the phantom (disc + bars) and its bright-centered k-space; Center (low-pass) outlines the center, k-space keeps only the middle, and the image goes blurry but full-contrast; Edges (high-pass) keeps the periphery and the image shows only outlines. Toggling is instant.

- [ ] **Step 5: Commit**

```bash
git add web/course_diagrams.js web/course.html
git commit -m "feat(course): k-space center vs periphery reconstruction diagram"
```

---

### Task 4: Prototype, final verification, PR

**Files:** none (verification + PR)

- [ ] **Step 1: Artifact prototype**

Regenerate the standalone prototype from `web/course_diagrams_math.js` + `web/course_diagrams.js` with mock `.edu` cards for all nine diagrams (seven prior + the two new titles), reusing the `.diag-*` CSS (include the new bar + canvas rules). Publish via the Artifact tool (favicon 🧲). Canvas renders in the Artifact sandbox (the phantom is generated in JS, no external asset).

- [ ] **Step 2: Full verification**

Run: `npm run test:web` → PASS. `npm run lint` → clean. `ruff check src/ tests/` → clean.

- [ ] **Step 3: PR + gate-merge**

```bash
git push -u origin HEAD
gh pr create --title "feat(course): physics diagrams batch 3 (SNR trade-offs + k-space reconstruction)" --body "$(cat <<'EOF'
Two diagrams with new primitives, reusing the diagram mounting: an SNR/scan-time trade-off calculator (HTML bars, relative to a baseline) and a k-space center-vs-periphery widget that does a real inverse FFT on a synthetic phantom (canvas) so learners see low-pass = blurry-but-full-contrast and high-pass = edges-only. New math (radix-2 fft1d/fft2d, fftshift2d, snrScanRel) is unit-tested with round-trip assertions; the guard test covers the two new DIAGRAM_MAP keys against real education titles. No new files, no DB change, no course.js/sw.js/eslint change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Then gate-merge:

```bash
sleep 20 && gh pr checks --watch --interval 20 && gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Update memory**

Append batch 3 (the two widgets, the FFT/canvas primitive, the bar primitive) to `project_course_diagrams.md`.

---

## Self-Review

**Spec coverage:** FFT + shift + SNR math + 2 map keys + tests (Task 1); SNR bars widget + CSS (Task 2); k-space canvas widget + CSS (Task 3); prototype/verify/PR (Task 4). ✓

**Placeholder scan:** every code step has complete code. ✓

**Type consistency:** new math names (`fft1d`, `fft2d`, `fftshift2d`, `snrScanRel`) defined + exported in Task 1, consumed with those names in Tasks 2–3. Both widgets use only module-scope `figure`/`el` and canvas/`document` browser globals — neither touches `makePlot` or `svgEl`. `BUILDERS` grows to exactly the nine ids that match `DIAGRAM_MAP` values (asserted in Task 1's test). ✓

**No-wiring check:** scripts, attach hook, sw.js precache, eslint globals already cover `course_diagrams*.js`; canvas/`document` are in the existing `globals.browser` eslint set — no eslint change. ✓

**Risk note:** FFT correctness is the one non-trivial numerical piece; Task 1's round-trip + delta/DC + shift tests pin it before any widget renders. The k-space builder's mask/render is visually verified in Task 3/4.
