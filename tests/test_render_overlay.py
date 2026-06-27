"""Viewport overlay rendering shared by desktop + web (render_overlay.py).

Focus: the anatomical orientation letters (radiological convention — a silent-error
risk if wrong) and the tissue overlay / annotation drawing.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import render_overlay as ro


# --- orientation_letters: the radiological-convention edge labels ------------- #
def test_orientation_letters_per_plane_brain():
    assert ro.orientation_letters("axial", sequence="Spin Echo", region="Brain") == ("A", "P", "R", "L")
    assert ro.orientation_letters("coronal", sequence="Spin Echo", region="Brain") == ("S", "I", "R", "L")
    assert ro.orientation_letters("sagittal", sequence="Spin Echo", region="Brain") == ("S", "I", "A", "P")


def test_radiological_convention_patient_right_is_viewer_left():
    """The defining safety invariant: on axial/coronal the LEFT edge is patient-R
    and the RIGHT edge is patient-L (radiological display). Get this backwards and
    every scan reads mirror-imaged."""
    for plane in ("axial", "coronal"):
        _top, _bot, left, right = ro.orientation_letters(plane, sequence="Spin Echo", region="Brain")
        assert (left, right) == ("R", "L")


def test_orientation_letters_apply_to_body_regions():
    for region in ro.BODY_REGIONS:
        assert ro.orientation_letters("axial", sequence="Spin Echo", region=region) == ("A", "P", "R", "L")


def test_orientation_letters_suppressed_when_unsafe():
    # MRA is a rotatable MIP projection — no fixed cardinal axes.
    assert ro.orientation_letters("axial", sequence="MR Angiography", region="Brain") is None
    # Oblique planning tilts the plane off the cardinal axes.
    assert ro.orientation_letters("axial", sequence="Spin Echo", region="Brain",
                                  fov_planning=True, tilt=10.0) is None
    assert ro.orientation_letters("axial", sequence="Spin Echo", region="Brain",
                                  fov_planning=True, rot=10.0) is None
    # …but a straight (un-tilted) planned scan still gets letters.
    assert ro.orientation_letters("axial", sequence="Spin Echo", region="Brain",
                                  fov_planning=True, tilt=0.0, rot=0.0) == ("A", "P", "R", "L")
    # A loaded mask of unknown axis convention → no letters (better none than wrong).
    assert ro.orientation_letters("axial", sequence="Spin Echo", region="My NIfTI") is None


# --- tissue_overlay ----------------------------------------------------------- #
def test_tissue_overlay_maps_labels_to_colours():
    labels = np.array([[0, 1], [2, 3]])
    rgba = ro.tissue_overlay(labels, (2, 2))
    assert rgba.shape == (2, 2, 4) and rgba.dtype == np.uint8
    assert tuple(rgba[0, 0]) == ro.TISSUE_COLORS[0]      # background transparent
    assert rgba[0, 0, 3] == 0                            # …alpha 0
    assert tuple(rgba[1, 0]) == ro.TISSUE_COLORS[2]      # gray matter colour


def test_tissue_overlay_resamples_to_target_shape():
    labels = np.array([[1, 2], [3, 6]])                 # 2×2 → upsample 4×4 (nearest)
    rgba = ro.tissue_overlay(labels, (4, 4))
    assert rgba.shape == (4, 4, 4)
    assert tuple(rgba[0, 0]) == ro.TISSUE_COLORS[1]      # nearest keeps label identity


# --- annotate_image / frame_image_axes (matplotlib drawing) ------------------- #
def _params(**over):
    p = dict(sequence="Spin Echo", TR=500, TE=12, TI=150, flip_angle=90,
             field_strength="3T", matrix_size=256, FOV=240)
    p.update(over)
    return p


def test_annotate_image_draws_identity_geometry_and_letters():
    fig, ax = plt.subplots()
    letters = ro.orientation_letters("axial", sequence="Spin Echo", region="Brain")
    ro.annotate_image(ax, _params(), "axial", 90, width=1.0, center=0.5,
                      region="Brain", letters=letters)
    texts = {t.get_text() for t in ax.texts}
    assert "Spin Echo" in texts                          # identity (top-left)
    assert "Brain" in texts                              # region (top-right)
    assert any("TR 500" in t for t in texts)             # timing
    assert {"A", "P", "R", "L"} <= texts                 # orientation letters drawn
    plt.close(fig)


def test_annotate_image_omits_letters_when_none():
    fig, ax = plt.subplots()
    ro.annotate_image(ax, _params(sequence="MR Angiography"), "axial", 90,
                      width=1.0, center=0.5, region="Brain", letters=None)
    texts = {t.get_text() for t in ax.texts}
    assert not ({"A", "P", "R", "L"} & texts)            # no orientation letters
    plt.close(fig)


def test_frame_image_axes_strips_ticks():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [1, 2])
    ro.frame_image_axes(ax)
    assert list(ax.get_xticks()) == [] and list(ax.get_yticks()) == []
    plt.close(fig)
