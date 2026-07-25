# Render-path orientation mismatch (default vs FOV-planning) — design

**Status:** RESOLVED (branch `fix/sagittal-render-convention`). The diagnosis below was refined
during implementation: the mismatch is **sagittal-only** and is a *double-flip*, not the global
resampling difference first suspected. `get_slice` flips sagittal L-R (`np.fliplr`, into the
radiological anterior-left convention) and the display layer applied a *second* flip
(`ax.invert_xaxis()`), netting to a mirrored (anterior-right) main image; the oblique path skipped
`get_slice`'s flip and so, with the single display invert, rendered correctly. Verified objectively
by label centroids (spinal cord posterior vs vertebral bodies anterior) and in the live browser.

**Fix shipped:** (1) the oblique branch of `Simulator._get_phantom_slice` now applies `np.fliplr`
for sagittal so both render paths share `get_slice`'s convention; (2) the redundant sagittal
`ax.invert_xaxis()` was removed from every main-image display path (`web_adapter._draw_image`,
`app_qt._match_sagittal_flip`, `app_protocol` review/thumbnail) and the probe label-map
compensation (`web_adapter._probe_data`). The scout/FOV-planning coordinate system and recon
reformats were left untouched (they were already un-inverted and correct). Regression guard:
`tests/test_simulator.py::test_sagittal_render_paths_agree_on_handedness`.

---

**Original diagnosis (superseded in part — the resampling-difference theory below was wrong; kept
for history):**

## Symptom

On the web simulator, an asymmetric region (Knee, Spine) renders **mirrored/wrong in the default
view**, but as soon as FOV planning is enabled with *any* tilt/rot angle, the main image "flips" to
the correct orientation. Reported from the live site on the Knee (sagittal) and Spine.

## Root cause (confirmed by rendering)

The engine has two slice-render paths in `src/simulator.py::_get_phantom_slice`:

- **Default / plain path** — `ph = get_slice(vol, orient, sl_idx)` (`simulator.py:277`,
  `phantom3d.get_slice`). Used when FOV planning is off, OR on when the oblique angle ≤ 0.5°.
- **Oblique path** — `oblique_plane(vol, row_vec, col_vec, center, shape=(max_dim, max_dim),
  order=0)` (`simulator.py:265-275`), taken only when `fov_planning and (|tilt|>0.5 or |rot|>0.5)`,
  with vectors from `oblique.plane_from_angles(orient, tilt, rot)`.

The two paths produce **different orientations**, and this is **global** — verified by rendering the
BRAIN sagittal through both paths: the default shows the face on the right, the oblique shows it on
the left (the conventional radiological orientation). It is only *visible* on asymmetric anatomy
(knee/spine, brain-sagittal); symmetric views (brain axial) hide it. The user's ground truth: the
**oblique orientation is correct**; the default path is the wrong one.

**Important nuance (why it is NOT a one-line flip):** `oblique_plane` does not merely mirror
`get_slice`. It resamples onto a **square `(max_dim, max_dim)` grid with its own centering/scale**
(`_compute_slab_center`, `sg.cfg_for`). A quantitative correlation of `get_slice`, `fliplr(get_slice)`,
`flipud(get_slice)` against `oblique_plane(0°)` was **inconclusive** — no single axis-flip maps one
to the other, because the sampling geometry differs. So the fix must reproduce the oblique path's
*geometry*, not guess a flip.

This is orthogonal to the atlas-tilt fix (PR #481): `region_orient.straighten` rotates the *volume*
at load, so both paths see the same volume; this mismatch is in the *sampling*, pre-existing.

## Proposed fix

1. **Unify the two paths.** In `_get_phantom_slice`, make the plain branch produce the same
   geometry as the oblique branch at zero angle — i.e. route the default slice through the same
   `oblique_plane` sampling with `tilt=rot=0` (dropping the `>0.5°` guard so the sampling is
   identical at 0°), OR extract the exact orientation/resample `oblique_plane` applies and apply it
   to `get_slice`. Routing through `oblique_plane(0°)` is preferred — default and FOV become
   identical *by construction*, and the jarring flip when crossing 0.5° disappears.
   - Watch performance: `oblique_plane` resamples every slice; confirm it is acceptable for the
     default (non-planning) render (it already runs on every angled render). Cache/short-circuit if
     needed.
   - Preserve the plain branch's post-steps that the oblique branch skips: sat-band
     (`_apply_sat_band`, only active with `fov_planning`), FOV crop (`sg.fov_transform`), inplane
     crop. Verify these still align on the unified geometry.

2. **Reconcile every other `get_slice` consumer** so the whole app shares one convention:
   - `reslice_3d` (3D recon reformats, `simulator.py:632`) — recon must match the main image.
   - `_b0_field_slice` and any overlay slices keyed to the phantom slice.
   - The 3-plane **scout localizer** render.

3. **Audit the FOV-planning overlay coordinates** (`web/app.js`, `web/protocol.js`): the scout band,
   FOV box, oblique center, and measure tools compute display coordinates assuming the *current*
   orientation. Changing the default main-image orientation may shift what the overlays must map to.
   NOTE: in FOV-angled mode the app already pairs scout(`get_slice`) ↔ main(`oblique`) and that
   workflow works today — so making the default main also oblique-convention should *increase*
   consistency, but this must be verified with a real scout-drag, not assumed. See memory
   [[project_scout_band_interaction]].

## Verification (required before shipping)

- Before/after engine renders for **Brain, Knee, Spine** in all three planes (sagittal, coronal,
  axial), default vs FOV-planning — confirm default now matches FOV and reads anatomically correct
  (face-left brain sagittal; patella-anterior knee; vertebral bodies anterior spine).
- **Scout-drag check** in a real browser (Playwright): enable FOV planning, drag the band/FOV box,
  confirm the prescription lands where clicked (no mirrored drag).
- **Recon check**: acquire a 3D slab, open reconstruction, confirm reformats match the main image
  orientation and click-to-navigate is not mirrored.
- **Measure check**: ruler/ROI on the main image still reads correctly.
- Full `web/smoke.mjs` + `pytest` + `ruff`/`mypy` green; `web/sw.js` cache bump.

## Risks

- **Blast radius:** `get_slice` (or its consumers) is the core render primitive — main image, scout,
  recon, overlays, measure. A wrong move mirrors everything or misaligns the planning drag. Hence the
  full-consumer audit + browser verification above are mandatory, not optional.
- **Convention question:** treat the **oblique path as canonical** (user-confirmed correct on the
  knee; conventional on the brain). Do not "fix" by making oblique match the (wrong) default.

## Out of scope

Atlas base-tilt corrections (done, PR #481, `src/region_orient.py`). No new UI. No change to the
oblique path's own math beyond using it at 0° for the default.
