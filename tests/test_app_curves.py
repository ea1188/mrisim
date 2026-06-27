"""Perfusion signal-curve rendering (CurvesMixin._plot_curves, perfusion branches)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app_curves import CurvesMixin
from simulator import default_params


class _Host(CurvesMixin):
    """Minimal host: CurvesMixin only needs `axes` + `plot_curve_mode`."""
    def __init__(self):
        self._fig, ax = plt.subplots()
        self.axes = [None, ax]
        self.plot_curve_mode = type("V", (), {"get": staticmethod(lambda: "TE decay")})()

    def curve(self, **over):
        self.axes[1].clear()
        self._plot_curves(default_params(**over))
        return self.axes[1].get_lines()


def _area(line):
    # all curves share the same uniform x-grid, so the summed |y| is a valid area proxy
    return float(np.abs(line.get_ydata()).sum())


def test_dsc_bolus_area_tracks_cbv():
    """DSC first-pass curve: area ∝ CBV, so tumour (high CBV) > grey > infarct (low CBV)."""
    lines = _Host().curve(sequence="Perfusion (Dynamic)", perf_dyn_display="CBV (DSC)")
    grey, infarct, tumour = lines[0], lines[1], lines[2]   # plotted in this order
    assert _area(tumour) > _area(grey) > _area(infarct) > 0


def test_dce_uptake_tumour_enhances_normal_brain_flat():
    """DCE Tofts curve: a leaky tumour enhances; normal grey/white (intact BBB) stay low."""
    lines = _Host().curve(sequence="Perfusion (Dynamic)", perf_dyn_display="Ktrans (DCE)")
    grey, white, tumour = lines[0], lines[1], lines[2]
    assert tumour.get_ydata().max() > 5 * grey.get_ydata().max()
    assert grey.get_ydata().max() >= white.get_ydata().max()   # grey leaks marginally more


def test_asl_signal_decays_with_pld_and_grey_exceeds_white():
    """ASL ΔM falls as the post-label delay grows (blood T1), grey-matter flow > white."""
    lines = _Host().curve(sequence="Perfusion (ASL)", pld=1800)
    grey, white = lines[0], lines[1]
    gy = grey.get_ydata()
    assert gy[0] > gy[-1] > 0                       # decays over PLD
    assert grey.get_ydata().max() > white.get_ydata().max()    # grey > white
