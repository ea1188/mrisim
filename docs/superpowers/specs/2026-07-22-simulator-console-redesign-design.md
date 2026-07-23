# Web simulator: protocol-planner-style console — design

**Goal:** Reshape the web simulator (`web/simulator.html` + `web/app.js` + `web/styles.css`) into a
scanner-console layout like the Protocol Planning page: **presets rail on the left, the simulated
image centered, and a tabbed control strip below the image** with tabs
**Setup · Contrast · Quality · Learn**. Clicking a tab fills the strip with that group's controls.
No vertical page scrolling on desktop; panels scroll internally. Audience: learners.

This supersedes the shelved accordion consolidation (branch `feat/param-ui-consolidation`,
unmerged). The **4-group control mapping and every control id** from
`docs/superpowers/specs/2026-07-22-simulator-parameter-ui-consolidation-design.md` (on that
branch) are reused verbatim; only the presentation changes.

## Approaches considered

- **A (chosen): fixed-height console grid, planner-style.** `#app` becomes a `100vh`-minus-topbar
  grid — rail | center | metrics columns, with the tabbed strip in a bottom `auto` row under the
  center column, capped at ~40vh (the planner caps its params panel at 42vh). Matches the
  planner's "page never scrolls, panels do" model exactly.
- **B: keep the page-scroll layout, float the strip.** A sticky bottom strip over a scrolling
  page. Rejected: keeps the vertical-scroll feel the user wants gone, and sticky-over-content
  fights the lesson panel and tour overlays.
- **C: move controls into a planner-identical single flat params row.** Rejected: the simulator
  has ~40 controls vs the planner's 10 — a flat row can't hold them; tabs are the reconciliation
  the user already chose (pivot note, Option A).

## Layout (desktop > 920px)

```
#topbar  (existing, unchanged)
#app  grid: columns [232px rail | 1fr center | 230px metrics], rows [minmax(0,1fr) | auto]
  ├─ #preset-rail   (col 1, spans both rows; scrolls internally)
  ├─ .viewport      (col 2, row 1; image + overlays; scrolls internally if overlays open)
  ├─ #controls      (col 2, row 2; the tabbed strip, max-height ≈ 40vh, scrolls internally)
  └─ #metrics       (col 3, spans both rows; unchanged content)
```

- `html, body, #app` heights pinned (planner pattern: `height: 100vh` grid minus the topbar row)
  so the page itself never scrolls on desktop.
- **`.viewport`** becomes a scrolling flex column: `.image-row` keeps a strong min-height so the
  image never collapses; optional overlay panels (curve, k-space, PSD, B0, g-factor, contrast
  map, scout, recon, math) stack below and the column scrolls internally when they exceed the
  space. All overlay wrap ids/behavior unchanged.
- **`#metrics`** panel is kept as the right column (image stays visually centered, minimal churn).

## Presets rail (left)

- New `<aside id="preset-rail">`: a "Presets" header + one button per preset (populated in
  `buildControls` from `info.presets`, same source as the select) + a leading "Custom" state row.
- The existing **`#preset` select stays in the DOM** (visually hidden) as the single source of
  truth: a rail click sets `$("preset").value = name` and dispatches `change`, so `onPreset` and
  the CI smoke's `selectOption("#preset", …)` work untouched.
- Active highlight: a `syncPresetRail()` helper marks the rail row matching `$("preset").value`
  (or "Custom" when empty). Called after `onPreset` completes and at the two manual-tweak reset
  sites (`app.js:1274`, `app.js:1287`), plus once at build.
- Rail scrolls internally; planner-queue styling (flat rows, `--panel` hover, active outline).

## Control strip (bottom, tabbed)

Markup: the existing `<section id="controls">` moves below the viewport and becomes the strip.

```
#controls
  .strip-bar     ── tabs (role=tablist): Setup · Contrast · Quality · Learn
                 ── .ctrl-search (existing #ctrl-find + #ctrl-find-x + #ctrl-find-empty)
                 ── .strip-actions: #setA #compare #exitAB · #copylink #download   (#abdelta below)
  .pane[data-sec=setup]     (default visible)
  .pane[data-sec=contrast]
  .pane[data-sec=quality]
  .pane[data-sec=learn]
```

Each pane is a horizontal flex of `.col` blocks (each with an `<h3 class="subhead">`), wrapping
on narrow widths. Contents = the approved 4-group mapping, **every control id/class verbatim**:

