# Simulator Console Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `web/simulator.html` as a protocol-planner-style console — presets rail left, image centered, tabbed control strip (Setup · Contrast · Quality · Learn) below the image, no page scroll on desktop.

**Architecture:** Fixed-height CSS grid (`#app`: rail | center | metrics columns, viewport + strip rows in the center), mirroring `web/protocol.html`'s `#pp-root`/`#pp-body` model. Controls keep every existing id/class and move into four `.pane[data-sec]` blocks; a hidden `#preset` select stays the source of truth behind a new rail. Tabs/search/tour wiring in `web/app.js`; a generic `reveal()` step hook in shared `web/tour.js`.

**Tech Stack:** Vanilla JS + CSS (no frameworks), Playwright smoke (`web/smoke.mjs`), ESLint.

## Global Constraints

- Every existing control `id`, class, and event wiring preserved verbatim (spec invariant; 40+ controls).
- Palette: only existing `web/styles.css` `:root` vars; flat/clinical — no pills, gradients, emoji.
- No changes to `web/theme.css`, `#topbar`, `#metrics` content, viewport overlay wrap markup, or the desktop app.
- `web/tour.js` change must be additive (protocol page unaffected).
- Spec: `docs/superpowers/specs/2026-07-22-simulator-console-redesign-design.md`.
- CI to keep green: `npx eslint web/`, `npm run test:web`, `web/smoke.mjs` (update its accordion steps).

---

### Task 1: Console markup (`web/simulator.html`)

**Files:**
- Modify: `web/simulator.html:153-450` (the `<main id="app">` block only)

**Interfaces:**
- Produces: `<aside id="preset-rail">` with `.rail-head` + `<ol id="preset-list">` (empty; JS fills), hidden `#preset` select inside the rail; `<section id="controls" class="strip">` containing `.strip-bar` (`.tabs` with 4 `button[data-tab]`, `.ctrl-search`, `.strip-actions`) and 4 `.pane[data-sec]` divs with `.col` sub-blocks and `<h3 class="subhead">` headers. Task 3's JS selects `.tabs button[data-tab]`, `.pane[data-sec]`, `#preset-list`.

- [ ] **Step 1: Restructure `<main id="app">`** to this order (moving, not rewriting, the existing control markup; every id/class verbatim):

