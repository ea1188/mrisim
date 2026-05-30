"""
app.py — Gradio web front-end for the MRI simulator (Phases 1–3).

A live web layer over the Qt-free acquisition engine in ``src/simulator.py``
(class :class:`Simulator`, method ``simulate(params)``). This deliberately does
NOT use ``src/simulate.py`` — that is the legacy 2-D matplotlib demo with
hardcoded tissues and no field-strength handling.

Phase 1: single-panel live rendering. Phase 2: side-by-side Compare mode.
Phase 3: three guided lessons that lock all but the relevant control and tell
the learner what to look for (lesson content lives in ``lessons.py`` as data).

Architecture notes:
  * ``src/`` is injected onto ``sys.path`` before any engine import (the engine
    modules import each other by bare name; there is no installable package).
  * The Simulator is stateful (active volume on ``self.volume``, view state on
    ``self.orientation`` / ``self.slice_idx``, caches like ``self._b0_cache``).
    We hold ONE Simulator per panel per session in ``gr.State`` — not a module
    global — so panels never race on engine state. Region label volumes and
    their textures are immutable and cached read-only at module scope, so one
    expensive region load serves both panels.
  * Sequence is a per-panel control (each panel has its own selector): the
    "SE vs FSE" lesson must show two different sequences at once, which a single
    shared sequence control cannot express.

Run with ``python app.py``; the Codespace forwards the port automatically.
"""

import os
import sys
from functools import partial

# --- src/ onto sys.path before any engine import (bare-name imports) ---------
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import numpy as np
import gradio as gr

import body_phantoms
import tissue_db
from brainweb_loader import get_brainweb_or_synthetic
from simulator import Simulator, default_params

import lessons

# Register body tissue properties with the engine's tissue tables (Abdomen,
# Knee, Spine, Pelvis labels), exactly as the Qt app does on startup.
body_phantoms.merge_into_engine()

# --- Controls / regions ------------------------------------------------------
# Synthetic regions only (no NIfTI loading — that is a later phase). Brain comes
# from the BrainWeb/synthetic loader; the rest from body_phantoms.build_region.
REGIONS = body_phantoms.REGION_NAMES                      # Brain, Abdomen, Knee, Spine, Pelvis
SEQUENCES = ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery"]

_FAT_LABEL = 4  # tissue_db label for Fat (STIR null targets fat T1)

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


# --- Rendering ---------------------------------------------------------------
def _render_core(region, sequence, tr, te, flip, ti, field, sim):
    """Set up the per-session Simulator and simulate; return (display, metrics, sim).

    Mirrors app_qt._sync_sim: copy the active (cached, read-only) volume + a
    default axial mid-slice view onto the controller, then simulate.
    """
    if sim is None:
        sim = Simulator()

    vol, texture, native_fov = _region_data(region)
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
    image, metrics = sim.simulate(params)
    return _to_display(image), metrics, sim


def render_mri(region, sequence, tr, te, flip, ti, field, sim):
    """Render one panel; returns ``(display_image, sim)`` for [image, state].

    Reused unchanged by every panel and every per-panel control — there is one
    rendering path. The metrics dict is discarded here (scan time is read via
    ``_render_core`` where a lesson needs it)."""
    img, _metrics, sim = _render_core(region, sequence, tr, te, flip, ti, field, sim)
    return img, sim


def render_both(region, field,
                seq_l, tr_l, te_l, flip_l, ti_l,
                seq_r, tr_r, te_r, flip_r, ti_r,
                sim_l, sim_r):
    """Re-render BOTH panels — used on shared-control (region/field) changes.
    Both panels point at the same module-cached region volume; only their
    parameter dicts (and per-panel sequence) differ, and the two Simulators are
    independent so engine state never races between panels."""
    img_l, sim_l = render_mri(region, seq_l, tr_l, te_l, flip_l, ti_l, field, sim_l)
    img_r, sim_r = render_mri(region, seq_r, tr_r, te_r, flip_r, ti_r, field, sim_r)
    return img_l, sim_l, img_r, sim_r


# --- Info-text formatters ----------------------------------------------------
def _fmt_scan_time(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d} min"


def _fat_null_text(field: str) -> str:
    """Live STIR readout: the TI that nulls fat at the current field strength."""
    t1_fat = tissue_db.properties(field)[_FAT_LABEL]["T1"]
    ti = lessons.fat_null_ti(t1_fat)
    return (f"### 🎯 Target TI ≈ {ti:.0f} ms to null fat at {field}\n"
            f"*(0.69 × fat T1 = {t1_fat} ms)*")


# --- Per-control event handlers ----------------------------------------------
def _on_panel_sequence(region, seq, tr, te, flip, ti, field, sim):
    """A panel's sequence changed: re-render that panel and toggle its TI
    slider (visible only for Inversion Recovery)."""
    img, sim = render_mri(region, seq, tr, te, flip, ti, field, sim)
    return img, sim, gr.update(visible=(seq == "Inversion Recovery"))


