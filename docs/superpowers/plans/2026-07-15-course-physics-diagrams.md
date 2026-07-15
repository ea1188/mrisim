# Course Physics Diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four interactive, animated SVG physics diagrams (T1 recovery, T2 decay, T2 vs T2\*, TR/TE→weighting) to the guided course's education cards.

**Architecture:** A pure, DOM-free physics module (`web/course_diagrams_math.js`, UMD, node-tested) holds the relaxation math, tissue constants, and the diagram→card map. A browser-only renderer (`web/course_diagrams.js`) turns those into inline SVG widgets and exposes `window.CourseDiagrams.attach(card, eduTitle)`. `course.js` calls `attach` once per education card. This mirrors the existing `course_logic.js` (pure, tested) / `course.js` (DOM, lint-only) split. Zero Supabase/DB change.

**Tech Stack:** Vanilla ES2022 classic scripts, inline SVG, `node --test` for unit tests, ESLint flat config, existing course CSS tokens.

## Global Constraints

- No ES modules for browser files — classic scripts, `sourceType: "script"`; pure module uses the repo's UMD wrapper (`module.exports` under node, `root.X` in browser). Copy the wrapper verbatim from `web/course_logic.js`.
- UI aesthetic: professional/clinical — no emoji, no pills, no gradients; flat solid accents on dark bones. Theme via existing tokens: `--accent #5db0ef`, `--ok #6bbf83`, `--warn #d98a8a`, `--muted #8b97a6`, `--line-2 #2a3441`, `--ease cubic-bezier(.2,.6,.2,1)`.
- No `Co-Authored-By` trailer on commits.
- Motion only inside `@media (prefers-reduced-motion: no-preference)`; under reduced-motion the widget paints its final state and hides the play button. Never auto-play.
- US spelling in any visible copy.
- Physics constants are 1.5 T teaching approximations; label them as approximate in captions.
- Do not modify read-tracking, `PROGRESS_KEYS`, `buildRail`, or navigation.

---

### Task 1: Physics math module (`course_diagrams_math.js`) + unit tests

**Files:**
- Create: `web/course_diagrams_math.js`
- Test: `web/course_diagrams_math.test.mjs`
- Modify: `package.json` (add the new test file to the `test:web` script)

**Interfaces:**
- Produces (all pure, DOM-free):
  - `mz(t, T1) -> number` — longitudinal recovery fraction `1 - e^(-t/T1)`.
  - `mxy(t, T2) -> number` — transverse decay fraction `e^(-t/T2)`.
  - `t2star(T2, T2prime) -> number` — `1 / (1/T2 + 1/T2prime)`.
  - `classifyWeighting(tr, te) -> "T1" | "T2" | "PD" | "mixed"`.
  - `sample(fn, tMax, n) -> Array<[t, v]>` — `n+1` evenly spaced points `t` in `[0, tMax]`, `v = fn(t)`.
  - `TISSUES -> Array<{id, label, t1, t2}>`.
  - `DIAGRAM_MAP -> { [eduTitle: string]: string[] }`.

- [ ] **Step 1: Write the failing test**

Create `web/course_diagrams_math.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import Math2 from "./course_diagrams_math.js";

const { mz, mxy, t2star, classifyWeighting, sample, TISSUES, DIAGRAM_MAP } = Math2;

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
  const titles = Object.keys(DIAGRAM_MAP);
  assert.ok(titles.includes("What makes an image T1 weighted?"));
  assert.deepEqual(DIAGRAM_MAP["What makes an image T1 weighted?"], ["t1-recovery"]);
  assert.deepEqual(DIAGRAM_MAP["Why is fluid bright on a T2 weighted image?"], ["t2-decay"]);
  assert.deepEqual(DIAGRAM_MAP["How does spin echo differ from gradient echo?"], ["t2-vs-t2star"]);
  assert.deepEqual(DIAGRAM_MAP["Contrast & weighting: the exam synthesis"], ["tr-te-weighting"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/course_diagrams_math.test.mjs`
Expected: FAIL — cannot find module `./course_diagrams_math.js`.