```html
<main id="app" hidden>
  <aside class="panel" id="preset-rail" aria-label="Clinical presets">
    <div class="rail-head"><h2>Presets</h2></div>
    <!-- The select stays as the state source (JS + CI drive it); the rail buttons proxy it. -->
    <label class="visually-hidden">Preset
      <select id="preset"><option value="">— custom —</option></select></label>
    <ol id="preset-list"></ol>
  </aside>

  <section class="viewport" aria-label="Image viewport"> …unchanged existing content… </section>

  <section class="panel strip" id="controls" aria-label="Scan controls">
    <div class="strip-bar">
      <div class="tabs" role="tablist" aria-label="Control groups">
        <button data-tab="setup" role="tab" aria-selected="true" class="on">Setup</button>
        <button data-tab="contrast" role="tab" aria-selected="false">Contrast</button>
        <button data-tab="quality" role="tab" aria-selected="false">Quality</button>
        <button data-tab="learn" role="tab" aria-selected="false">Learn</button>
      </div>
      <div class="ctrl-search">
        <input type="search" id="ctrl-find" placeholder="Find a control…" aria-label="Filter controls" autocomplete="off" spellcheck="false" />
        <button id="ctrl-find-x" type="button" title="Clear" aria-label="Clear search" hidden>✕</button>
      </div>
      <div class="strip-actions">
        <button id="setA" type="button">Set as A</button>
        <button id="compare" type="button">Compare A/B</button>
        <button id="exitAB" type="button" hidden>Exit compare</button>
        <button id="copylink" type="button" title="Copy a shareable link to this exact setup">Copy link</button>
        <button id="download" type="button" title="Download the current image as PNG">Download PNG</button>
      </div>
    </div>
    <p class="tiny ctrl-find-empty" id="ctrl-find-empty" hidden>No control matches that.</p>
    <p class="hint" id="abdelta" role="status" aria-live="polite"></p>

    <div class="pane" data-sec="setup" role="tabpanel">
      <div class="col"><h3 class="subhead">Sequence</h3> [region … pathology-row markup from old anatomy section, main lines 181-219] </div>
      <div class="col"><h3 class="subhead">Geometry</h3> [fovplan check + #planctl block, main lines 220-241] </div>
    </div>
    <div class="pane" data-sec="contrast" hidden role="tabpanel">
      <div class="col"><h3 class="subhead">Timing</h3> [tr/te/ti-row/fa-row, main lines 266-273] </div>
      <div class="col"><h3 class="subhead">Effects</h3> [fatsat/gd/flow checks, main lines 278-280] </div>
    </div>
    <div class="pane" data-sec="quality" hidden role="tabpanel">
      <div class="col"><h3 class="subhead">Sampling</h3> [receivecoil … etl-row, main lines 300-318] </div>
      <div class="col"><h3 class="subhead">Parallel imaging</h3> [accel/accelmethod-row/pv + tiny hint, main lines 383-389] </div>
      <div class="col"><h3 class="subhead">3D &amp; reconstruction</h3> [acq3d … recon-download, main lines 335-378] </div>
    </div>
    <div class="pane" data-sec="learn" hidden role="tabpanel">
      <div class="col"><h3 class="subhead">Overlays</h3> [curveshow … mathshow, main lines 246-261 incl. intro tiny] </div>
      <div class="col"><h3 class="subhead">Artifacts</h3> [motion … artifact-help, main lines 285-295] </div>
      <div class="col"><h3 class="subhead">Measure</h3> [measuremode radios/readout/clear, main lines 323-330] </div>
    </div>
  </section>

  <section class="panel" id="metrics" aria-label="Measurements"> …unchanged… </section>
</main>
```

All `<details class="group">`/`<summary>` wrappers are dropped. `#abdelta` moves out of the old protocol section to just under the strip bar.

- [ ] **Step 2: Verify no control id was lost**

Run (compares ids on main vs working tree):
```bash
{ git show main:web/simulator.html; cat web/simulator.html; } | grep -o 'id="[^"]*"' | sort | uniq -u
```
Expected: only ids intentionally added (`preset-rail`, `preset-list`) — none removed.

- [ ] **Step 3: Commit** — `git commit -m "feat(sim): console markup — preset rail, tabbed control strip"`

---

### Task 2: Console CSS (`web/styles.css`)

**Files:**
- Modify: `web/styles.css` — replace the `#app` layout rule (line 70), the `details.group` rules (72-85, 100), `.ctrl-search` sticky (88-100), and the ≤920px media block (456-476); add rail/strip/tabs/pane rules.

**Interfaces:**
- Consumes: Task 1's classes (`#preset-rail`, `.rail-head`, `#preset-list`, `.strip`, `.strip-bar`, `.tabs`, `.pane`, `.col`, `.subhead`, `.strip-actions`).
- Produces: `.pane[hidden]` hidden via the global `[hidden]` rule; `body.filtering` reveals matching panes for search.

- [ ] **Step 1: Write the layout CSS** (key rules):

