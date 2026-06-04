"""Qt-free image-overlay rendering shared by the desktop app (``app_qt``) and the
browser/Pyodide adapter (``web_adapter``).

Pure matplotlib + numpy: the DICOM-style corner annotations, the 3-D slab badges,
the anatomical orientation letters, the framed-viewport look, and the tissue
overlay. No Qt and no application object — every input is passed explicitly — so
both the desktop window and a headless web host can draw an identical viewport
from a single source of truth.
"""
from typing import Any

import numpy as np

from theme_colors import C_ACCENT_HI, C_BORDER

# Anatomical edge labels (top, bottom, left, right), radiological convention —
# anterior up, patient-right on the viewer's LEFT. The brain (BrainWeb) is
# already radiological and the body phantoms are mirrored L/R at build time, so a
# single map serves both.
ORIENT_LABELS: dict[str, tuple[str, str, str, str]] = {
    "axial":    ("A", "P", "R", "L"),
    "coronal":  ("S", "I", "R", "L"),
    "sagittal": ("S", "I", "A", "P"),
}
BODY_REGIONS = frozenset({"Abdomen", "Spine", "Pelvis", "Knee", "Torso"})
ACQ3D_SEQUENCES = frozenset({"Spin Echo", "Gradient Echo",
                             "Inversion Recovery", "Balanced SSFP"})

# Translucent RGBA per tissue label, for the optional label overlay.
TISSUE_COLORS: dict[int, tuple[int, int, int, int]] = {
    0:  (0,   0,   0,   0),    # background: transparent
    1:  (0,   200, 255, 110),  # CSF/fluid: cyan
    2:  (255, 140, 0,   90),   # gray matter: orange
    3:  (255, 220, 50,  90),   # white matter: yellow
    4:  (255, 255, 80,  80),   # fat: bright yellow
    5:  (190, 190, 190, 100),  # skull/bone: gray
    6:  (220, 60,  60,  90),   # muscle: red
    7:  (180, 100, 30,  90),   # liver: brown
    8:  (160, 80,  200, 90),   # spleen: purple
    9:  (255, 145, 110, 90),   # kidney cortex: salmon
    10: (210, 100, 80,  90),   # kidney medulla: dark salmon
    11: (255, 30,  30,  110),  # blood: bright red
    12: (20,  20,  20,  120),  # gas: near-black
    13: (200, 200, 200, 100),  # cortical bone: light gray
    14: (255, 185, 185, 90),   # marrow: pale pink
    15: (100, 200, 255, 90),   # cartilage/disc: light blue
    16: (50,  230, 100, 90),   # spinal cord: green
    17: (200, 165, 100, 90),   # bowel: tan
    18: (150, 200, 150, 80),   # lung: pale green
    19: (255, 200, 100, 90),   # pancreas: amber
    20: (255, 100, 150, 90),   # heart: pink
    21: (200, 150, 210, 90),   # soft tissue/gland: lavender
}


def orientation_letters(orient: str, *, sequence: str, region: str,
                        fov_planning: bool = False, tilt: float = 0.0,
                        rot: float = 0.0) -> "tuple[str, str, str, str] | None":
    """Anatomical edge labels for the current view, or None when they can't be
    asserted safely. Skipped for MRA (a rotatable MIP projection), for oblique
    planning (the plane is tilted off the cardinal axes), and for loaded NIfTI
    volumes whose axis convention is unknown — better no letters than wrong ones."""
    if sequence == "MR Angiography":
        return None
    if fov_planning and (abs(tilt) > 0.5 or abs(rot) > 0.5):
        return None
    if region == "Brain" or region in BODY_REGIONS:
        return ORIENT_LABELS.get(orient)
    return None   # loaded mask / unknown convention


def frame_image_axes(ax: Any) -> None:
    """Give an image axes a clean framed-viewport look: no ticks, a thin themed
    border instead of the default white axis box."""
    ax.set_xticks([]); ax.set_yticks([])
    for _s in ax.spines.values():
        _s.set_visible(True); _s.set_color(C_BORDER); _s.set_linewidth(1.0)


