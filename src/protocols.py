"""Prebuilt examination protocols — ordered sequence queues for the console-style
protocol-planning workspace.

Each queue entry names a clinical preset from ``presets.PRESETS`` (so the engine,
contrast and defaults are reused), except the synthetic ``Localizer`` entry, which
just renders the 3-plane scout and is never "acquired".
"""
from __future__ import annotations

import presets

LOCALIZER = "Localizer"

# exam → ordered list of preset names (Localizer first).
PROTOCOLS: dict[str, list[str]] = {
    "Brain": [
        LOCALIZER,
        "Brain T1 SE",
        "Brain T2 SE",
        "Brain FLAIR",
        "DWI Stroke",
        "Brain ASL Perfusion",
        "Brain SWI",
        "Brain T1 Post-Gd",
        "Brain MPRAGE",
    ],
    "Spine": [
        LOCALIZER,
        "Spine T1 Sagittal",
        "Spine T2 Sagittal",
        "Spine STIR",
        "Spine Axial T2",
        "Spine T1 Post-Gd",
    ],
    "Knee": [
        LOCALIZER,
        "Knee T2 FS Axial",
        "Knee PD FS Coronal",
        "Knee PD Coronal",
        "Knee PD FSE",
        "Knee T2 Fat-Sat",
    ],
    "Abdomen": [
        LOCALIZER,
        "Abdomen T2 FSE",
        "Abdomen In-Phase",
        "Abdomen Opposed-Phase",
        "Abdomen DWI",
        "Abdomen 3D GRE (VIBE)",
        "Abdomen T1 FS Post-Gd",
    ],
    "Pelvis": [
        LOCALIZER,
        "Pelvis T2 High-Res",
        "Pelvis T1 SE",
        "Pelvis STIR",
        "Pelvis DWI",
        "Pelvis T1 Post-Gd",
    ],
}

# Short, scanner-style queue labels (preset name → label).
_LABELS: dict[str, str] = {
    LOCALIZER: "Localizer",
    "Brain T1 SE": "T1 SE  ax",
    "Brain T2 SE": "T2 SE  ax",
    "Brain FLAIR": "FLAIR  ax",
    "DWI Stroke": "DWI (stroke)",
    "Brain ASL Perfusion": "ASL CBF  ax",
    "Brain SWI": "SWI",
    "Brain T1 Post-Gd": "T1 Post-Gd",
    "Brain MPRAGE": "MPRAGE 3D",
    "Spine T1 Sagittal": "T1  sag",
    "Spine T2 Sagittal": "T2  sag",
    "Spine STIR": "STIR  sag",
    "Spine Axial T2": "T2  ax",
    "Spine T1 Post-Gd": "T1 Post-Gd  sag",
    "Knee T2 FS Axial": "T2 FS  ax",
    "Knee PD FS Coronal": "PD FS  cor",
    "Knee PD Coronal": "PD  cor",
    "Knee PD FSE": "PD  sag",
    "Knee T1 FSE": "T1 FSE  sag",
    "Knee PD Fat-Sat (CHESS)": "PD FS  sag",
    "Knee T2 Fat-Sat": "T2 FS  sag",
    "Knee GRE T2*": "GRE T2*  sag",
    "Abdomen T2 FSE": "T2 FSE  ax",
    "Abdomen In-Phase": "T1 in-phase  ax",
    "Abdomen Opposed-Phase": "T1 opp-phase  ax",
    "Abdomen DWI": "DWI  ax",
    "Abdomen 3D GRE (VIBE)": "VIBE 3D  ax",
    "Abdomen T1 FS Post-Gd": "VIBE FS Post-Gd",
    "Pelvis T2 High-Res": "T2 HR  ax",
    "Pelvis T1 SE": "T1 SE  ax",
    "Pelvis STIR": "STIR  ax",
    "Pelvis DWI": "DWI  ax",
    "Pelvis T1 Post-Gd": "T1 Post-Gd  ax",
}


def exam_names() -> list[str]:
    """Exams that have a defined protocol (e.g. ``["Brain"]``)."""
    return list(PROTOCOLS.keys())


def get_protocol(exam: str) -> list[dict]:
    """Ordered queue for an exam as ``[{preset, label, sequence}]``.

    ``sequence`` is the underlying MRI sequence (from the preset), or ``None`` for
    the synthetic Localizer entry.
    """
    out: list[dict] = []
    for name in PROTOCOLS.get(exam, []):
        if name == LOCALIZER:
            out.append({"preset": LOCALIZER, "label": _LABELS[LOCALIZER], "sequence": None})
            continue
        p = presets.get_preset(name) or {}
        out.append({"preset": name,
                    "label": _LABELS.get(name, name),
                    "sequence": p.get("sequence")})
    return out
