# Course Physics Diagrams — Batch 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Four advanced-imaging diagrams — parallel imaging, k-space trajectories, chemical shift/Dixon, Gibbs ringing — reusing the batch 1-3 engine. Brings the course to 13 diagrams.

**Architecture:** New pure math `fatWaterSignal` (node-tested); four widget builders + shared canvas helpers in `course_diagrams.js`; four `DIAGRAM_MAP` keys; one CSS rule. The FFT (`fft1d/fft2d/fftshift2d`) and `makePlot`/`svgEl`/`el`/`figure` already exist. No new files; no course.js/sw.js/eslint change.

## Global Constraints

- Classic browser scripts; UMD for the pure module. No emoji/pills/gradients; theme tokens only; **no em dashes in visible strings**. US spelling.
- Do NOT modify read-tracking, PROGRESS_KEYS, buildRail, navigation, course.js, sw.js, eslint.config.mjs.
- 1.5 T teaching approximations; captions say so. No `Co-Authored-By`.
- **Invariant:** every `DIAGRAM_MAP` key MUST be an exact `kind:"education"` `body.title` in `data/course_content.json` (guard test enforces).

---

### Task 1: `fatWaterSignal` math + DIAGRAM_MAP keys + tests

**Files:** Modify `web/course_diagrams_math.js`, `web/course_diagrams_math.test.mjs`

- [ ] **Step 1: Write the failing tests**

Extend the destructure on line 6 of the test to add `fatWaterSignal`:

```js
const { mz, mxy, t2star, spinEchoSignal, ernstAngle, spoiledGreSignal, irMz, nullTI, dwiSignal, fft1d, fft2d, fftshift2d, snrScanRel, fatWaterSignal, classifyWeighting, sample, TISSUES, ADCS, DIAGRAM_MAP } = Math2;
```

Add this test (after the snrScanRel test):

```js
test("fatWaterSignal: in-phase at TE=0 and 1/df, opposed at 1/(2df)", () => {
  const df = 220;
  assert.ok(Math.abs(fatWaterSignal(0, 0.5, df) - 1) < 1e-9);
  assert.ok(Math.abs(fatWaterSignal(1000 / df, 0.5, df) - 1) < 1e-6);          // in-phase -> add -> 1
  assert.ok(Math.abs(fatWaterSignal(1000 / (2 * df), 0.5, df)) < 1e-6);        // opposed, equal -> 0
  assert.ok(Math.abs(fatWaterSignal(1000 / (2 * df), 0.3, df) - 0.4) < 1e-6);  // |0.7 - 0.3|
});
```

Update the DIAGRAM_MAP block in the `"data tables are well-formed"` test — add four assertions (note the fat-suppression key now has TWO ids) and change `ids` to 13 sorted:

```js
  assert.deepEqual(DIAGRAM_MAP["Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration"], ["parallel-imaging"]);
  assert.deepEqual(DIAGRAM_MAP["Spatial encoding: slice, phase, and frequency gradients into k-space"], ["kspace-trajectories"]);
  assert.deepEqual(DIAGRAM_MAP["Fat suppression: STIR, spectral, Dixon and water excitation"], ["ir-nulling", "chemical-shift"]);
  assert.deepEqual(DIAGRAM_MAP["MR image quality: SNR, scan time, and spatial resolution tradeoffs"], ["gibbs-ringing"]);
  const ids = Object.values(DIAGRAM_MAP).reduce((a, v) => a.concat(v), []).sort();
  assert.deepEqual(ids, ["chemical-shift", "dwi-bvalue", "ernst-angle", "gibbs-ringing", "ir-nulling", "kspace-recon", "kspace-trajectories", "parallel-imaging", "snr-tradeoff", "t1-recovery", "t2-decay", "t2-vs-t2star", "tr-te-weighting"]);
```

- [ ] **Step 2: Run to verify fail** — `node --test web/course_diagrams_math.test.mjs` → FAIL.

- [ ] **Step 3: Implement**

In `web/course_diagrams_math.js`, add after `dwiSignal`:

