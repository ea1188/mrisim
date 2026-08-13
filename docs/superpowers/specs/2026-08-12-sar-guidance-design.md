# SAR-limit guidance — design

**Date:** 2026-08-12
**Status:** approved (design), implementing
**Origin:** student suggestion — "a SAR limit warning so you can pick what parameters to change."

## Purpose

When the web simulator's estimated head SAR exceeds the limit, tell the user
**which parameters to change and to what value** to get back under — instead of
just the bare ⚠ it shows today. Informational (no auto-apply).

## Background (what already exists)

- The engine estimates SAR in `src/simulator.py` via `presets.estimate_sar(FA, TR, sequence)`
  and returns `sar_head` (field-scaled by `(B0/3)²`) and `sar_exceeds = sar_head > 3.2`
  in the metrics dict.
- `web/app.js` already renders `x-sar` = `sar_head + " W/kg" + (sar_exceeds ? " ⚠" : "")`.
- SAR ∝ flip_angle² · (1/TR) · sequence_factor (whole-body ×2.5 for head). The web
  path calls `estimate_sar` **without** `num_slices`, so it is fixed at 20 — **slice
  count does not move the modeled SAR** and is therefore NOT a suggested lever.

## Levers (in the current model)

flip angle (quadratic — biggest), TR (linear), sequence factor (SE 1.5, IR 2.0,
GRE 0.5, EPI 0.5, Diffusion 1.5). Field is a lever physically but **excluded** by
decision (rarely the intended mid-protocol fix).

## Computation — `web/sar_guidance.js` (pure UMD, node-tested)

Works from the **current** `sar_head` so it is automatically field-aware and can't
drift from the displayed number.

`sarGuidance({ flip_angle, TR, sequence, sar_head, limit = 3.2 })` returns:

```
{
  over: sar_head > limit,
  ratio: sar_head / limit,                 // how far over (>1 = over)
  maxSafeFa,     // int° = round(flip_angle * sqrt(limit / sar_head)), clamped [1, flip_angle-1]
  minSafeTr,     // int ms = ceil(TR * sar_head / limit)
  lowerSeqOptions // display names of sequences whose factor alone gets under the limit
}
```

Derivation (SAR ∝ FA², so scaling FA by √(limit/sar_head) hits the limit; SAR ∝ 1/TR,
so scaling TR by sar_head/limit hits it). `maxSafeFa` matches the desktop formula
`90·√(limit·TR/(2500·seqfactor))` but is field-aware because it divides the actual
`sar_head`. Sequence options: for each candidate with factor `f_new < f_cur`, include
it iff `sar_head · f_new/f_cur ≤ limit`. Never list the current sequence. When not
`over`, the target fields are null/empty.

Sequence factor table (mirrors `estimate_sar`'s `seq_factors`, keyed by the web
display names): Spin Echo 1.5, Inversion Recovery 2.0, Diffusion (DWI) 1.5,
Gradient Echo 0.5, Echo Planar (EPI) 0.5; others default 1.0.

## UI — `web/app.js` + `web/simulator.html`

- Add a hidden container `#sar-guidance` near the SAR readout in `simulator.html`.
- In the metrics-render path of `app.js` (where `x-sar` is set), after computing the
  SAR text: if `m.sar_exceeds`, call `sarGuidance(...)` with the current control
  values + `m.sar_head`, build a one-line callout, and show it; else clear + hide it.
- Copy: `SAR {x} W/kg is over the 3.2 limit. Any one of these brings it under:
  lower flip angle to ≤{maxSafeFa}°, raise TR to ≥{minSafeTr} ms{, or switch to {seqs}}.`
  Omit a clause if its target is degenerate (e.g. maxSafeFa < 1, or minSafeTr absurdly
  large — cap the shown TR suggestion and drop it if it exceeds a sane ceiling, e.g.
  > 10000 ms, so we don't advise an impossible TR).
- Styling: a small warning callout using existing theme vars (a `--warn`-accented
  block), consistent with the app's flat clinical look. No new dependencies.

## Data flow

engine metrics (`sar_head`, `sar_exceeds`) → app.js render → if over, `sarGuidance`
computes targets from current controls → callout shown. Pure client-side; no engine
or network change.

## Testing — `web/sar_guidance.test.mjs`

- under limit → `over:false`, no targets.
- over limit → `maxSafeFa` and `minSafeTr` bring SAR to ≈ the limit (verify by
  plugging back into the SAR ∝ FA²/TR relation).
- `maxSafeFa` clamped ≥ 1 and < current FA.
- sequence options: from Spin Echo when far over, includes GRE/EPI; never includes
  the current sequence; empty when switching alone can't get under.
- degenerate cases: exactly at limit, tiny overage, huge overage.

## Out of scope

- Auto-apply / one-click fixes (informational only, by choice).
- Slice-count and field-strength suggestions (slices don't move the modeled SAR;
  field excluded by decision).
- Changing the SAR physics itself.

## Deploy

Static web change — live on the next `deploy-web` run. No migration, no re-seed.
`web/sw.js`: app.js is network-first shell; `sar_guidance.js` is a new shell script —
add it to the precache SHELL list and (optionally) bump the cache version.