def annotate_image(ax: Any, params: dict, orient: str, sl_idx: int,
                   width: float, center: float, *, region: str,
                   letters: "tuple[str, str, str, str] | None" = None,
                   recon_geom: "dict | None" = None) -> None:
    """DICOM-style corner annotations on the main viewport: sequence identity +
    timing top-left, geometry top-right, the 3-D slab/reformat badges, window/level
    bottom-left, FOV bottom-right, and anatomical orientation letters at the
    mid-edges. Monospace, edge-anchored and outline-stroked like a real MR
    workstation overlay. ``letters`` / ``recon_geom`` are passed in so this stays
    free of any application object."""
    import matplotlib.patheffects as _pe
    stroke = [_pe.withStroke(linewidth=2.2, foreground="#05080b")]
    ACC, LIGHT, MUTE = C_ACCENT_HI, "#eef1f5", "#9aa4b2"

    def t(x: float, y: float, s: str, color: str, *, ha: str = "left",
          size: float = 8.0, weight: str = "normal", mono: bool = True) -> None:
        ax.text(x, y, s, transform=ax.transAxes, color=color, fontsize=size,
                ha=ha, va="top" if y > 0.5 else "bottom", weight=weight,
                family="monospace" if mono else "sans-serif",
                path_effects=stroke, zorder=5)

    seq = params.get("sequence", "")
    head = params.get("qmri_display", "qMRI") if seq == "Quantitative (qMRI)" else seq
    # Top-left: identity + key parameters
    t(0.022, 0.978, head, ACC, size=11, weight="bold", mono=False)
    timing = f"TR {params['TR']:.0f}   TE {params['TE']:.0f}"
    if seq in ("Inversion Recovery",):
        timing += f"   TI {params.get('TI', 0):.0f}"
    if seq in ("Gradient Echo", "Balanced SSFP", "MR Angiography"):
        timing += f"   FA {params.get('flip_angle', 0):.0f}°"
    t(0.022, 0.928, timing, LIGHT)
    t(0.022, 0.892, f"{params.get('field_strength', '')}   "
                    f"{int(params.get('matrix_size', 0))}²", MUTE, size=7.5)
    # Top-right: geometry
    t(0.978, 0.978, region, LIGHT, ha="right")
    t(0.978, 0.936, orient.capitalize(), MUTE, ha="right", size=7.5)
    t(0.978, 0.900, f"Slice {sl_idx}", MUTE, ha="right", size=7.5)
    # 3-D slab: flag the acquisition mode, and whether this view is a reformat of
    # the once-acquired slab (the headline "acquire once, view any plane").
    if params.get("acq3d") and seq in ACQ3D_SEQUENCES:
        t(0.022, 0.856, f"3D SLAB · {int(params.get('n_partitions', 0))}p",
          ACC, size=7.5, weight="bold")
        if recon_geom and recon_geom.get("orient") and recon_geom["orient"] != orient:
            t(0.978, 0.864, f"REFORMAT ⟵ {recon_geom['orient'].capitalize()}",
              ACC, ha="right", size=7.5, weight="bold")
    # Bottom corners: window/level and FOV
    t(0.022, 0.022, f"W {width:.2f}   L {center:.2f}", MUTE, size=7.5)
    t(0.978, 0.022, f"FOV {params.get('FOV', 0):.0f} mm", MUTE, ha="right", size=7.5)
    # Anatomical orientation markers at the mid-edges (only where verified).
    if letters:
        top, bot, lft, rgt = letters
        for x, y, s, ha, va in [(0.5, 0.985, top, "center", "top"),
                                (0.5, 0.015, bot, "center", "bottom"),
                                (0.012, 0.5, lft, "left", "center"),
                                (0.988, 0.5, rgt, "right", "center")]:
            ax.text(x, y, s, transform=ax.transAxes, color="#d7dee8",
                    fontsize=10.5, weight="bold", ha=ha, va=va,
                    family="sans-serif", path_effects=stroke, zorder=6)


def tissue_overlay(label_map: np.ndarray,
                   target_shape: tuple[int, int]) -> np.ndarray:
    """Return an RGBA image mapping each tissue label to a translucent colour,
    resampled (nearest) to ``target_shape`` when needed."""
    if label_map.shape != target_shape:
        from scipy.ndimage import zoom
        scale = (target_shape[0] / label_map.shape[0],
                 target_shape[1] / label_map.shape[1])
        label_map = zoom(label_map, scale, order=0)
    rgba = np.zeros((*target_shape, 4), dtype=np.uint8)
    for lab, color in TISSUE_COLORS.items():
        mask = label_map == lab
        if mask.any():
            rgba[mask] = color
    return rgba
