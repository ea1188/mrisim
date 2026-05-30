"""
app.py — Phase 1 Gradio web front-end for the MRI simulator.

A minimal, live web layer over the Qt-free acquisition engine in
``src/simulator.py`` (class :class:`Simulator`, method ``simulate(params)``).
This deliberately does NOT use ``src/simulate.py`` — that is the legacy 2-D
matplotlib demo with hardcoded tissues and no field-strength handling.

Architecture notes:
  * ``src/`` is injected onto ``sys.path`` before any local imports, because the
    engine modules import each other by bare name (no installable package).
  * The Simulator is stateful (active volume on ``self.volume``, view state on
    ``self.orientation`` / ``self.slice_idx``, internal caches like
    ``self._b0_cache``). We therefore hold one Simulator instance *per Gradio
    session* in ``gr.State`` rather than a module global, mirroring the
    attribute-setup of ``app_qt._sync_sim()``.
  * Region label volumes (and their real-MRI texture fields) are immutable and
    expensive to build, so they are cached once at module scope and shared
    read-only across sessions; only the per-session Simulator mutates state.

Run with ``python app.py``; the Codespace forwards the port automatically.
"""

import os
import sys

# --- src/ onto sys.path before any engine import (bare-name imports) ---------
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import numpy as np
import gradio as gr

import body_phantoms
from brainweb_loader import get_brainweb_or_synthetic
from simulator import Simulator, default_params

# Register body tissue properties with the engine's tissue tables (Abdomen,
# Knee, Spine, Pelvis labels), exactly as the Qt app does on startup.
body_phantoms.merge_into_engine()

# --- Phase 1 controls --------------------------------------------------------
# Synthetic regions only (no NIfTI loading — that is Phase 2). Brain comes from
# the BrainWeb/synthetic loader; the rest from body_phantoms.build_region.
REGIONS = body_phantoms.REGION_NAMES                      # Brain, Abdomen, Knee, Spine, Pelvis
SEQUENCES = ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery"]

# Physical FOV (mm) per region — mirrors app_qt._get_native_fov.
_NATIVE_FOV = {"Brain": 220.0, "Abdomen": 380.0, "Spine": 380.0,
               "Pelvis": 380.0, "Knee": 150.0}

# Module-scope caches of immutable region data, shared read-only across sessions.
_VOLUME_CACHE: dict[str, np.ndarray] = {}
_TEXTURE_CACHE: dict[str, "np.ndarray | None"] = {}


def _region_data(name: str) -> tuple[np.ndarray, "np.ndarray | None", float]:
    """Return (label volume, real-MRI texture or None, native FOV mm) for a region.

    Built once per region and memoised; the arrays are treated as read-only.
    """
    if name not in _VOLUME_CACHE:
        if name == "Brain":
            vol, _src = get_brainweb_or_synthetic()
            _VOLUME_CACHE[name] = vol
            _TEXTURE_CACHE[name] = None
        else:
            _VOLUME_CACHE[name] = body_phantoms.build_region(name)
            _TEXTURE_CACHE[name] = body_phantoms.build_region_texture(name)
    return _VOLUME_CACHE[name], _TEXTURE_CACHE.get(name), _NATIVE_FOV.get(name, 220.0)


def _to_display(image: np.ndarray) -> np.ndarray:
    """Float engine output → 8-bit grayscale for gr.Image.

    Normalises against the 99.5th percentile (so a stray bright noise voxel does
    not crush the window) and flips vertically to match the engine's
    ``origin="lower"`` display convention used in the Qt app.
    """
    img = np.nan_to_num(np.asarray(image, dtype=float), nan=0.0,
                        posinf=0.0, neginf=0.0)
    pos = img[img > 0]
    vmax = float(np.percentile(pos, 99.5)) if pos.size else float(img.max())
    if vmax <= 0:
        vmax = 1.0
    norm = np.clip(img / vmax, 0.0, 1.0)
    return np.flipud((norm * 255.0).astype(np.uint8))


def render_mri(region: str, sequence: str, tr: float, te: float,
               flip: float, ti: float, field: str,
               sim: "Simulator | None"):
    """Single render callback: set up the per-session Simulator, simulate, display.

    Returns ``(display_image, sim)`` — the second value flows back into
    ``gr.State`` so the same Simulator instance (and its caches) is reused for
    this session. The metrics dict from ``simulate`` is intentionally discarded
    in Phase 1.
    """
    if sim is None:
        sim = Simulator()

    vol, texture, native_fov = _region_data(region)

    # Mirror app_qt._sync_sim: copy active volume + view/geometry state onto the
    # controller. Phase 1 shows an axial mid-slice, no oblique planning.
    sim.volume = vol
    sim.vessels = None
    sim.activation = None
    sim.real_tof = None
    sim.texture = texture if (texture is not None and texture.shape == vol.shape) else None
    sim.native_fov = native_fov
    sim.orientation = "axial"
    sim.slice_idx = vol.shape[0] // 2
    sim.fov_planning = False
    sim.tilt = 0.0
    sim.rot = 0.0
    sim.inplane_fov_pct = 100.0
    sim.inplane_off = 0.0

    params = default_params(
        sequence=sequence, TR=float(tr), TE=float(te),
        flip_angle=float(flip), TI=float(ti), FOV=native_fov,
        field_strength=field,
    )
    image, _metrics = sim.simulate(params)
    return _to_display(image), sim


# A T2-weighted starting point for the comparison panel (long TR/TE) versus the
# T1-weighted left default (short TR/TE) — the canonical contrast lesson, so
# enabling Compare mode immediately shows T1 vs T2 on the same anatomy.
_T2W_TR, _T2W_TE = 4000.0, 90.0


