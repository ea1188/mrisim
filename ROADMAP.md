# MRISim Roadmap

Where the project is, and where it can go. This is a living document — a menu of
directions with honest effort/value notes, not a committed schedule. MRISim is two things
at once: a **teaching platform** for learning MRI, and a **research-grade sequence
simulator** with a headless API. Most decisions below trade off between those two hats.

## Where we are (v1.48)

A mature, dual-edition (PyQt desktop + Pyodide browser) simulator over one shared physics
engine. It already covers:

- **Sequences** — SE, FSE/TSE, GRE, IR, bSSFP, EPI, Diffusion (DWI/ADC/FA), Perfusion
  (ASL + DSC/DCE), MR Angiography (TOF/PC), SWI, fMRI BOLD, qMRI (T1/T2/T2\*).
- **Anatomy** — real BrainWeb brain, TotalSegmentator body atlases, real knee, synthetic
  fallbacks, NIfTI loading (desktop), demo pathologies.
- **Acquisition & physics** — k-space, true 3D slab + reconstruction (MPR/MIP/oblique),
  parallel imaging (SENSE/GRAPPA/CS) with g-factor, partial Fourier, non-Cartesian radial,
  contrast/Gd, fat-sat (STIR/Dixon/CHESS), B0/B1, MT, artifacts, coil shading.
- **Teaching layer** — guided lessons + a 9-module curriculum, an image-library positioning
  trainer, a scanner-console protocol planner, a read-the-scan quiz (5 topics), and a home
  launcher tying the modes together.
- **Foundations** — ~2200 tests, ruff/mypy/eslint + Playwright smokes in CI, guarded
  releases (web deploy + 3 binaries), a knowledge-graph index + ADR.

The codebase is healthy: no debt markers, strong coverage, the two highest-complexity
methods recently refactored. **Adding content (lessons, quiz questions, presets) is now
nearly free** — pure data edits. Adding *physics* is the meaty work.

## North star

> Be the clearest, most trustworthy way to **learn** MRI in a browser — and a credible,
> citable **research** sandbox for prototyping sequences and contrast.

Given how feature-complete the simulator is, the **highest-leverage near-term work is
deepening the learning experience**, not adding more physics breadth (which has steep
effort and diminishing teaching returns). The big new-physics items are worth doing when
they unlock genuinely new teaching (e.g. spectroscopy) or research use.

---

## Theme 1 — Learning & assessment  *(highest leverage)*

The platform teaches well but barely *measures* learning. This is where small effort buys
the most.