- [ ] **Step 3: Write minimal implementation**

Create `web/course_diagrams_math.js` (UMD wrapper copied from `course_logic.js`):

```js
/* Pure, DOM-free physics for the course diagrams. Shared by course_diagrams.js
 * (browser) and the node unit test. No DOM, no globals beyond the export.
 * UMD: attaches window.CourseDiagramsMath in the browser, module.exports under node. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CourseDiagramsMath = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Longitudinal magnetization recovered by time t (fraction of equilibrium).
  function mz(t, T1) { return 1 - Math.exp(-t / T1); }

  // Transverse magnetization remaining at time t (fraction of the post-90 peak).
  function mxy(t, T2) { return Math.exp(-t / T2); }

  // Effective transverse decay including static field inhomogeneity (T2prime).
  function t2star(T2, T2prime) { return 1 / (1 / T2 + 1 / T2prime); }

  // TR/TE thresholds (ms), 1.5 T teaching values.
  var TR_SHORT = 700, TR_LONG = 1500, TE_SHORT = 35, TE_LONG = 80;

  function classifyWeighting(tr, te) {
    var trShort = tr < TR_SHORT, trLong = tr >= TR_LONG;
    var teShort = te < TE_SHORT, teLong = te >= TE_LONG;
    if (trShort && teShort) return "T1";
    if (trLong && teLong) return "T2";
    if (trLong && teShort) return "PD";
    return "mixed"; // short TR + long TE, or any mid-range combination
  }

  // Evenly sample fn over [0, tMax] into n+1 [t, v] points.
  function sample(fn, tMax, n) {
    var pts = [];
    for (var i = 0; i <= n; i++) {
      var t = (tMax * i) / n;
      pts.push([t, fn(t)]);
    }
    return pts;
  }

  // Representative 1.5 T relaxation constants (ms). Teaching approximations.
  var TISSUES = [
    { id: "fat", label: "Fat", t1: 260, t2: 80 },
    { id: "wm", label: "White matter", t1: 510, t2: 90 },
    { id: "gm", label: "Gray matter", t1: 760, t2: 100 },
    { id: "csf", label: "CSF", t1: 2400, t2: 1400 },
  ];

  // Diagram id(s) shown inside each premium education card, keyed by exact title.
  var DIAGRAM_MAP = {
    "What makes an image T1 weighted?": ["t1-recovery"],
    "Why is fluid bright on a T2 weighted image?": ["t2-decay"],
    "How does spin echo differ from gradient echo?": ["t2-vs-t2star"],
    "Contrast & weighting: the exam synthesis": ["tr-te-weighting"],
  };

  return { mz: mz, mxy: mxy, t2star: t2star, classifyWeighting: classifyWeighting,
    sample: sample, TISSUES: TISSUES, DIAGRAM_MAP: DIAGRAM_MAP };
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test web/course_diagrams_math.test.mjs`
Expected: PASS — all tests.

- [ ] **Step 5: Wire the test into the suite**

In `package.json`, extend the `test:web` script to include the new file (append `web/course_diagrams_math.test.mjs` to the existing `node --test ...` list):

```json
"test:web": "node --test web/course_logic.test.mjs web/auth_url.test.mjs web/join_link.test.mjs web/class_insight.test.mjs web/assignments.test.mjs web/blueprint.test.mjs web/course_diagrams_math.test.mjs"
```

Run: `npm run test:web`
Expected: PASS — the whole web suite including the new file.

- [ ] **Step 6: Commit**

```bash
git add web/course_diagrams_math.js web/course_diagrams_math.test.mjs package.json
git commit -m "feat(course): physics math module for interactive diagrams"
```

---

### Task 2: Renderer scaffold + T1 recovery widget + full wiring

Delivers a working, linted T1-recovery diagram inside its education card, plus all the plumbing (script tags, course.js hook, eslint, sw.js). After this task the feature is visibly live for one diagram; Tasks 3–5 only add more widget builders.

