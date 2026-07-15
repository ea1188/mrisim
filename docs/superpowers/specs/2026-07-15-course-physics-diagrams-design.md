# Course physics diagrams — design

Date: 2026-07-15
Status: approved (design), pending spec review

## Goal

Add interactive, animated physics diagrams to the guided course's education
cards so learners can *see* the relaxation relationships behind the prose:
T1 longitudinal recovery, T2 transverse decay, T2 vs T2\* dephasing, and how
TR/TE choices pick image weighting.

## Decisions (from brainstorming)

- **Interactive/animated**, not static figures.
- **Four diagrams** in batch one: T1 recovery, T2 decay, T2 vs T2\*, TR/TE → weighting.
- **Placement: inside the matching lesson card**, appended at the bottom of the
  specific `.edu` card whose topic it illustrates. Mapping lives in code
  (diagram → education title), so **no Supabase content edit and no production
  DB write** is needed to add or fix a diagram.
- **TR/TE markers: preset buttons** (short / medium / long), not draggable.
  Simpler and keyboard-accessible by default.
- **Read tracking untouched.** Diagrams are a visual aid; the existing "✓ Read"
  button and the progress-sync `PROGRESS_KEYS` path are not modified.

## Card mapping

Education titles are stable (curriculum-linked; kept in sync per project rules),
so map by exact title string:

| Diagram id      | Education card title                                  |
|-----------------|-------------------------------------------------------|
| `t1-recovery`   | What makes an image T1 weighted?                      |
| `t2-decay`      | Why is fluid bright on a T2 weighted image?           |
| `t2-vs-t2star`  | How does spin echo differ from gradient echo?         |
| `tr-te-weighting` | Contrast & weighting: the exam synthesis            |

A card can receive more than one diagram; the map value is a list of diagram ids.
If a mapped title is absent (content reshuffle), nothing renders — fail-soft, no error.

## Architecture

### New file: `web/course_diagrams.js`

A classic script (no ES modules) exposing a single global, matching the
existing `Accounts` / `course_logic` pattern:

```js
window.CourseDiagrams = {
  DIAGRAM_MAP: { "<edu title>": ["t1-recovery", ...], ... },
  // Build every widget mapped to this education title and append to `card`.
  attach: function (card, eduTitle) { ... },
};
```

Internally, one builder per diagram id returns a self-contained DOM node
(`<figure class="diagram">` → caption + inline `<svg>` + `.diag-controls`).
No dependency on `course.js` internals; it only reads the title and builds DOM.

### Hook in `course.js`

In the education render loop (~line 545, right after the `.edu` card is built and
its worked-example/hooks/traps/foot are appended), add:

```js
if (window.CourseDiagrams) CourseDiagrams.attach(card, b.title);
```

This is the only change to `course.js`. It does not touch read-tracking,
`buildRail`, or navigation.

### Rendering

- **Inline SVG built by JS**, not canvas: crisp at any zoom, theme-aware via the
  existing CSS tokens (`--accent`, `--ok`, `--muted`, `--line-2`, `--warn`),
  easy to label and to animate.
- **Animation:** a play button sweeps the curve by growing the SVG path's `d`
  attribute on `requestAnimationFrame` from t=0 to t=max, then leaves it drawn.
- **Reduced motion:** under `@media (prefers-reduced-motion: reduce)` (and the
  matchMedia check in JS) the widget paints the final curve immediately and the
  play button is hidden. No auto-play ever; animation is user-initiated.
- **Accessibility:** SVG has `role="img"` + `<title>`/`aria-label`; controls are
  real `<button>`/`<select>` elements, keyboard-focusable, using the course's
  existing focus-ring styles.

### The four widgets (physics at 1.5 T, labeled approximate)

Representative 1.5 T constants (ms), teaching values:

| Tissue        | T1   | T2   |
|---------------|------|------|
| Fat           | 260  | 80   |
| White matter  | 510  | 90   |
| Gray matter   | 760  | 100  |
| CSF           | 2400 | 1400 |

1. **T1 recovery** — `Mz(t) = 1 − e^(−t/T1)`. Tissue `<select>`; ▶ sweeps the
   curve; preset **TR** buttons (short ≈ 400, medium ≈ 1200, long ≈ 2500 ms)
   drop a vertical marker and read out "% of Mz recovered at TR".
2. **T2 decay** — `Mxy(t) = e^(−t/T2)`. Tissue `<select>`; preset **TE** buttons
   (short ≈ 15, medium ≈ 40, long ≈ 90 ms) marker reads "signal remaining at TE".
3. **T2 vs T2\*** — both envelopes on one plot; `Mxy* = e^(−t/T2*)` with
   `1/T2* = 1/T2 + 1/T2′`. A slider for T2′ (field inhomogeneity) pinches the
   T2\* curve toward the axis. Caption: T2\* is what GRE sees; the 180° refocuser
   in SE recovers the T2′ dephasing, so SE sees true T2.
4. **TR/TE → weighting** — two preset rows (TR short/long, TE short/long) driving
   markers on mini recovery + decay curves, with a live text readout:
   - short TR + short TE → **T1-weighted**
   - long TR + long TE → **T2-weighted**
   - long TR + short TE → **PD**
   - short TR + long TE → mixed (rarely used) — labeled as such.

### Styling

New CSS added to the existing `<style>` block in `web/course.html`, on-theme:
flat solid accents, dark bones, no gradients/pills/emoji. Classes:
`.diagram`, `.diag-cap`, `.diag-svg`, `.diag-controls`, `.diag-btn`,
`.diag-btn.on`, `.diag-readout`. Motion rules gated in the existing
`@media (prefers-reduced-motion: no-preference)` block.

## Wiring checklist (do not drop any)

- `web/course.html`: add `<script src="course_diagrams.js"></script>` **before**
  `course.js` (after `blueprint.js`, ~line 401); add the diagram CSS.
- `web/course.js`: the one-line `CourseDiagrams.attach(card, b.title)` hook.
- `web/sw.js` (line 33): add `"course_diagrams.js"` to the precache list and bump
  the cache version so the new asset ships.
- `eslint.config.mjs` (line 32): add `"web/course_diagrams.js"` to the files glob.

## Verification

- `node_modules/.bin/eslint web/course_diagrams.js web/course.js` → clean.
- Standalone **Artifact prototype** rendering all four widgets so the look and the
  interactions can be clicked through before shipping.
- Manual: load `course.html`, open the four host cards, confirm each widget
  renders, animates on ▶, snaps markers on preset buttons, updates the weighting
  readout, and paints statically under reduced-motion.
- No engine change (no ruff/mypy). No `Co-Authored-By` trailer. Branch → PR →
  gate-merge. Outward-facing polish, but additive and non-gating.

## Out of scope (YAGNI)

- Draggable markers (chose presets).
- Read/progress changes (left untouched).
- Editing Supabase content or adding placeholder tokens to prose.
- Sequence/timing diagrams, k-space, Larmor — possible later batches, not now.
