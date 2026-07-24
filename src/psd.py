"""
Pulse Sequence Diagram (PSD) renderer.

Draws RF, Gz (slice-select), Gy (phase-encode), Gx (frequency-encode/readout)
and the Signal/echo timing for the standard sequences.

Time base: each diagram is drawn on a *local* timeline that spans only the
active part of one TR (excitation → echo → readout), with event widths scaled to
that window — so the relative ordering (90° before 180°, prephaser before
readout, echo inside the ADC) is always correct, independent of how small TE is
relative to TR. A "↻ TR" marker notes that the cycle repeats. Sequences with a
long internal delay (Inversion Recovery's TI) use a schematic axis that
compresses the delay so the readout cluster stays legible.
"""
from typing import Any

import numpy as np

# Palette (matches the app's near-black + blue theme)
RF_C = "#ff6b6b"     # RF pulses
SS_C = "#74c0fc"     # slice-select gradient (Gz)
PE_C = "#69db7c"     # phase-encode gradient (Gy)
RO_C = "#ffa94d"     # readout gradient (Gx)
SIG_C = "#ffd43b"    # signal / echo / ADC
DIFF_C = "#e64980"   # diffusion gradients
TXT = "#dfe5ec"
MUT = "#8b94a3"
BG = "#0d1014"
PANEL = "#12161c"
GRID = "#3a424d"


# --------------------------------------------------------------------------- #
#  Primitives — all coordinates are in the axis's own units (ms or schematic)
# --------------------------------------------------------------------------- #
def _rf(ax: Any, t: float, half_w: float, amp: float, label: str,
        color: str = RF_C) -> None:
    """A sinc RF pulse centred at ``t``."""
    tt = np.linspace(t - half_w, t + half_w, 80)
    env = amp * np.sinc(np.linspace(-3, 3, 80)) * np.hanning(80)
    ax.fill_between(tt, 0, env, alpha=0.35, color=color)
    ax.plot(tt, env, color=color, lw=1.3)
    if label:
        ax.text(t, amp * 1.05 + 0.05, label, ha="center", va="bottom",
                color=color, fontsize=7, fontweight="bold")


def _trap(ax: Any, t_center: float, width: float, amp: float, color: str,
          fill: bool = True, lw: float = 1.4) -> None:
    """A trapezoidal gradient lobe centred at ``t_center``."""
    r = width * 0.18
    t = [t_center - width / 2, t_center - width / 2 + r,
         t_center + width / 2 - r, t_center + width / 2]
    g = [0.0, amp, amp, 0.0]
    if fill:
        ax.fill_between(t, 0, g, alpha=0.22, color=color)
    ax.plot(t, g, color=color, lw=lw)


def _echo(ax: Any, t: float, half_w: float, amp: float, color: str = SIG_C) -> None:
    """A gaussian echo centred at ``t``."""
    tt = np.linspace(t - half_w, t + half_w, 80)
    s = amp * np.exp(-0.5 * ((tt - t) / (half_w / 3.0)) ** 2)
    ax.plot(tt, s, color=color, lw=1.8)
    ax.fill_between(tt, 0, s, alpha=0.18, color=color)


def _adc(ax: Any, t_center: float, width: float, color: str = SIG_C) -> None:
    """An ADC (data-acquisition) window centred at ``t_center``."""
    a, b = t_center - width / 2, t_center + width / 2
    ax.plot([a, a, b, b], [0, 0.32, 0.32, 0], color=color, lw=1.3)
    ax.text(t_center, 0.40, "ADC", ha="center", va="bottom", color=color, fontsize=6)