**Files:**
- Create: `web/course_diagrams.js`
- Modify: `web/course.html` (script tag + CSS), `web/course.js` (attach hook), `eslint.config.mjs` (globals + files), `web/sw.js` (precache + cache bump)

**Interfaces:**
- Consumes: `CourseDiagramsMath` (`mz`, `sample`, `TISSUES`, `DIAGRAM_MAP` from Task 1).
- Produces (used by Tasks 3–5):
  - `window.CourseDiagrams.attach(card, eduTitle)` — for each id in `DIAGRAM_MAP[eduTitle]`, build that widget and append to `card`.
  - Internal builder registry `BUILDERS = { "t1-recovery": fn, ... }`; Tasks 3–5 add keys.
  - Shared helper `makePlot(opts) -> { svg, toX, toY, addAxes, addCurve, animateCurve, addMarker }` (signatures below) that later widgets reuse.
  - Module-scope helpers `figure(title, caption) -> HTMLElement`, `el(tag, attrs, kids) -> HTMLElement`, and boolean `reduceMotion`.

- [ ] **Step 1: Create the renderer with the shared plot helper and the T1 widget**

Create `web/course_diagrams.js`:

```js
/* Interactive SVG physics diagrams for the guided course. Classic browser script;
 * defines window.CourseDiagrams. Pure math comes from window.CourseDiagramsMath.
 * attach(card, eduTitle) drops the mapped widget(s) into an education card. */
(function () {
  "use strict";

  var M = window.CourseDiagramsMath;
  var SVGNS = "http://www.w3.org/2000/svg";
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function svgEl(name, attrs) {
    var e = document.createElementNS(SVGNS, name);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }

  // A padded plot area with axes. Returns coordinate mappers and draw helpers.
  // opts: { xMax, yMax (default 1), xLabel, yLabel, title }
  function makePlot(opts) {
    var W = 320, H = 180, padL = 34, padB = 26, padT = 8, padR = 10;
    var x0 = padL, x1 = W - padR, y0 = H - padB, y1 = padT;
    var svg = svgEl("svg", { class: "diag-svg", viewBox: "0 0 " + W + " " + H,
      role: "img", "aria-label": opts.title });
    var t = svgEl("title", {}); t.textContent = opts.title; svg.appendChild(t);
    function toX(tv) { return x0 + (x1 - x0) * (tv / opts.xMax); }
    function toY(v) { return y0 - (y0 - y1) * (v / (opts.yMax || 1)); }
    function addAxes() {
      svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: y0, x2: x1, y2: y0 }));
      svg.appendChild(svgEl("line", { class: "diag-axis", x1: x0, y1: y0, x2: x0, y2: y1 }));
      var yl = svgEl("text", { class: "diag-axtext", x: x0 - 6, y: y1 + 4, "text-anchor": "end" });
      yl.textContent = opts.yLabel; svg.appendChild(yl);
      var xl = svgEl("text", { class: "diag-axtext", x: x1, y: y0 + 18, "text-anchor": "end" });
      xl.textContent = opts.xLabel; svg.appendChild(xl);
    }
    function pathData(points) {
      return points.map(function (p, i) {
        return (i ? "L" : "M") + toX(p[0]).toFixed(1) + " " + toY(p[1]).toFixed(1);
      }).join(" ");
    }
    // points: Array<[t,v]>. Returns the <path> so callers can animate it.
    function addCurve(points, cls) {
      var path = svgEl("path", { class: "diag-curve " + (cls || ""), d: pathData(points) });
      svg.appendChild(path);
      return path;
    }
    // Animate a curve drawing from left to right by growing its point set.
    function animateCurve(path, points) {
      if (reduceMotion) return; // final curve already drawn by addCurve
      var start = null, dur = 650;
      path.setAttribute("d", pathData(points.slice(0, 1)));
      function frame(ts) {
        if (start === null) start = ts;
        var k = Math.min(1, (ts - start) / dur);
        var n = Math.max(1, Math.round(k * (points.length - 1)));
        path.setAttribute("d", pathData(points.slice(0, n + 1)));
        if (k < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }
    function addMarker(tv, cls) {
      var line = svgEl("line", { class: "diag-marker " + (cls || ""),
        x1: toX(tv), y1: y0, x2: toX(tv), y2: y1 });
      svg.appendChild(line);
      return line;
    }
    return { svg: svg, toX: toX, toY: toY, addAxes: addAxes, addCurve: addCurve,
      animateCurve: animateCurve, addMarker: addMarker };
  }

  // A labeled figure shell shared by every widget.
  function figure(title, caption) {
    var fig = el("figure", { class: "diagram", "aria-label": title });
    fig.appendChild(el("figcaption", { class: "diag-cap", text: caption }));
    return fig;
  }

  // ---- Widget: T1 longitudinal recovery ---- //
  function buildT1Recovery() {
    var fig = figure("T1 recovery", "T1 recovery — Mz rebuilds along B0 (1.5 T, approximate).");
    var state = { tissue: M.TISSUES[1], tr: null };
    var xMax = 3000;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Mz",
      title: "T1 longitudinal recovery curve" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw(animate) {
      if (curve) curve.remove(); if (marker) marker.remove();
      var pts = M.sample(function (t) { return M.mz(t, state.tissue.t1); }, xMax, 60);
      curve = plot.addCurve(pts, "");
      if (animate) plot.animateCurve(curve, pts);
      readout.textContent = state.tr === null ? "Pick a TR to see recovery at that time."
        : "At TR " + state.tr + " ms, " + state.tissue.label + " has recovered "
          + Math.round(M.mz(state.tr, state.tissue.t1) * 100) + "% of Mz.";
      if (state.tr !== null) marker = plot.addMarker(state.tr, "");
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

    [["Short", 400], ["Medium", 1200], ["Long", 2500]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn", text: "TR " + p[0] });
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

  var BUILDERS = { "t1-recovery": buildT1Recovery };

  function attach(card, eduTitle) {
    if (!M || !card) return;
    var ids = M.DIAGRAM_MAP[eduTitle];
    if (!ids) return;
    ids.forEach(function (id) {
      var fn = BUILDERS[id];
      if (fn) card.appendChild(fn());
    });
  }

  // Expose the API plus internals so later widget tasks extend BUILDERS in place.
  window.CourseDiagrams = { attach: attach, _BUILDERS: BUILDERS,
    _makePlot: makePlot, _figure: figure, _el: el, _reduceMotion: reduceMotion };
})();
```