def _on_field_change(field, lesson_key, region,
                     seq_l, tr_l, te_l, flip_l, ti_l,
                     seq_r, tr_r, te_r, flip_r, ti_r,
                     sim_l, sim_r):
    """Field strength is shared: re-render both panels. If the STIR lesson is
    active, also refresh the live fat-null target text (it shifts with field)."""
    img_l, sim_l, img_r, sim_r = render_both(
        region, field, seq_l, tr_l, te_l, flip_l, ti_l,
        seq_r, tr_r, te_r, flip_r, ti_r, sim_l, sim_r)
    lesson = lessons.get(lesson_key)
    target = (gr.update(value=_fat_null_text(field), visible=True)
              if (lesson and lesson.show_target_ti) else gr.update())
    return img_l, sim_l, img_r, sim_r, target


def _on_compare_toggle(compare, region, field,
                       seq_r, tr_r, te_r, flip_r, ti_r, sim_r):
    """Show/hide the right panel. On enable, render it so it isn't stale; on
    disable, leave its image untouched."""
    if compare:
        img_r, sim_r = render_mri(region, seq_r, tr_r, te_r, flip_r, ti_r, field, sim_r)
        return gr.update(visible=True), img_r, sim_r
    return gr.update(visible=False), gr.update(), sim_r


# --- Lesson application ------------------------------------------------------
def apply_lesson(key, sim_l, sim_r):
    """Apply a lesson (or Free Explore): set every control's value / interactivity
    / visibility, render both panels, and surface the lesson's explanation plus
    any info widgets. Returns updates for LESSON_OUTPUTS (see build_ui) in order.

    Locked controls use ``interactive=False`` (the learner can see the value but
    can't move it); Free Explore releases every lock and returns the Step-2 UI.
    """
    view = lessons.resolve(key)
    c = view.controls

    img_l, m_l, sim_l = _render_core(
        view.region, c["sequence_l"].value, c["tr_l"].value, c["te_l"].value,
        c["flip_l"].value, c["ti_l"].value, view.field, sim_l)
    img_r, m_r, sim_r = _render_core(
        view.region, c["sequence_r"].value, c["tr_r"].value, c["te_r"].value,
        c["flip_r"].value, c["ti_r"].value, view.field, sim_r)

    explanation = gr.update(value=view.explanation, visible=bool(view.explanation))
    target = (gr.update(value=_fat_null_text(view.field), visible=True)
              if view.show_target_ti else gr.update(value="", visible=False))
    scan_l = (gr.update(value=f"**⏱ Estimated scan time: {_fmt_scan_time(m_l['scan_time'])}**",
                        visible=True)
              if view.show_scan_time else gr.update(value="", visible=False))
    scan_r = (gr.update(value=f"**⏱ Estimated scan time: {_fmt_scan_time(m_r['scan_time'])}**",
                        visible=True)
              if view.show_scan_time else gr.update(value="", visible=False))

    def upd(name, **extra):
        cs = c[name]
        return gr.update(value=cs.value, interactive=cs.interactive, **extra)

    is_lesson = key != lessons.FREE_EXPLORE
    compare_upd = gr.update(value=view.compare, interactive=not is_lesson)

    return (
        explanation, target,
        compare_upd, gr.update(visible=view.compare),
        upd("region"), upd("field"),
        upd("sequence_l"), upd("tr_l"), upd("te_l"), upd("flip_l"),
        upd("ti_l", visible=c["ti_l"].visible), scan_l,
        upd("sequence_r"), upd("tr_r"), upd("te_r"), upd("flip_r"),
        upd("ti_r", visible=c["ti_r"].visible), scan_r,
        img_l, img_r, sim_l, sim_r, view.key,
    )


