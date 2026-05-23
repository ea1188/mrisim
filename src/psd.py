"""
Pulse Sequence Diagram (PSD) renderer.
Draws RF, Gx (readout/frequency), Gy (phase encode), Gz (slice select),
and Signal/Echo timing for standard MRI sequences.
"""
import numpy as np


def _draw_rf_pulse(ax, t_start, duration, amplitude=1.0, label="90°", color='#ff6b6b', style='sinc'):
    """Draw an RF pulse (sinc envelope or block)."""
    t = np.linspace(t_start, t_start + duration, 100)
    if style == 'sinc':
        x = np.linspace(-3, 3, 100)
        envelope = amplitude * np.sinc(x) * np.hanning(100)
    else:
        envelope = amplitude * np.ones(100)
    ax.fill_between(t, 0, envelope, alpha=0.4, color=color)
    ax.plot(t, envelope, color=color, linewidth=1.5)
    ax.text(t_start + duration / 2, amplitude * 1.1, label, ha='center', va='bottom',
            color=color, fontsize=7, fontweight='bold')


def _draw_gradient(ax, t_start, duration, amplitude=1.0, ramp=0.05):
    """Draw a trapezoidal gradient lobe."""
    ramp_time = duration * ramp
    t = [t_start, t_start + ramp_time, t_start + duration - ramp_time, t_start + duration]
    g = [0, amplitude, amplitude, 0]
    ax.fill_between(t, 0, g, alpha=0.3, color=ax.lines[-1].get_color() if ax.lines else '#69db7c')
    ax.plot(t, g, linewidth=1.5, color=ax.lines[-1].get_color() if len(ax.lines) > 1 else '#69db7c')


def _draw_trapezoid(ax, t_start, duration, amplitude, color, ramp_frac=0.1, fill=True):
    """Generic trapezoidal waveform."""
    ramp = duration * ramp_frac
    t = [t_start, t_start + ramp, t_start + duration - ramp, t_start + duration]
    g = [0, amplitude, amplitude, 0]
    if fill:
        ax.fill_between(t, 0, g, alpha=0.25, color=color)
    ax.plot(t, g, linewidth=1.5, color=color)


def _draw_echo(ax, t_center, width, amplitude=0.8, color='#ffd43b'):
    """Draw signal echo (gaussian-ish)."""
    t = np.linspace(t_center - width / 2, t_center + width / 2, 80)
    sig = amplitude * np.exp(-0.5 * ((t - t_center) / (width / 6)) ** 2)
    ax.plot(t, sig, color=color, linewidth=2)
    ax.fill_between(t, 0, sig, alpha=0.2, color=color)


def _draw_adc(ax, t_start, duration, color='#ffd43b'):
    """Draw ADC (data acquisition) window."""
    ax.plot([t_start, t_start, t_start + duration, t_start + duration],
            [0, 0.3, 0.3, 0], color=color, linewidth=1.5, linestyle='-')
    ax.text(t_start + duration / 2, 0.4, 'ADC', ha='center', va='bottom',
            color=color, fontsize=6)


def _setup_axis(ax, label, ylim=(-1.3, 1.5)):
    """Configure a single PSD channel axis."""
    ax.set_ylim(ylim)
    ax.set_ylabel(label, color='white', fontsize=8, rotation=0, labelpad=25, va='center')
    ax.axhline(0, color='#444444', linewidth=0.5)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.tick_params(colors='white')
    ax.set_facecolor('#1e1e1e')
    for spine in ax.spines.values():
        spine.set_visible(False)