```js
  // Combined fat+water transverse signal magnitude at echo time teMs. Fat precesses deltaFHz
  // slower than water, so the two vectors rephase (in phase) and dephase (opposed) as TE grows.
  function fatWaterSignal(teMs, fatFrac, deltaFHz) {
    var w = 1 - fatFrac, f = fatFrac, ph = 2 * Math.PI * deltaFHz * (teMs / 1000);
    var re = w + f * Math.cos(ph), im = f * Math.sin(ph);
    return Math.sqrt(re * re + im * im);
  }
```

Add the four `DIAGRAM_MAP` entries (add `chemical-shift` to the existing fat-suppression key; keep all others):

```js
    "Fat suppression: STIR, spectral, Dixon and water excitation": ["ir-nulling", "chemical-shift"],
    "Acquisition parameters and k-space: matrix, FOV, NEX, and acceleration": ["parallel-imaging"],
    "Spatial encoding: slice, phase, and frequency gradients into k-space": ["kspace-trajectories"],
    "MR image quality: SNR, scan time, and spatial resolution tradeoffs": ["gibbs-ringing"],
```

Add `fatWaterSignal: fatWaterSignal,` to the returned object.

- [ ] **Step 4: Run to verify pass** — `npm run test:web` → PASS (guard test covers the four new keys).

- [ ] **Step 5: Commit** — `git add web/course_diagrams_math.js web/course_diagrams_math.test.mjs && git commit -m "feat(course): batch4 math (fatWaterSignal) + 4 map keys"`

---

### Task 2: k-space trajectories widget (SVG)

**Files:** Modify `web/course_diagrams.js`, `web/course.html`

**Interfaces:** Consumes module-scope `svgEl`, `el`, `figure`. Produces `BUILDERS["kspace-trajectories"]`.

- [ ] **Step 1: Add the builder** (in `web/course_diagrams.js`, next to the other builders):

```js
  // ---- Widget: k-space sampling trajectories ---- //
  function buildKspaceTrajectories() {
    var fig = figure("k-space sampling", "How k-space gets filled. Cartesian scans one line at a time (the standard). Radial and spiral sweep through the center on every readout, so they oversample low frequencies and tolerate motion (non-Cartesian).");
    var W = 220, H = 220, cx = W / 2, cy = H / 2, Rmax = 96;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "k-space sampling pattern" });
    svg.style.maxWidth = "240px";
    svg.appendChild(svgEl("line", { class: "diag-axis", x1: cx, y1: 8, x2: cx, y2: H - 8 }));
    svg.appendChild(svgEl("line", { class: "diag-axis", x1: 8, y1: cy, x2: W - 8, y2: cy }));
    var g = svgEl("g", {});
    svg.appendChild(g);
    var readout = el("div", { class: "diag-readout" });
    function draw(mode) {
      while (g.firstChild) g.removeChild(g.firstChild);
      var pts = [], a, r, rr, t, ang, rad, kx, ky;
      if (mode === "cartesian") {
        for (ky = -11; ky <= 11; ky++) { for (kx = -22; kx <= 22; kx++) { pts.push([kx / 22 * Rmax, ky / 11 * Rmax]); } }
      } else if (mode === "radial") {
        for (var s = 0; s < 16; s++) { a = Math.PI * s / 16; for (r = -22; r <= 22; r++) { rr = r / 22 * Rmax; pts.push([rr * Math.cos(a), rr * Math.sin(a)]); } }
      } else {
        for (t = 0; t <= 1.0001; t += 0.006) { ang = t * 2 * Math.PI * 6; rad = t * Rmax; pts.push([rad * Math.cos(ang), rad * Math.sin(ang)]); }
      }
      pts.forEach(function (p) { g.appendChild(svgEl("circle", { class: "diag-kpt", cx: (cx + p[0]).toFixed(1), cy: (cy + p[1]).toFixed(1), r: "1.1" })); });
      readout.textContent = mode === "cartesian" ? "Cartesian: parallel lines, one phase-encode step per TR. Simple and robust, but slower."
        : mode === "radial" ? "Radial: spokes through the center. Every spoke resamples low frequencies, so motion averages out."
          : "Spiral: one winding readout from the center outward. Very fast coverage, sensitive to off-resonance.";
    }
    fig.appendChild(svg);
    var controls = el("div", { class: "diag-controls" });
    [["Cartesian", "cartesian"], ["Radial", "radial"], ["Spiral", "spiral"]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === "cartesian" ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); draw(p[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    draw("cartesian");
    return fig;
  }
```