| Pane (`data-sec`) | Columns → controls |
|---|---|
| **Setup** | *Sequence*: region, sequence, seq-help, field, diffdisp/perfdisp/perfdyndisp/angiotype/qmridisp/fmridisp rows, orientation, slice, labelanat, pathology-row · *Geometry*: fovplan + `#planctl` (all sat-band / slices / gap rows, oblique-readout) |
| **Contrast** | *Timing*: tr, te, ti-row, fa-row · *Effects*: fatsat, gd, flow |
| **Quality** | *Sampling*: receivecoil, matrix, bw, nex, thick, bval-row, etl-row · *Parallel*: accel, accelmethod-row, pv, hint · *3D*: acq3d, np-row, slabsharp-row, kzpf-row, slab-readout, reconshow + recon-need, `#reconctl` |
| **Learn** | *Overlays*: curveshow, curvemode-row, cmap, kspaceshow, psdshow, b0mapshow, gfactorshow, mathshow · *Artifacts*: motion, motiontype-row, chemshift, suscept, artifact-help · *Measure*: measuremode, measure-readout, measure-clear |

- Default tab **Setup**; the active tab persists per-device in `localStorage` `mrisim_tab`
  (replaces `mrisim_sections`, whose keys become stale and are ignored).
- Old `protocol` section content becomes `.strip-actions` (A/B compare, copy-link, download) —
  always visible in the strip bar, like the planner's actions row. `#abdelta` renders under the
  bar when non-empty.

## JS changes (`web/app.js`)

- **`setupTabs()`** replaces `setupCollapsibles()`/`restoreSectionState()`: tab click → show that
  `.pane`, `aria-selected`, persist. Exposes `showTab(sec)` for search and the tour.
- **`setupSearch()` reworked for panes:** on a term, add `body.filtering`; show **all** panes
  stacked with only matching rows (each pane keeps its subheads for context), hide the tab
  states visually; clearing restores the active tab. The row-filter logic (label/btnrow/p/div by
  text) is reused, now scoped to rows within each pane's `.col` blocks.
- **`buildPresetRail()` + `syncPresetRail()`** as above.
- **Tour:** `web/tour.js` gains an optional per-step `reveal()` callback invoked before locating
  the element (generic; the protocol page is unaffected; the existing `details.group` auto-open
  stays for any page still using it). Simulator steps targeting in-pane controls pass
  `reveal: () => showTab("…")`. Copy updates: curve step "Visualizations section" → "Learn tab";
  find-anything step "the panel filters" → "the strip filters"; intro-dialog bullets that say
  "left panel" / "Section headers collapse" reworded for the console.
- Dead code removed: `SECTION_LS`, collapsible persistence.

## CSS changes (`web/styles.css`)

New: `#app` console grid + pinned heights, `#preset-rail`, `.strip-bar`, `.tabs` (flat planner-
style tab buttons, active = accent underline/border on `--raised`), `.pane`, `.col`, `.subhead`,
`.strip-actions`. Adjusted: `.viewport` internal scroll, `.ctrl-search` no longer sticky.
Removed: `details.group` summary/chevron rules (no accordions left on this page). All control
primitives (labels, `.numval`, sliders, `.radios`, `.check`, `.btnrow`) untouched. Palette: reuse
the existing `styles.css` `:root` vars only — no theme.css changes, no new colors (professional/
clinical: flat, no pills/gradients).

## Responsive

- **≤ 920px:** `#app` back to one auto-height scrolling column, order: viewport → strip (tabs
  still work) → rail → metrics. Pinned heights lifted (planner's mobile pattern).
- `@media (pointer: coarse)` hit-target rules already cover the new buttons (`.tabs button`
  added to the list).

## What stays identical (invariants)

- Every control id, class, event wiring, and behavior; number+slider sync; sequence-conditional
  rows via `syncVisibility`; presets via the real `#preset` select; A/B compare; share-link
  state; lesson/curriculum dialogs; slice rail; window/level; measure tools; embed mode.
- `#metrics`, `#topbar`, viewport overlay wraps: unchanged markup.
- No engine/physics change; no desktop change; no new parameters.

## Verification

- `npx eslint web/` clean; `npm run test:web` still green (doesn't touch simulator DOM).
- **`web/smoke.mjs` updated**: the accordion steps (`details[data-sec=…]` open/collapse checks)
  become tab steps (click Quality tab → bandwidth visible; search "bandwidth" reveals the row
  across panes; clear restores the active tab). Preset apply via `selectOption("#preset")`
  unchanged; add a rail-click assertion.
- Manual/Playwright pass at 1440px and 900px: no page scroll on desktop; every tab shows its
  controls; sequence switch reveals TI/FA/b-value/ETL in their panes; tour steps activate tabs;
  FOV planning shows scout + Geometry controls; recon view works from Quality.
- `web/sw.js`: bump cache `mrisim-v15` → `mrisim-v16`.

## Out of scope

No control redesign, no new parameters, no desktop app changes, no metrics-panel rework, no
protocol-page changes beyond the additive `tour.js` hook.