- [ ] **Step 2: Add the diagram CSS to `web/course.html`**

Inside the existing `<style>` block, add (near the `.edu` rules):

```css
.diagram { margin: 14px 0 4px; padding: 12px; border: 1px solid var(--line-2); border-radius: 8px; background: rgba(255,255,255,.02); }
.diag-cap { font-size: 12px; color: var(--muted); margin: 0 0 8px; }
.diag-svg { width: 100%; max-width: 420px; height: auto; display: block; }
.diag-axis { stroke: var(--line-2); stroke-width: 1; }
.diag-axtext { fill: var(--muted); font-size: 9px; }
.diag-curve { fill: none; stroke: var(--accent); stroke-width: 2; }
.diag-curve.alt { stroke: var(--warn); }
.diag-curve.pd { stroke: var(--muted); }
.diag-marker { stroke: var(--ok); stroke-width: 1; stroke-dasharray: 3 3; }
.diag-controls { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 10px; }
.diag-select { background: rgba(255,255,255,.03); color: inherit; border: 1px solid var(--line-2); border-radius: 6px; padding: 4px 6px; font: inherit; font-size: 12px; }
.diag-btn { background: transparent; color: var(--muted); border: 1px solid var(--line-2); border-radius: 6px; padding: 4px 8px; font: inherit; font-size: 12px; cursor: pointer; }
.diag-btn:hover { color: inherit; }
.diag-btn.on { color: #061018; background: var(--accent); border-color: var(--accent); }
.diag-readout { margin-top: 8px; font-size: 12px; color: var(--muted); min-height: 16px; }
@media (prefers-reduced-motion: no-preference) {
  .diag-btn { transition: background .15s var(--ease), color .15s var(--ease); }
}
```

