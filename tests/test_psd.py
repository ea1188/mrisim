"""Tests for the pulse-sequence-diagram renderer (psd.py).

These assert the *physical ordering* of events on the rendered axes — the thing
that was broken when the time axis was normalised to TR (e.g. the 180° pulse
drawing before the 90°). They inspect the actual matplotlib artists.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

import psd  # noqa: E402

RF_C = psd.RF_C


def _fig() -> Figure:
    return Figure(figsize=(4, 5))


def _draw(seq, **kw) -> Figure:
    fig = _fig()
    psd.draw_psd(fig, seq, kw.get("TR", 500), kw.get("TE", 15),
                 TI=kw.get("TI", 150), flip_angle=kw.get("flip_angle", 90),
                 etl=kw.get("etl", 1), echo_spacing=kw.get("echo_spacing", 10),
                 b_value=kw.get("b_value", 1000))
    return fig


def _rf_label_x(fig, label):
    """X positions of RF pulse text labels on the RF (first) axis."""
    ax0 = fig.axes[0]
    return sorted(t.get_position()[0] for t in ax0.texts
                  if t.get_text().strip() == label.strip())


def _signal_peak_x(fig):
    """X of the tallest point on the Signal (last) axis — the echo peak. Only
    considers the echo curves (many-point gaussians), not the 2-point ADC outline
    or vertical marker/break lines."""
    ax = fig.axes[-1]
    best = None
    for ln in ax.lines:
        yd = np.asarray(ln.get_ydata(), dtype=float)
        xd = np.asarray(ln.get_xdata(), dtype=float)
        if yd.size <= 5 or np.allclose(xd, xd[0]):   # skip ADC / axvline markers
            continue
        i = int(np.argmax(yd))
        if best is None or yd[i] > best[1]:
            best = (xd[i], yd[i])
    return best[0] if best else None


def _rf_pulse_count(fig):
    """Number of RF pulse envelopes (Line2D in the RF colour) on the RF axis."""
    ax0 = fig.axes[0]
    return sum(1 for ln in ax0.lines
               if mcolors.same_color(ln.get_color(), RF_C))


# --------------------------------------------------------------------------- #
#  Dispatch: the right diagram for each sequence (no silent SE fallback)
# --------------------------------------------------------------------------- #
class TestDispatch:
    CASES = [
        ("Spin Echo", "Spin Echo"),
        ("FSE / TSE", "FSE"),
        ("Gradient Echo", "Gradient Echo"),
        ("Inversion Recovery", "Inversion Recovery"),
        ("Balanced SSFP", "SSFP"),
        ("Diffusion (DWI)", "Diffusion"),
        ("MR Angiography", "TOF"),
        ("fMRI (BOLD)", "EPI"),
        ("Echo Planar (EPI)", "EPI"),
        ("Quantitative (qMRI)", "qMRI"),
    ]

    @pytest.mark.parametrize("seq,keyword", CASES)
    def test_title_matches_sequence(self, seq, keyword):
        fig = _draw(seq, TR=500, TE=15, flip_angle=45, TI=2500,
                    etl=16, echo_spacing=10)
        title = fig._suptitle.get_text()
        assert keyword.lower() in title.lower(), f"{seq} drew {title!r}"

    def test_bssfp_epi_qmri_not_spin_echo(self):
        for seq in ("Balanced SSFP", "Echo Planar (EPI)", "Quantitative (qMRI)"):
            fig = _draw(seq, TR=5, TE=2.5, flip_angle=45)
            assert "spin echo" not in fig._suptitle.get_text().lower()

    def test_unknown_sequence_falls_back_without_error(self):
        fig = _draw("Totally Unknown", TR=500, TE=20)
        assert len(fig.axes) == 5


# --------------------------------------------------------------------------- #
#  Event ordering — the core regression
# --------------------------------------------------------------------------- #
class TestOrdering:
    @pytest.mark.parametrize("TR,TE", [(500, 15), (4000, 80), (500, 250), (2000, 30)])
    def test_spin_echo_90_before_180_before_echo(self, TR, TE):
        fig = _draw("Spin Echo", TR=TR, TE=TE)
        x90 = _rf_label_x(fig, "90°")[0]
        x180 = _rf_label_x(fig, "180°")[0]
        xecho = _signal_peak_x(fig)
        assert x90 < x180 < xecho, f"order broken at TR={TR}, TE={TE}"

    @pytest.mark.parametrize("TR,TE", [(500, 15), (4000, 80), (250, 60)])
    def test_diffusion_90_before_180(self, TR, TE):
        fig = _draw("Diffusion (DWI)", TR=TR, TE=TE, b_value=1000)
        assert _rf_label_x(fig, "90°")[0] < _rf_label_x(fig, "180°")[0]

    def test_ir_inversion_first_then_90_then_180(self):
        fig = _draw("Inversion Recovery", TR=9000, TE=100, TI=2500)
        x_inv = _rf_label_x(fig, "180°\n(inv)")[0]
        x90 = _rf_label_x(fig, "90°")[0]
        x180 = _rf_label_x(fig, "180°")[0]
        assert x_inv < x90 < x180 < _signal_peak_x(fig)

    def test_gradient_echo_single_rf_and_echo_after(self):
        fig = _draw("Gradient Echo", TR=50, TE=5, flip_angle=20)
        assert _rf_pulse_count(fig) == 1
        xrf = _rf_label_x(fig, "20°")[0]
        assert _signal_peak_x(fig) > xrf


# --------------------------------------------------------------------------- #
#  Everything stays inside the drawn window (no off-axis / negative-time events)
# --------------------------------------------------------------------------- #
class TestWithinWindow:
    SEQS = [
        ("Spin Echo", dict(TR=500, TE=15)),
        ("Gradient Echo", dict(TR=50, TE=5, flip_angle=20)),
        ("Inversion Recovery", dict(TR=9000, TE=100, TI=2500)),
        ("FSE / TSE", dict(TR=4000, TE=80, etl=16, echo_spacing=10)),
        ("Diffusion (DWI)", dict(TR=4000, TE=90, b_value=1000)),
        ("Balanced SSFP", dict(TR=5, TE=2.5, flip_angle=45)),
        ("Echo Planar (EPI)", dict(TR=4000, TE=50)),
        ("MR Angiography", dict(TR=25, TE=4, flip_angle=25)),
        ("Quantitative (qMRI)", dict(TR=1000, TE=20)),
    ]

    @pytest.mark.parametrize("seq,kw", SEQS)
    def test_all_rf_and_echo_inside_xlim(self, seq, kw):
        fig = _draw(seq, **kw)
        ax0 = fig.axes[0]
        t0, t1 = ax0.get_xlim()
        margin = 0.02 * (t1 - t0)
        for txt in ax0.texts:                       # every RF / annotation label
            if not txt.get_text().strip():
                continue
            x = txt.get_position()[0]
            assert t0 - margin <= x <= t1 + margin, \
                f"{seq}: label {txt.get_text()!r} at {x} outside [{t0},{t1}]"
        xe = _signal_peak_x(fig)
        assert xe is not None and t0 - margin <= xe <= t1 + margin, \
            f"{seq}: echo outside window"


# --------------------------------------------------------------------------- #
#  Sequence-specific structure
# --------------------------------------------------------------------------- #
class TestStructure:
    def test_fse_has_echo_train(self):
        fig = _draw("FSE / TSE", TR=4000, TE=80, etl=16, echo_spacing=10)
        assert _rf_pulse_count(fig) >= 6        # 90° + one 180° per shown echo

    def test_bssfp_alternates_rf_phase(self):
        fig = _draw("Balanced SSFP", TR=5, TE=2.5, flip_angle=50)
        ax0 = fig.axes[0]
        miny = min((np.asarray(ln.get_ydata(), float).min()
                    for ln in ax0.lines if np.asarray(ln.get_ydata()).size),
                   default=0.0)
        assert miny < -0.1, "bSSFP should show negative (±) RF pulses"

    def test_epi_oscillating_readout(self):
        fig = _draw("Echo Planar (EPI)", TR=4000, TE=50)
        gx = fig.axes[3]
        ys = [np.asarray(ln.get_ydata(), float) for ln in gx.lines]
        has_pos = any(y.size and y.max() > 0.3 for y in ys)
        has_neg = any(y.size and y.min() < -0.3 for y in ys)
        assert has_pos and has_neg, "EPI readout should oscillate in polarity"


def test_all_sequences_render_without_error():
    for seq, _ in TestWithinWindow.SEQS:
        fig = _fig()
        psd.draw_psd(fig, seq, 1000, 30)        # should not raise
        assert fig._suptitle is not None