Register it in `BUILDERS` (append `"kspace-trajectories": buildKspaceTrajectories`, keep all nine existing).

- [ ] **Step 2: CSS** — in `web/course.html`, near the other `.diag-*` rules, add:

```css
    .diag-kpt { fill: var(--accent); }
```

- [ ] **Step 3: Lint** — `npm run lint` → clean.

- [ ] **Step 4: Manual smoke** — Load *Spatial encoding: slice, phase, and frequency gradients into k-space*; confirm Cartesian shows a dot grid, Radial shows spokes through center, Spiral shows a spiral, and the readout updates.

- [ ] **Step 5: Commit** — `git add web/course_diagrams.js web/course.html && git commit -m "feat(course): k-space sampling trajectory diagram (Cartesian/radial/spiral)"`

---

### Task 3: chemical shift / Dixon widget (curve)

**Files:** Modify `web/course_diagrams.js`

**Interfaces:** Consumes `makePlot`, `el`, `figure`; `M.fatWaterSignal`, `M.sample`. Produces `BUILDERS["chemical-shift"]`.

- [ ] **Step 1: Add the builder**:

```js
  // ---- Widget: chemical shift and the Dixon method ---- //
  function buildChemicalShift() {
    var fig = figure("Chemical shift and Dixon", "Fat precesses about 220 Hz slower than water at 1.5 T, so as TE grows the two signals drift in and out of phase. Acquiring an in-phase and an opposed-phase echo is how the Dixon method separates fat from water (1.5 T, approximate).");
    var dF = 220, xMax = 10, state = { fatFrac: 0.5 };
    var opp = 1000 / (2 * dF), inph = 1000 / dF;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "TE (ms)", yLabel: "signal", xTicks: [0, 2.5, 5, 7.5, 10], title: "Combined fat and water signal versus echo time" });
    plot.addAxes();
    var curve = null, mO = null, mI = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (curve) curve.remove(); if (mO) mO.remove(); if (mI) mI.remove();
      var pts = M.sample(function (te) { return M.fatWaterSignal(te, state.fatFrac, dF); }, xMax, 100);
      curve = plot.addCurve(pts, "");
      mO = plot.addMarker(opp, "", "opp"); mI = plot.addMarker(inph, "", "in");
      readout.textContent = "Opposed-phase at " + opp.toFixed(1) + " ms (fat and water subtract), in-phase at " + inph.toFixed(1) + " ms (they add). Fat fraction " + Math.round(state.fatFrac * 100) + "%.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "Fat fraction:" }));
    [["10%", 0.1], ["30%", 0.3], ["50%", 0.5]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.fatFrac ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.fatFrac = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    redraw();
    return fig;
  }
```

Register it (append `"chemical-shift": buildChemicalShift`, keep all prior).

- [ ] **Step 2: Lint** — `npm run lint` → clean.

- [ ] **Step 3: Manual smoke** — Load *Fat suppression: STIR, spectral, Dixon and water excitation*; confirm the IR nulling widget AND a second "Chemical shift" curve both render; the curve dips to a minimum near 2.3 ms and returns to 1 near 4.6 ms; fat-fraction presets change the opposed-phase depth.

- [ ] **Step 4: Commit** — `git add web/course_diagrams.js && git commit -m "feat(course): chemical shift / Dixon in-and-opposed-phase diagram"`

---

### Task 4: shared canvas helpers + kspace-recon refactor + parallel imaging + Gibbs ringing