```css
/* Console layout: rail | image | metrics, tabbed strip under the image (planner model). */
#app { display: grid; grid-template-columns: 232px minmax(0,1fr) 230px;
  grid-template-rows: minmax(0,1fr) auto; gap: 10px; padding: 10px; height: calc(100% - 52px); }
#preset-rail { grid-row: 1 / 3; display: flex; flex-direction: column; min-height: 0; padding: 0; }
.rail-head { padding: 10px 12px 8px; border-bottom: 1px solid var(--border); }
.rail-head h2 { font-size: 11px; letter-spacing: .6px; color: var(--text-dim); text-transform: uppercase; margin: 0; }
#preset-list { list-style: none; margin: 0; padding: 6px; overflow-y: auto; flex: 1; min-height: 0; }
#preset-list button { display: block; width: 100%; text-align: left; background: none; border: none;
  color: #c4cad2; font-size: 12px; padding: 7px 8px; border-radius: 2px; cursor: pointer; }
#preset-list button:hover { background: var(--raised); }
#preset-list li.active button { background: #142231; color: var(--accent-hi); outline: 1px solid var(--accent); }
#metrics { grid-column: 3; grid-row: 1 / 3; }
.viewport { display: flex; flex-direction: column; gap: 10px; min-width: 0; min-height: 0; overflow-y: auto; }
.image-row { flex: 1 1 auto; min-height: min(48vh, 460px); }
.strip { max-height: 40vh; overflow-y: auto; display: flex; flex-direction: column; }
.strip-bar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  position: sticky; top: -12px; margin: -12px -12px 0; padding: 10px 12px; z-index: 5;
  background: var(--panel); border-bottom: 1px solid var(--border); }
.tabs { display: flex; gap: 2px; }
.tabs button { background: none; border: 1px solid transparent; border-bottom: 2px solid transparent;
  color: var(--text-dim); font-size: 12px; font-weight: 700; padding: 6px 12px; cursor: pointer; }
.tabs button:hover { color: var(--text); }
.tabs button.on { color: var(--accent-hi); border-bottom-color: var(--accent); }
.ctrl-search { position: relative; flex: 1; min-width: 140px; max-width: 260px; }
.strip-actions { display: flex; gap: 6px; margin-left: auto; }
.strip-actions button { background: var(--raised); color: var(--text); border: 1px solid var(--border);
  border-radius: 2px; padding: 6px 10px; font-size: 11px; font-weight: 700; cursor: pointer; }
.strip-actions button:hover { border-color: var(--border-hi); }
.strip-actions button.on { background: #142231; color: var(--accent-hi); border-color: var(--accent); }
.pane { display: flex; gap: 26px; flex-wrap: wrap; padding: 4px 0 10px; }
.pane .col { flex: 1 1 220px; min-width: 200px; max-width: 340px; }
.subhead { font-size: 10px; letter-spacing: .6px; color: var(--text-faint); text-transform: uppercase;
  font-weight: 700; margin: 12px 0 0; }
#abdelta:empty { display: none; }
```

Delete: `details.group > summary` rules (72-85), the `data-sec="protocol"` rule (85), `.ctrl-search` sticky block + its 920px override (88-100). `.group h2` heading style is reused by `.rail-head h2`.

- [ ] **Step 2: Responsive** — in the ≤920px block: `#app { grid-template-columns: 1fr; grid-template-rows: none; height: auto; }`, `.viewport { order: -1; min-height: 52vh; overflow: visible; }`, `#preset-rail, #metrics { grid-column: auto; grid-row: auto; }`, `.strip { max-height: none; overflow: visible; }`, `#preset-list { max-height: 30vh; }`. Add `.tabs button` to the `pointer: coarse` min-height list.

- [ ] **Step 3: Commit** — `git commit -m "style(sim): console grid, preset rail, tabbed strip"`

---

### Task 3: JS wiring (`web/app.js`, `web/tour.js`)

**Files:**
- Modify: `web/app.js` — replace `setupCollapsibles`/`restoreSectionState`/`SECTION_LS` (lines 922-947) with tabs; rework `setupSearch` (949-991); add `buildPresetRail`/`syncPresetRail`; call sites in `buildControls` (line 637), preset-reset sites (1274, 1287), `onPreset` (849); update `TOUR` steps (294-317) + intro copy (simulator.html lines 51-52).
- Modify: `web/tour.js` — add `step.reveal()` hook in `showStep()` (~line 34).

