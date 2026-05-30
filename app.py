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


def _on_sequence_change(region, sequence, tr, te, flip, ti, field, sim):
    """Sequence change also toggles TI-slider visibility (IR only)."""
    img, sim = render_mri(region, sequence, tr, te, flip, ti, field, sim)
    return img, sim, gr.update(visible=(sequence == "Inversion Recovery"))


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="MRI Simulator — Phase 1") as demo:
        gr.Markdown("# MRI Simulator\nInteractive spin-physics simulation. "
                    "Move a control to re-render.")
        sim_state = gr.State(None)

        with gr.Row():
            with gr.Column(scale=1):
                region = gr.Dropdown(REGIONS, value="Brain", label="Region")
                sequence = gr.Dropdown(SEQUENCES, value="Spin Echo", label="Sequence")
                tr = gr.Slider(50, 5000, value=500, step=10, label="TR (ms)")
                te = gr.Slider(1, 300, value=15, step=1, label="TE (ms)")
                flip = gr.Slider(1, 180, value=90, step=1, label="Flip angle (°)")
                ti = gr.Slider(50, 4000, value=2500, step=10, label="TI (ms)",
                               visible=False)
                field = gr.Radio(["1.5T", "3T"], value="3T", label="Field strength")
            with gr.Column(scale=2):
                output = gr.Image(label="Image", type="numpy",
                                  image_mode="L", height=512)

        ctrl_inputs = [region, sequence, tr, te, flip, ti, field, sim_state]
        img_outputs = [output, sim_state]

        # Sequence change re-renders AND toggles the TI slider.
        sequence.change(_on_sequence_change, ctrl_inputs,
                        [output, sim_state, ti])

        # Every other control fires one render per interaction (no full reruns).
        region.change(render_mri, ctrl_inputs, img_outputs)
        field.change(render_mri, ctrl_inputs, img_outputs)
        for s in (tr, te, flip, ti):
            s.release(render_mri, ctrl_inputs, img_outputs)

        # Initial render on page load.
        demo.load(render_mri, ctrl_inputs, img_outputs)

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