**Files:** Modify `web/course_diagrams.js`

**Interfaces:** Adds module-scope `phantom(N)`, `centeredSpectrum(img,N)`, `drawKMag(ctx,re,im,N)`, `drawIMag(ctx,re,im,N)`, `reconMag(ctx,mre,mim,N)`. Produces `BUILDERS["parallel-imaging"]`, `BUILDERS["gibbs-ringing"]`. Refactors `buildKspaceRecon` to use the helpers.

- [ ] **Step 1: Add the shared helpers** (module scope, near `figure`):

```js
  // ---- shared canvas helpers for the FFT widgets ---- //
  // 64x64 teaching phantom: a bright disc (contrast) plus two sharp bars (detail/edges).
  function phantom(N) {
    var img = new Array(N * N), x, y;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) {
        var dx = x - N / 2, dy = y - N / 2;
        var v = (dx * dx + dy * dy) < (N * 0.24) * (N * 0.24) ? 0.8 : 0.08;
        if ((x > N * 0.30 && x < N * 0.34) || (y > N * 0.60 && y < N * 0.64)) v = 1.0;
        img[y * N + x] = v;
      }
    }
    return img;
  }
  // Forward-transform a real image to a DC-centered complex spectrum { re, im }.
  function centeredSpectrum(img, N) {
    var re = img.slice(), im = new Array(N * N), i;
    for (i = 0; i < N * N; i++) im[i] = 0;
    M.fft2d(re, im, N, false); M.fftshift2d(re, N); M.fftshift2d(im, N);
    return { re: re, im: im };
  }
  // Draw log-magnitude of a centered complex spectrum (grayscale) to a 2D context.
  function drawKMag(ctx, re, im, N) {
    var d = ctx.createImageData(N, N), mag = new Array(N * N), mx = 0, p;
    for (p = 0; p < N * N; p++) { mag[p] = Math.log(1 + Math.sqrt(re[p] * re[p] + im[p] * im[p])); if (mag[p] > mx) mx = mag[p]; }
    for (p = 0; p < N * N; p++) { var g = Math.round(255 * mag[p] / (mx || 1)); d.data[p * 4] = g; d.data[p * 4 + 1] = g; d.data[p * 4 + 2] = g; d.data[p * 4 + 3] = 255; }
    ctx.putImageData(d, 0, 0);
  }
  // Draw magnitude of a complex image (grayscale) to a 2D context.
  function drawIMag(ctx, re, im, N) {
    var d = ctx.createImageData(N, N), mag = new Array(N * N), mx = 0, p;
    for (p = 0; p < N * N; p++) { mag[p] = Math.sqrt(re[p] * re[p] + im[p] * im[p]); if (mag[p] > mx) mx = mag[p]; }
    for (p = 0; p < N * N; p++) { var g = Math.round(255 * mag[p] / (mx || 1)); d.data[p * 4] = g; d.data[p * 4 + 1] = g; d.data[p * 4 + 2] = g; d.data[p * 4 + 3] = 255; }
    ctx.putImageData(d, 0, 0);
  }
  // Inverse-transform a centered masked spectrum (copies) and draw its magnitude image.
  function reconMag(ctx, mre, mim, N) {
    var sre = mre.slice(), sim = mim.slice();
    M.fftshift2d(sre, N); M.fftshift2d(sim, N); M.fft2d(sre, sim, N, true);
    drawIMag(ctx, sre, sim, N);
  }
```

- [ ] **Step 2: Refactor `buildKspaceRecon` to use the helpers.** In the existing `buildKspaceRecon`, replace the inline phantom build + forward FFT with `var N = 64, sp = centeredSpectrum(phantom(N), N), kre = sp.re, kim = sp.im;` and, inside its `render(mode)`, replace the inline k-space-magnitude draw with `drawKMag(kctx, mre, mim, N);` (keep the existing arc-outline code that runs after it for non-full modes) and replace the inline inverse-FFT + image draw with `reconMag(ictx, mre, mim, N);`. Behavior is identical; only the drawing/transform code is now shared.