**Interfaces:**
- Consumes: Task 1 markup (`.tabs button[data-tab]`, `.pane[data-sec]`, `#preset-list`).
- Produces: `showTab(sec)` (module-scope, `"setup"|"contrast"|"quality"|"learn"`), `syncPresetRail()`.

- [ ] **Step 1: Tabs + rail implementation**

```js
// Tabbed control strip: one pane visible at a time; remember the active tab per-device.
const TAB_LS = "mrisim_tab";
function showTab(sec) {
  document.querySelectorAll(".tabs button[data-tab]").forEach((b) => {
    const on = b.dataset.tab === sec;
    b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".pane[data-sec]").forEach((p) => { p.hidden = p.dataset.sec !== sec; });
  try { localStorage.setItem(TAB_LS, sec); } catch (e) { /* private mode */ }
}
function setupTabs() {
  document.querySelectorAll(".tabs button[data-tab]").forEach((b) =>
    b.addEventListener("click", () => showTab(b.dataset.tab)));
  let sec = "setup";
  try { sec = localStorage.getItem(TAB_LS) || sec; } catch (e) { /* private mode */ }
  if (!document.querySelector(`.pane[data-sec="${sec}"]`)) sec = "setup";
  showTab(sec);
}

// Presets rail: buttons proxy the hidden #preset select (single source of truth).
function buildPresetRail() {
  const list = $("preset-list");
  [...$("preset").options].forEach((o) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button"; b.textContent = o.value ? o.value : "Custom";
    b.addEventListener("click", () => {
      $("preset").value = o.value;
      $("preset").dispatchEvent(new Event("change"));
      syncPresetRail();
    });
    li.dataset.preset = o.value; li.appendChild(b); list.appendChild(li);
  });
  syncPresetRail();
}
function syncPresetRail() {
  const cur = $("preset").value;
  document.querySelectorAll("#preset-list li").forEach((li) =>
    li.classList.toggle("active", li.dataset.preset === cur));
}
```

- [ ] **Step 2: Search rework** — same row-filter idea, scoped to pane columns; while filtering every pane shows its hits (panes with none stay hidden); clearing restores the active tab:

```js
function setupSearch() {
  const box = $("ctrl-find"), clear = $("ctrl-find-x"), empty = $("ctrl-find-empty");
  if (!box) return;
  const colRows = (c) => c.querySelectorAll(":scope > label, :scope > .btnrow, :scope > p, :scope > div, :scope > button");
  const run = () => {
    const term = box.value.trim().toLowerCase();
    clear.hidden = term === "";
    if (!term) {
      document.querySelectorAll(".pane[data-sec]").forEach((p) => {
        p.querySelectorAll(".col").forEach((c) => {
          c.style.display = "";
          colRows(c).forEach((r) => { r.style.display = ""; });
        });
      });
      document.body.classList.remove("filtering");
      showTab(document.querySelector(".tabs button.on")?.dataset.tab || "setup");
      empty.hidden = true;
      return;
    }
    document.body.classList.add("filtering");
    let anyHit = false;
    document.querySelectorAll(".pane[data-sec]").forEach((p) => {
      let paneHit = false;
      p.querySelectorAll(".col").forEach((c) => {
        const head = (c.querySelector(".subhead")?.textContent || "").toLowerCase();
        const headHit = head.includes(term);
        let colHit = headHit;
        colRows(c).forEach((r) => {
          if (r.classList.contains("subhead")) return;
          const hit = headHit || r.textContent.toLowerCase().includes(term);
          r.style.display = hit ? "" : "none";
          if (hit) colHit = true;
        });
        c.style.display = colHit ? "" : "none";
        if (colHit) paneHit = true;
      });
      p.hidden = !paneHit;
      if (paneHit) anyHit = true;
    });
    empty.hidden = anyHit;
  };
  box.addEventListener("input", run);
  clear.addEventListener("click", () => { box.value = ""; run(); box.focus(); });
  box.addEventListener("keydown", (e) => { if (e.key === "Escape" && box.value) { box.value = ""; run(); } });
}
```

