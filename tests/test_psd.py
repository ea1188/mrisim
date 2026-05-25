import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytest
from psd import (
    draw_spin_echo_psd,
    draw_gradient_echo_psd,
    draw_inversion_recovery_psd,
    draw_fse_psd,
    draw_diffusion_psd,
    draw_epi_psd,
    draw_tof_psd,
    draw_psd,
    _draw_rf_pulse,
    _draw_gradient,
)


@pytest.fixture
def fig():
    f = plt.figure(figsize=(10, 6))
    yield f
    plt.close(f)


class TestDrawSpinEchoPsd:
    def test_runs_without_error(self, fig):
        draw_spin_echo_psd(fig, TR=500, TE=20)

    def test_creates_axes(self, fig):
        draw_spin_echo_psd(fig, TR=500, TE=20)
        assert len(fig.axes) > 0

    def test_different_te(self, fig):
        draw_spin_echo_psd(fig, TR=4000, TE=100)
        assert len(fig.axes) > 0


class TestDrawGradientEchoPsd:
    def test_runs_without_error(self, fig):
        draw_gradient_echo_psd(fig, TR=250, TE=5, flip_angle=70)

    def test_creates_axes(self, fig):
        draw_gradient_echo_psd(fig, TR=250, TE=5, flip_angle=70)
        assert len(fig.axes) > 0

    def test_small_flip_angle(self, fig):
        draw_gradient_echo_psd(fig, TR=600, TE=20, flip_angle=20)
        assert len(fig.axes) > 0


class TestDrawInversionRecoveryPsd:
    def test_runs_without_error(self, fig):
        draw_inversion_recovery_psd(fig, TR=9000, TE=90, TI=2500)

    def test_creates_axes(self, fig):
        draw_inversion_recovery_psd(fig, TR=9000, TE=90, TI=2500)
        assert len(fig.axes) > 0

    def test_stir_ti(self, fig):
        draw_inversion_recovery_psd(fig, TR=5000, TE=30, TI=180)
        assert len(fig.axes) > 0


class TestDrawFsePsd:
    def test_runs_without_error(self, fig):
        draw_fse_psd(fig, TR=4000, TE=100, etl=8, echo_spacing=12)

    def test_creates_axes(self, fig):
        draw_fse_psd(fig, TR=4000, TE=100, etl=8, echo_spacing=12)
        assert len(fig.axes) > 0

    def test_etl_1(self, fig):
        draw_fse_psd(fig, TR=4000, TE=100, etl=1, echo_spacing=10)
        assert len(fig.axes) > 0


class TestDrawDiffusionPsd:
    def test_runs_without_error(self, fig):
        draw_diffusion_psd(fig, TR=8000, TE=80, b_value=1000)

    def test_creates_axes(self, fig):
        draw_diffusion_psd(fig, TR=8000, TE=80, b_value=1000)
        assert len(fig.axes) > 0

    def test_high_b_value(self, fig):
        draw_diffusion_psd(fig, TR=8000, TE=90, b_value=2000)
        assert len(fig.axes) > 0


class TestDrawEpiPsd:
    def test_runs_without_error(self, fig):
        draw_epi_psd(fig, TR=2000, TE=30)

    def test_creates_axes(self, fig):
        draw_epi_psd(fig, TR=2000, TE=30)
        assert len(fig.axes) > 0


class TestDrawTofPsd:
    def test_runs_without_error(self, fig):
        draw_tof_psd(fig, TR=25, TE=4, flip_angle=60)

    def test_creates_axes(self, fig):
        draw_tof_psd(fig, TR=25, TE=4, flip_angle=60)
        assert len(fig.axes) > 0


class TestDrawPsd:
    def test_spin_echo_dispatch(self, fig):
        draw_psd(fig, sequence="Spin Echo", TR=500, TE=20, TI=150, flip_angle=90,
                 etl=1, echo_spacing=10, b_value=0)
        assert len(fig.axes) > 0

    def test_gradient_echo_dispatch(self, fig):
        draw_psd(fig, sequence="Gradient Echo", TR=250, TE=5, TI=150, flip_angle=70,
                 etl=1, echo_spacing=10, b_value=0)
        assert len(fig.axes) > 0

    def test_inversion_recovery_dispatch(self, fig):
        draw_psd(fig, sequence="Inversion Recovery", TR=9000, TE=90, TI=2500,
                 flip_angle=90, etl=1, echo_spacing=10, b_value=0)
        assert len(fig.axes) > 0

    def test_fse_dispatch(self, fig):
        draw_psd(fig, sequence="FSE/TSE", TR=4000, TE=100, TI=150, flip_angle=90,
                 etl=8, echo_spacing=12, b_value=0)
        assert len(fig.axes) > 0

    def test_diffusion_dispatch(self, fig):
        draw_psd(fig, sequence="Diffusion (DWI)", TR=8000, TE=80, TI=150,
                 flip_angle=90, etl=1, echo_spacing=10, b_value=1000)
        assert len(fig.axes) > 0

    def test_epi_dispatch(self, fig):
        draw_psd(fig, sequence="fMRI (BOLD)", TR=2000, TE=30, TI=150, flip_angle=90,
                 etl=1, echo_spacing=10, b_value=0)
        assert len(fig.axes) > 0

    def test_tof_dispatch(self, fig):
        draw_psd(fig, sequence="MR Angiography", TR=25, TE=4, TI=150, flip_angle=60,
                 etl=1, echo_spacing=10, b_value=0)
        assert len(fig.axes) > 0

    def test_unknown_sequence_does_not_raise(self, fig):
        draw_psd(fig, sequence="Unknown Sequence", TR=500, TE=20, TI=150,
                 flip_angle=90, etl=1, echo_spacing=10, b_value=0)

    def test_fse_tse_exact_string_dispatch(self, fig):
        """sequence="FSE / TSE" (with spaces) hits line 479 — draw_fse_psd branch."""
        draw_psd(fig, sequence="FSE / TSE", TR=4000, TE=100, TI=150,
                 flip_angle=90, etl=8, echo_spacing=12, b_value=0)
        assert len(fig.axes) > 0


# ---------------------------------------------------------------------------
# Branch coverage additions — private helpers
# ---------------------------------------------------------------------------
class TestDrawRfPulseBlockStyle:
    def test_block_style_hits_else_branch(self, fig):
        """_draw_rf_pulse with style!='sinc' executes the else branch (line 26)."""
        ax = fig.add_subplot(1, 1, 1)
        _draw_rf_pulse(ax, t_start=0.0, duration=0.1, amplitude=1.0,
                       label="flip", color="#ff6b6b", style="block")
        # No assertion needed beyond no exception; line 26 is now covered


class TestDrawGradient:
    def test_gradient_draws_without_error(self, fig):
        """_draw_gradient body (lines 35-39) executes when called directly."""
        ax = fig.add_subplot(1, 1, 1)
        _draw_gradient(ax, t_start=0.0, duration=0.2, amplitude=0.8)