- [ ] **Step 3: Add `buildParallelImaging`**:

```js
  // ---- Widget: parallel imaging (undersampling and aliasing) ---- //
  function buildParallelImaging() {
    var fig = figure("Parallel imaging", "Skipping k-space lines shortens the scan but shrinks the phase field of view, so the image aliases and wraps onto itself. Parallel imaging (SENSE, GRAPPA) uses several receive coils to unfold that wrap. Acceleration R is how many phase-encode lines are skipped (unfolding is not simulated here).");
    var N = 64, sp = centeredSpectrum(phantom(N), N), kre = sp.re, kim = sp.im;
    var kC = document.createElement("canvas"); kC.width = N; kC.height = N; kC.className = "diag-canvas";
    var iC = document.createElement("canvas"); iC.width = N; iC.height = N; iC.className = "diag-canvas";
    var kctx = kC.getContext("2d"), ictx = iC.getContext("2d");
    var readout = el("div", { class: "diag-readout" });
    function render(R) {
      var mre = kre.slice(), mim = kim.slice(), ky, kx;
      for (ky = 0; ky < N; ky++) {
        if (((ky - N / 2) % R + R) % R !== 0) { for (kx = 0; kx < N; kx++) { mre[ky * N + kx] = 0; mim[ky * N + kx] = 0; } }
      }
      drawKMag(kctx, mre, mim, N);
      reconMag(ictx, mre, mim, N);
      readout.textContent = R === 1 ? "Full sampling: no acceleration, the complete image."
        : "R = " + R + ": every " + (R === 2 ? "2nd" : "3rd") + " line kept, scan " + R + "x faster. The phase field of view drops to 1/" + R + ", so the image wraps.";
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [kC, el("figcaption", { class: "diag-canvas-cap", text: "k-space" })]));
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [iC, el("figcaption", { class: "diag-canvas-cap", text: "image" })]));
    fig.appendChild(stage);
    var controls = el("div", { class: "diag-controls" });
    [["Full", 1], ["R = 2", 2], ["R = 3", 3]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === 1 ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); render(p[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    render(1);
    return fig;
  }
```

- [ ] **Step 4: Add `buildGibbsRinging`**:

```js
  // ---- Widget: Gibbs (truncation) ringing ---- //
  function buildGibbsRinging() {
    var fig = figure("Gibbs ringing", "An image is built from a finite patch of k-space. Truncating the high frequencies (a smaller matrix) blurs sharp borders and adds faint ringing lines parallel to them, the Gibbs or truncation artifact.");
    var N = 64, sp = centeredSpectrum(phantom(N), N), kre = sp.re, kim = sp.im;
    var kC = document.createElement("canvas"); kC.width = N; kC.height = N; kC.className = "diag-canvas";
    var iC = document.createElement("canvas"); iC.width = N; iC.height = N; iC.className = "diag-canvas";
    var kctx = kC.getContext("2d"), ictx = iC.getContext("2d");
    var readout = el("div", { class: "diag-readout" });
    function render(keep) {
      var mre = kre.slice(), mim = kim.slice(), ky, kx, half = keep / 2;
      for (ky = 0; ky < N; ky++) {
        for (kx = 0; kx < N; kx++) {
          if (Math.abs(ky - N / 2) >= half || Math.abs(kx - N / 2) >= half) { mre[ky * N + kx] = 0; mim[ky * N + kx] = 0; }
        }
      }
      drawKMag(kctx, mre, mim, N);
      reconMag(ictx, mre, mim, N);
      readout.textContent = keep === N ? "Full matrix (" + N + "): sharp edges, no ringing."
        : "Matrix " + keep + ": only the central " + keep + "x" + keep + " of k-space is kept. Edges blur and ringing appears alongside them.";
    }
    var stage = el("div", { class: "diag-kspace" });
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [kC, el("figcaption", { class: "diag-canvas-cap", text: "k-space" })]));
    stage.appendChild(el("figure", { class: "diag-canvas-wrap" }, [iC, el("figcaption", { class: "diag-canvas-cap", text: "image" })]));
    fig.appendChild(stage);
    fig.appendChild(el("span", { class: "diag-glabel", text: "Matrix:" }));
    var controls = el("div", { class: "diag-controls" });
    [["64", 64], ["32", 32], ["16", 16]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === 64 ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (z) { z.classList.remove("on"); });
        b.classList.add("on"); render(p[1]);
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls); fig.appendChild(readout);
    render(64);
    return fig;
  }
```