- [ ] **Step 3: Load the scripts in `web/course.html`**

After the `<script src="blueprint.js"></script>` line (~line 401) and **before** `<script src="course.js"></script>`, add:

```html
  <script src="course_diagrams_math.js"></script>
  <script src="course_diagrams.js"></script>
```

- [ ] **Step 4: Call attach from `course.js`**

First Read `web/course.js` lines 535–590 to locate the `edu.forEach(function (b) { ... })` loop where the `.edu` card is built and `foot` is appended. At the **end** of that callback body — after the read-tag/`foot` logic and before the card is appended to its container — add:

```js
if (window.CourseDiagrams) window.CourseDiagrams.attach(card, b.title);
```

- [ ] **Step 5: Update ESLint config (`eslint.config.mjs`)**

In the block whose `files` array contains `"web/course.js"` (around line 32):
1. Add `"web/course_diagrams.js"` to the `files` array.
2. Add two globals to that block's `globals`: `CourseDiagrams: "readonly"` and `CourseDiagramsMath: "readonly"`.

Result:

```js
    files: ["web/accounts.js", "web/account.js", "web/course.js", "web/course_diagrams.js", "web/config.js", "web/config.example.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, Accounts: "readonly", CourseDiagrams: "readonly", CourseDiagramsMath: "readonly" },
    },
```

(`course_diagrams_math.js` is intentionally left unmatched by any block, exactly like `course_logic.js` — it is covered by the node unit test instead.)

- [ ] **Step 6: Precache the new assets in `web/sw.js`**

At line 33, add `"course_diagrams_math.js", "course_diagrams.js"` to the precache array (next to `"course.js"`). Then bump the cache-version constant near the top of `sw.js` (the `const CACHE = "...vN"` string) so clients fetch the new files.

- [ ] **Step 7: Lint and unit-test**

Run: `npm run lint`
Expected: clean (no errors).
Run: `npm run test:web`
Expected: PASS.

- [ ] **Step 8: Manual smoke**

Open `web/course.html` in a browser signed in as an entitled user, navigate to *What makes an image T1 weighted?*, and confirm: the T1 curve renders, the tissue dropdown reshapes it, TR presets drop a dashed marker with a correct readout, and ▸ Play animates the sweep. Toggle OS reduced-motion and confirm the curve paints statically with no Play button.

- [ ] **Step 9: Commit**

```bash
git add web/course_diagrams.js web/course.html web/course.js eslint.config.mjs web/sw.js
git commit -m "feat(course): interactive T1 recovery diagram + renderer scaffold"
```

---

### Task 3: T2 decay widget

**Files:**
- Modify: `web/course_diagrams.js`

**Interfaces:**
- Consumes: `makePlot`, `figure`, `el`, `reduceMotion` (Task 2); `M.mxy`, `M.sample`, `M.TISSUES` (Task 1).
- Produces: `BUILDERS["t2-decay"]`.

- [ ] **Step 1: Add the builder**

In `web/course_diagrams.js`, add this function next to `buildT1Recovery`, then register it in `BUILDERS`:

```js
  // ---- Widget: T2 transverse decay ---- //
  function buildT2Decay() {
    var fig = figure("T2 decay", "T2 decay — Mxy dephases in the transverse plane (1.5 T, approximate).");
    var state = { tissue: M.TISSUES[1], te: null };
    var xMax = 400;
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Mxy",
      title: "T2 transverse decay curve" });
    plot.addAxes();
    var curve = null, marker = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw(animate) {
      if (curve) curve.remove(); if (marker) marker.remove();
      var pts = M.sample(function (t) { return M.mxy(t, state.tissue.t2); }, xMax, 60);
      curve = plot.addCurve(pts, "");
      if (animate) plot.animateCurve(curve, pts);
      readout.textContent = state.te === null ? "Pick a TE to see signal remaining at that echo time."
        : "At TE " + state.te + " ms, " + state.tissue.label + " retains "
          + Math.round(M.mxy(state.te, state.tissue.t2) * 100) + "% of Mxy.";
      if (state.te !== null) marker = plot.addMarker(state.te, "");
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
    [["Short", 15], ["Medium", 40], ["Long", 90]].forEach(function (p) {
      var b = el("button", { type: "button", class: "diag-btn", text: "TE " + p[0] });
      b.addEventListener("click", function () {
        state.te = p[1];
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

Update the registry line:

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay };
```

