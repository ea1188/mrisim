"""Guided-lesson data + browser→desktop state translation (Qt-free).

The lesson content is authored once in ``data/lessons.json`` — the single source
the browser fetches at runtime (copied into ``web/`` by ``build_web.py``) and the
desktop app reads here. Lesson ``state`` dicts use the *browser's* control IDs as
keys; the maps below translate those onto the desktop's ``Var`` names so the same
lessons drive both UIs. ``desktop_supported`` filters to the lessons the desktop
can faithfully reproduce (a handful rely on browser-only panels and are skipped).
"""
import json
import os
import sys
from typing import Any


def _data_dir() -> str:
    """Where bundled data lives — under sys._MEIPASS when frozen, else <repo>/data
    (mirrors brainweb_loader.data_dir so the frozen desktop app finds lessons.json)."""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), "data")
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def load_lessons() -> "dict[str, list]":
    """Return ``{"lessons": [...], "curriculum": [...]}`` from data/lessons.json.
    Empty lists if the file is missing (the picker just shows nothing)."""
    path = os.path.join(_data_dir(), "lessons.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {"lessons": list(data.get("lessons", [])),
                "curriculum": list(data.get("curriculum", []))}
    except (OSError, ValueError):
        return {"lessons": [], "curriculum": []}


# ── browser state key → desktop Var attribute ──────────────────────────────── #
# Numeric controls: (browser key, Var attribute, cast). Desktop widgets follow the
# Var via their write-trace, so setting the Var moves the slider/spinbox.
NUMERIC_KEYS: "list[tuple[str, str, Any]]" = [
    ("slice", "slice_idx", int), ("tr", "TR", float), ("te", "TE", float),
    ("ti", "TI", float), ("fa", "flip_angle", float), ("matrix", "matrix_size", int),
    ("bw", "bandwidth", float), ("nex", "NEX", int), ("thick", "slice_thickness", float),
    ("bval", "b_value", float), ("etl", "etl", int), ("np", "n_partitions", int),
    ("nslices", "n_slices", int), ("sgap", "slice_gap", float),
    ("accel", "accel_factor", int), ("pv", "pv_sigma", int),
]
# Boolean toggles: (browser key, Var attribute).
BOOL_KEYS: "list[tuple[str, str]]" = [
    ("acq3d", "acq3d"), ("kzpf", "kz_pf_enabled"), ("fovplan", "fov_planning"),
    ("kspaceshow", "show_kspace"), ("psdshow", "show_psd"),
    ("curveshow", "show_signal_curve"), ("labelanat", "show_tissue_overlay"),
    ("fatsat", "fatsat_enabled"), ("gd", "contrast_enabled"), ("flow", "flow_enabled"),
    ("motion", "motion_enabled"), ("chemshift", "chemical_shift_enabled"),
    ("suscept", "susceptibility_enabled"),
    ("cmap", "show_contrast_map"), ("b0mapshow", "show_b0map"),
    ("gfactorshow", "show_gfactor"),
]
# Dropdowns whose values are identical on both platforms: (browser key, Var attr).
ENUM_KEYS: "list[tuple[str, str]]" = [
    ("accelmethod", "accel_method"), ("diffdisp", "diff_display"),
    ("qmridisp", "qmri_display"), ("fmridisp", "fmri_display"),
    ("motiontype", "motion_type"),
]
# Dropdowns whose values differ (browser code → desktop label).
COIL_LABEL = {"uniform": "Uniform (ideal)", "head8": "Head array (8-ch)",
              "quad": "Quadrature (2-ch)", "surface": "Surface coil"}
PATHOLOGY_LABEL = {"": "None", "lesion": "Lesion (focal)", "ms": "MS plaques",
                   "stroke": "Stroke (infarct)", "hemorrhage": "Hemorrhage",
                   "tumor": "Tumor (mass)", "abscess": "Abscess (rim + core)"}

# Keys the desktop applies via its own handlers (region/seq/orient) or the maps above.
_STRUCTURAL = {"region", "seq", "orient", "field", "receivecoil", "pathology"}
# Browser-only display panels with no desktop equivalent — ignored when toggled OFF,
# but a lesson that turns one ON (its teaching focus) is treated as unsupported.
# (The contrast map, B0 map and g-factor map now have desktop panels and live in
# BOOL_KEYS; only the equation/"math" panel remains browser-only.)
IGNORE_WHEN_FALSE = {"mathshow"}

SUPPORTED_KEYS = (_STRUCTURAL
                  | {k for k, _, _ in NUMERIC_KEYS}
                  | {k for k, _ in BOOL_KEYS}
                  | {k for k, _ in ENUM_KEYS})


def _step_states(lesson: dict) -> "list[dict]":
    out = []
    for s in lesson.get("steps", []):
        out.append(s.get("state") or {})
        if s.get("compareWith"):
            out.append(s["compareWith"])
    return out


def desktop_supported(lesson: dict) -> bool:
    """True if every state key in the lesson is one the desktop can faithfully
    apply (ignoring browser-only panel toggles that are merely switched off)."""
    for st in _step_states(lesson):
        for key, val in st.items():
            if key in SUPPORTED_KEYS:
                continue
            if key in IGNORE_WHEN_FALSE and not val:
                continue
            return False
    return True


def desktop_lessons() -> "list[dict]":
    """The lessons (in authored order) the desktop app can run."""
    return [L for L in load_lessons()["lessons"] if desktop_supported(L)]
