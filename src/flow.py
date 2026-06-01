"""flow.py — flowing-blood signal effects (spin-echo flow void, GRE inflow).

Blood (tissue label 11) is moving spins, so it does not behave like the static
signal the per-label equations assume:

* **Spin echo / FSE / IR** — spins excited by the slice-selective 90° wash out of
  the slice before the 180° refocusing pulse, so they produce no echo: a flow
  *void* (dark vessels), deeper for faster flow.
* **Gradient echo** — there is no slice-selective refocusing, and with a short TR
  the in-flowing spins are unsaturated (fully relaxed) while static tissue is
  saturated, so vessels are *bright* (inflow / time-of-flight enhancement),
  stronger for faster flow, shorter TR and higher flip angle.

The effect scales with a 0–1 ``velocity`` (0 = static, 1 = fast arterial flow).
"""
import numpy as np

BLOOD_LABEL = 11

# Sequences whose contrast the per-label renderer already produces; flow turns
# blood dark on the spin-echo family and bright on gradient echo.
_SE_FAMILY = ("Spin Echo", "FSE / TSE", "Inversion Recovery")
_GRE_FAMILY = ("Gradient Echo",)


def apply_flow(
    image: np.ndarray,
    phantom_slice: np.ndarray,
    sequence: str,
    blood_props: dict,
    TE: float,
    flip_angle: float,
    velocity: float = 0.7,
) -> np.ndarray:
    """Return ``image`` with flowing-blood (label 11) signal adjusted for *sequence*.

    ``blood_props`` is the tissue_db entry for blood (keys PD, T2, T2star); the
    GRE inflow signal is the unsaturated fresh-spin magnitude in the renderer's
    own units, so it blends cleanly with the rendered image.
    """
    if phantom_slice.shape != image.shape:
        return image
    blood = phantom_slice == BLOOD_LABEL
    v = float(np.clip(velocity, 0.0, 1.0))
    if v <= 0.0 or not blood.any():
        return image

    out = image.astype(float, copy=True)

    if sequence in _GRE_FAMILY:
        # Inflow: fresh, fully-relaxed spins -> unsaturated GRE signal
        # (PD·sinα·e^(-TE/T2*)), which exceeds the saturated steady state.
        T2star = blood_props.get("T2star", blood_props.get("T2", 1.0))
        PD = blood_props.get("PD", 1.0)
        fresh = PD * np.sin(np.radians(flip_angle)) * np.exp(-TE / max(float(T2star), 1e-3))
        out[blood] = (1.0 - v) * image[blood] + v * fresh
    elif sequence in _SE_FAMILY:
        # Flow void: up to ~85% signal loss at full velocity.
        out[blood] = image[blood] * (1.0 - 0.85 * v)

    return out