- [ ] **Step 2: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 3: Manual smoke**

Load *Why is fluid bright on a T2 weighted image?*; confirm the decay curve renders, tissue selector reshapes it (CSF decays far slower — stays bright at long TE), TE presets mark the echo time with a correct readout, Play animates.

- [ ] **Step 4: Commit**

```bash
git add web/course_diagrams.js
git commit -m "feat(course): interactive T2 decay diagram"
```

---

### Task 4: T2 vs T2\* widget

**Files:**
- Modify: `web/course_diagrams.js`, `web/course.html` (one CSS rule)

**Interfaces:**
- Consumes: `makePlot`, `figure`, `el` (Task 2); `M.mxy`, `M.t2star`, `M.sample` (Task 1).
- Produces: `BUILDERS["t2-vs-t2star"]`.

- [ ] **Step 1: Add the builder**

Add next to the others; the widget draws two curves (true T2 and the faster T2\*) and a slider for field inhomogeneity T2′:

```js
  // ---- Widget: T2 vs T2* ---- //
  function buildT2vsT2star() {
    var fig = figure("T2 vs T2*", "T2 vs T2* — field inhomogeneity speeds transverse decay; spin echo's 180 refocuses it, gradient echo does not.");
    var T2 = 90;             // fixed representative tissue T2 (ms)
    var xMax = 300;
    var state = { t2prime: 40 };  // ms; smaller = worse inhomogeneity
    var plot = makePlot({ xMax: xMax, yMax: 1, xLabel: "t (ms)", yLabel: "Mxy",
      title: "T2 versus T2-star decay envelopes" });
    plot.addAxes();
    // True T2 curve is static; T2* curve redraws with the slider.
    plot.addCurve(M.sample(function (t) { return M.mxy(t, T2); }, xMax, 60), "");
    var starCurve = null;
    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (starCurve) starCurve.remove();
      var ts = M.t2star(T2, state.t2prime);
      var pts = M.sample(function (t) { return M.mxy(t, ts); }, xMax, 60);
      starCurve = plot.addCurve(pts, "alt");
      readout.textContent = "True T2 = " + T2 + " ms (spin echo). With T2' = "
        + state.t2prime + " ms, T2* = " + Math.round(ts) + " ms (gradient echo).";
    }
    fig.appendChild(plot.svg);
    var controls = el("div", { class: "diag-controls" });
    var lab = el("span", { class: "diag-glabel", text: "Field inhomogeneity (T2'):" });
    var slider = el("input", { type: "range", min: "10", max: "120", value: "40",
      class: "diag-slider", "aria-label": "Field inhomogeneity T2 prime in ms" });
    slider.addEventListener("input", function () {
      state.t2prime = parseInt(slider.value, 10);
      redraw();
    });
    controls.appendChild(lab);
    controls.appendChild(slider);
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }
```