def draw_spin_echo_psd(fig, TR, TE):
    """Draw Spin Echo pulse sequence diagram."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    # Time normalization
    T = TR
    te = TE / T
    half_te = te / 2

    # RF channel
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.5))
    _draw_rf_pulse(ax, 0.02, 0.08, 1.0, '90°', '#ff6b6b', 'sinc')
    _draw_rf_pulse(ax, half_te - 0.04, 0.08, 1.2, '180°', '#ff6b6b', 'sinc')

    # Gz (slice select)
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.10, 1.0, '#74c0fc')
    _draw_trapezoid(ax, 0.11, 0.04, -0.5, '#74c0fc')  # refocus
    _draw_trapezoid(ax, half_te - 0.05, 0.10, 1.0, '#74c0fc')  # 180 slice select

    # Gy (phase encode)
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    # Phase encode table (multiple amplitudes shown as stack)
    for amp in np.linspace(-0.8, 0.8, 7):
        _draw_trapezoid(ax, 0.13, 0.06, amp, '#69db7c', fill=False)

    # Gx (frequency encode / readout)
    ax = axes[3]
    _setup_axis(ax, 'Gx')
    _draw_trapezoid(ax, 0.13, 0.04, -0.6, '#ffa94d')  # dephase
    _draw_trapezoid(ax, te - 0.08, 0.16, 0.8, '#ffa94d')  # readout

    # Signal
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    _draw_echo(ax, te, 0.10, 0.8)
    _draw_adc(ax, te - 0.08, 0.16)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    # TE/TR annotations
    axes[0].annotate('', xy=(te, -0.3), xytext=(0.06, -0.3),
                     arrowprops=dict(arrowstyle='<->', color='yellow', lw=1.2))
    axes[0].text(te / 2 + 0.03, -0.45, f'TE={TE:.0f}ms', ha='center', color='yellow', fontsize=7)

    fig.suptitle('Spin Echo PSD', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_gradient_echo_psd(fig, TR, TE, flip_angle):
    """Draw Gradient Echo pulse sequence diagram."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    te = TE / TR

    # RF
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.5))
    amp = flip_angle / 90.0
    _draw_rf_pulse(ax, 0.02, 0.06, amp, f'{flip_angle:.0f}°', '#ff6b6b', 'sinc')

    # Gz
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.08, 1.0, '#74c0fc')
    _draw_trapezoid(ax, 0.09, 0.03, -0.5, '#74c0fc')  # refocus

    # Gy
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    for amp_val in np.linspace(-0.8, 0.8, 7):
        _draw_trapezoid(ax, 0.10, 0.05, amp_val, '#69db7c', fill=False)
    # Rewinder
    for amp_val in np.linspace(0.8, -0.8, 7):
        _draw_trapezoid(ax, te + 0.08, 0.05, amp_val, '#69db7c', fill=False)

    # Gx
    ax = axes[3]
    _setup_axis(ax, 'Gx')
    _draw_trapezoid(ax, 0.10, 0.04, -0.6, '#ffa94d')  # dephase
    _draw_trapezoid(ax, te - 0.06, 0.14, 0.8, '#ffa94d')  # readout

    # Signal
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    _draw_echo(ax, te + 0.01, 0.08, 0.6)
    _draw_adc(ax, te - 0.06, 0.14)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    axes[0].annotate('', xy=(te, -0.3), xytext=(0.05, -0.3),
                     arrowprops=dict(arrowstyle='<->', color='yellow', lw=1.2))
    axes[0].text(te / 2 + 0.025, -0.45, f'TE={TE:.0f}ms', ha='center', color='yellow', fontsize=7)

    fig.suptitle(f'Gradient Echo PSD (α={flip_angle:.0f}°)', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_inversion_recovery_psd(fig, TR, TE, TI):
    """Draw Inversion Recovery pulse sequence diagram."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    ti = TI / TR
    te_abs = (TI + TE) / TR
    half_te_after_90 = TE / (2 * TR)

    # RF
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.8))
    _draw_rf_pulse(ax, 0.02, 0.06, 1.3, '180°\n(inv)', '#ff6b6b', 'sinc')
    _draw_rf_pulse(ax, ti - 0.03, 0.06, 1.0, '90°', '#ff6b6b', 'sinc')
    _draw_rf_pulse(ax, ti + half_te_after_90 - 0.03, 0.06, 1.2, '180°', '#ff6b6b', 'sinc')

    # Gz
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.08, 1.0, '#74c0fc')
    _draw_trapezoid(ax, ti - 0.04, 0.08, 1.0, '#74c0fc')
    _draw_trapezoid(ax, ti + half_te_after_90 - 0.04, 0.08, 1.0, '#74c0fc')

    # Gy
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    for amp_val in np.linspace(-0.8, 0.8, 5):
        _draw_trapezoid(ax, ti + 0.04, 0.04, amp_val, '#69db7c', fill=False)

    # Gx
    ax = axes[3]
    _setup_axis(ax, 'Gx')
    _draw_trapezoid(ax, ti + 0.04, 0.03, -0.6, '#ffa94d')
    _draw_trapezoid(ax, te_abs - 0.06, 0.12, 0.8, '#ffa94d')

    # Signal
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    _draw_echo(ax, te_abs, 0.08, 0.7)
    _draw_adc(ax, te_abs - 0.06, 0.12)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    # TI annotation
    axes[0].annotate('', xy=(ti, -0.3), xytext=(0.05, -0.3),
                     arrowprops=dict(arrowstyle='<->', color='#74c0fc', lw=1.2))
    axes[0].text(ti / 2 + 0.025, -0.45, f'TI={TI:.0f}ms', ha='center', color='#74c0fc', fontsize=7)

    fig.suptitle('Inversion Recovery PSD', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_fse_psd(fig, TR, TE, etl, echo_spacing):
    """Draw FSE/TSE pulse sequence diagram with echo train."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    # Normalize: show up to min(etl, 6) echoes for clarity
    n_show = min(etl, 6)
    total_time = echo_spacing * n_show
    scale = 0.9 / total_time if total_time > 0 else 1.0

    # RF
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.8))
    _draw_rf_pulse(ax, 0.02, 0.05, 1.0, '90°', '#ff6b6b', 'sinc')
    for i in range(n_show):
        t_180 = 0.08 + (i * echo_spacing) * scale
        _draw_rf_pulse(ax, t_180, 0.04, 1.2, '180°' if i == 0 else '', '#ff6b6b', 'sinc')

    # Gz
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.07, 1.0, '#74c0fc')
    for i in range(n_show):
        t_180 = 0.08 + (i * echo_spacing) * scale
        _draw_trapezoid(ax, t_180 - 0.01, 0.06, 0.8, '#74c0fc')

    # Gy (different phase encode per echo)
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    amplitudes = np.linspace(-0.8, 0.8, n_show)
    for i in range(n_show):
        t_echo = 0.08 + (i * echo_spacing + echo_spacing / 2) * scale
        _draw_trapezoid(ax, t_echo - 0.04, 0.02, amplitudes[i], '#69db7c')
        _draw_trapezoid(ax, t_echo + 0.03, 0.02, -amplitudes[i], '#69db7c')  # rewinder

    # Gx
    ax = axes[3]
    _setup_axis(ax, 'Gx')
    for i in range(n_show):
        t_echo = 0.08 + (i * echo_spacing + echo_spacing / 2) * scale
        _draw_trapezoid(ax, t_echo - 0.03, 0.06, 0.8, '#ffa94d')

    # Signal (decaying echoes)
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    for i in range(n_show):
        t_echo = 0.08 + (i * echo_spacing + echo_spacing / 2) * scale
        decay = np.exp(-i * echo_spacing / 100.0)  # approximate T2 decay
        _draw_echo(ax, t_echo, 0.04, 0.8 * decay)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    # Mark effective TE
    te_echo_idx = int(etl / 2)
    if te_echo_idx < n_show:
        t_eff = 0.08 + (te_echo_idx * echo_spacing + echo_spacing / 2) * scale
        axes[4].axvline(t_eff, color='yellow', linestyle='--', alpha=0.7)
        axes[4].text(t_eff, 1.0, f'TE_eff≈{TE:.0f}', ha='center', color='yellow', fontsize=7)

    fig.suptitle(f'FSE/TSE PSD (ETL={etl}, ESP={echo_spacing:.0f}ms)', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_diffusion_psd(fig, TR, TE, b_value):
    """Draw Diffusion-Weighted SE with Stejskal-Tanner gradients."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    te = TE / TR
    half_te = te / 2

    # RF
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.5))
    _draw_rf_pulse(ax, 0.02, 0.06, 1.0, '90°', '#ff6b6b', 'sinc')
    _draw_rf_pulse(ax, half_te - 0.03, 0.06, 1.2, '180°', '#ff6b6b', 'sinc')

    # Gz
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.08, 1.0, '#74c0fc')
    _draw_trapezoid(ax, half_te - 0.04, 0.08, 1.0, '#74c0fc')

    # Gy
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    for amp_val in np.linspace(-0.8, 0.8, 5):
        _draw_trapezoid(ax, 0.12, 0.04, amp_val, '#69db7c', fill=False)

    # Gx — with diffusion gradients (Stejskal-Tanner)
    ax = axes[3]
    _setup_axis(ax, 'Gx', (-1.5, 1.5))
    diff_amp = min(1.2, 0.4 + b_value / 3000.0)  # scale with b-value
    _draw_trapezoid(ax, 0.10, 0.06, diff_amp, '#e64980')  # 1st diffusion gradient
    ax.text(0.13, diff_amp + 0.1, 'Gdiff', ha='center', color='#e64980', fontsize=7)
    _draw_trapezoid(ax, half_te + 0.04, 0.06, diff_amp, '#e64980')  # 2nd diffusion gradient
    _draw_trapezoid(ax, te - 0.06, 0.12, 0.6, '#ffa94d')  # readout

    # Signal
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    _draw_echo(ax, te, 0.08, 0.5)  # lower signal due to diffusion attenuation
    _draw_adc(ax, te - 0.06, 0.12)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    # b-value annotation
    axes[3].text(0.5, -1.3, f'b = {b_value:.0f} s/mm²', ha='center', color='#e64980',
                 fontsize=8, fontweight='bold', transform=axes[3].transAxes)

    fig.suptitle('Diffusion-Weighted SE (Stejskal-Tanner)', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_epi_psd(fig, TR, TE):
    """Draw single-shot EPI pulse sequence diagram (fMRI)."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    te = TE / TR

    # RF — single excitation
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.5))
    _draw_rf_pulse(ax, 0.02, 0.05, 1.0, '90°', '#ff6b6b', 'sinc')

    # Gz
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.07, 1.0, '#74c0fc')
    _draw_trapezoid(ax, 0.08, 0.03, -0.5, '#74c0fc')

    # Gy — blipped phase encode (small blips)
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    _draw_trapezoid(ax, 0.10, 0.03, -0.8, '#69db7c')  # pre-phase
    n_blips = 8
    for i in range(n_blips):
        t_blip = 0.15 + i * 0.08
        if t_blip < 0.9:
            _draw_trapezoid(ax, t_blip, 0.015, 0.3, '#69db7c')

    # Gx — oscillating readout (EPI train)
    ax = axes[3]
    _setup_axis(ax, 'Gx')
    _draw_trapezoid(ax, 0.10, 0.03, -0.6, '#ffa94d')  # dephase
    for i in range(n_blips):
        t_read = 0.14 + i * 0.08
        if t_read < 0.88:
            polarity = 1.0 if i % 2 == 0 else -1.0
            _draw_trapezoid(ax, t_read, 0.065, 0.8 * polarity, '#ffa94d')

    # Signal — echo at TE
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    # Multiple gradient echoes with overall T2* envelope
    for i in range(n_blips):
        t_echo = 0.14 + i * 0.08 + 0.032
        if t_echo < 0.9:
            envelope = np.exp(-abs(t_echo - te) * 5)
            _draw_echo(ax, t_echo, 0.03, 0.6 * envelope)
    ax.axvline(te, color='yellow', linestyle='--', alpha=0.5)
    ax.text(te, 1.0, f'TE={TE:.0f}', ha='center', color='yellow', fontsize=7)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    fig.suptitle('EPI (fMRI / BOLD)', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_tof_psd(fig, TR, TE, flip_angle):
    """Draw TOF MRA (short TR GRE with flow compensation)."""
    fig.clear()
    axes = fig.subplots(5, 1, sharex=True, gridspec_kw={'hspace': 0.05, 'height_ratios': [1.2, 1, 1, 1, 1]})

    te = TE / TR

    # RF
    ax = axes[0]
    _setup_axis(ax, 'RF', (-0.5, 1.5))
    amp = flip_angle / 90.0
    _draw_rf_pulse(ax, 0.02, 0.05, amp, f'{flip_angle:.0f}°', '#ff6b6b', 'sinc')

    # Gz — flow compensated (bipolar)
    ax = axes[1]
    _setup_axis(ax, 'Gz')
    _draw_trapezoid(ax, 0.01, 0.07, 1.0, '#74c0fc')
    _draw_trapezoid(ax, 0.08, 0.03, -0.7, '#74c0fc')  # flow comp
    _draw_trapezoid(ax, 0.11, 0.03, 0.3, '#74c0fc')

    # Gy
    ax = axes[2]
    _setup_axis(ax, 'Gy')
    for amp_val in np.linspace(-0.8, 0.8, 7):
        _draw_trapezoid(ax, 0.09, 0.04, amp_val, '#69db7c', fill=False)

    # Gx — flow compensated readout
    ax = axes[3]
    _setup_axis(ax, 'Gx')
    _draw_trapezoid(ax, 0.09, 0.03, -0.4, '#ffa94d')
    _draw_trapezoid(ax, 0.12, 0.02, 0.3, '#ffa94d')  # flow comp
    _draw_trapezoid(ax, te - 0.05, 0.12, 0.8, '#ffa94d')  # readout

    # Signal
    ax = axes[4]
    _setup_axis(ax, 'Signal', (-0.3, 1.2))
    _draw_echo(ax, te + 0.01, 0.06, 0.6)
    _draw_adc(ax, te - 0.05, 0.12)
    ax.set_xlabel('Time →', color='white', fontsize=8)

    # Annotation: short TR emphasis
    axes[0].text(0.85, 1.2, f'Short TR={TR:.0f}ms\n(saturates static)',
                 ha='center', color='#aaaaaa', fontsize=7, style='italic')

    fig.suptitle(f'TOF MRA (GRE, α={flip_angle:.0f}°, flow comp.)', color='white', fontsize=10, y=0.98)
    fig.patch.set_facecolor('#1e1e1e')


def draw_psd(fig, sequence, TR, TE, TI=150, flip_angle=90, etl=1, echo_spacing=10, b_value=1000):
    """
    Main dispatcher — draws the appropriate PSD for the given sequence.
    
    Parameters
    ----------
    fig : matplotlib Figure
    sequence : str — one of the sequence names from the simulator
    TR, TE, TI, flip_angle, etl, echo_spacing, b_value : sequence parameters
    """
    if sequence == "Spin Echo":
        draw_spin_echo_psd(fig, TR, TE)
    elif sequence == "FSE / TSE":
        draw_fse_psd(fig, TR, TE, etl, echo_spacing)
    elif sequence == "Gradient Echo":
        draw_gradient_echo_psd(fig, TR, TE, flip_angle)
    elif sequence == "Inversion Recovery":
        draw_inversion_recovery_psd(fig, TR, TE, TI)
    elif sequence == "Diffusion (DWI)":
        draw_diffusion_psd(fig, TR, TE, b_value)
    elif sequence == "MR Angiography":
        draw_tof_psd(fig, TR, TE, flip_angle)
    elif sequence == "fMRI (BOLD)":
        draw_epi_psd(fig, TR, TE)
    else:
        draw_spin_echo_psd(fig, TR, TE)