def build_ui() -> gr.Blocks:
    _dl, _dr = lessons.DEFAULT_LEFT, lessons.DEFAULT_RIGHT

    with gr.Blocks(title="MRI Simulator") as demo:
        gr.Markdown("# MRI Simulator\nInteractive spin-physics simulation. Pick a "
                    "**guided lesson** below to be walked through one idea, or use "
                    "**Free Explore** to drive everything yourself. Enable "
                    "**Compare mode** to view two parameter sets side by side.")

        # One Simulator per panel (own session state); current lesson key tracked
        # so the field handler knows whether to refresh the STIR target text.
        sim_l = gr.State(None)
        sim_r = gr.State(None)
        lesson_state = gr.State(lessons.FREE_EXPLORE)

        # --- Guided lessons ---
        with gr.Accordion("📚 Guided Lessons", open=True):
            with gr.Row():
                lesson_buttons = [gr.Button(k, variant=("secondary" if k == lessons.FREE_EXPLORE
                                                         else "primary"))
                                  for k in lessons.keys()]
            explanation = gr.Markdown("", visible=False)
            target_ti_text = gr.Markdown("", visible=False)

        # --- Shared, top-level controls ---
        with gr.Row():
            region = gr.Dropdown(REGIONS, value="Brain", label="Region", scale=2)
            field = gr.Radio(["1.5T", "3T"], value="3T", label="Field strength", scale=2)
            compare = gr.Checkbox(value=False, label="Compare mode", scale=1)

        with gr.Row():
            # --- Panel A (always visible; the single-panel layout when off) ---
            with gr.Column():
                gr.Markdown("### Panel A")
                sequence_l = gr.Dropdown(SEQUENCES, value=_dl.sequence, label="Sequence")
                image_l = gr.Image(label="Panel A", type="numpy", image_mode="L", height=480)
                scan_time_l = gr.Markdown("", visible=False)
                tr_l = gr.Slider(50, 5000, value=_dl.tr, step=10, label="TR (ms)")
                te_l = gr.Slider(1, 300, value=_dl.te, step=1, label="TE (ms)")
                flip_l = gr.Slider(1, 180, value=_dl.flip, step=1, label="Flip angle (°)")
                ti_l = gr.Slider(50, 4000, value=_dl.ti, step=1, label="TI (ms)", visible=False)

            # --- Panel B (revealed only in Compare mode) ---
            with gr.Column(visible=False) as panel_b:
                gr.Markdown("### Panel B")
                sequence_r = gr.Dropdown(SEQUENCES, value=_dr.sequence, label="Sequence")
                image_r = gr.Image(label="Panel B", type="numpy", image_mode="L", height=480)
                scan_time_r = gr.Markdown("", visible=False)
                tr_r = gr.Slider(50, 5000, value=_dr.tr, step=10, label="TR (ms)")
                te_r = gr.Slider(1, 300, value=_dr.te, step=1, label="TE (ms)")
                flip_r = gr.Slider(1, 180, value=_dr.flip, step=1, label="Flip angle (°)")
                ti_r = gr.Slider(50, 4000, value=_dr.ti, step=1, label="TI (ms)", visible=False)

        left_params = [tr_l, te_l, flip_l, ti_l]
        right_params = [tr_r, te_r, flip_r, ti_r]

        both_inputs = [region, field,
                       sequence_l, tr_l, te_l, flip_l, ti_l,
                       sequence_r, tr_r, te_r, flip_r, ti_r,
                       sim_l, sim_r]
        both_outputs = [image_l, sim_l, image_r, sim_r]

        # Shared controls re-render BOTH panels.
        region.change(render_both, both_inputs, both_outputs)
        field.change(_on_field_change,
                     [field, lesson_state, region,
                      sequence_l, tr_l, te_l, flip_l, ti_l,
                      sequence_r, tr_r, te_r, flip_r, ti_r,
                      sim_l, sim_r],
                     [image_l, sim_l, image_r, sim_r, target_ti_text])

        # Per-panel sequence: render only that panel and toggle its TI slider.
        sequence_l.change(_on_panel_sequence,
                          [region, sequence_l, tr_l, te_l, flip_l, ti_l, field, sim_l],
                          [image_l, sim_l, ti_l])
        sequence_r.change(_on_panel_sequence,
                          [region, sequence_r, tr_r, te_r, flip_r, ti_r, field, sim_r],
                          [image_r, sim_r, ti_r])

        # Per-panel sliders render ONLY their own panel (independent) — the left
        # TR does not re-render the right. render_mri is reused as-is.
        left_inputs = [region, sequence_l, tr_l, te_l, flip_l, ti_l, field, sim_l]
        right_inputs = [region, sequence_r, tr_r, te_r, flip_r, ti_r, field, sim_r]
        for s in left_params:
            s.release(render_mri, left_inputs, [image_l, sim_l])
        for s in right_params:
            s.release(render_mri, right_inputs, [image_r, sim_r])

        # Compare toggle shows/hides Panel B (and renders it fresh on enable).
        compare.change(_on_compare_toggle,
                       [compare, region, field,
                        sequence_r, tr_r, te_r, flip_r, ti_r, sim_r],
                       [panel_b, image_r, sim_r])

        # --- Lesson buttons: each applies its lesson (re-clickable = reset) ---
        lesson_outputs = [
            explanation, target_ti_text,
            compare, panel_b,
            region, field,
            sequence_l, tr_l, te_l, flip_l, ti_l, scan_time_l,
            sequence_r, tr_r, te_r, flip_r, ti_r, scan_time_r,
            image_l, image_r, sim_l, sim_r, lesson_state,
        ]
        for btn in lesson_buttons:
            btn.click(partial(apply_lesson, btn.value), [sim_l, sim_r], lesson_outputs)

        # Initial render of both panels on load (Panel B stays hidden until toggled).
        demo.load(render_both, both_inputs, both_outputs)

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