- **Quiz depth & progress** *(S–M)* — persist per-topic scores (localStorage), add a
  "review the ones you missed" pass and lightweight spaced repetition; difficulty levels;
  more question types ("which parameter changed?" on an image pair; "tune this to match the
  target"). Pure `quiz.json` + small `quiz.js` work.
- **More guided content** *(S, ongoing)* — advanced lesson tracks (an artifacts deep-dive,
  a perfusion track, MSK/body reading, contrast & fat-sat). Data-only via `lessons.json`.
- **"Reproduce the image" challenges** *(M)* — show a target image; the learner tunes
  TR/TE/etc. to match it, scored by image similarity. A new mini-mode reusing the engine.
- **Connect learn → test** *(S)* — link relevant quiz topics from each lesson and vice
  versa; a simple progress/badges view on the home launcher.
- **Image-library content** *(S, needs assets)* — drop in real, licensed MSK/body images for
  the positioning trainer (framework is already there; this needs *you* to supply images).

## Theme 2 — Physics & modality breadth  *(research + new teaching)*

Each is a new `src/` module + the standard "add a sequence" wiring (now a one-line registry
entry, see ADR-4).

- **MR Spectroscopy (MRS)** *(L)* — the most notable absent modality; output is a *spectrum*,
  not an image, so it needs a new display panel. High teaching novelty (NAA/Cr/Cho/lactate).
- **Dynamic 4D perfusion** *(M–L)* — DSC/DCE currently emit parameter maps from modelled
  kinetics; a true time-series with a scrollable dynamic + an AIF/curve-fit view would make
  the dynamics first-class (the bolus/uptake curves already exist in `dsc_dce.py`).
- **More contrast mechanisms** *(M each)* — CEST, T1ρ, an MT-ratio map, multi-echo Dixon
  water/fat maps (the pieces exist as toggles; surface them as maps).
- **Non-Cartesian spiral + 4D flow** *(M)* — radial exists; spiral trajectories and phase-
  contrast flow *quantification* (not just MIP) extend the acquisition story.
- **Bloch-equation mode** *(L)* — an optional rigorous spin-evolution path alongside the
  analytic signal equations, for fidelity and as a "show the real physics" teaching toggle.

## Theme 3 — Fidelity & anatomy

- **More anatomy** *(M, asset-dependent)* — cardiac, more body regions, a small curated
  pathology atlas beyond the demo lesions.
- **DICOM / NIfTI import in the browser** *(M)* — desktop loads NIfTI; bringing import to the
  browser (and DICOM in) closes the loop with `dicom_export`.
- **Validation expansion** *(S–M)* — grow `scripts/validation_report.py` and
  `docs/VALIDATION.md` to benchmark more sequences against literature values — the credible-
  research backbone.

## Theme 4 — Platform, performance & reach

- **Pyodide load time** *(M)* — first load is ~30–50 MB; investigate trimming the bundle /
  lazy-loading atlases / a lighter math path for the common case.
- **Render performance** *(M–L)* — profile the hot render path; consider caching or a
  WASM/WebGL assist for interactive sweeps.
- **Mobile & accessibility** *(S–M)* — a focused a11y pass (keyboard nav, ARIA, contrast)
  and continued mobile polish; the platform is educational and should be reachable.
- **Headless-API docs** *(S)* — document the `Simulator` API + `default_params` contract as
  a first-class research entry point (it is the project's stated preferred surface).

## Theme 5 — Community & research credibility

- **Citability** *(S)* — a Zenodo DOI + `CITATION.cff`; a short methods write-up / poster.
- **Custom-sequence plugin path** *(L)* — a documented extension point so researchers can
  drop in a physics module without forking (the registry refactors make this realistic).

---

## Suggested next 3–5 (if picking up tomorrow)

1. **Quiz progress + a 2nd lesson track** *(S–M, high value, no assets)* — banks the
   learning-platform lead with near-zero risk.
2. **"Reproduce the image" challenge mode** *(M)* — a fresh, engaging teaching mechanic that
   reuses everything already built.
3. **Validation-report expansion** *(S–M)* — cheap credibility for the research hat.
4. **MR Spectroscopy** *(L)* — the marquee new modality, when ready for a bigger build.
5. **Browser DICOM/NIfTI import** *(M)* — closes the import/export loop.

## Explicit non-goals (for now)

- Not a clinical/diagnostic tool — every viewport says *simulated, not for clinical use*;
  keep it that way.
- No login/accounts/backend — the browser edition is static + client-side by design;
  progress stays in `localStorage`.
- No second rendering stack — keep the single shared physics engine (ADR-1); don't fork
  desktop/browser logic.
- Don't refactor for refactoring's sake — the remaining complexity hotspots
  (`_draw_scout`, `render_scout`) are inherent and thinly coupled; leave them unless a
  feature needs them.

## How to extend (pointers)

- **Add a sequence** → physics module in `src/` + a registry line in
  `Simulator._simulate_single_slice` + the GUI/web/preset wiring (ADR-4 in the knowledge
  graph spells out the 8 steps).
- **Add a lesson / quiz question** → edit `data/lessons.json` / `web/quiz.json`; the apps
  build the menus from the data.
- **Release** → branch `release/vX.Y.Z`, bump `src/version.py` + this changelog, merge, tag;
  the tag deploys the web build and the 3 desktop binaries (guarded — verify SHA == HEAD).