def render_both(region, sequence, field,
                tr_l, te_l, flip_l, ti_l,
                tr_r, te_r, flip_r, ti_r,
                sim_l, sim_r):
    """Re-render BOTH panels — used on shared-control (region/sequence/field)
    changes. Both panels point at the same module-cached region volume; only
    their parameter dicts differ. The two Simulators are independent so their
    engine state (volume/view/caches) never races between panels."""
    img_l, sim_l = render_mri(region, sequence, tr_l, te_l, flip_l, ti_l, field, sim_l)
    img_r, sim_r = render_mri(region, sequence, tr_r, te_r, flip_r, ti_r, field, sim_r)
    return img_l, sim_l, img_r, sim_r


def _on_sequence_change(region, sequence, field,
                        tr_l, te_l, flip_l, ti_l,
                        tr_r, te_r, flip_r, ti_r,
                        sim_l, sim_r):
    """Sequence is shared: re-render both panels and toggle each panel's TI
    slider (IR shows TI, every other sequence hides it)."""
    img_l, sim_l, img_r, sim_r = render_both(
        region, sequence, field, tr_l, te_l, flip_l, ti_l,
        tr_r, te_r, flip_r, ti_r, sim_l, sim_r)
    ti_vis = gr.update(visible=(sequence == "Inversion Recovery"))
    return img_l, sim_l, img_r, sim_r, ti_vis, ti_vis


def _on_compare_toggle(compare, region, sequence, field,
                       tr_r, te_r, flip_r, ti_r, sim_r):
    """Show/hide the right panel. On enable, render it so it isn't stale; on
    disable, leave its image untouched (gr.update())."""
    if compare:
        img_r, sim_r = render_mri(region, sequence, tr_r, te_r, flip_r, ti_r, field, sim_r)
        return gr.update(visible=True), img_r, sim_r
    return gr.update(visible=False), gr.update(), sim_r


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="MRI Simulator") as demo:
        gr.Markdown("# MRI Simulator\nInteractive spin-physics simulation. "
                    "Enable **Compare mode** to view the same anatomy under two "
                    "parameter sets side by side (e.g. T1- vs T2-weighting).")

        # One Simulator per panel, each in its own session state (no shared
        # instance — see render_both).
        sim_l = gr.State(None)
        sim_r = gr.State(None)

        # --- Shared, top-level controls (drive both panels) ---
        with gr.Row():
            region = gr.Dropdown(REGIONS, value="Brain", label="Region", scale=2)
            sequence = gr.Dropdown(SEQUENCES, value="Spin Echo", label="Sequence", scale=2)
            field = gr.Radio(["1.5T", "3T"], value="3T", label="Field strength", scale=2)
            compare = gr.Checkbox(value=False, label="Compare mode", scale=1)

        with gr.Row():
            # --- Panel A (always visible; the single-panel layout when off) ---
            with gr.Column():
                gr.Markdown("### Panel A")
                image_l = gr.Image(label="Panel A", type="numpy",
                                   image_mode="L", height=512)
                tr_l = gr.Slider(50, 5000, value=500, step=10, label="TR (ms)")
                te_l = gr.Slider(1, 300, value=15, step=1, label="TE (ms)")
                flip_l = gr.Slider(1, 180, value=90, step=1, label="Flip angle (°)")
                ti_l = gr.Slider(50, 4000, value=2500, step=10, label="TI (ms)",
                                 visible=False)

            # --- Panel B (revealed only in Compare mode) ---
            with gr.Column(visible=False) as panel_b:
                gr.Markdown("### Panel B")
                image_r = gr.Image(label="Panel B", type="numpy",
                                   image_mode="L", height=512)
                tr_r = gr.Slider(50, 5000, value=_T2W_TR, step=10, label="TR (ms)")
                te_r = gr.Slider(1, 300, value=_T2W_TE, step=1, label="TE (ms)")
                flip_r = gr.Slider(1, 180, value=90, step=1, label="Flip angle (°)")
                ti_r = gr.Slider(50, 4000, value=2500, step=10, label="TI (ms)",
                                 visible=False)

        shared = [region, sequence, field]
        left_params = [tr_l, te_l, flip_l, ti_l]
        right_params = [tr_r, te_r, flip_r, ti_r]

        both_inputs = shared + left_params + right_params + [sim_l, sim_r]
        both_outputs = [image_l, sim_l, image_r, sim_r]

        # Shared controls re-render BOTH panels.
        region.change(render_both, both_inputs, both_outputs)
        field.change(render_both, both_inputs, both_outputs)
        # Sequence also toggles each panel's TI slider.
        sequence.change(_on_sequence_change, both_inputs,
                        both_outputs + [ti_l, ti_r])

        # Per-panel sliders render ONLY their own panel (independent) — moving
        # the left TR does not re-render the right. render_mri is reused as-is:
        # its signature is (region, sequence, tr, te, flip, ti, field, sim).
        left_inputs = [region, sequence, tr_l, te_l, flip_l, ti_l, field, sim_l]
        right_inputs = [region, sequence, tr_r, te_r, flip_r, ti_r, field, sim_r]
        for s in left_params:
            s.release(render_mri, left_inputs, [image_l, sim_l])
        for s in right_params:
            s.release(render_mri, right_inputs, [image_r, sim_r])

        # Compare toggle shows/hides Panel B (and renders it fresh on enable).
        compare.change(_on_compare_toggle,
                       [compare] + shared + right_params + [sim_r],
                       [panel_b, image_r, sim_r])

        # Initial render of both panels on load (Panel B stays hidden until toggled).
        demo.load(render_both, both_inputs, both_outputs)

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