Register both (append `"parallel-imaging": buildParallelImaging, "gibbs-ringing": buildGibbsRinging`, keeping all prior — completes all 13).

- [ ] **Step 5: Lint + tests** — `npm run lint` → clean; `npm run test:web` → still PASS.

- [ ] **Step 6: Manual smoke** — Load *Acquisition parameters and k-space...*: Full shows the phantom, R=2/R=3 wrap it. Load *MR image quality: SNR, scan time...*: matrix 64 sharp, 32/16 show ringing. Confirm the existing k-space-recon widget still works (refactor didn't break it).

- [ ] **Step 7: Commit** — `git add web/course_diagrams.js && git commit -m "feat(course): parallel-imaging + Gibbs-ringing diagrams; shared FFT-canvas helpers"`

---

### Task 5: Prototype, final verification, PR

- [ ] **Step 1: Artifact prototype** — regenerate the standalone prototype from `web/course_diagrams_math.js` + `web/course_diagrams.js` with mock `.edu` cards for all 13 diagrams (11 prior + the 2 new titles; the fat-suppression card now hosts ir-nulling + chemical-shift), reusing the `.diag-*` CSS (add `.diag-kpt`). Publish via the Artifact tool (favicon 🧲).

- [ ] **Step 2: Full verification** — `npm run test:web` PASS; `npm run lint` clean; `ruff check src/ tests/` clean.

- [ ] **Step 3: PR + gate-merge**:

```bash
git push -u origin HEAD
gh pr create --title "feat(course): physics diagrams batch 4 (parallel imaging, k-space trajectories, chemical shift, Gibbs)" --body "$(cat <<'EOF'
Four advanced-imaging diagrams reusing the engine (no new files): parallel imaging (undersampling -> aliasing, canvas+FFT), k-space trajectories (Cartesian/radial/spiral, SVG), chemical shift / Dixon (in/opposed phase vs TE, curve), Gibbs ringing (k-space truncation, canvas+FFT). Adds tested math fatWaterSignal; extracts shared FFT-canvas helpers (phantom/centeredSpectrum/drawKMag/drawIMag/reconMag) and refactors the k-space-recon widget onto them. Guard test covers the four new DIAGRAM_MAP keys against real education titles. No DB change; no course.js/sw.js/eslint change.

Course now has 13 interactive diagrams.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
sleep 20 && gh pr checks --watch --interval 20 && gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Update memory** — append batch 4 (the 4 widgets, the shared FFT-canvas helpers, fatWaterSignal) to `project_course_diagrams.md`.

---

## Self-Review

**Spec coverage:** fatWaterSignal + keys + tests (T1); trajectories (T2); chemical shift (T3); shared helpers + kspace-recon refactor + parallel + gibbs (T4); prototype/verify/PR (T5). ✓
**Placeholder scan:** complete code in every step. ✓
**Type consistency:** `fatWaterSignal` defined/exported T1, consumed T3. Helpers defined T4 used by parallel/gibbs/kspace-recon. `svgEl` already module-scope (batch 1) — trajectories uses it, no hoist. `BUILDERS` grows to 13 ids matching `DIAGRAM_MAP` values (asserted T1). ✓
**No-wiring check:** scripts/course.js/sw.js/eslint already cover course_diagrams*.js; canvas/`document` in the existing browser eslint globals — no eslint change. ✓
**Risk:** the kspace-recon refactor (T4 Step 2) touches a shipped widget — its manual smoke (T4 Step 6) and the final whole-branch review must confirm it still renders identically.