Update the registry:

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star };
```

Add the slider style to `web/course.html` (near the other `.diag-*` rules):

```css
.diag-slider { accent-color: var(--warn); vertical-align: middle; }
```

- [ ] **Step 2: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 3: Manual smoke**

Load *How does spin echo differ from gradient echo?*; confirm two curves (accent = true T2, warn = T2\*), the T2\* curve pinches toward the axis as the slider lowers T2′, and the readout reports both time constants.

- [ ] **Step 4: Commit**

```bash
git add web/course_diagrams.js web/course.html
git commit -m "feat(course): interactive T2 vs T2* diagram"
```

---

### Task 5: TR/TE → weighting widget

**Files:**
- Modify: `web/course_diagrams.js`, `web/course.html` (CSS)

**Interfaces:**
- Consumes: `makePlot`, `figure`, `el` (Task 2); `M.classifyWeighting`, `M.mz`, `M.mxy`, `M.sample`, `M.TISSUES` (Task 1).
- Produces: `BUILDERS["tr-te-weighting"]`.

- [ ] **Step 1: Add the builder**

This widget shows two mini-plots (recovery vs TR, decay vs TE) with markers driven by preset buttons, and a live weighting readout:

```js
  // ---- Widget: TR/TE -> weighting ---- //
  function buildTrTeWeighting() {
    var fig = figure("TR/TE and weighting", "TR/TE and weighting — long TR undoes T1 differences; long TE reveals T2 differences (1.5 T, approximate).");
    var state = { tr: 400, te: 15 };
    var trMax = 3000, teMax = 200;
    var wm = M.TISSUES[1], csf = M.TISSUES[3]; // contrast pair: white matter vs CSF

    var recov = makePlot({ xMax: trMax, yMax: 1, xLabel: "TR (ms)", yLabel: "Mz",
      title: "Longitudinal recovery vs TR" });
    recov.addAxes();
    recov.addCurve(M.sample(function (t) { return M.mz(t, wm.t1); }, trMax, 60), "");
    recov.addCurve(M.sample(function (t) { return M.mz(t, csf.t1); }, trMax, 60), "pd");
    var trMark = null;

    var decay = makePlot({ xMax: teMax, yMax: 1, xLabel: "TE (ms)", yLabel: "Mxy",
      title: "Transverse decay vs TE" });
    decay.addAxes();
    decay.addCurve(M.sample(function (t) { return M.mxy(t, wm.t2); }, teMax, 60), "");
    decay.addCurve(M.sample(function (t) { return M.mxy(t, csf.t2); }, teMax, 60), "pd");
    var teMark = null;

    var readout = el("div", { class: "diag-readout" });
    function redraw() {
      if (trMark) trMark.remove();
      if (teMark) teMark.remove();
      trMark = recov.addMarker(state.tr, "");
      teMark = decay.addMarker(state.te, "");
      var w = M.classifyWeighting(state.tr, state.te);
      var name = { T1: "T1-weighted", T2: "T2-weighted", PD: "proton-density", mixed: "mixed (rarely used)" }[w];
      readout.textContent = "TR " + state.tr + " / TE " + state.te + " ms → " + name
        + ". (Accent = white matter, gray = CSF.)";
    }
    var wrap = el("div", { class: "diag-dual" });
    wrap.appendChild(recov.svg);
    wrap.appendChild(decay.svg);
    fig.appendChild(wrap);

    var controls = el("div", { class: "diag-controls" });
    function group(labelTxt, key, presets) {
      controls.appendChild(el("span", { class: "diag-glabel", text: labelTxt }));
      presets.forEach(function (p) {
        var b = el("button", { type: "button", class: "diag-btn diag-" + key, text: p[0] });
        b.addEventListener("click", function () {
          state[key] = p[1];
          [].forEach.call(controls.querySelectorAll(".diag-" + key), function (x) { x.classList.remove("on"); });
          b.classList.add("on");
          redraw();
        });
        controls.appendChild(b);
      });
    }
    group("TR:", "tr", [["Short", 400], ["Long", 2500]]);
    group("TE:", "te", [["Short", 15], ["Long", 90]]);
    fig.appendChild(controls);
    fig.appendChild(readout);
    redraw();
    return fig;
  }
```

Update the registry:

```js
  var BUILDERS = { "t1-recovery": buildT1Recovery, "t2-decay": buildT2Decay, "t2-vs-t2star": buildT2vsT2star, "tr-te-weighting": buildTrTeWeighting };
