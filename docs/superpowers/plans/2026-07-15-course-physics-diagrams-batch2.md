# Course Physics Diagrams — Batch 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three more interactive SVG diagrams to the course — Ernst angle, inversion-recovery nulling (STIR/FLAIR), and DWI vs b-value — reusing the batch 1 engine.

**Architecture:** New pure physics functions in `web/course_diagrams_math.js` (node-tested); three new widget builders + one backward-compatible `makePlot` tweak in `web/course_diagrams.js`; three new `DIAGRAM_MAP` keys (real `kind:"education"` titles). No new files, no sw.js/eslint/course.js changes (wiring already exists from PR #438). One CSS rule re-added to `web/course.html`.

**Tech Stack:** Vanilla ES2022 classic scripts, inline SVG, `node --test`, ESLint flat config, existing course CSS tokens.

## Global Constraints

- Classic browser scripts (`sourceType: "script"`); pure module keeps its UMD wrapper.
- UI: no emoji, no pills, no gradients; flat accents on dark bones; theme tokens (`--accent`, `--ok`, `--warn`, `--muted`, `--line-2`, `--ease`). No em dashes in any visible string.
- Motion only when `!reduceMotion`; never auto-play (initial `redraw(false)` / `redraw()`).
- Do NOT modify read-tracking, `PROGRESS_KEYS`, `buildRail`, navigation, `sw.js`, `eslint.config.mjs`, or `course.js`.
- Physics are 1.5 T teaching approximations; captions say so. US spelling.
- No `Co-Authored-By` trailer.
- **Invariant:** every `DIAGRAM_MAP` key MUST be an exact `kind:"education"` `body.title` in `data/course_content.json` (guard test enforces).

---

### Task 1: Math functions + ADC table + DIAGRAM_MAP keys + tests

**Files:**
- Modify: `web/course_diagrams_math.js`, `web/course_diagrams_math.test.mjs`

**Interfaces:**
- Produces (pure): `ernstAngle(TR,T1)`, `spoiledGreSignal(alpha,TR,T1)`, `irMz(t,T1)`, `nullTI(T1)`, `dwiSignal(b,ADC)`, `ADCS` (array of `{id,label,adc}`), and three new `DIAGRAM_MAP` entries.

- [ ] **Step 1: Write the failing tests**

Add to `web/course_diagrams_math.test.mjs` — first extend the destructure on line 6 to include the new names:

```js
const { mz, mxy, t2star, spinEchoSignal, ernstAngle, spoiledGreSignal, irMz, nullTI, dwiSignal, classifyWeighting, sample, TISSUES, ADCS, DIAGRAM_MAP } = Math2;
```

Then add these tests (place them after the `spinEchoSignal` test):

```js
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
```

Also update the DIAGRAM_MAP assertions inside the existing `"data tables are well-formed"` test — add three `deepEqual`s and change the `ids` expectation to the seven sorted ids:

```js
  assert.deepEqual(DIAGRAM_MAP["Flip angle: the Ernst angle and the SAR trade-off"], ["ernst-angle"]);
  assert.deepEqual(DIAGRAM_MAP["Fat suppression: STIR, spectral, Dixon and water excitation"], ["ir-nulling"]);
  assert.deepEqual(DIAGRAM_MAP["Diffusion in disease: stroke, abscess and cellular tumors"], ["dwi-bvalue"]);
  const ids = Object.values(DIAGRAM_MAP).reduce((a, v) => a.concat(v), []).sort();
  assert.deepEqual(ids, ["dwi-bvalue", "ernst-angle", "ir-nulling", "t1-recovery", "t2-decay", "t2-vs-t2star", "tr-te-weighting"]);
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_diagrams_math.test.mjs`
Expected: FAIL (new functions undefined / map keys missing).

- [ ] **Step 3: Implement**

In `web/course_diagrams_math.js`, add the functions after `spinEchoSignal`:

```js
  // Ernst angle (radians): the flip angle that maximizes spoiled-GRE signal at a given TR/T1.
  function ernstAngle(TR, T1) { return Math.acos(Math.exp(-TR / T1)); }

  // Spoiled gradient-echo steady-state signal vs flip angle alpha (radians).
  function spoiledGreSignal(alpha, TR, T1) {
    var e1 = Math.exp(-TR / T1);
    return Math.sin(alpha) * (1 - e1) / (1 - Math.cos(alpha) * e1);
  }

  // Inversion-recovery longitudinal magnetization: starts at -1 after the 180, recovers to +1.
  function irMz(t, T1) { return 1 - 2 * Math.exp(-t / T1); }

  // Inversion time that nulls a tissue (irMz crosses zero).
  function nullTI(T1) { return T1 * Math.LN2; }

  // Diffusion-weighted signal: mono-exponential decay with b-value and ADC.
  function dwiSignal(b, ADC) { return Math.exp(-b * ADC); }
```

Add the ADC table after `TISSUES`:

```js
  // Apparent diffusion coefficients (mm^2/s), 1.5 T teaching approximations.
  var ADCS = [
    { id: "restricted", label: "Restricted (stroke)", adc: 0.0006 },
    { id: "normal", label: "Normal tissue", adc: 0.0010 },
    { id: "free", label: "Free water (CSF)", adc: 0.0030 },
  ];
```

Add the three `DIAGRAM_MAP` entries (keep the existing three):

```js
  var DIAGRAM_MAP = {
    "Relaxation: T1 spin-lattice and T2 spin-spin": ["t1-recovery", "t2-decay"],
    "Dephasing, T2 vs T2*, and the spin-echo refocusing pulse": ["t2-vs-t2star"],
    "TR, TE, TI, and flip angle: setting image contrast": ["tr-te-weighting"],
    "Flip angle: the Ernst angle and the SAR trade-off": ["ernst-angle"],
    "Fat suppression: STIR, spectral, Dixon and water excitation": ["ir-nulling"],
    "Diffusion in disease: stroke, abscess and cellular tumors": ["dwi-bvalue"],
  };
```

Extend the return object to export the new names:

```js
  return { mz: mz, mxy: mxy, t2star: t2star, spinEchoSignal: spinEchoSignal,
    ernstAngle: ernstAngle, spoiledGreSignal: spoiledGreSignal, irMz: irMz, nullTI: nullTI,
    dwiSignal: dwiSignal, classifyWeighting: classifyWeighting, sample: sample,
    TISSUES: TISSUES, ADCS: ADCS, DIAGRAM_MAP: DIAGRAM_MAP };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:web`
Expected: PASS (all files). The guard test `"every DIAGRAM_MAP key is a real education-card title"` passes because the three new keys are real education titles.

- [ ] **Step 5: Commit**

```bash
git add web/course_diagrams_math.js web/course_diagrams_math.test.mjs
git commit -m "feat(course): batch2 physics (Ernst, IR/nullTI, DWI) + ADC table + map keys"
```

---

### Task 2: Ernst angle widget

**Files:**
- Modify: `web/course_diagrams.js`

**Interfaces:**
- Consumes: `makePlot`, `figure`, `el`, `reduceMotion`; `M.spoiledGreSignal`, `M.ernstAngle`, `M.sample`, `M.TISSUES`.
- Produces: `BUILDERS["ernst-angle"]`.

- [ ] **Step 1: Add the builder**

In `web/course_diagrams.js`, add next to the other builders:

```js
  // ---- Widget: Ernst angle ---- //
  function buildErnstAngle() {
    var fig = figure("Ernst angle", "Ernst angle: for a given TR, one flip angle gives the most spoiled-GRE signal. Going higher adds SAR for little gain (1.5 T, approximate).");
    var state = { tissue: M.TISSUES[1], tr: 500 };
    var xMax = 90;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "flip angle (deg)", yLabel: "signal",
      xTicks: [0, 30, 60, 90], title: "Spoiled gradient-echo signal versus flip angle" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw(animate) {
      if (curve) curve.remove(); if (marker) marker.remove();
      var pts = M.sample(function (deg) {
        return M.spoiledGreSignal(deg * Math.PI / 180, state.tr, state.tissue.t1); }, xMax, 90);
      curve = plot.addCurve(pts, "");
      if (animate) plot.animateCurve(curve, pts);
      var aeDeg = M.ernstAngle(state.tr, state.tissue.t1) * 180 / Math.PI;
      marker = plot.addMarker(aeDeg, "", Math.round(aeDeg) + "°");
      readout.textContent = "Ernst angle " + Math.round(aeDeg) + "° for TR " + state.tr
        + " ms, " + state.tissue.label + " (T1 " + state.tissue.t1 + " ms). Above it, more flip angle costs SAR for little extra signal.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    var sel = el("select", { class: "diag-select", "aria-label": "Tissue" });
    M.TISSUES.forEach(function (ti, i) {
      var o = el("option", { value: ti.id, text: ti.label });
      if (i === 1) o.setAttribute("selected", "selected");
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      state.tissue = M.TISSUES.filter(function (t) { return t.id === sel.value; })[0];
      redraw(false);
    });
    controls.appendChild(sel);
    [["Short", 150], ["Medium", 500], ["Long", 1500]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.tr ? " on" : ""), text: "TR " + p[0] });
      b.addEventListener("click", function () {
        state.tr = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw(false);
      });
      controls.appendChild(b);
    });
    if (!reduceMotion) {
      var play = el("button", { type: "button", class: "diag-btn diag-play", text: "▸ Play" });
      play.addEventListener("click", function () { redraw(true); });
      controls.appendChild(play);
    }
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw(false);
    return fig;
  }
```

Register it in `BUILDERS` (add the entry, keep the existing four):

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle };
```

- [ ] **Step 2: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 3: Manual smoke**

Load *Flip angle: the Ernst angle and the SAR trade-off*; confirm the signal-vs-angle curve renders, tissue / TR presets reshape it, the marker sits at the Ernst angle (peak), and Play sweeps.

- [ ] **Step 4: Commit**

```bash
git add web/course_diagrams.js
git commit -m "feat(course): interactive Ernst angle diagram"
```

---

### Task 3: Inversion-recovery nulling widget + makePlot negative-y support

**Files:**
- Modify: `web/course_diagrams.js`, `web/course.html`

**Interfaces:**
- Consumes: `makePlot` (extended here), `figure`, `el`; `M.irMz`, `M.nullTI`, `M.sample`, `M.TISSUES`.
- Produces: `BUILDERS["ir-nulling"]`; `makePlot` gains `opts.yMin`.

- [ ] **Step 1: Extend `makePlot` for a negative y-axis**

In `web/course_diagrams.js` `makePlot`, replace the `toY` definition. Find:

```js
    function toY(v) { return y0 - (y0 - y1) * (v / (opts.yMax || 1)); }
