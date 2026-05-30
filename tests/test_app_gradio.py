"""Headless smoke test for the Phase 1 Gradio front-end (app.py at repo root).

Exercises the render callback directly — no Gradio UI is launched — to confirm
the web layer drives the Qt-free engine and returns a displayable 2-D image.
"""

import os
import sys

import numpy as np

# app.py lives at the repo root (one level up from tests/); conftest only puts
# src/ on the path, so add the root here before importing it.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import app
from simulator import Simulator


def test_render_callback_returns_2d_image():
    """The render callback, given a synthetic region and default-ish params,
    returns a 2-D uint8 image aligned to the volume's axial slice, plus the
    Simulator carried in session state."""
    region = "Knee"  # fully synthetic body region (no BrainWeb/NIfTI needed)
    vol, _texture, _fov = app._region_data(region)

    sim = Simulator()
    image, returned_sim = app.render_mri(
        region, "Spin Echo", tr=500.0, te=15.0, flip=90.0,
        ti=2500.0, field="3T", sim=sim,
    )

    assert isinstance(image, np.ndarray)
    assert image.ndim == 2
    # Engine reconstructs at phantom-slice resolution; axial slice = (H, W).
    assert image.shape == (vol.shape[1], vol.shape[2])
    assert image.dtype == np.uint8
    assert image.max() > 0  # not a blank frame

    # The same Simulator instance flows back for reuse in gr.State.
    assert returned_sim is sim
    assert returned_sim.orientation == "axial"


def test_render_callback_creates_simulator_when_state_empty():
    """First interaction in a fresh session (state is None) lazily builds a
    per-session Simulator rather than relying on a module global."""
    image, sim = app.render_mri(
        "Knee", "Gradient Echo", tr=300.0, te=8.0, flip=25.0,
        ti=2500.0, field="1.5T", sim=None,
    )
    assert isinstance(sim, Simulator)
    assert isinstance(image, np.ndarray) and image.ndim == 2