def _setup_axis(ax: Any, label: str, ylim: tuple[float, float]) -> None:
    ax.set_ylim(ylim)
    ax.set_ylabel(label, color=TXT, fontsize=8, rotation=0, labelpad=22, va="center")
    ax.axhline(0, color=GRID, lw=0.5)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _frame(fig: Any, title: str, t0: float, t1: float,
           xlabel: str = "time (ms)  →") -> list[Any]:
    """Lay out the 5 stacked channels and return their axes (RF, Gz, Gy, Gx, Signal)."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True,
                        gridspec_kw={"hspace": 0.06,
                                     "height_ratios": [1.35, 1, 1, 1, 1]})
    rows = [("RF", (-0.5, 1.75)), ("Gz", (-1.3, 1.45)), ("Gy", (-1.3, 1.45)),
            ("Gx", (-1.6, 1.45)), ("Signal", (-0.3, 1.35))]
    for ax, (lab, yl) in zip(axes, rows, strict=True):
        _setup_axis(ax, lab, yl)
        ax.set_xlim(t0, t1)
    axes[-1].set_xlabel(xlabel, color=TXT, fontsize=8)
    fig.suptitle(title, color=TXT, fontsize=10, y=0.99)
    fig.patch.set_facecolor(BG)
    return list(axes)


def _tr_marker(axes: list[Any], x: float, tr: float, span: float) -> None:
    """Note that the window is one (partial) TR that repeats; only when the shown
    window is meaningfully shorter than TR."""
    if x >= tr * 0.98:
        return
    for ax in axes:
        ax.axvline(x, color=GRID, lw=0.8, ls=(0, (2, 2)))
    axes[0].text(x - span * 0.01, 1.55, f"↻ TR = {tr:.0f} ms",
                 ha="right", va="top", color=MUT, fontsize=7)


def _te_bracket(ax: Any, t_a: float, t_b: float, label: str,
                color: str = SIG_C, y: float = -0.34) -> None:
    ax.annotate("", xy=(t_b, y), xytext=(t_a, y),
                arrowprops=dict(arrowstyle="<->", color=color, lw=1.1))
    ax.text((t_a + t_b) / 2, y - 0.12, label, ha="center", va="top",
            color=color, fontsize=7)


# --------------------------------------------------------------------------- #
#  Spin Echo
# --------------------------------------------------------------------------- #
def draw_spin_echo_psd(fig: Any, TR: float, TE: float) -> None:
    t0, t1 = -0.14 * TE, 1.28 * TE
    span = t1 - t0
    rfw, gw, row, ew = 0.022 * span, 0.05 * span, 0.16 * span, 0.05 * span
    ax = _frame(fig, f"Spin Echo  —  TE={TE:.0f}, TR={TR:.0f} ms", t0, t1)

    _rf(ax[0], 0.0, rfw, 1.0, "90°"); _rf(ax[0], TE / 2, rfw, 1.25, "180°")
    # Gz: slice-select under each RF; slice-refocus lobe after the 90°
    _trap(ax[1], 0.0, 1.8 * rfw, 1.0, SS_C)
    _trap(ax[1], 1.8 * rfw, gw, -0.55, SS_C)
    _trap(ax[1], TE / 2, 1.8 * rfw, 1.0, SS_C)
    # Gy: phase-encode table (between excitation and readout)
    t_pe = 0.22 * TE
    for a in np.linspace(-0.85, 0.85, 7):
        _trap(ax[2], t_pe, gw, a, PE_C, fill=False)
    # Gx: prephaser BEFORE the 180° → same sign as readout (the 180° conjugates it)
    _trap(ax[3], t_pe, gw, 0.7, RO_C)
    _trap(ax[3], TE, row, 0.8, RO_C)
    # Signal
    _echo(ax[4], TE, ew, 0.85); _adc(ax[4], TE, row)
    _te_bracket(ax[0], 0.0, TE, f"TE = {TE:.0f} ms")
    _tr_marker(ax, t1, TR, span)


# --------------------------------------------------------------------------- #
#  Gradient Echo (spoiled)
# --------------------------------------------------------------------------- #
def draw_gradient_echo_psd(fig: Any, TR: float, TE: float, flip_angle: float) -> None:
    t0, t1 = -0.16 * TE, 1.30 * TE
    span = t1 - t0
    rfw, gw, row, ew = 0.022 * span, 0.05 * span, 0.16 * span, 0.05 * span
    ax = _frame(fig, f"Spoiled Gradient Echo  —  α={flip_angle:.0f}°, "
                     f"TE={TE:.0f}, TR={TR:.0f} ms", t0, t1)

    _rf(ax[0], 0.0, rfw, max(0.25, flip_angle / 90.0), f"{flip_angle:.0f}°")
    _trap(ax[1], 0.0, 1.8 * rfw, 1.0, SS_C)
    _trap(ax[1], 1.8 * rfw, gw, -0.55, SS_C)
    t_pe = 0.24 * TE
    for a in np.linspace(-0.85, 0.85, 7):
        _trap(ax[2], t_pe, gw, a, PE_C, fill=False)
    # Spoiled (FLASH/SPGR): the phase encode is NOT rewound; instead an end-of-TR
    # spoiler on slice + readout dephases the residual transverse magnetisation.
    t_spoil = TE + 0.65 * row
    _trap(ax[1], t_spoil, gw, 1.15, SS_C)
    # No 180° → prephaser is NEGATIVE (opposite sign to the readout)
    _trap(ax[3], t_pe, gw, -0.7, RO_C)
    _trap(ax[3], TE, row, 0.8, RO_C)
    _trap(ax[3], t_spoil, gw, 1.15, RO_C)          # readout spoiler
    ax[3].text(t_spoil, -0.95, "spoiler", ha="center", va="top", fontsize=6, color=RO_C)
    _echo(ax[4], TE, ew, 0.65); _adc(ax[4], TE, row)
    _te_bracket(ax[0], 0.0, TE, f"TE = {TE:.0f} ms")
    _tr_marker(ax, t1, TR, span)


# --------------------------------------------------------------------------- #
#  Inversion Recovery — schematic axis (the TI delay is compressed)
# --------------------------------------------------------------------------- #
def draw_inversion_recovery_psd(fig: Any, TR: float, TE: float, TI: float) -> None:
    ax = _frame(fig, f"Inversion Recovery  —  TI={TI:.0f}, TE={TE:.0f}, TR={TR:.0f} ms",
                0.0, 1.0, xlabel="time (schematic — TI compressed)  →")
    rfw = 0.018

    # Inversion at the far left, then a compressed-TI break, then the SE cluster.
    x_inv = 0.05
    x_brk = 0.185
    cl0, cl1 = 0.30, 0.93           # cluster maps [TI, TI+1.2·TE]
    def xc(t: float) -> float:
        return cl0 + (t - TI) / (1.2 * TE) * (cl1 - cl0)
    x90, x180, xecho = xc(TI), xc(TI + TE / 2), xc(TI + TE)
    gw = 0.022

    _rf(ax[0], x_inv, rfw, 1.4, "180°\n(inv)")
    _rf(ax[0], x90, rfw, 1.0, "90°"); _rf(ax[0], x180, rfw, 1.25, "180°")
    # TI break glyph + label
    for a in ax:
        a.plot([x_brk - 0.012, x_brk + 0.012], [a.get_ylim()[0] * 0.0, 0], alpha=0)
    ax[0].text(x_brk, 1.45, f"TI = {TI:.0f} ms", ha="center", va="top",
               color=MUT, fontsize=7)
    for a in ax:
        a.axvline(x_brk, color=GRID, lw=0.8, ls=(0, (1, 2)))

    _trap(ax[1], x_inv, 1.8 * rfw, 1.0, SS_C)
    _trap(ax[1], x90, 1.8 * rfw, 1.0, SS_C)
    _trap(ax[1], x180, 1.8 * rfw, 1.0, SS_C)
    for a in np.linspace(-0.8, 0.8, 5):
        _trap(ax[2], x90 + 0.04, gw, a, PE_C, fill=False)
    _trap(ax[3], x90 + 0.04, gw, 0.7, RO_C)
    _trap(ax[3], xecho, 0.07, 0.8, RO_C)
    _echo(ax[4], xecho, 0.03, 0.7); _adc(ax[4], xecho, 0.07)
    _te_bracket(ax[0], x90, xecho, f"TE={TE:.0f}ms")


# --------------------------------------------------------------------------- #
#  FSE / TSE — 90° then a 180° echo train
# --------------------------------------------------------------------------- #
def draw_fse_psd(fig: Any, TR: float, TE: float, etl: int, echo_spacing: float,
                 t2: float = 90.0) -> None:
    n = max(1, min(int(etl), 6))
    esp = echo_spacing
    t0, t1 = -0.35 * esp, (n + 0.55) * esp
    span = t1 - t0
    rfw, gw, ew = 0.020 * span, 0.018 * span, 0.020 * span
    ax = _frame(fig, f"FSE / TSE  —  ETL={etl}, ESP={esp:.0f} ms, TR={TR:.0f} ms", t0, t1)

    _rf(ax[0], 0.0, rfw, 1.0, "90°")
    _trap(ax[1], 0.0, 1.8 * rfw, 1.0, SS_C)
    amps = np.linspace(-0.85, 0.85, n)
    for i in range(n):
        t180 = (i + 0.5) * esp
        techo = (i + 1.0) * esp
        _rf(ax[0], t180, rfw, 1.25, "180°" if i == 0 else "")
        _trap(ax[1], t180, 1.8 * rfw, 1.0, SS_C)
        # phase-encode + rewinder straddling each echo
        _trap(ax[2], techo - 0.30 * esp, gw, amps[i], PE_C)
        _trap(ax[2], techo + 0.30 * esp, gw, -amps[i], PE_C)
        _trap(ax[3], techo, 0.34 * esp, 0.8, RO_C)
        # The echo-train envelope decays with tissue T2 (each echo is at t=techo),
        # not with the user's TE — that's the physical CPMG amplitude.
        decay = float(np.exp(-techo / max(t2, 1.0)))
        _echo(ax[4], techo, ew, 0.85 * decay)
        _adc(ax[4], techo, 0.34 * esp)
    # effective TE marker (centre of k-space)
    k = min(max(int(round(TE / esp)) - 1, 0), n - 1)
    t_eff = (k + 1.0) * esp
    ax[4].axvline(t_eff, color=SIG_C, ls="--", alpha=0.7)
    ax[4].text(t_eff, 1.05, f"TE_eff≈{TE:.0f}", ha="center", color=SIG_C, fontsize=7)
    _tr_marker(ax, t1, TR, span)


# --------------------------------------------------------------------------- #
#  Diffusion-weighted SE (Stejskal–Tanner)
# --------------------------------------------------------------------------- #
def draw_diffusion_psd(fig: Any, TR: float, TE: float, b_value: float) -> None:
    t0, t1 = -0.14 * TE, 1.28 * TE
    span = t1 - t0
    rfw, gw, row, ew = 0.022 * span, 0.05 * span, 0.16 * span, 0.05 * span
    ax = _frame(fig, f"Diffusion-Weighted SE (Stejskal–Tanner)  —  b={b_value:.0f} s/mm²",
                t0, t1)

    _rf(ax[0], 0.0, rfw, 1.0, "90°"); _rf(ax[0], TE / 2, rfw, 1.25, "180°")
    _trap(ax[1], 0.0, 1.8 * rfw, 1.0, SS_C); _trap(ax[1], TE / 2, 1.8 * rfw, 1.0, SS_C)
    for a in np.linspace(-0.8, 0.8, 5):
        _trap(ax[2], 0.22 * TE, gw, a, PE_C, fill=False)
    # Diffusion gradients straddle the 180°, equal area (drawn on Gx row)
    diff_amp = min(1.2, 0.45 + b_value / 3000.0)
    _trap(ax[3], 0.30 * TE, 0.12 * span, diff_amp, DIFF_C)
    _trap(ax[3], 0.70 * TE, 0.12 * span, diff_amp, DIFF_C)
    ax[3].text(0.30 * TE, diff_amp + 0.12, "G_diff", ha="center", color=DIFF_C, fontsize=7)
    _trap(ax[3], TE, row, 0.7, RO_C)
    _echo(ax[4], TE, ew, 0.5); _adc(ax[4], TE, row)
    _te_bracket(ax[0], 0.0, TE, f"TE = {TE:.0f} ms")
    _tr_marker(ax, t1, TR, span)


# --------------------------------------------------------------------------- #
#  Balanced SSFP (TrueFISP / FIESTA) — fully refocused, alternating RF phase
# --------------------------------------------------------------------------- #
def draw_bssfp_psd(fig: Any, TR: float, TE: float, flip_angle: float) -> None:
    n_tr = 3                       # show a few TRs to convey the steady state
    t0, t1 = -0.18 * TR, (n_tr + 0.18) * TR
    span = t1 - t0
    rfw, gw = 0.020 * span, 0.045 * TR
    amp = max(0.3, flip_angle / 90.0)
    ax = _frame(fig, f"Balanced SSFP  —  α={flip_angle:.0f}° (±), TE≈TR/2, TR={TR:.0f} ms",
                t0, t1)

    for k in range(n_tr + 1):
        tc = k * TR
        sign = 1.0 if k % 2 == 0 else -1.0          # alternating ±α RF phase
        lbl = f"{'+' if sign > 0 else '−'}α" if k < 2 else ""
        _rf(ax[0], tc, rfw, amp * sign, lbl)
        _trap(ax[1], tc, 1.7 * rfw, 1.0, SS_C)      # slice-select ...
        if k < n_tr:
            # every gradient is fully rewound within the TR (zero net area)
            _trap(ax[1], tc + 0.30 * TR, gw, -0.6, SS_C)
            _trap(ax[1], tc + 0.70 * TR, gw, -0.6, SS_C)
            for a in (0.7, -0.7):                   # PE encode then rewind
                _trap(ax[2], tc + 0.28 * TR, gw, a, PE_C)
                _trap(ax[2], tc + 0.72 * TR, gw, -a, PE_C)
            _trap(ax[3], tc + 0.28 * TR, gw, -0.6, RO_C)   # readout prephase
            _trap(ax[3], tc + 0.50 * TR, 0.30 * TR, 0.7, RO_C)  # readout @ TE=TR/2
            _trap(ax[3], tc + 0.72 * TR, gw, -0.6, RO_C)   # readout rephase
            _echo(ax[4], tc + 0.50 * TR, 0.05 * TR, 0.7)
            _adc(ax[4], tc + 0.50 * TR, 0.30 * TR)
            ax[0].axvline(tc + TR, color=GRID, lw=0.6, ls=(0, (2, 3)))
    ax[4].text(0.5 * TR, 1.08, f"TE≈{TE:.0f}", ha="center", color=SIG_C, fontsize=7)


# --------------------------------------------------------------------------- #
#  Echo-Planar Imaging — single shot, oscillating readout + blipped PE
# --------------------------------------------------------------------------- #
def draw_epi_psd(fig: Any, TR: float, TE: float) -> None:
    ax = _frame(fig, f"Single-shot EPI  —  TE={TE:.0f} ms (BOLD / diffusion readout)",
                0.0, 1.0, xlabel="time (schematic)  →")
    rfw = 0.018
    n = 9                          # readout lobes shown
    tr0, tr1 = 0.18, 0.96          # readout-train extent (schematic)
    w = (tr1 - tr0) / n
    t_center = (tr0 + tr1) / 2     # k-space centre ≈ TE

    _rf(ax[0], 0.05, rfw, 1.0, "90°")
    _trap(ax[1], 0.05, 1.8 * rfw, 1.0, SS_C)
    _trap(ax[1], 0.11, 0.025, -0.5, SS_C)
    # PE: prephase then a small blip between each readout lobe
    _trap(ax[2], tr0 - 0.03, 0.025, -0.8, PE_C)
    for i in range(1, n):
        _trap(ax[2], tr0 + i * w, 0.012, 0.28, PE_C)
    # Gx: prephase then alternating-polarity readout train
    _trap(ax[3], tr0 - 0.03, 0.025, -0.6, RO_C)
    for i in range(n):
        pol = 1.0 if i % 2 == 0 else -1.0
        _trap(ax[3], tr0 + (i + 0.5) * w, w * 0.82, 0.8 * pol, RO_C)
    # Signal: gradient echo per lobe under a T2* envelope peaking at the centre
    for i in range(n):
        tcx = tr0 + (i + 0.5) * w
        env = float(np.exp(-((tcx - t_center) / 0.26) ** 2))
        _echo(ax[4], tcx, w * 0.32, 0.7 * env)
    ax[4].axvline(t_center, color=SIG_C, ls="--", alpha=0.6)
    ax[4].text(t_center, 1.08, f"TE={TE:.0f}", ha="center", color=SIG_C, fontsize=7)


# --------------------------------------------------------------------------- #
#  TOF MRA — short-TR spoiled GRE with flow compensation
# --------------------------------------------------------------------------- #
def draw_tof_psd(fig: Any, TR: float, TE: float, flip_angle: float) -> None:
    t0, t1 = -0.18 * TE, 1.30 * TE
    span = t1 - t0
    rfw, gw, row, ew = 0.024 * span, 0.045 * span, 0.16 * span, 0.05 * span
    ax = _frame(fig, f"TOF MRA — spoiled GRE  —  α={flip_angle:.0f}°, flow-comp., "
                     f"TR={TR:.0f} ms", t0, t1)

    _rf(ax[0], 0.0, rfw, max(0.3, flip_angle / 90.0), f"{flip_angle:.0f}°")
    # Flow-compensated (bipolar) slice and readout gradients
    _trap(ax[1], 0.0, 1.7 * rfw, 1.0, SS_C)
    _trap(ax[1], 0.10 * TE, gw, -0.7, SS_C); _trap(ax[1], 0.16 * TE, gw, 0.35, SS_C)
    for a in np.linspace(-0.85, 0.85, 7):
        _trap(ax[2], 0.20 * TE, gw, a, PE_C, fill=False)
    _trap(ax[3], 0.20 * TE, gw, -0.5, RO_C)
    _trap(ax[3], 0.30 * TE, gw, 0.3, RO_C)
    _trap(ax[3], TE, row, 0.8, RO_C)
    _echo(ax[4], TE, ew, 0.6); _adc(ax[4], TE, row)
    ax[0].text(t1, 1.45, "short TR saturates static spins", ha="right", va="top",
               color=MUT, fontsize=7, style="italic")
    _te_bracket(ax[0], 0.0, TE, f"TE = {TE:.0f} ms")
    _tr_marker(ax, t1, TR, span)


# --------------------------------------------------------------------------- #
#  Quantitative (qMRI) — multi-measurement schematic (multi-echo GRE)
# --------------------------------------------------------------------------- #
def draw_qmri_psd(fig: Any, TR: float, TE: float) -> None:
    ax = _frame(fig, "Quantitative (qMRI) — multi-measurement (multi-echo / variable-α)",
                0.0, 1.0, xlabel="time (schematic)  →")
    rfw = 0.02
    _rf(ax[0], 0.06, rfw, 1.0, "α")
    _trap(ax[1], 0.06, 1.8 * rfw, 1.0, SS_C)
    _trap(ax[1], 0.12, 0.03, -0.5, SS_C)
    for a in np.linspace(-0.8, 0.8, 5):
        _trap(ax[2], 0.16, 0.03, a, PE_C, fill=False)
    # A train of gradient echoes at increasing TE (the multi-echo measurement)
    n = 4
    te_x = np.linspace(0.34, 0.92, n)
    _trap(ax[3], 0.16, 0.03, -0.6, RO_C)
    for i, tx in enumerate(te_x):
        pol = 1.0 if i % 2 == 0 else -1.0
        _trap(ax[3], tx, 0.10, 0.8 * pol, RO_C)
        _echo(ax[4], tx, 0.035, 0.75 * float(np.exp(-i * 0.45)))
        ax[4].text(tx, -0.18, f"TE{i + 1}", ha="center", va="top", color=MUT, fontsize=6)
    ax[0].text(0.5, 1.5, "maps fit signal vs TE / flip angle → T1, T2, T2*",
               ha="center", va="top", color=MUT, fontsize=7, style="italic")


# --------------------------------------------------------------------------- #
#  Dispatcher
# --------------------------------------------------------------------------- #
def draw_psd(
    fig: Any,
    sequence: str,
    TR: float,
    TE: float,
    TI: float = 150,
    flip_angle: float = 90,
    etl: int = 1,
    echo_spacing: float = 10,
    b_value: float = 1000,
    t2: float = 90.0,
) -> None:
    """Draw the appropriate pulse-sequence diagram for ``sequence``."""
    if sequence == "Spin Echo":
        draw_spin_echo_psd(fig, TR, TE)
    elif sequence == "FSE / TSE":
        draw_fse_psd(fig, TR, TE, etl, echo_spacing, t2)
    elif sequence in ("Gradient Echo", "Susceptibility (SWI)"):
        draw_gradient_echo_psd(fig, TR, TE, flip_angle)
    elif sequence == "Inversion Recovery":
        draw_inversion_recovery_psd(fig, TR, TE, TI)
    elif sequence == "Balanced SSFP":
        draw_bssfp_psd(fig, TR, TE, flip_angle)
    elif sequence == "Diffusion (DWI)":
        draw_diffusion_psd(fig, TR, TE, b_value)
    elif sequence == "MR Angiography":
        draw_tof_psd(fig, TR, TE, flip_angle)
    elif sequence in ("fMRI (BOLD)", "Echo Planar (EPI)"):
        draw_epi_psd(fig, TR, TE)
    elif sequence == "Quantitative (qMRI)":
        draw_qmri_psd(fig, TR, TE)
    else:
        draw_spin_echo_psd(fig, TR, TE)