```

Add styles to `web/course.html`:

```css
.diag-dual { display: flex; flex-wrap: wrap; gap: 10px; }
.diag-dual .diag-svg { max-width: 240px; }
.diag-glabel { font-size: 12px; color: var(--muted); margin-right: 2px; }
```

- [ ] **Step 2: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 3: Manual smoke**

Load *Contrast & weighting: the exam synthesis*; step the four TR/TE combinations and confirm the readout reports T1-weighted (short/short), T2-weighted (long/long), proton-density (long/short), mixed (short/long), with markers moving on both mini-plots.

- [ ] **Step 4: Commit**

```bash
git add web/course_diagrams.js web/course.html
git commit -m "feat(course): interactive TR/TE weighting diagram"
```

---

### Task 6: Prototype preview, final verification, and PR

**Files:** none (verification + PR only)

- [ ] **Step 1: Build a standalone Artifact prototype**

Create a scratchpad HTML page that inlines `course_diagrams_math.js` + `course_diagrams.js` and renders all four widgets in mock `.edu` cards (one per `DIAGRAM_MAP` title), reusing the `.diag-*` CSS. Publish via the Artifact tool (favicon 🧲) so the diagrams can be clicked through before review. Preview only — not shipped in `web/`.

- [ ] **Step 2: Full test + lint pass**

Run: `npm run test:web`
Expected: PASS (includes `course_diagrams_math.test.mjs`).
Run: `npm run lint`
Expected: clean.
Run (CI parity — Python untouched, confirm nothing broke): `ruff check src/ tests/`
Expected: clean.

- [ ] **Step 3: Open the PR and gate-merge**

```bash
git push -u origin HEAD
gh pr create --title "feat(course): interactive physics diagrams (T1/T2/T2*/weighting)" --body "$(cat <<'EOF'
Adds four interactive SVG physics diagrams inside the guided course's education cards: T1 recovery, T2 decay, T2 vs T2*, and TR/TE weighting. Pure physics lives in a node-tested UMD module (course_diagrams_math.js); the SVG renderer (course_diagrams.js) is attached per card by title via CourseDiagrams.attach. No Supabase/DB change; read-tracking untouched; reduced-motion paints statically.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Then gate-merge (wait for checks to register, gate with `&&`):

```bash
sleep 20 && gh pr checks --watch --interval 20 && gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Update memory**

Append a `project` memory note recording the diagram feature (files, the title→diagram map, the math/renderer split, `attach` seam in `course.js`) and add its one-line index entry to `MEMORY.md`.

---

## Self-Review

**Spec coverage:**
- Interactive/animated → Task 2 `animateCurve` + Play button. ✓
- Four diagrams → Tasks 2–5. ✓
- Inside matching card, mapped by title, no DB write → `DIAGRAM_MAP` (Task 1) + `attach` hook (Task 2). ✓
- Preset TR/TE buttons → Tasks 2, 3, 5. ✓
- Read tracking untouched → only a single additive `attach` call in `course.js`; noted in Global Constraints. ✓
- 1.5 T constants labeled approximate → captions in each widget. ✓
- Theme tokens / no gradients-pills-emoji → CSS in Task 2. ✓
- Reduced motion → `reduceMotion` guard in Task 2, reused everywhere. ✓
- Wiring checklist (html script, course.js hook, sw.js, eslint) → Task 2 Steps 2–6. ✓
- Verification (eslint, node test, Artifact prototype) → Tasks 1, 2, 6. ✓
- T2\* slider (the one non-preset control flagged in the spec) → Task 4. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `makePlot` returns `{svg,toX,toY,addAxes,addCurve,animateCurve,addMarker}` (Task 2) and every consumer (Tasks 3–5) uses exactly those names. `M` = `CourseDiagramsMath` with `mz/mxy/t2star/classifyWeighting/sample/TISSUES/DIAGRAM_MAP` used consistently. `BUILDERS` keys match `DIAGRAM_MAP` values (`t1-recovery/t2-decay/t2-vs-t2star/tr-te-weighting`). `figure/el/reduceMotion` are module-scope in Task 2 and consumed by Tasks 3–5. ✓

**Note vs spec:** Spec said "one file `course_diagrams.js`"; this plan splits pure math into `course_diagrams_math.js` to match the repo's `course_logic.js`/`course.js` pattern and gain unit-test coverage. Strict improvement, same behavior.