Note: `showTab` un-hides only the active pane, so restoring after a filter is exactly `showTab(activeTab)`. The `.tabs button.on` class is never touched by filtering, so it still records the active tab.

Call sites: in `buildControls` replace `setupCollapsibles();` with `setupTabs(); buildPresetRail();`. Append `syncPresetRail();` after each `$("preset").value = ""` (1274, 1287) and after `$("preset").value = name;` in `onPreset` (849).

- [ ] **Step 3: tour.js reveal hook** — in `showStep()`, right after `const step = STEPS[idx];`:

```js
if (typeof step.reveal === "function") step.reveal();   // e.g. activate the tab holding the target
```

- [ ] **Step 4: TOUR steps + copy** — add `reveal: () => showTab("setup")` to the `#sequence` step, `showTab("contrast")` to `#tr`, `showTab("quality")` to `#acq3d`, `showTab("learn")` to `#measuremode`; retarget the preset step `el: "#preset"` → `el: "#preset-list"` (rail); curve-step text "in the <b>Visualizations</b> section" → "on the <b>Learn</b> tab"; `#ctrl-find` step text → "Type here to find any control — matching rows from every tab appear together."; in `simulator.html` intro bullet 2, replace "on the left panel … Section headers <b>collapse</b>, and the <b>Find a control</b> box at the top jumps you to any parameter." with "in the strip below the image — four tabs (<b>Setup · Contrast · Quality · Learn</b>) group every control, and <b>Find a control</b> searches across all of them."

- [ ] **Step 5: Lint + unit tests**

Run: `npx eslint web/ && npm run test:web`
Expected: clean / all pass.

- [ ] **Step 6: Commit** — `git commit -m "feat(sim): tabs, preset rail, search + tour wiring for the console"`

---

### Task 4: Smoke test, cache bump, verification

**Files:**
- Modify: `web/smoke.mjs:59-111` (accordion steps → tab steps), `web/sw.js:27` (cache v15→v16)

**Interfaces:**
- Consumes: Task 1-3 DOM (`.tabs button[data-tab]`, `.pane[data-sec]`, `#preset-list`).

- [ ] **Step 1: Rewrite the accordion smoke steps** (lines 59-68 collapse/expand; the search assertions at 81-89; the open-all at 111):

```js
step("tabbed control strip");
if (await page.evaluate(() => document.querySelector('.pane[data-sec="quality"]').offsetParent !== null))
  fail("Quality pane should be hidden initially");
await page.click('.tabs button[data-tab="quality"]');
if (!(await page.evaluate(() => document.querySelector('.pane[data-sec="quality"]').offsetParent !== null)))
  fail("clicking the Quality tab did not show its pane");
await page.click('.tabs button[data-tab="contrast"]');
```

Search step: fill `#ctrl-find` with "bandwidth" → wait for `body.classList.contains("filtering")` and the `#bw` row visible; clear → wait for the contrast pane visible and quality pane hidden. Replace the open-all-details sweep line with `await page.evaluate(() => document.querySelectorAll(".pane").forEach((p) => { p.hidden = false; }));` before the full control sweep. After the preset-apply step, add: click the first `#preset-list li button` with a non-empty `li.dataset.preset` and assert that `li` gains `.active`.

- [ ] **Step 2: Bump `web/sw.js`** `CACHE = "mrisim-v15"` → `"mrisim-v16"`.

- [ ] **Step 3: Full local verification**

Run: `npx eslint web/ && npm run test:web`; then serve `web/` (`python -m http.server`) and drive `simulator.html` with Playwright: boot to `#app`, tab switching, search filter + restore, rail preset click applies + highlights, `document.documentElement.scrollHeight <= innerHeight` at 1440×900, single column at 900px wide.
Expected: all pass; no page scroll on desktop.

- [ ] **Step 4: Commit** — `git commit -m "test(sim): console smoke steps; bump sw cache to v16"`