```

Replace with:

```js
    var yMin = opts.yMin || 0, yMax = opts.yMax || 1;
    function toY(v) { return y0 - (y0 - y1) * ((v - yMin) / (yMax - yMin)); }
```

Then, inside `addAxes`, immediately after the two axis `line` appends (the bottom and left axes) and before the y-tick loop, add a faint zero line for signed plots:

```js
      if (yMin < 0) {
        svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: toY(0), x2: x1, y2: toY(0) }));
      }
```

(For `yMin = 0`, `toY` is unchanged and no zero line is drawn — existing widgets are unaffected.)

- [ ] **Step 2: Add the builder**

```js
  // ---- Widget: inversion-recovery nulling (STIR / FLAIR) ---- //
  function buildIrNulling() {
    var fig = figure("Inversion recovery", "After a 180 pulse Mz starts at -1 and recovers. At a tissue's null time TI its signal crosses zero: STIR nulls fat, FLAIR nulls CSF. Fat blue, white matter grey, CSF red (1.5 T, approximate).");
    var fat = M.TISSUES[0], wm = M.TISSUES[1], csf = M.TISSUES[3];
    var xMax = 3000;
    var state = { ti: Math.round(M.nullTI(fat.t1)) };
    var plot = makePlot({ xMax: xMax, yMin: -1, yMax: 1, xLabel: "TI (ms)", yLabel: "Mz",
      xTicks: [0, 1000, 2000, 3000], yTicks: [-1, -0.5, 0, 0.5, 1],
      title: "Inversion-recovery curves and the null time" });
    plot.addAxes();
    plot.addCurve(M.sample(function (t) { return M.irMz(t, fat.t1); }, xMax, 80), "");
    plot.addCurve(M.sample(function (t) { return M.irMz(t, wm.t1); }, xMax, 80), "pd");
    plot.addCurve(M.sample(function (t) { return M.irMz(t, csf.t1); }, xMax, 80), "alt");
    var marker = null;
    var readout = el("div", { class: "diag-readout" });
    function nulled(ti) {
      var best = null, bestAbs = Infinity;
      [fat, wm, csf].forEach(function (t) {
        var a = Math.abs(M.irMz(ti, t.t1));
        if (a < bestAbs) { bestAbs = a; best = t; }
      });
      return best;
    }
    function redraw() {
      if (marker) marker.remove();
      marker = plot.addMarker(state.ti, "", "TI");
      readout.textContent = "At TI " + state.ti + " ms, " + nulled(state.ti).label + " is nulled (its curve crosses zero).";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "TI:" }));
    [["STIR (null fat)", Math.round(M.nullTI(fat.t1))], ["FLAIR (null CSF)", Math.round(M.nullTI(csf.t1))]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn" + (p[1] === state.ti ? " on" : ""), text: p[0] });
      b.addEventListener("click", function () {
        state.ti = p[1];
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }
```

Register it (keep prior entries):

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle, "ir-nulling": buildIrNulling };
```

- [ ] **Step 3: Re-add the third curve color to `web/course.html`**

In the `<style>` block, next to the other `.diag-curve` rules (after `.diag-curve.env`), add:

```css
    .diag-curve.alt { stroke: var(--warn); }
```

- [ ] **Step 4: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 5: Manual smoke**

Load *Fat suppression: STIR, spectral, Dixon and water excitation*; confirm three IR curves rising from −1 through a mid zero line, the STIR preset marker landing where fat crosses zero (readout says "Fat is nulled"), FLAIR where CSF crosses zero. Confirm the existing 0–1 widgets are visually unchanged.

- [ ] **Step 6: Commit**

```bash
git add web/course_diagrams.js web/course.html
git commit -m "feat(course): inversion-recovery nulling diagram (STIR/FLAIR) + signed y-axis"
```

---

### Task 4: DWI vs b-value widget

**Files:**
- Modify: `web/course_diagrams.js`

**Interfaces:**
- Consumes: `makePlot`, `figure`, `el`; `M.dwiSignal`, `M.sample`, `M.ADCS`.
- Produces: `BUILDERS["dwi-bvalue"]`.

- [ ] **Step 1: Add the builder**

```js
  // ---- Widget: DWI signal vs b-value ---- //
  function buildDwiBvalue() {
    var fig = figure("DWI and b-value", "Diffusion weighting: signal falls as e to the minus b times ADC. Restricted diffusion (low ADC, e.g. acute stroke) stays bright at high b while free water darkens. Restricted blue, normal grey, free water red (1.5 T, approximate).");
    var xMax = 1000;
    var state = { b: 1000 };
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "b-value (s/mm2)", yLabel: "signal",
      xTicks: [0, 250, 500, 750, 1000], title: "Diffusion signal versus b-value" });
    plot.addAxes();
    M.ADCS.forEach(function (a, i) {
      plot.addCurve(M.sample(function (b) { return M.dwiSignal(b, a.adc); }, xMax, 80),
        i === 0 ? "" : (i === 1 ? "pd" : "alt"));
    });
    var marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (marker) marker.remove();
      marker = plot.addMarker(state.b, "", "b");
      var parts = M.ADCS.map(function (a) {
        return a.label + " " + Math.round(M.dwiSignal(state.b, a.adc) * 100) + "%"; });
      readout.textContent = "At b " + state.b + " s/mm2: " + parts.join(", ") + ". Restricted diffusion stays brightest.";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    controls.appendChild(el("span", { class: "diag-glabel", text: "b-value:" }));
    [0, 500, 1000].forEach(function (bv) {
      var b = el("button", { type: "button", class: "diag-btn" + (bv === state.b ? " on" : ""), text: String(bv) });
      b.addEventListener("click", function () {
        state.b = bv;
        [].forEach.call(controls.querySelectorAll(".diag-btn"), function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        redraw();
      });
      controls.appendChild(b);
    });
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }
```

Register it (keep prior entries — this completes all seven):

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting, "ernst-angle": buildErnstAngle, "ir-nulling": buildIrNulling, "dwi-bvalue": buildDwiBvalue };
```

- [ ] **Step 2: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 3: Manual smoke**

Load *Diffusion in disease: stroke, abscess and cellular tumors*; confirm three decay curves (restricted decays slowest, free water fastest), b presets move the marker, and the readout shows restricted stays brightest at b=1000.

- [ ] **Step 4: Commit**

```bash
git add web/course_diagrams.js
git commit -m "feat(course): interactive DWI signal vs b-value diagram"
```

---

### Task 5: Prototype, final verification, PR

**Files:** none (verification + PR)

- [ ] **Step 1: Artifact prototype**

Regenerate the standalone prototype (from `web/course_diagrams_math.js` + `web/course_diagrams.js`) with mock `.edu` cards for all seven diagrams (the four batch-1 titles + the three new ones), reusing the `.diag-*` CSS. Publish via the Artifact tool (favicon 🧲) to click through before merge.

- [ ] **Step 2: Full verification**

Run: `npm run test:web` → PASS.
Run: `npm run lint` → clean.
Run: `ruff check src/ tests/` → clean.

- [ ] **Step 3: PR + gate-merge**

```bash
git push -u origin HEAD
gh pr create --title "feat(course): physics diagrams batch 2 (Ernst angle, IR nulling, DWI)" --body "$(cat <<'EOF'
Three more interactive diagrams reusing the batch 1 engine: the Ernst angle (signal vs flip angle, marker at the peak), inversion-recovery nulling (STIR/FLAIR, signed y-axis with a zero line), and DWI signal vs b-value (restricted vs free diffusion). New physics is unit-tested in course_diagrams_math.js; the guard test covers the three new DIAGRAM_MAP keys against real education titles. No new files, no DB change, no course.js/sw.js/eslint change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Then gate-merge:

```bash
sleep 20 && gh pr checks --watch --interval 20 && gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Update memory**

Append the three new diagrams to `project_course_diagrams.md` (new builders, map keys, the `makePlot` yMin capability).

---

## Self-Review

**Spec coverage:** Ernst (Task 2), IR nulling + yMin engine tweak (Task 3), DWI (Task 4), math + ADCS + map keys + tests (Task 1), prototype/verify/PR (Task 5), `.diag-curve.alt` re-added (Task 3). ✓

**Placeholder scan:** every code step has complete code. ✓

**Type consistency:** new math names (`ernstAngle`, `spoiledGreSignal`, `irMz`, `nullTI`, `dwiSignal`, `ADCS`) are defined and exported in Task 1 and consumed with those exact names in Tasks 2–4. `makePlot` `opts.yMin` added in Task 3 is used only by the IR widget. `BUILDERS` grows to exactly the seven ids that match `DIAGRAM_MAP` values (asserted in Task 1's test). Widgets use existing `makePlot`/`figure`/`el`/`addMarker(tv,cls,label)`/`addCurve`/`addAxes` signatures from batch 1. ✓

**No-wiring check:** `course.html` scripts, `course.js` attach hook, `sw.js` precache, `eslint.config.mjs` globals already cover `course_diagrams*.js` from PR #438 — batch 2 needs none of them (only one CSS rule). ✓
