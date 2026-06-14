"""
MRI Simulation Platform — PyQt6 port.

This is a 1:1 functional port of the Tkinter app to PyQt6. All MRI physics
lives in the imported backend modules (signal_engine, phantom3d, kspace, ...),
which are unchanged. Only the GUI layer (widgets, layout, event wiring) was
rewritten.

Two compatibility shims keep the core logic identical to the Tkinter version:
  * Var       -> mimics tk.StringVar/DoubleVar/IntVar/BooleanVar (.get/.set/.trace_add)
  * DLabel    -> a QLabel exposing .config(text=, fg=) like a tk.Label

Run:  pip install PyQt6 matplotlib numpy   (plus your existing backend deps)
      python app_qt.py
"""

import os
import sys
from typing import Any

# Force matplotlib's Qt backend onto PyQt6 before it is imported.
os.environ.setdefault("QT_API", "PyQt6")

import numpy as np

from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QRect, QSettings
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QComboBox, QCheckBox, QRadioButton, QButtonGroup, QFrame, QScrollArea,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QSpinBox, QAbstractSpinBox, QLineEdit, QRubberBand,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from psd import draw_psd

from kspace import get_kspace_display
from brainweb_loader import get_brainweb_or_synthetic, data_dir
from phantom3d_extended import (add_vessels_3d, add_activation_3d,
                                load_real_tof_mra)
from presets import get_preset_names, get_preset, get_preset_region, get_preset_plane
from simulator import Simulator, _B0_MAP, _PF_MAP
import render_overlay

# SAR scaling factor per sequence type (relative to SE reference) — used by the
# metrics display's max-safe-FA hint (the simulation SAR lives in simulator.py).
# --------------------------------------------------------------------------- #
#  Compatibility shims
# --------------------------------------------------------------------------- #
class Var:
    """Drop-in replacement for tk.*Var. Holds a value and notifies callbacks."""
    __slots__ = ("_value", "_callbacks")

    def __init__(self, value: object) -> None:
        self._value = value
        self._callbacks: list[Any] = []

    def get(self) -> Any:
        return self._value

    def set(self, value: object) -> None:
        self._value = value
        for cb in self._callbacks:
            cb()

    def trace_add(self, _mode: str, callback: Any) -> None:
        # tk passes (name, index, mode) to the callback; we ignore them.
        self._callbacks.append(lambda: callback())


class DLabel(QLabel):
    """QLabel with a tk-style .config(text=, fg=) method and a preserved base style."""
    def __init__(self, text: str = "", base_style: str = "", parent: Any = None) -> None:
        super().__init__(text, parent)
        self._base = base_style
        if base_style:
            self.setStyleSheet(base_style)

    def config(self, text: str | None = None, fg: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        if fg is not None:
            self.setStyleSheet(self._base + f"color:{fg};")


# Visual theme (palette tokens, stylesheet, solid-bg helper) lives in app_theme
# so the window and the UI mixins share a single source of truth.
from app_theme import (  # noqa: E402
    C_CANVAS, C_PANEL, C_RAISED, C_BEZEL, C_HEADER, C_BORDER,
    C_BORDER_SOFT, C_BORDER_HI, C_TEXT, C_TEXT_DIM, C_ACCENT,
    C_ACCENT_HI, C_ACCENT_DK, C_ACCENT_INK, _solid_bg, GLOBAL_QSS,
)
from app_curves import CurvesMixin  # noqa: E402
from app_scout import ScoutMixin  # noqa: E402
from app_regions import RegionMixin  # noqa: E402
from app_interaction import InteractionMixin  # noqa: E402
from app_metrics import MetricsMixin  # noqa: E402
from app_export import ExportMixin  # noqa: E402


class CollapsibleSection(QWidget):
    """Vertically collapsible panel with a clickable header toggle."""

    def __init__(self, title: str, collapsed: bool = False, parent: Any = None) -> None:
        super().__init__(parent)
        self._title = title
        self._collapsed = collapsed
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 0)
        root.setSpacing(0)

        self._btn = QPushButton()
        self._btn.setObjectName("section-toggle")
        self._btn.setCheckable(True)
        self._btn.setChecked(not collapsed)
        self._btn.clicked.connect(self._on_toggle)
        self._refresh_label()
        root.addWidget(self._btn)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{C_PANEL}; border-left:2px solid {C_BORDER_SOFT}; margin-left:0;")
        self._inner = QVBoxLayout(self._body)
        self._inner.setContentsMargins(6, 4, 6, 8)
        self._inner.setSpacing(0)
        self._body.setVisible(not collapsed)
        root.addWidget(self._body)

    def _refresh_label(self) -> None:
        arrow = "▼" if not self._collapsed else "▶"
        # Escape '&' so Qt doesn't treat it as a mnemonic accelerator.
        self._btn.setText(f"  {arrow}  {self._title.replace('&', '&&')}")

    def _on_toggle(self, checked: bool) -> None:
        self._collapsed = not checked
        self._refresh_label()
        self._body.setVisible(checked)

    def set_expanded(self, expanded: bool) -> None:
        """Programmatically expand/collapse (used by the control search filter)."""
        if expanded == (not self._collapsed):
            return
        self._btn.setChecked(expanded)
        self._on_toggle(expanded)

    @property
    def title(self) -> str:
        return self._title

    @property
    def inner(self) -> QVBoxLayout:
        return self._inner


class TourOverlay:
    """A lightweight feature tour: highlights one control at a time with a rubber-
    band rectangle and a floating tooltip (Back / Next / Skip). Steps are
    (widget, title, text) tuples; steps whose widget is None are skipped."""

    def __init__(self, host: Any) -> None:
        self._host = host
        self._steps: list = []
        self._idx = 0
        self._band = QRubberBand(QRubberBand.Shape.Rectangle, host)
        self._card = QFrame(host)
        self._card.setObjectName("tour-card")
        self._card.setStyleSheet(
            f"#tour-card {{ background:{C_PANEL}; border:1px solid {C_BORDER_HI}; border-radius:10px; }}")
        self._card.hide()
        v = QVBoxLayout(self._card); v.setContentsMargins(14, 12, 14, 12); v.setSpacing(8)
        self._title = QLabel(); self._title.setWordWrap(True)
        self._title.setStyleSheet(f"color:{C_ACCENT_HI}; font-size:13px; font-weight:bold;")
        self._text = QLabel(); self._text.setWordWrap(True)
        self._text.setStyleSheet(f"color:{C_TEXT}; font-size:12px;")
        self._text.setMinimumWidth(270); self._text.setMaximumWidth(300)
        v.addWidget(self._title); v.addWidget(self._text)
        foot = QHBoxLayout()
        self._progress = QLabel(); self._progress.setStyleSheet(f"color:{C_TEXT_DIM}; font-size:11px;")
        foot.addWidget(self._progress); foot.addStretch(1)
        self._skip = QPushButton("Skip"); self._prev = QPushButton("‹ Back"); self._next = QPushButton("Next ›")
        for b in (self._skip, self._prev, self._next):
            b.setStyleSheet(f"QPushButton {{ background:{C_RAISED}; color:{C_TEXT}; border:1px solid {C_BORDER}; "
                            "border-radius:6px; padding:5px 11px; font-size:12px; }")
            foot.addWidget(b)
        self._next.setStyleSheet(f"QPushButton {{ background:{C_ACCENT}; color:{C_ACCENT_INK}; border:none; "
                                 "border-radius:6px; padding:5px 12px; font-size:12px; font-weight:bold; }")
        v.addLayout(foot)
        self._skip.clicked.connect(self.end)
        self._prev.clicked.connect(self.prev)
        self._next.clicked.connect(self.next)

    @property
    def active(self) -> bool:
        return self._card.isVisible()

    def start(self, steps: list) -> None:
        self._steps = [s for s in steps if s[0] is not None]
        if not self._steps:
            return
        self._idx = 0
        self._show_step()

    def _show_step(self) -> None:
        widget, title, text = self._steps[self._idx]
        p = widget                                   # expand any collapsed section
        while p is not None:
            if isinstance(p, CollapsibleSection):
                p.set_expanded(True)
            p = p.parentWidget()
        try:
            self._host.left_scroll.ensureWidgetVisible(widget, 60, 60)
        except Exception:
            pass
        self._title.setText(title); self._text.setText(text)
        self._progress.setText(f"{self._idx + 1} / {len(self._steps)}")
        self._prev.setEnabled(self._idx > 0)
        self._next.setText("Done" if self._idx == len(self._steps) - 1 else "Next ›")
        QTimer.singleShot(0, self._position)         # after layout/scroll settles
        self._position()

    def _position(self) -> None:
        if not self._steps:
            return
        widget = self._steps[self._idx][0]
        tl = widget.mapTo(self._host, QPoint(0, 0))
        rect = QRect(tl, widget.size())
        self._band.setGeometry(rect)
        self._band.show(); self._band.raise_()
        self._card.adjustSize()
        cw, ch = self._card.width(), self._card.height()
        hw, hh = self._host.width(), self._host.height()
        x = rect.right() + 14
        if x + cw > hw - 8:
            x = rect.left() - cw - 14
        x = max(8, min(x, hw - cw - 8))
        y = max(8, min(rect.center().y() - ch // 2, hh - ch - 8))
        self._card.move(x, y)
        self._card.show(); self._card.raise_()

    def next(self) -> None:
        if self._idx >= len(self._steps) - 1:
            self.end(); return
        self._idx += 1; self._show_step()

    def prev(self) -> None:
        if self._idx > 0:
            self._idx -= 1; self._show_step()

    def end(self) -> None:
        self._band.hide(); self._card.hide()


class MRISimulator(RegionMixin, InteractionMixin, ScoutMixin,
                   CurvesMixin, MetricsMixin, ExportMixin, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        from version import __version__
        self.setWindowTitle(f"MRISim  v{__version__}")
        # App/window icon (title bar, dock, taskbar) — the rounded app icon, with
        # the plain logo as a fallback.
        _icon_path = os.path.join(data_dir(), "app_icon.png")
        if not os.path.exists(_icon_path):
            _icon_path = os.path.join(data_dir(), "logo.png")
        if os.path.exists(_icon_path):
            _icon = QIcon(_icon_path)
            self.setWindowIcon(_icon)
            _app = QApplication.instance()
            if isinstance(_app, QApplication):
                _app.setWindowIcon(_icon)
        self.resize(1500, 900)

        print("Loading 3D phantom...")
        self.phantom_3d, self.phantom_source = get_brainweb_or_synthetic()
        self.phantom_3d_vessels = add_vessels_3d(self.phantom_3d)
        self.activation_3d = add_activation_3d(self.phantom_3d)
        self.real_tof = load_real_tof_mra()
        self.sim = Simulator()   # Qt-free acquisition controller (see simulator.py)
        print(f"Ready. ({self.phantom_source})")

        # Region registry: add body tissue properties to the engine, cache the
        # loaded brain volume, and lazily build other regions on first use.
        import body_phantoms
        self._body_phantoms = body_phantoms
        body_phantoms.merge_into_engine()
        self._brain_volume = self.phantom_3d
        self._region_cache = {"Brain": self.phantom_3d}
        self._lesion_vol_cache: dict[str, np.ndarray] = {}  # demo-pathology brains, per kind
        self._region_sequences: dict[str, list[str]] = {}
        # Real-MRI texture field per region (None = use synthetic texture, e.g. Brain)
        self.texture_3d: np.ndarray | None = None
        self._region_texture_cache: dict[str, "np.ndarray | None"] = {"Brain": None}

        # --- State variables (Var shim instead of tk.*Var) ---
        self.region = Var("Brain")
        self.brain_subject = Var("04")   # BrainWeb subject id (Brain region only)
        self.field_strength = Var("3T")
        self.sequence_type = Var("Spin Echo")
        self.preset_name = Var("")
        self.TR = Var(500.0)
        self.TE = Var(15.0)
        self.TI = Var(150.0)
        self.flip_angle = Var(90.0)
        self.NEX = Var(1)
        self.matrix_size = Var(256)
        self.trajectory = Var("Cartesian")
        self.radial_spokes = Var(128)
        self.FOV = Var(240.0)
        self.fov_fraction = Var(100.0)
        self.bandwidth = Var(125.0)
        self.snr_level = Var(35.0)
        self.show_kspace = Var(False)
        self.slice_thickness = Var(5.0)
        # 3-D (slab) acquisition
        self.acq3d = Var(False)
        self.n_partitions = Var(32)
        # Enabling the 3-D slab covers the whole anatomy from the first click (the
        # engine clamps to the through-axis extent); the slider still thins it.
        self.acq3d.trace_add("write", self._on_acq3d_toggle)
        self.kz_pf_enabled = Var(False)
        self._acq3d_key: tuple | None = None   # prescription cache for reformat
        self._acq3d_metrics: dict = {}
        # 3-D reconstruction view (MPR / MIP / oblique from the acquired slab)
        self.recon_enabled = Var(False)
        self.recon_mode = Var("MPR (3 planes)")
        self.recon_z = Var(50); self.recon_y = Var(50); self.recon_x = Var(50)
        self.recon_mip_plane = Var("axial")
        self.recon_mip_thick = Var(20)
        self.recon_mip_center = Var(50)
        self.recon_mip_mode = Var("MIP (brightest)")
        self.recon_azimuth = Var(0); self.recon_elevation = Var(0)
        self.recon_tilt = Var(0); self.recon_rot = Var(0)
        self.multi_slice = Var(False)
        self.show_psd = Var(False)

        # Control-search (Find a control) filter state.
        self._ctrl_filtering: bool = False
        self._ctrl_saved_expanded: dict[Any, bool] = {}

        # FOV / slice-group prescription (graphic planning on the scout)
        self.fov_planning = Var(False)
        self.n_slices = Var(1)
        self.slice_gap = Var(0.0)
        self.inplane_fov_pct = Var(100)   # in-plane FOV as integer % (10–100)
        self.inplane_off = Var(0.0)
        self.slice_tilt = Var(0.0)        # tilt angle in degrees (-45…+45)
        self.slice_rot  = Var(0.0)        # rotation angle in degrees (-45…+45)

        self.orientation = Var("axial")
        self.slice_idx = Var(90)

        # FSE
        self.etl = Var(1)
        self.echo_spacing = Var(10.0)

        # Acceleration
        self.accel_factor = Var(1)
        self.accel_method = Var("SENSE")

        # Partial Fourier
        self.pf_enabled = Var(False)
        self.pf_fraction = Var("Full")

        # Gadolinium contrast agent
        self.contrast_enabled = Var(False)
        self.contrast_dose = Var(1)      # × 0.1 mmol/kg  (1 = 0.1, 5 = 0.5)

        # k-Space filter (Gibbs ringing suppression)
        self.kspace_filter_enabled = Var(False)
        self.kspace_filter_window = Var("hamming")

        # Signal curve plot mode
        self.plot_curve_mode = Var("TE")   # "TE" | "TR"

        # Diffusion
        self.b_value = Var(1000.0)
        self.diff_direction = Var("Left-Right")
        self.diff_display = Var("DWI")

        # MRA
        self.angio_type = Var("TOF")
        self.angio_mip_slab = Var(20)
        self.angio_azimuth = Var(0)      # rotating-MIP view angle (deg)
        self.angio_elevation = Var(0)
        self.venc = Var(80.0)
        self.flow_velocity = Var(60.0)
        self.angio_display = Var("Magnitude")

        # fMRI
        self.fmri_display = Var("EPI Image")
        self.fmri_volumes = Var(100)
        self.fmri_threshold = Var(3.0)

        # Quantitative MRI (parameter mapping / synthetic contrast)
        self.qmri_display = Var("T1 Map (VFA)")

        # Echo-planar imaging (integer Vars; interpreted as scaled units)
        self.epi_esp = Var(5)            # echo spacing, ×0.1 ms  (5 = 0.5 ms)
        self.epi_b0_hz = Var(60)         # peak B0 off-resonance, Hz
        self.epi_ghost = Var(10)         # Nyquist ghost phase, ×0.01 rad
        self.epi_correct_ghost = Var(False)   # navigator-based ghost correction

        # Display options
        self.display_cmap = Var("gray")
        self.receive_coil = Var("Uniform (ideal)")
        self.pathology = Var("None")         # demo brain pathology (None | a lesion kind)
        self.measure_mode = Var("Off")       # Off | Ruler | ROI (on-image measurement)
        self.show_signal_curve = Var(True)   # show the signal curve beside the image
        self.show_tissue_overlay = Var(False)
        self.rician_bias_correct = Var(False)
        self.pv_sigma = Var(10)          # partial-volume PSF width, ×0.1 vox

        # Artifacts
        self.motion_enabled = Var(False)
        self.motion_amplitude = Var(3.0)
        self.motion_type = Var("periodic")
        self.chemical_shift_enabled = Var(False)
        self.susceptibility_enabled = Var(False)
        self.susceptibility_strength = Var(3.0)
        self.zipper_enabled = Var(False)
        self.gradient_distort = Var(0)   # gradient-nonlinearity distortion (% , 0 = off)

        # Physics effects
        self.mt_enabled = Var(False)
        self.mt_power = Var(50)      # integer 0–100 → 0.0–1.0
        self.b1_inhom_enabled = Var(False)
        self.flow_enabled = Var(True)
        self.flow_velocity = Var(70)   # integer 0–100 → 0.0–1.0 (blood velocity)
        self.fatsat_enabled = Var(False)

        # Comparison
        self.compare_mode = Var(False)
        self.compare_params: dict | None = None
        self._compare_images: "tuple[np.ndarray, np.ndarray] | None" = None

        # FOV slider widget reference (set in build_controls; guarded until then)
        self._fov_slider: Any = None

        # Debounced recalculate timer (replaces root.after)
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.timeout.connect(self.recalculate)

        # Window/level
        self.window_width = 1.0
        self.window_level = 0.5
        self.current_image: np.ndarray | None = None
        self._last_kspace: np.ndarray | None = None
        self.current_title = ""
        self.wl_dragging = False
        self.wl_start_x = 0
        self.wl_start_y = 0
        self._mra_dragging = False    # left-drag spins the MRA MIP
        self._mra_rotating = False    # use the fast downsampled MIP mid-drag

        self.build_ui()

    # ------------------------------------------------------------------ #
    #  Layout
    # ------------------------------------------------------------------ #
    def build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top workflow/header strip (syngo-style)
        outer.addWidget(self.build_header_bar())

        # Main content row — large viewport with parameter/metrics dock on the right
        content = QWidget()
        content_row = QHBoxLayout(content)
        content_row.setContentsMargins(2, 2, 2, 2)
        content_row.setSpacing(2)

        # Center panel — image + PSD canvases (the dominant viewport)
        self.center_panel = QWidget()
        # Frame the viewport like a screen: deep-black background inside a thin
        # bezel that separates it from the lighter control chrome around it.
        # Scoped by object name so the border doesn't cascade onto the canvases.
        self.center_panel.setObjectName("viewport")
        self.center_panel.setStyleSheet(
            f"QWidget#viewport {{ background:{C_CANVAS}; border:1px solid {C_BEZEL};"
            f" border-radius:6px; }}")
        self.center_layout = QHBoxLayout(self.center_panel)
        self.center_layout.setContentsMargins(4, 4, 4, 4)
        self.center_layout.setSpacing(4)

        # Right dock — scrollable parameter cards stacked above the metrics panel
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setStyleSheet(f"QScrollArea {{ background:{C_PANEL}; border:none; }}")
        self.controls_host = QWidget()
        self.controls_host.setObjectName("controls-host")
        self.controls_host.setStyleSheet(f"background:{C_PANEL};")
        self.controls_layout = QVBoxLayout(self.controls_host)
        self.controls_layout.setContentsMargins(6, 8, 6, 6)
        self.controls_layout.setSpacing(0)
        self.left_scroll.setWidget(self.controls_host)

        self.right_panel = QWidget()
        self.right_panel.setStyleSheet(f"background:{C_PANEL};")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(8, 6, 8, 8)
        self.right_layout.setSpacing(2)

        # The Measurements panel lives in its own scroll area so the splitter can
        # shrink it (its content scrolls) without its size hint blocking the drag.
        self.measurements_scroll = QScrollArea()
        self.measurements_scroll.setWidgetResizable(True)
        self.measurements_scroll.setStyleSheet(f"QScrollArea {{ background:{C_PANEL}; border:none; }}")
        self.measurements_scroll.setWidget(self.right_panel)
        self.measurements_scroll.setMinimumHeight(70)
        self.left_scroll.setMinimumHeight(90)

        # Vertical splitter: drag the handle to trade space between the parameter
        # cards (top) and the Measurements panel (bottom).
        self.right_split = QSplitter(Qt.Orientation.Vertical)
        self.right_split.setObjectName("right-split")
        self.right_split.setChildrenCollapsible(False)
        self.right_split.setHandleWidth(7)
        self.right_split.setStyleSheet(
            f"QSplitter#right-split::handle {{ background:{C_BORDER_SOFT}; margin:1px 10px; "
            f"border-radius:2px; }} "
            f"QSplitter#right-split::handle:hover {{ background:{C_ACCENT}; }}")
        self.right_split.addWidget(self.left_scroll)
        self.right_split.addWidget(self.measurements_scroll)
        self.right_split.setStretchFactor(0, 1)   # parameter cards absorb extra space
        self.right_split.setStretchFactor(1, 0)

        self.right_dock = QWidget()
        self.right_dock.setFixedWidth(338)
        dock_l = QVBoxLayout(self.right_dock)
        dock_l.setContentsMargins(0, 0, 0, 0)
        dock_l.setSpacing(2)
        dock_l.addWidget(self.right_split, stretch=1)

        content_row.addWidget(self.center_panel, stretch=1)
        content_row.addWidget(self.right_dock)
        outer.addWidget(content, stretch=1)

        # Bottom series/thumbnail strip
        outer.addWidget(self.build_series_strip())

        self.build_image_display()
        self.build_metrics_panel()
        self.build_controls()
        self._update_header()
        self.recalculate()

    # ------------------------------------------------------------------ #
    #  syngo-style chrome: header strip + bottom series tray
    # ------------------------------------------------------------------ #
    def build_header_bar(self) -> QFrame:
        bar = QFrame(); bar.setObjectName("header-bar"); bar.setFixedHeight(54)
        _solid_bg(bar, C_HEADER)
        h = QHBoxLayout(bar); h.setContentsMargins(12, 6, 14, 6); h.setSpacing(10)

        logo = QLabel(); logo.setObjectName("app-logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _logo_path = os.path.join(data_dir(), "logo.png")
        _logo_pix = QPixmap(_logo_path) if os.path.exists(_logo_path) else QPixmap()
        if not _logo_pix.isNull():
            logo.setPixmap(_logo_pix.scaledToHeight(
                38, Qt.TransformationMode.SmoothTransformation))
            # Image carries its own look; drop the gradient "MR" box styling and
            # the fixed 32px box so the pixmap isn't clipped.
            logo.setStyleSheet("background: transparent; min-width: 0; max-width: 16777215;"
                               " min-height: 0; max-height: 16777215;")
        else:
            logo.setText("MR")   # fallback to the styled monogram box
        h.addWidget(logo)

        tbox = QVBoxLayout(); tbox.setSpacing(0); tbox.setContentsMargins(0, 0, 0, 0)
        title = QLabel("MRISim"); title.setObjectName("app-title")
        tbox.addWidget(title)
        tw = QWidget(); tw.setLayout(tbox); h.addWidget(tw)

        h.addStretch(1)
        self._hdr_chips: dict[str, QLabel] = {}
        for key, cap in [("region", "REGION"), ("sequence", "SEQUENCE"),
                         ("field", "FIELD"), ("scan", "SCAN TIME")]:
            chip = QFrame(); chip.setObjectName("chip")
            cl = QVBoxLayout(chip); cl.setContentsMargins(11, 4, 11, 4); cl.setSpacing(0)
            capl = QLabel(cap); capl.setObjectName("chip-cap")
            vall = QLabel("—"); vall.setObjectName("chip-val")
            cl.addWidget(capl); cl.addWidget(vall)
            self._hdr_chips[key] = vall
            h.addWidget(chip)
        return bar

    def _update_header(self) -> None:
        chips = getattr(self, "_hdr_chips", None)
        if chips:
            chips["region"].setText(self.region.get())
            chips["sequence"].setText(self.sequence_type.get())
            chips["field"].setText(self.field_strength.get())
            lbl = getattr(self, "metrics_labels", {}).get("scan_time")
            chips["scan"].setText((lbl.text() if lbl is not None else "") or "—")
        thumbs = getattr(self, "_series_thumbs", None)
        if thumbs:
            cur = self.orientation.get()
            for o, b in thumbs.items():
                b.blockSignals(True); b.setChecked(o == cur); b.blockSignals(False)

    def build_series_strip(self) -> QFrame:
        strip = QFrame(); strip.setObjectName("series-strip"); strip.setFixedHeight(98)
        _solid_bg(strip, C_HEADER)
        h = QHBoxLayout(strip); h.setContentsMargins(14, 7, 14, 7); h.setSpacing(8)
        cap = QLabel("SERIES"); cap.setObjectName("strip-cap")
        h.addWidget(cap, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._series_group = QButtonGroup(self); self._series_group.setExclusive(True)
        self._series_thumbs: dict[str, QPushButton] = {}
        for orient, label in [("axial", "Axial"), ("coronal", "Coronal"),
                              ("sagittal", "Sagittal")]:
            col = QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(2)
            btn = QPushButton(); btn.setObjectName("thumb")
            btn.setCheckable(True); btn.setFixedSize(82, 60)
            pix = self._thumb_pixmap(orient)
            if pix is not None:
                btn.setIcon(QIcon(pix)); btn.setIconSize(QSize(74, 52))
            btn.setChecked(self.orientation.get() == orient)
            btn.clicked.connect(lambda _=False, o=orient: self._select_series(o))
            cap = QLabel(label); cap.setObjectName("thumb-cap")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(btn); col.addWidget(cap)
            wrap = QWidget(); wrap.setLayout(col)
            self._series_group.addButton(btn)
            self._series_thumbs[orient] = btn
            h.addWidget(wrap)
        h.addStretch(1)
        return strip

    def _thumb_pixmap(self, orient: str) -> QPixmap | None:
        vol = self.phantom_3d
        try:
            if orient == "axial":
                sl = vol[vol.shape[0] // 2, :, :]
            elif orient == "coronal":
                sl = vol[:, vol.shape[1] // 2, :]
            else:
                sl = vol[:, :, vol.shape[2] // 2]
        except Exception:
            return None
        lut = np.zeros(int(vol.max()) + 1, dtype=np.uint8)
        for lab, b in {0: 0, 1: 40, 2: 120, 3: 165, 4: 235, 5: 70,
                       6: 100, 11: 210, 14: 215, 15: 140}.items():
            if lab < lut.size:
                lut[lab] = b
        img = lut[np.clip(np.asarray(sl).astype(int), 0, lut.size - 1)]
        img = np.ascontiguousarray(np.flipud(img))
        h, w = img.shape
        self._thumb_keepalive = getattr(self, "_thumb_keepalive", [])
        self._thumb_keepalive.append(img)  # QImage shares the buffer, keep a ref
        qi = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8)  # type: ignore[call-overload]
        return QPixmap.fromImage(qi)

    def _select_series(self, orient: str) -> None:
        radio = getattr(self, "_orient_radios", {}).get(orient)
        if radio is not None:
            radio.setChecked(True)   # fires _on_orient_radio -> sets Var + recalcs
        else:
            self.orientation.set(orient); self.on_orientation_change()

    def build_image_display(self) -> None:
        # Scout / FOV-planning figure — 3-plane localizer (axial / coronal / sagittal)
        self.scout_fig = Figure(figsize=(3.5, 10), facecolor=C_CANVAS)
        gs = self.scout_fig.add_gridspec(3, 1, hspace=0.06,
                                          left=0.02, right=0.98,
                                          top=0.98, bottom=0.02)
        self._scout_plane_names = ["axial", "coronal", "sagittal"]
        self.scout_axes: list[Any] = [
            self.scout_fig.add_subplot(gs[0]),  # axial viewer
            self.scout_fig.add_subplot(gs[1]),  # coronal viewer
            self.scout_fig.add_subplot(gs[2]),  # sagittal viewer
        ]
        for ax in self.scout_axes:
            ax.set_facecolor(C_CANVAS)
        # Backward-compat alias; set dynamically in _draw_scout to the primary panel
        self.scout_ax: Any = self.scout_axes[1]
        self._scout_primary_ax: Any = None
        self._scout_overlays: dict = {}
        # Angle-drag handles: list of (hx, hy, panel_name, angle_var, cx, cy)
        self._scout_angle_handles: list = []

        self.scout_canvas = FigureCanvas(self.scout_fig)
        self.scout_canvas.setVisible(False)
        self.center_layout.addWidget(self.scout_canvas, stretch=2)
        self.scout_canvas.mpl_connect("button_press_event", self._scout_press)
        self.scout_canvas.mpl_connect("motion_notify_event", self._scout_motion)
        self.scout_canvas.mpl_connect("button_release_event", self._scout_release)
        self._scout_drag: dict | None = None
        self._scout_box_info: dict | None = None

        # Main image figure
        self.fig = Figure(figsize=(10, 5), facecolor=C_CANVAS)
        self.axes = self.fig.subplots(1, 2)
        # Title is gone (corner annotations now), so the viewport can use more of
        # the figure; leave a left margin for the plot's y-label in the wspace gap.
        self.fig.subplots_adjust(left=0.035, right=0.975, top=0.965,
                                 bottom=0.075, wspace=0.20)
        for ax in self.axes:
            ax.set_facecolor(C_CANVAS)
        self.canvas = FigureCanvas(self.fig)
        self.center_layout.addWidget(self.canvas, stretch=3)

        # PSD figure (conditionally shown)
        self.psd_fig = Figure(figsize=(4, 5), facecolor=C_CANVAS)
        self.psd_canvas = FigureCanvas(self.psd_fig)
        self.psd_canvas.setVisible(False)
        self.center_layout.addWidget(self.psd_canvas, stretch=2)

        # Window/level interaction via matplotlib's backend-agnostic events
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_press_event", self._on_recon_press)
        self._recon_mpr_axes: dict = {}
        self._recon_block_shape: tuple = (1, 1, 1)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        # Workstation interactions: wheel = scroll slices, keys = navigate/toggle
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("key_press_event", self._on_key)
        self.canvas.mpl_connect("axes_leave_event", lambda e: self._set_status_default())
        # Allow the canvas to receive keyboard focus for arrow-key navigation
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Status bar for the live cursor readout
        self.statusBar().setStyleSheet(f"color:{C_TEXT_DIM}; background:{C_HEADER}; border-top:1px solid {C_BORDER_SOFT};")  # type: ignore[union-attr]
        self._set_status_default()

    def _ensure_1x2_layout(self) -> None:
        """Restore the normal 1x2 subplot layout if the figure has a different configuration."""
        self._ensure_layout(2)

    def _ensure_layout(self, ncols: int) -> None:
        """Image-only (1x1) or image+second-panel (1x2) layout, rebuilt only when the
        column count changes. self.axes is always indexable as axes[0] (and axes[1]
        when ncols == 2)."""
        if len(self.fig.axes) == ncols:
            return
        self.fig.clear()
        if ncols == 1:
            self.axes = [self.fig.subplots(1, 1)]
            self.fig.subplots_adjust(left=0.04, right=0.97, top=0.965, bottom=0.075)
        else:
            self.axes = self.fig.subplots(1, 2)
            self.fig.subplots_adjust(left=0.035, right=0.975, top=0.965,
                                     bottom=0.075, wspace=0.20)
        for ax in self.axes:
            ax.set_facecolor(C_CANVAS)


    # RGBA colours for each tissue label (R, G, B, A) — used by the overlay.
    # Overlay data (tissue colours, orientation labels, body-region set) is shared
    # Qt-free in render_overlay — single source of truth for the desktop app and
    # the browser adapter.
    _TISSUE_COLORS = render_overlay.TISSUE_COLORS
    _ORIENT_LABELS = render_overlay.ORIENT_LABELS
    _BODY_REGIONS = render_overlay.BODY_REGIONS

    def _orientation_letters(self, orient: str) -> "tuple[str, str, str, str] | None":
        """Anatomical edge labels for the current view (delegates to the shared,
        Qt-free render_overlay so the desktop app and the browser agree)."""
        return render_overlay.orientation_letters(
            orient, sequence=self.sequence_type.get(), region=self.region.get(),
            fov_planning=self.fov_planning.get(),
            tilt=self.slice_tilt.get(), rot=self.slice_rot.get())

    def _make_tissue_overlay(self, label_map: np.ndarray,
                              target_shape: tuple[int, int]) -> np.ndarray:
        """Return an RGBA image mapping each label to a translucent colour."""
        return render_overlay.tissue_overlay(label_map, target_shape)

    def _frame_image_axes(self, ax: Any) -> None:
        """Give an image axes a clean framed-viewport look (shared helper)."""
        render_overlay.frame_image_axes(ax)

    def _annotate_image(self, ax: Any, params: dict, orient: str, sl_idx: int,
                        width: float, center: float) -> None:
        """DICOM-style corner annotations + 3-D badges + orientation letters on
        the main viewport (delegates to the shared, Qt-free render_overlay)."""
        render_overlay.annotate_image(
            ax, params, orient, sl_idx, width, center,
            region=self.region.get(),
            letters=self._orientation_letters(orient),
            recon_geom=getattr(self.sim, "_recon3d_geom", None))

    def _wl_bounds(self, img: np.ndarray) -> "tuple[float, float]":
        """(vmin, vmax) for an image at the current window/level, scaled to its own
        max so the same window applies fairly to either compare panel."""
        max_val = float(np.max(img)) if np.max(img) > 0 else 1.0
        center = self.window_level * max_val
        width = self.window_width * max_val
        return center - width / 2, center + width / 2

    def _apply_window_level_compare(self) -> None:
        """Fast re-window of both compare panels (set the colour limits, no
        re-simulation) as the user drags window/level."""
        imgs = getattr(self, "_compare_images", None)
        if not imgs:
            return
        for ax, im in zip(self.axes, imgs, strict=False):
            if not ax.images:
                continue
            ax.images[0].set_clim(*self._wl_bounds(im))
        self.canvas.draw()

    def apply_window_level(self) -> None:
        if self.current_image is None:
            return
        img = self.current_image
        max_val = np.max(img) if np.max(img) > 0 else 1
        center = self.window_level * max_val
        width = self.window_width * max_val
        cmap = self.display_cmap.get()
        orient = self.orientation.get(); sl_idx = self.slice_idx.get()
        _asp = self._get_voxel_aspect(orient)
        self.axes[0].clear()
        self.axes[0].imshow(img, cmap=cmap, origin="lower",
                            vmin=center - width / 2, vmax=center + width / 2,
                            aspect=_asp)
        if self.show_tissue_overlay.get():
            ph_slice = self._get_current_phantom_slice(orient, sl_idx, self.get_current_params())
            self.axes[0].imshow(self._make_tissue_overlay(ph_slice, img.shape),
                                origin="lower", aspect="auto")
        self._frame_image_axes(self.axes[0])
        self._annotate_image(self.axes[0], self.get_current_params(), orient, sl_idx, width, center)
        self.canvas.draw()

    # ------------------------------------------------------------------ #
    #  Widget factory helpers
    # ------------------------------------------------------------------ #
    def _section_label(self, parent_layout: Any, text: str, big: bool = False) -> QLabel:
        if big:
            style = "font-size:15px; font-weight:bold; color:white;"
        else:
            style = "font-size:11px; font-weight:bold; color:#9aa4b2;"
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        parent_layout.addWidget(lbl)
        return lbl

    def _separator(self, parent_layout: Any) -> None:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background:#313842; max-height:1px; border:none;")
        parent_layout.addWidget(line)

    def _slider(self, parent_layout: Any, label: str, var: Var, mn: float, mx: float) -> Any:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(4, 5, 4, 3)
        v.setSpacing(3)

        is_float = isinstance(var.get(), float)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("color:#9aa4b2; font-size:11px;")
        # Editable value: type an exact number or arrow-key it (no spin buttons —
        # the slider gives the coarse drag; this gives precise entry). The slider is
        # integer-resolution, so the spinbox matches that and clamps to [mn, mx].
        spin = QSpinBox()
        spin.setRange(int(mn), int(mx))
        spin.setValue(int(round(var.get())))
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setKeyboardTracking(False)   # commit on Enter / focus-out, not each keystroke
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        spin.setFixedWidth(70)
        spin.setStyleSheet(
            "QSpinBox { color:white; font-size:12px; font-weight:bold; "
            f"background:{C_RAISED}; border:1px solid {C_BORDER}; border-radius:4px; padding:1px 5px; }}"
            f"QSpinBox:focus {{ border-color:{C_ACCENT}; }}")
        row.addWidget(name_lbl)
        row.addStretch(1)
        row.addWidget(spin)
        v.addLayout(row)

        s = QSlider(Qt.Orientation.Horizontal)
        s.setMinimum(int(mn))
        s.setMaximum(int(mx))
        s.setValue(int(round(var.get())))
        v.addWidget(s)

        # Slider and spinbox both drive the same Var; a reentrancy guard stops the
        # sync (Var write trace) from echoing back into another valueChanged.
        guard = {"on": False}

        def commit(value: int) -> None:
            if guard["on"]:
                return
            var.set(float(value) if is_float else int(value))
            self.schedule_recalculate()

        s.valueChanged.connect(commit)
        spin.valueChanged.connect(commit)

        def sync() -> None:
            iv = int(round(var.get()))
            guard["on"] = True
            if s.value() != iv:
                s.setValue(iv)
            if spin.value() != iv:
                spin.setValue(iv)
            guard["on"] = False

        var.trace_add("write", sync)
        parent_layout.addWidget(container)
        container._qslider = s  # type: ignore[attr-defined]
        return container

    # ------------------------------------------------------------------ #
    #  Control search / filter
    # ------------------------------------------------------------------ #
    def _section_rows(self, sec: "CollapsibleSection") -> list:
        """The individual control-row widgets inside a collapsible section."""
        lay = sec.inner
        rows = []
        for i in range(lay.count()):
            item = lay.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                rows.append(w)
        return rows

    @staticmethod
    def _row_text(w: Any) -> str:
        """Lower-cased searchable text for a control row (its labels + checkbox text)."""
        parts: list[str] = []
        if isinstance(w, QCheckBox):
            parts.append(w.text())
        for lbl in w.findChildren(QLabel):
            parts.append(lbl.text())
        for cb in w.findChildren(QCheckBox):
            parts.append(cb.text())
        return " ".join(parts).lower()

    def _filter_controls(self, text: str) -> None:
        term = text.strip().lower()
        sections = self.controls_host.findChildren(CollapsibleSection)
        if not term:
            if self._ctrl_filtering:
                for sec in sections:
                    sec.setVisible(True)
                    for r in self._section_rows(sec):
                        r.setVisible(True)
                    sec.set_expanded(self._ctrl_saved_expanded.get(sec, True))
                self._ctrl_filtering = False
            return
        if not self._ctrl_filtering:
            # Entering filter mode — remember each section's expanded state to restore.
            self._ctrl_saved_expanded = {sec: not sec._collapsed for sec in sections}
            self._ctrl_filtering = True
        for sec in sections:
            title_hit = term in sec.title.lower()
            any_hit = False
            for r in self._section_rows(sec):
                hit = title_hit or term in self._row_text(r)
                r.setVisible(hit)
                any_hit = any_hit or hit
            sec.setVisible(any_hit)
            if any_hit:
                sec.set_expanded(True)

    # ------------------------------------------------------------------ #
    #  Guided feature tour
    # ------------------------------------------------------------------ #
    def _start_tour(self) -> None:
        if getattr(self, "_tour", None) is None:
            self._tour = TourOverlay(self)
        steps = [
            (self._seq_dropdown, "Pick a sequence",
             "Choose the pulse sequence here — the description below it says what each one is for."),
            (self.tr_slider, "Set the timing",
             "Sweep TR / TE / flip to change the contrast. Type an exact value in the box, or drag."),
            (self.canvas, "The image",
             "Scroll (or ↑/↓) to change slice, drag to window/level (double-click resets), and hover to read the tissue."),
            (self._preset_dd, "Clinical presets",
             "Apply a real-world protocol in one click — every setting is filled in for you."),
            (self._setA_btn, "Compare A / B",
             "Snapshot the current setup as A, change something, then Compare A↔B to see them side by side."),
            (self._acq3d_cb, "3D & reconstruction",
             "Acquire a 3D slab once and reformat any plane; the reconstruction view shows a 2×2 quad (MPR + a 3D MIP)."),
            (self._measure_dd, "Measure",
             "Pick Ruler or ROI, then drag on the image (or a reformat) to read a distance in mm or an ROI's mean / SD / SNR."),
            (self._ctrl_search, "Find a control",
             "Lost a setting? Type here to jump straight to it — the panel filters as you type. Re-open this tour with ❔ Tour."),
        ]
        self._tour.start(steps)

    def _maybe_offer_tour(self) -> None:
        """Auto-start the tour on the first launch (remembered via QSettings)."""
        try:
            s = QSettings("mrisim", "mrisim")
            if not s.value("tour_seen", False, type=bool):
                s.setValue("tour_seen", True)
                self._start_tour()
        except Exception:
            pass

    def _dropdown(self, parent_layout: Any, label: str, var: Var, options: Any, on_select: Any, inline: bool = False) -> Any:
        container = QWidget()
        lay: Any
        if inline:
            lay = QHBoxLayout(container)
            lay.setContentsMargins(4, 4, 4, 4)
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#9aa4b2; font-size:11px;")
            lay.addWidget(lbl)
            lay.addStretch(1)
        else:
            lay = QVBoxLayout(container)
            lay.setContentsMargins(4, 5, 4, 4)
            lay.setSpacing(3)
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#9aa4b2; font-size:11px;")
            lay.addWidget(lbl)

        combo = QComboBox()
        combo.addItems(list(options))
        if var.get() in options:
            combo.setCurrentText(var.get())
        if inline:
            combo.setMaximumWidth(140)
        lay.addWidget(combo)

        def on_text(text: str) -> None:
            var.set(text)
            on_select()

        combo.currentTextChanged.connect(on_text)

        def sync() -> None:
            if combo.currentText() != var.get() and var.get() in options:
                combo.blockSignals(True)
                combo.setCurrentText(var.get())
                combo.blockSignals(False)

        var.trace_add("write", sync)
        parent_layout.addWidget(container)
        container._combo = combo  # type: ignore[attr-defined]
        return container

    def _checkbox(self, parent_layout: Any, text: str, var: Var) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(bool(var.get()))
        cb.setStyleSheet("QCheckBox { color:#c4cad2; font-size:11px; padding:3px 4px; }")

        def on_toggle(checked: bool) -> None:
            var.set(bool(checked))
            self.schedule_recalculate()

        cb.toggled.connect(on_toggle)

        def sync() -> None:
            if cb.isChecked() != bool(var.get()):
                cb.blockSignals(True)
                cb.setChecked(bool(var.get()))
                cb.blockSignals(False)

        var.trace_add("write", sync)
        parent_layout.addWidget(cb)
        return cb

    def _button(self, parent_layout_or_row: Any, text: str, command: Any,
                color: str | None = None) -> QPushButton:
        b = QPushButton(text)
        if color == "accent":
            # Primary action: filled accent with dark ink.
            b.setStyleSheet(
                f"QPushButton {{ background:{C_ACCENT}; color:{C_ACCENT_INK}; border:1px solid {C_ACCENT}; "
                f"padding:6px 11px; border-radius:6px; font-weight:bold; }}"
                f"QPushButton:hover {{ background:{C_ACCENT_HI}; border-color:{C_ACCENT_HI}; }}"
                f"QPushButton:pressed {{ background:{C_ACCENT_DK}; }}")
        else:
            # Secondary action: raised surface (inherits the global QPushButton look).
            b.setStyleSheet(
                f"QPushButton {{ background:{C_RAISED}; color:{C_TEXT}; border:1px solid {C_BORDER}; "
                f"padding:6px 11px; border-radius:6px; font-weight:bold; }}"
                f"QPushButton:hover {{ background:#2b333d; border-color:{C_BORDER_HI}; }}"
                f"QPushButton:pressed {{ background:#14191f; }}")
        b.clicked.connect(command)
        parent_layout_or_row.addWidget(b)
        return b

    # ------------------------------------------------------------------ #
    #  Controls
    # ------------------------------------------------------------------ #
    def build_controls(self) -> None:
        L = self.controls_layout

        # \u2500\u2500 App header \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        hdrow = QHBoxLayout(); hdrow.setContentsMargins(0, 0, 0, 0)
        hdr = QLabel("ACQUISITION")
        hdr.setStyleSheet("font-size:11px; font-weight:bold; color:#6b7585; "
                          "letter-spacing:1px; padding:4px 6px 4px 6px;")
        hdrow.addWidget(hdr); hdrow.addStretch(1)
        tour_btn = QPushButton("❔ Tour")
        tour_btn.setToolTip("Take a guided tour of the main features")
        tour_btn.setStyleSheet(f"QPushButton {{ background:{C_RAISED}; color:{C_TEXT_DIM}; "
                               f"border:1px solid {C_BORDER}; border-radius:6px; padding:3px 9px; font-size:11px; }}"
                               f"QPushButton:hover {{ color:{C_ACCENT_HI}; border-color:{C_ACCENT}; }}")
        tour_btn.clicked.connect(self._start_tour)
        hdrow.addWidget(tour_btn)
        _hwrap = QWidget(); _hwrap.setLayout(hdrow); L.addWidget(_hwrap)

        # Find a control: type to show only matching controls (and the sections
        # holding them, expanded); clearing restores the normal layout.
        self._ctrl_search = QLineEdit()
        self._ctrl_search.setPlaceholderText("🔍  Find a control…")
        self._ctrl_search.setClearButtonEnabled(True)
        self._ctrl_search.setStyleSheet(
            "QLineEdit { color:%s; font-size:12px; background:%s; border:1px solid %s; "
            "border-radius:6px; padding:5px 8px; margin:2px 6px 4px 6px; }"
            "QLineEdit:focus { border-color:%s; }" % (C_TEXT, C_RAISED, C_BORDER, C_ACCENT))
        self._ctrl_search.textChanged.connect(self._filter_controls)
        L.addWidget(self._ctrl_search)

        # \u2500\u2500 Sequence & Protocol \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        seq_sec = CollapsibleSection("Sequence & Protocol")
        L.addWidget(seq_sec)
        SL = seq_sec.inner
        self._preset_dd = self._dropdown(SL, "Preset", self.preset_name, ["(Custom)"] + get_preset_names(), self.on_preset_change)
        self._dropdown(SL, "Field Strength", self.field_strength,
                       list(_B0_MAP.keys()), self.schedule_recalculate, inline=True)
        self._seq_dropdown = self._dropdown(SL, "Sequence", self.sequence_type,
                       ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
                        "Balanced SSFP",
                        "Diffusion (DWI)", "MR Angiography", "Susceptibility (SWI)",
                        "fMRI (BOLD)", "Quantitative (qMRI)", "Echo Planar (EPI)"],
                       self.on_sequence_change)
        self.desc_label = DLabel("", base_style="color:#6b7585; font-size:9px; padding:2px 2px;")
        self.desc_label.setWordWrap(True)
        SL.addWidget(self.desc_label)
        self._dropdown(SL, "Signal Curve", self.plot_curve_mode,
                       ["TE decay", "TR recovery", "TI sweep", "Flip angle", "Contrast Map", "Histogram"],
                       self.schedule_recalculate, inline=True)

        # FOV planning (scout) \u2014 toggle plus its slice-group / oblique controls.
        self._checkbox(SL, "FOV Planning (scout)", self.fov_planning)
        self.fov_planning.trace_add("write", self.on_fov_planning_toggle)
        self.plan_frame = QWidget()
        plan_l = QVBoxLayout(self.plan_frame); plan_l.setContentsMargins(0, 0, 0, 0); plan_l.setSpacing(1)
        self._slider(plan_l, "# Slices", self.n_slices, 1, 32)
        self._slider(plan_l, "Slice Gap (vox)", self.slice_gap, 0, 20)
        self._slider(plan_l, "In-plane FOV (%)", self.inplane_fov_pct, 10, 100)
        self._slider(plan_l, "Tilt (\u00b0)", self.slice_tilt, -45, 45)
        self._slider(plan_l, "Rotation (\u00b0)", self.slice_rot, -45, 45)
        _reset_row = QHBoxLayout(); _reset_row.setContentsMargins(4, 2, 4, 2)
        _reset_btn = QPushButton("Reset Angles && FOV")
        _reset_btn.setStyleSheet("font-size:10px; padding:3px 6px; background:#313842; color:#c4cad2; border:1px solid #313842;")
        _reset_btn.clicked.connect(self._reset_oblique)
        _reset_row.addWidget(_reset_btn)
        _reset_wrap = QWidget(); _reset_wrap.setLayout(_reset_row); plan_l.addWidget(_reset_wrap)
        hint2 = QLabel("Scout: drag box = move \u2022 edges = FOV / coverage \u2022 Tilt/Rot = oblique")
        hint2.setStyleSheet("color:#586273; font-size:9px;")
        plan_l.addWidget(hint2)
        SL.addWidget(self.plan_frame)
        self.plan_frame.setVisible(False)

        # \u2500\u2500 Timing \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        timing_sec = CollapsibleSection("Timing")
        L.addWidget(timing_sec)
        TL = timing_sec.inner
        self.tr_slider = self._slider(TL, "TR (ms)", self.TR, 50, 10000)
        self.te_slider = self._slider(TL, "TE (ms)", self.TE, 5, 300)
        self.ti_frame = self._slider(TL, "TI (ms)", self.TI, 50, 4000)
        self.fa_frame = self._slider(TL, "Flip Angle (\u00b0)", self.flip_angle, 1, 90)

        self.fse_frame = QWidget()
        fse_l = QVBoxLayout(self.fse_frame); fse_l.setContentsMargins(0, 0, 0, 0); fse_l.setSpacing(1)
        self._slider(fse_l, "Echo Train Length", self.etl, 1, 32)
        self._slider(fse_l, "Echo Spacing (ms)", self.echo_spacing, 5, 20)
        TL.addWidget(self.fse_frame)

        self.diff_frame = QWidget()
        diff_l = QVBoxLayout(self.diff_frame); diff_l.setContentsMargins(0, 0, 0, 0); diff_l.setSpacing(1)
        self._slider(diff_l, "b-value (s/mm\u00b2)", self.b_value, 0, 3000)
        self._dropdown(diff_l, "Direction", self.diff_direction, ["Left-Right", "Up-Down", "Diagonal"], self.schedule_recalculate)
        self._dropdown(diff_l, "Display", self.diff_display, ["DWI", "ADC Map", "FA Map"], self.schedule_recalculate)
        TL.addWidget(self.diff_frame)

        self.angio_frame = QWidget()
        angio_l = QVBoxLayout(self.angio_frame); angio_l.setContentsMargins(0, 0, 0, 0); angio_l.setSpacing(1)
        self._slider(angio_l, "MIP Azimuth (°)", self.angio_azimuth, 0, 360)
        self._slider(angio_l, "MIP Elevation (°)", self.angio_elevation, -60, 60)
        angio_hint = QLabel("Rotating Time-of-Flight MIP — click-drag on the image to spin the angiogram (or use the Azimuth/Elevation sliders).")
        angio_hint.setWordWrap(True); angio_hint.setStyleSheet("color:#6b7585; font-size:9px; padding-left:4px;")
        angio_l.addWidget(angio_hint)
        TL.addWidget(self.angio_frame)

        self.fmri_frame = QWidget()
        fmri_l = QVBoxLayout(self.fmri_frame); fmri_l.setContentsMargins(0, 0, 0, 0); fmri_l.setSpacing(1)
        self._dropdown(fmri_l, "Display", self.fmri_display, ["EPI Image", "Activation Map", "T-statistic Map"], self.schedule_recalculate)
        self._slider(fmri_l, "Num Volumes", self.fmri_volumes, 20, 500)
        self._slider(fmri_l, "T-threshold", self.fmri_threshold, 1, 8)
        TL.addWidget(self.fmri_frame)

        self.qmri_frame = QWidget()
        qmri_l = QVBoxLayout(self.qmri_frame); qmri_l.setContentsMargins(0, 0, 0, 0); qmri_l.setSpacing(1)
        self._dropdown(qmri_l, "Map", self.qmri_display,
                       ["T1 Map (VFA)", "T2 Map (multi-echo)", "T2* Map (multi-echo)",
                        "Synthetic SE"], self.schedule_recalculate)
        qmri_hint = QLabel("Maps are quantitative (ms). Synthetic SE uses TR/TE to render contrast from the maps.")
        qmri_hint.setWordWrap(True); qmri_hint.setStyleSheet("color:#6b7585; font-size:9px; padding-left:4px;")
        qmri_l.addWidget(qmri_hint)
        TL.addWidget(self.qmri_frame)

        self.epi_frame = QWidget()
        epi_l = QVBoxLayout(self.epi_frame); epi_l.setContentsMargins(0, 0, 0, 0); epi_l.setSpacing(1)
        self._slider(epi_l, "Echo Spacing (×0.1 ms)", self.epi_esp, 3, 15)
        self._slider(epi_l, "B0 off-resonance (Hz)", self.epi_b0_hz, 0, 300)
        self._slider(epi_l, "Nyquist ghost (×0.01 rad)", self.epi_ghost, 0, 40)
        self._checkbox(epi_l, "Ghost correction (navigator)", self.epi_correct_ghost)
        epi_hint = QLabel("Single-shot GRE-EPI: the tissue susceptibility B0 field warps geometry in the phase-encode (vertical) axis; even/odd phase errors give the N/2 ghost.")
        epi_hint.setWordWrap(True); epi_hint.setStyleSheet("color:#6b7585; font-size:9px; padding-left:4px;")
        epi_l.addWidget(epi_hint)
        TL.addWidget(self.epi_frame)

        # \u2500\u2500 3D Navigation \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        nav_sec = CollapsibleSection("3D Navigation")
        L.addWidget(nav_sec)
        NL = nav_sec.inner
        self._region_dd = self._dropdown(NL, "Region", self.region, self._body_phantoms.REGION_NAMES,
                       self.on_region_change, inline=True)
        self._dropdown(NL, "Brain Subject", self.brain_subject,
                       ["04", "05", "06", "18", "20", "38"],
                       self.on_subject_change, inline=True)
        self._pathology_dd = self._dropdown(NL, "Pathology (demo)", self.pathology,
                       list(self._PATHOLOGY_KIND.keys()),
                       self.on_pathology_change, inline=True)
        rl_row = QHBoxLayout(); rl_row.setContentsMargins(0, 0, 0, 2)
        self._button(rl_row, "Browse Masks\u2026", self.browse_masks, color="accent")
        self._button(rl_row, "Load File\u2026", self.load_nifti_region)
        rlwrap = QWidget(); rlwrap.setLayout(rl_row); NL.addWidget(rlwrap)
        orow = QHBoxLayout(); orow.setContentsMargins(0, 4, 0, 2)
        self._orient_group = QButtonGroup(self)
        self._orient_radios: dict[str, QRadioButton] = {}
        for orient, label in [("axial", "Axial"), ("sagittal", "Sagittal"), ("coronal", "Coronal")]:
            rb = QRadioButton(label)
            rb.setChecked(self.orientation.get() == orient)
            rb.toggled.connect(lambda checked, o=orient: self._on_orient_radio(checked, o))
            self._orient_group.addButton(rb)
            self._orient_radios[orient] = rb
            orow.addWidget(rb)
        orow.addStretch(1)
        owrap = QWidget(); owrap.setLayout(orow); NL.addWidget(owrap)
        self._slice_slider = self._slider(NL, "Slice", self.slice_idx, 0, 180)._qslider
        self._checkbox(NL, "Multi-slice (3\u00d73 grid)", self.multi_slice)

        # \u2500\u2500 Spatial / Acquisition \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        spatial_sec = CollapsibleSection("Spatial / Acquisition")
        L.addWidget(spatial_sec)
        SPL = spatial_sec.inner
        self._slider(SPL, "Matrix Size", self.matrix_size, 32, 256)
        self._dropdown(SPL, "Trajectory", self.trajectory,
                       ["Cartesian", "Radial"], self.schedule_recalculate, inline=True)
        self._slider(SPL, "Radial Spokes", self.radial_spokes, 16, 400)
        self._fov_slider = self._slider(SPL, "FOV (mm)", self.FOV, 100, 500)._qslider
        self._slider(SPL, "Phase FOV (%)", self.fov_fraction, 50, 100)
        self._slider(SPL, "Slice Thickness (mm)", self.slice_thickness, 1, 15)
        self._acq3d_cb = self._checkbox(SPL, "3D acquisition (slab)", self.acq3d)
        self._slider(SPL, "3D slab depth (partitions)", self.n_partitions, 4, 256)
        self._checkbox(SPL, "kz Partial Fourier", self.kz_pf_enabled)
        # Reconstruction view: turn the acquired slab into MPR / MIP / oblique.
        self._checkbox(SPL, "Reconstruction view (3D slab → MPR/MIP)", self.recon_enabled)
        self._dropdown(SPL, "Recon mode", self.recon_mode,
                       ["MPR (3 planes)", "Thick-slab MIP", "Rotating MIP", "Oblique MPR"],
                       self.schedule_recalculate)
        self._slider(SPL, "MPR crosshair ↕ (Z %)", self.recon_z, 0, 100)
        self._slider(SPL, "MPR crosshair A–P (Y %)", self.recon_y, 0, 100)
        self._slider(SPL, "MPR crosshair L–R (X %)", self.recon_x, 0, 100)
        self._dropdown(SPL, "Projection", self.recon_mip_mode,
                       ["MIP (brightest)", "MinIP (darkest)", "AIP (average)"],
                       self.schedule_recalculate)
        self._dropdown(SPL, "MIP plane", self.recon_mip_plane,
                       ["axial", "coronal", "sagittal"], self.schedule_recalculate)
        self._slider(SPL, "MIP slab thickness (part.)", self.recon_mip_thick, 1, 64)
        self._slider(SPL, "MIP slab position (%)", self.recon_mip_center, 0, 100)
        self._slider(SPL, "Rotating MIP azimuth (°)", self.recon_azimuth, 0, 360)
        self._slider(SPL, "Rotating MIP elevation (°)", self.recon_elevation, -60, 60)
        self._slider(SPL, "Oblique MPR tilt (°)", self.recon_tilt, -45, 45)
        self._slider(SPL, "Oblique MPR rotate (°)", self.recon_rot, -45, 45)
        self._slider(SPL, "Bandwidth (kHz)", self.bandwidth, 10, 500)
        self._dropdown(SPL, "Receive coil", self.receive_coil,
                       ["Uniform (ideal)", "Head array (8-ch)", "Quadrature (2-ch)", "Surface coil"],
                       self.schedule_recalculate, inline=True)
        self._slider(SPL, "NEX", self.NEX, 1, 8)
        self._slider(SPL, "Acceleration (R)", self.accel_factor, 1, 4)
        self._dropdown(SPL, "Accel Method", self.accel_method, ["SENSE", "GRAPPA", "CS"], self.schedule_recalculate, inline=True)
        self._checkbox(SPL, "Partial Fourier", self.pf_enabled)
        self._dropdown(SPL, "PF Fraction", self.pf_fraction, list(_PF_MAP.keys()), self.schedule_recalculate, inline=True)
        self._checkbox(SPL, "k-Space Filter (anti-Gibbs)", self.kspace_filter_enabled)
        self._dropdown(SPL, "Filter Window", self.kspace_filter_window,
                       ["hamming", "hanning", "blackman"], self.schedule_recalculate, inline=True)

        # \u2500\u2500 Artifacts (collapsed by default) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        art_sec = CollapsibleSection("Artifacts", collapsed=True)
        L.addWidget(art_sec)
        AL = art_sec.inner
        self._checkbox(AL, "Motion (ghosting)", self.motion_enabled)
        self._slider(AL, "Motion Amplitude", self.motion_amplitude, 1, 15)
        self._dropdown(AL, "Motion Type", self.motion_type, ["periodic", "random", "linear"], self.schedule_recalculate, inline=True)
        self._checkbox(AL, "Chemical Shift", self.chemical_shift_enabled)
        self._checkbox(AL, "Susceptibility", self.susceptibility_enabled)
        self._slider(AL, "Susceptibility Strength", self.susceptibility_strength, 1, 10)
        self._slider(AL, "Gradient Distortion (%)", self.gradient_distort, 0, 100)
        self._checkbox(AL, "Zipper (RF leak)", self.zipper_enabled)
        self._checkbox(AL, "Gadolinium Contrast", self.contrast_enabled)
        self._slider(AL, "Gd Dose (mmol/kg × 10)", self.contrast_dose, 1, 5)

        # ── Physics Effects (collapsed by default) ───────────────────────────────
        phys_sec = CollapsibleSection("Physics Effects", collapsed=True)
        L.addWidget(phys_sec)
        PHL = phys_sec.inner
        self._checkbox(PHL, "Magnetization Transfer (MT)", self.mt_enabled)
        self._slider(PHL, "MT Saturation Power (%)", self.mt_power, 0, 100)
        self._checkbox(PHL, "Blood Flow (SE void / GRE inflow)", self.flow_enabled)
        self._slider(PHL, "Flow Velocity (%)", self.flow_velocity, 0, 100)
        self._checkbox(PHL, "Fat Sat (CHESS, spectral)", self.fatsat_enabled)
        self._checkbox(PHL, "B1+ Field Inhomogeneity", self.b1_inhom_enabled)
        b1_hint = QLabel("B1+: mild at 1.5T/3T · dramatic at 7T")
        b1_hint.setStyleSheet("color:#6b7585; font-size:9px; padding-left:4px;")
        PHL.addWidget(b1_hint)

        # \u2500\u2500 Display (collapsed by default) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        disp_sec = CollapsibleSection("Display", collapsed=True)
        L.addWidget(disp_sec)
        DL = disp_sec.inner
        self._slider(DL, "Noise Level (SNR)", self.snr_level, 5, 100)
        self._slider(DL, "Partial Volume (×0.1 vox)", self.pv_sigma, 0, 30)
        self._checkbox(DL, "Rician bias correction", self.rician_bias_correct)
        self._dropdown(DL, "Colormap", self.display_cmap,
                       ["gray", "bone", "hot", "plasma", "viridis", "magma"],
                       self.schedule_recalculate, inline=True)
        self._checkbox(DL, "Tissue label overlay", self.show_tissue_overlay)
        self._checkbox(DL, "Show signal curve", self.show_signal_curve)
        self._measure_dd = self._dropdown(DL, "Measure tool", self.measure_mode, ["Off", "Ruler", "ROI"],
                       self._on_measure_mode_change, inline=True)
        self.measure_readout = DLabel("Ruler/ROI: drag on the image.",
                                      base_style="color:#586273; font-size:9px;")
        DL.addWidget(self.measure_readout)
        self._checkbox(DL, "Show k-space", self.show_kspace)
        self._checkbox(DL, "Show Pulse Sequence Diagram", self.show_psd)
        hint = QLabel("Wheel/\u2191\u2193: slice \u2022 drag: W/L \u2022 dbl-click/R: reset")
        hint.setStyleSheet("color:#586273; font-size:9px;")
        DL.addWidget(hint)

        # \u2500\u2500 Comparison (collapsed by default) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        cmp_sec = CollapsibleSection("Comparison", collapsed=True)
        L.addWidget(cmp_sec)
        CL = cmp_sec.inner
        crow = QHBoxLayout(); crow.setContentsMargins(0, 0, 0, 0)
        self._setA_btn = self._button(crow, "Set as A", self.set_protocol_a, color="accent")
        self._button(crow, "Compare A\u2194B", self.toggle_compare)
        self._button(crow, "Clear", self.clear_compare)
        cwrap = QWidget(); cwrap.setLayout(crow); CL.addWidget(cwrap)
        self.compare_status = DLabel("No comparison set", base_style="color:#586273; font-size:9px;")
        CL.addWidget(self.compare_status)

        # \u2500\u2500 Export \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        erow = QHBoxLayout(); erow.setContentsMargins(6, 6, 6, 4)
        self._button(erow, "Save Img", self.export_current_image)
        self._button(erow, "Protocol", self.export_current_protocol)
        self._button(erow, "PDF", self.export_current_report)
        self._button(erow, "Load", self.load_protocol_file)
        ewrap = QWidget(); ewrap.setLayout(erow)
        L.addWidget(ewrap)

        L.addStretch(1)
        self.on_sequence_change()

    def build_metrics_panel(self) -> None:
        title = QLabel("MEASUREMENTS")
        title.setStyleSheet("font-size:11px; font-weight:bold; color:#6b7585; "
                            "letter-spacing:1px; padding:2px 0 2px 0;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.right_layout.addWidget(title)
        self._separator(self.right_layout)

        self.metrics_labels: dict = {}

        def _card(key: str, label: str, value_color: str = C_ACCENT) -> QWidget:
            card = QWidget()
            card.setStyleSheet("background:#262c34; border-radius:5px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(7, 4, 7, 5)
            cl.setSpacing(1)
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#6b7585; font-size:9px; font-weight:normal;")
            val = DLabel("--", base_style=f"font-size:13px; font-weight:bold; color:{value_color};")
            cl.addWidget(lbl); cl.addWidget(val)
            self.metrics_labels[key] = val
            return card

        # 2-column grid: SNR / timing / spatial
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(5)
        pairs = [
            ("snr_wm", "SNR  WM"),  ("snr_gm", "SNR  GM"),
            ("cnr", "CNR"),          ("snr_eff", "SNR Eff. (√min)"),
            ("scan_time", "Scan Time"), ("resolution", "Resolution"),
            ("voxel_size", "Voxel Size"), ("sar", "SAR (W/kg)"),
            ("weighting", "Weighting"), ("matrix_display", "Matrix"),
            ("bw_pixel", "BW / pixel"), ("etl_accel", "ETL / Accel"),
            ("slice_info", "Slice"),  ("field_disp", "Field"),
            ("fw_phase", "Fat-Water"),
        ]
        for i, (key, dn) in enumerate(pairs):
            grid.addWidget(_card(key, dn), i // 2, i % 2)
        self.right_layout.addWidget(grid_w)

        # Artifacts: full width, amber accent
        art_card = _card("artifacts", "Artifacts", value_color="#ffaa44")
        art_card.setStyleSheet("background:#2a2418; border-radius:5px;")
        self.right_layout.addWidget(art_card)

        self._separator(self.right_layout)
        self.compare_metrics_label = DLabel("", base_style="color:#8a93a3; font-size:10px;")
        self.compare_metrics_label.setWordWrap(True)
        self.right_layout.addWidget(self.compare_metrics_label)
        self.right_layout.addStretch(1)

    # ------------------------------------------------------------------ #
    #  Core (unchanged from Tkinter version)
    # ------------------------------------------------------------------ #
    def get_current_params(self) -> dict:
        return {"sequence": self.sequence_type.get(), "field_strength": self.field_strength.get(),
                "TR": self.TR.get(), "TE": self.TE.get(), "TI": self.TI.get(),
                "flip_angle": self.flip_angle.get(), "matrix_size": self.matrix_size.get(), "FOV": self.FOV.get(),
                "trajectory": self.trajectory.get(), "radial_spokes": self.radial_spokes.get(),
                "fov_fraction": self.fov_fraction.get(), "bandwidth": self.bandwidth.get(), "NEX": self.NEX.get(),
                "etl": self.etl.get(), "echo_spacing": self.echo_spacing.get(), "accel_factor": self.accel_factor.get(),
                "accel_method": self.accel_method.get(), "b_value": self.b_value.get(),
                "diff_direction": self.diff_direction.get(), "diff_display": self.diff_display.get(),
                "angio_type": self.angio_type.get(), "angio_mip_slab": self.angio_mip_slab.get(),
                "angio_azimuth": self.angio_azimuth.get(), "angio_elevation": self.angio_elevation.get(),
                "angio_fast": getattr(self, "_mra_rotating", False),
                "fmri_display": self.fmri_display.get(), "fmri_volumes": self.fmri_volumes.get(),
                "fmri_threshold": self.fmri_threshold.get(), "qmri_display": self.qmri_display.get(),
                "epi_esp": self.epi_esp.get(), "epi_b0_hz": self.epi_b0_hz.get(),
                "epi_ghost": self.epi_ghost.get(), "epi_correct_ghost": self.epi_correct_ghost.get(),
                "slice_thickness": self.slice_thickness.get(), "snr_level": self.snr_level.get(),
                "n_slices": self.n_slices.get(), "slice_gap": self.slice_gap.get(),
                "rician_bias_correction": self.rician_bias_correct.get(),
                "pv_sigma": self.pv_sigma.get(),
                "motion_enabled": self.motion_enabled.get(), "motion_amplitude": self.motion_amplitude.get(),
                "motion_type": self.motion_type.get(), "chemical_shift_enabled": self.chemical_shift_enabled.get(),
                "susceptibility_enabled": self.susceptibility_enabled.get(),
                "susceptibility_strength": self.susceptibility_strength.get(),
                "gradient_distort": self.gradient_distort.get(),
                "zipper_enabled": self.zipper_enabled.get(),
                "pf_enabled": self.pf_enabled.get(), "pf_fraction": self.pf_fraction.get(),
                "kspace_filter_enabled": self.kspace_filter_enabled.get(),
                "kspace_filter_window": self.kspace_filter_window.get(),
                "contrast_enabled": self.contrast_enabled.get(),
                "contrast_dose": self.contrast_dose.get(),
                "mt_enabled": self.mt_enabled.get(), "mt_power": self.mt_power.get(),
                "b1_inhom_enabled": self.b1_inhom_enabled.get(),
                "flow_enabled": self.flow_enabled.get(), "flow_velocity": self.flow_velocity.get(),
                "fatsat_enabled": self.fatsat_enabled.get(),
                "acq3d": self.acq3d.get(), "n_partitions": self.n_partitions.get(),
                "kz_pf": 0.75 if self.kz_pf_enabled.get() else None,
                "slab_sharpness": 0.85}

    def set_protocol_a(self) -> None:
        self.compare_params = self.get_current_params()
        self.compare_status.config(text=f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", fg=C_ACCENT)
        self.compare_mode.set(True); self.recalculate()

    def toggle_compare(self) -> None:
        if not self.compare_params:
            self.compare_status.config(text="Set A first!", fg="#ff6b6b"); return
        self.compare_mode.set(not self.compare_mode.get()); self.recalculate()

    def clear_compare(self) -> None:
        self.compare_params = None; self.compare_mode.set(False)
        self.compare_status.config(text="No comparison set", fg="#586273")
        self.compare_metrics_label.config(text=""); self.recalculate()

    def _sync_sim(self) -> None:
        """Copy the active volume + view/geometry state onto the controller."""
        s = self.sim
        s.volume = self.phantom_3d
        s.vessels = self.phantom_3d_vessels
        s.activation = self.activation_3d
        s.real_tof = self.real_tof
        s.texture = self.texture_3d
        s.native_fov = self._get_native_fov()
        s.orientation = self.orientation.get()
        s.slice_idx = self.slice_idx.get()
        s.fov_planning = self.fov_planning.get()
        s.tilt = self.slice_tilt.get()
        s.rot = self.slice_rot.get()
        s.inplane_fov_pct = self.inplane_fov_pct.get()
        s.inplane_off = self.inplane_off.get()

    def _simulate_single_slice(self, params: dict, orient: str, sl_idx: int) -> np.ndarray:
        self._sync_sim()
        return self.sim._simulate_single_slice(params, orient, sl_idx)

    def simulate_with_params(self, params: dict) -> tuple[np.ndarray, dict]:
        self._sync_sim()
        image, metrics = self.sim.simulate(params)
        self._last_kspace = self.sim.last_kspace
        return image, metrics

    # Sequences whose 3D toggle takes effect (mirrors simulator._ACQ3D_SEQUENCES).
    _ACQ3D_SEQUENCES = frozenset({"Spin Echo", "Gradient Echo",
                                  "Inversion Recovery", "Balanced SSFP"})

    def _acquire_or_reformat(self, params: dict) -> "tuple[np.ndarray, dict]":
        """Main-view render. In 3D mode the slab is acquired once; changing only
        the view plane or slice **reformats** the stored recon block (no re-scan).
        A scan-affecting change, or scrolling outside the slab, re-acquires."""
        if not (params.get("acq3d") and params["sequence"] in self._ACQ3D_SEQUENCES):
            return self.simulate_with_params(params)
        key = tuple((k, repr(v)) for k, v in sorted(params.items())
                    if k not in ("acq3d",))          # orient/slice live on self, not params
        orient, sl = self.orientation.get(), self.slice_idx.get()
        if key == self._acq3d_key and self.sim._recon3d is not None:
            self._sync_sim()
            img = self.sim.reslice_3d(orient, sl)
            if img is not None:                      # in-slab reslice / reformat
                return img, self._acq3d_metrics
        img, m = self.simulate_with_params(params)   # acquire (re-centres the slab)
        self._acq3d_key, self._acq3d_metrics = key, m
        return img, m

    # --- Display ---
    _COIL_CODE = {"Uniform (ideal)": "uniform", "Head array (8-ch)": "head8",
                  "Quadrature (2-ch)": "quad", "Surface coil": "surface"}

    # Demo-pathology dropdown labels → rendering.paint_brain_pathology kinds.
    _PATHOLOGY_KIND = {"None": "", "MS plaques": "ms", "Lesion (focal)": "lesion",
                       "Stroke (infarct)": "stroke", "Hemorrhage": "hemorrhage",
                       "Tumor (mass)": "tumor", "Abscess (rim + core)": "abscess"}

    def _apply_coil_shading(self, image: np.ndarray) -> np.ndarray:
        """Modulate the image by the selected receive coil's spatial sensitivity
        (the shared coil.py envelope). Uniform → no-op."""
        import coil
        code = self._COIL_CODE.get(self.receive_coil.get(), "uniform")
        if code == "uniform" or getattr(image, "ndim", 0) != 2:
            return image
        env = coil.receive_coil_envelope(image.shape, code)
        if env is None:
            return image
        return (np.asarray(image, dtype=float) * env).astype(image.dtype)

    def _add_map_colorbar(self, ax: Any, cmap: str, unit: str,
                          vlo: float, vhi: float) -> None:
        """Overlaid inset colorbar for a quantitative map (doesn't resize the image
        axes, so window/level and the layout are unaffected)."""
        cax = ax.inset_axes((0.905, 0.07, 0.03, 0.42))
        cax.imshow(np.linspace(1.0, 0.0, 256).reshape(-1, 1), cmap=cmap,
                   aspect="auto", extent=(0.0, 1.0, vlo, vhi), vmin=0.0, vmax=1.0)
        cax.set_xticks([])
        cax.set_yticks([vlo, (vlo + vhi) / 2.0, vhi])
        cax.yaxis.set_ticks_position("right")
        cax.tick_params(axis="y", colors="#e6e9ee", labelsize=6, length=2, pad=1)
        for _s in cax.spines.values():
            _s.set_edgecolor("#3a424d")
        cax.set_title(unit, color="#e6e9ee", fontsize=6, pad=2)
        self._map_cbar = cax

    def recalculate(self, *args: object) -> None:
        # Stale recon panel axes are gone once the figure rebuilds; the recon view
        # repopulates these. The active measurement drag also ends on any re-render.
        self._recon_measure_targets = {}
        self._measure_drag = None
        # Drop a previous map colorbar inset (axes/figure get cleared below).
        prev_cbar = getattr(self, "_map_cbar", None)
        if prev_cbar is not None:
            try:
                prev_cbar.remove()
            except Exception:
                pass
            self._map_cbar = None
        current_params = self.get_current_params()

        # FOV planning takes over the main view with the prescribed slice group
        if self.fov_planning.get() and not self.compare_mode.get():
            self._display_prescription(current_params)
            self._draw_scout(current_params)
            self.update_metrics(current_params,
                                self.simulate_with_params(current_params)[1])
            return

        # Reconstruction view takes over the main view with MPR / MIP / oblique
        # reformats of the acquired 3-D slab.
        if (self.recon_enabled.get() and current_params.get("acq3d")
                and current_params["sequence"] in self._ACQ3D_SEQUENCES
                and not self.compare_mode.get()):
            self._display_reconstruction(current_params)
            return

        if self.multi_slice.get() and not self.compare_mode.get():
            self._display_multi_slice(current_params)
            return

        # The second panel holds the A/B comparison, k-space, or the signal curve.
        # When none of those are shown, drop it and give the image the full width.
        want_second = (self.compare_mode.get() or self.show_kspace.get()
                       or self.show_signal_curve.get())
        self._ensure_layout(2 if want_second else 1)

        image_b, metrics_b = self._acquire_or_reformat(current_params)
        image_b = self._apply_coil_shading(image_b)   # receive-coil display shading
        for ax in self.axes:
            ax.clear()

        cmap = self.display_cmap.get()
        _asp = self._get_voxel_aspect(self.orientation.get())
        if self.compare_mode.get() and self.compare_params:
            image_a, metrics_a = self.simulate_with_params(self.compare_params)
            image_a = self._apply_coil_shading(image_a)
            # Both panels share the live window/level (drag either to re-window both),
            # so the contrast comparison is fair.
            self._compare_images = (image_a, image_b)
            va0, va1 = self._wl_bounds(image_a); vb0, vb1 = self._wl_bounds(image_b)
            self.axes[0].imshow(image_a, cmap=cmap, origin="lower", aspect=_asp, vmin=va0, vmax=va1)
            self.axes[0].set_title(f"A · {self.compare_params['sequence']}  TR {self.compare_params['TR']:.0f}", color=C_ACCENT_HI, fontsize=10, fontweight="bold"); self._frame_image_axes(self.axes[0])
            self.axes[1].imshow(image_b, cmap=cmap, origin="lower", aspect=_asp, vmin=vb0, vmax=vb1)
            self.axes[1].set_title(f"B · {current_params['sequence']}  TR {current_params['TR']:.0f}", color=C_ACCENT_HI, fontsize=10, fontweight="bold"); self._frame_image_axes(self.axes[1])
            self.update_compare_metrics(metrics_a, metrics_b)
            self.current_image = None
        else:
            self.current_image = image_b
            orient = self.orientation.get(); sl_idx = self.slice_idx.get()
            if current_params["sequence"] == "Quantitative (qMRI)":
                _qd = current_params["qmri_display"]
                _unit = "" if _qd == "Synthetic SE" else "  [pixel value = ms]"
                self.current_title = f"{_qd}{_unit} | {orient.capitalize()} #{sl_idx}"
            else:
                self.current_title = f"{current_params['sequence']} | TR={current_params['TR']:.0f} TE={current_params['TE']:.0f} | {orient.capitalize()} #{sl_idx}"
            max_val = np.max(image_b) if np.max(image_b) > 0 else 1
            center = self.window_level * max_val; width = self.window_width * max_val
            vlo, vhi = center - width / 2, center + width / 2
            # Quantitative maps get a perceptual, colorblind-safe colormap + a
            # calibrated colorbar; the user's colormap pick still applies to
            # weighted images (and overrides if they picked a non-default one).
            import rendering
            mapspec = rendering.quantitative_map_spec(
                current_params["sequence"], current_params.get("qmri_display", ""),
                current_params.get("diff_display", ""))
            img_cmap = mapspec[0] if (mapspec and cmap == "gray") else cmap
            self.axes[0].imshow(image_b, cmap=img_cmap, origin="lower",
                                vmin=vlo, vmax=vhi, aspect=_asp)
            if mapspec is not None and not self.show_tissue_overlay.get():
                self._add_map_colorbar(self.axes[0], img_cmap, mapspec[1], vlo, vhi)
            if self.show_tissue_overlay.get():
                ph_slice = self._get_current_phantom_slice(orient, sl_idx, current_params)
                self.axes[0].imshow(
                    self._make_tissue_overlay(ph_slice, image_b.shape),
                    origin="lower", aspect="auto")
            self._frame_image_axes(self.axes[0])
            self._annotate_image(self.axes[0], current_params, orient, sl_idx, width, center)
            # The second panel (when present): k-space takes priority, else the
            # signal curve. With both off it was dropped above (image spans full).
            if self.show_kspace.get():
                ks = self._last_kspace if self._last_kspace is not None else None
                if ks is None:
                    from kspace import image_to_kspace
                    ks = image_to_kspace(image_b)
                self.axes[1].imshow(get_kspace_display(ks), cmap="hot", origin="lower")
                self.axes[1].set_title("k-Space (acquired)", color=C_TEXT_DIM, fontsize=10); self.axes[1].set_axis_off()
            elif self.show_signal_curve.get():
                self._plot_curves(current_params)
            self.compare_metrics_label.config(text="")

        # PSD display
        if self.show_psd.get():
            self.psd_canvas.setVisible(True)
            draw_psd(self.psd_fig,
                     current_params["sequence"],
                     current_params["TR"],
                     current_params["TE"],
                     TI=current_params["TI"],
                     flip_angle=current_params["flip_angle"],
                     etl=current_params["etl"],
                     echo_spacing=current_params["echo_spacing"],
                     b_value=current_params["b_value"])
            self.psd_canvas.draw()
        else:
            self.psd_canvas.setVisible(False)

        self.canvas.draw()
        self.update_metrics(current_params, metrics_b)

    def _display_reconstruction(self, params: dict) -> None:
        """Reconstruction view: reformat / project the acquired 3-D slab. MPR shows
        the three orthogonal reformats at a crosshair; MIP / oblique show a single
        projection or tilted reformat. Reuses the shared ``reconstruction`` module."""
        import reconstruction as rc
        _, metrics = self._acquire_or_reformat(params)   # ensure the slab is built
        block = self.sim._recon3d
        cmap = self.display_cmap.get()
        self.fig.clear()
        if block is None:
            ax = self.fig.subplots(1, 1); ax.set_facecolor(C_CANVAS); ax.set_axis_off()
            ax.text(0.5, 0.5, "Enable a 3-D slab acquisition to reconstruct",
                    color=C_TEXT_DIM, ha="center", va="center", transform=ax.transAxes)
            self.canvas.draw(); self.update_metrics(params, metrics); return

        nz, ny, nx = block.shape
        cz = int(round(self.recon_z.get() / 100 * (nz - 1)))
        cy = int(round(self.recon_y.get() / 100 * (ny - 1)))
        cx = int(round(self.recon_x.get() / 100 * (nx - 1)))

        mm_per_px = self.sim.native_fov / max(1, nx)   # isotropic recon voxel

        def _show(ax: Any, arr: np.ndarray, title: str,
                  cross: "tuple[float, float] | None" = None, bar: bool = False) -> None:
            a = np.asarray(arr, dtype=float)
            fin = a[np.isfinite(a)]
            hi = float(np.percentile(fin, 99)) if fin.size else 1.0
            ax.set_facecolor(C_CANVAS)
            # aspect="equal" keeps the reformat's true proportions (a thin slab
            # reformats to a thin strip) instead of stretching it to fill the panel;
            # click-navigation uses data coords, so it is unaffected.
            ax.imshow(a, cmap=cmap, origin="lower", aspect="equal",
                      vmin=0.0, vmax=hi if hi > 0 else 1.0)
            if cross is not None:
                H, W = a.shape
                ax.axvline(cross[0] * W, color="#ffdd44", lw=0.6, alpha=0.6)
                ax.axhline(cross[1] * H, color="#ffdd44", lw=0.6, alpha=0.6)
            if bar and mm_per_px > 0:
                from web_adapter import WebHost
                H, W = a.shape
                bar_mm = WebHost._scale_bar_mm(W, mm_per_px)
                if bar_mm > 0:
                    bar_px = bar_mm / mm_per_px
                    x0, y0 = 0.04 * W, 0.05 * H
                    ax.plot([x0, x0 + bar_px], [y0, y0], color="#ffdd44", lw=2.0, solid_capstyle="butt")
                    lbl = f"{bar_mm / 10:.0f} cm" if bar_mm >= 10 else f"{bar_mm:.0f} mm"
                    ax.text(x0 + bar_px / 2, y0 + 0.02 * H, lbl, color="#ffdd44",
                            fontsize=7, ha="center", va="bottom")
            ax.set_title(title, color=C_TEXT_DIM, fontsize=9)
            ax.set_axis_off()

        # No single current_image in recon view — keep window/level inert here.
        self.current_image = None
        mode = self.recon_mode.get()
        if mode.startswith("MPR"):
            # 2×2 quad (PACS-style): the three orthogonal reformats + a 3-D MIP
            # overview of the whole slab in the 4th cell.
            axs = self.fig.subplots(2, 2).ravel()
            self.fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.02,
                                     wspace=0.05, hspace=0.12)
            tri = rc.mpr_triplanar(block, (cz, cy, cx))
            cross = {"axial": (cx / nx, cy / ny), "coronal": (cx / nx, cz / nz),
                     "sagittal": (cy / ny, cz / nz)}
            names = ("axial", "coronal", "sagittal")
            for ax, name in zip(axs[:3], names, strict=True):
                _show(ax, tri[name], name.capitalize(), cross[name])
                self._recon_measure_targets[ax] = (np.asarray(tri[name], dtype=float), mm_per_px)
            ov = rc.rotating_mip(block, 35.0, 20.0)
            _show(axs[3], ov, "3D MIP")   # reference, not a cross panel
            self._recon_measure_targets[axs[3]] = (np.asarray(ov, dtype=float), mm_per_px)
            # Remember the cross-panel axes + block dims so a click navigates the crosshair.
            self._recon_mpr_axes = dict(zip(names, axs[:3], strict=True))
            self._recon_block_shape = (nz, ny, nx)
        else:
            self._recon_mpr_axes = {}
            ax = self.fig.subplots(1, 1)
            self.fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.02)
            if mode == "Thick-slab MIP":
                plane = self.recon_mip_plane.get()
                axn = block.shape[rc.THROUGH_AXIS[plane]]
                c = int(round(self.recon_mip_center.get() / 100 * (axn - 1)))
                proj = {"MIP (brightest)": "mip", "MinIP (darkest)": "minip",
                        "AIP (average)": "aip"}.get(self.recon_mip_mode.get(), "mip")
                arr = rc.thick_slab_projection(block, plane, c, int(self.recon_mip_thick.get()), proj)
                _show(ax, arr, f"{proj.upper()} · {plane} · {int(self.recon_mip_thick.get())}p slab", bar=True)
            elif mode == "Rotating MIP":
                az, el = self.recon_azimuth.get(), self.recon_elevation.get()
                arr = rc.rotating_mip(block, az, el)
                _show(ax, arr, f"Rotating MIP · az {az:.0f}° el {el:.0f}°", bar=True)
            else:  # Oblique MPR
                tilt, rot = self.recon_tilt.get(), self.recon_rot.get()
                arr = rc.oblique_mpr(block, (cz, cy, cx), tilt, rot)
                _show(ax, arr, f"Oblique MPR · tilt {tilt:.0f}° rot {rot:.0f}°", bar=True)
            self._recon_measure_targets[ax] = (np.asarray(arr, dtype=float), mm_per_px)

        self.canvas.draw()
        self.update_metrics(params, metrics)

    def _on_acq3d_toggle(self, *_: object) -> None:
        """When the 3-D slab is enabled, default to covering the whole anatomy (the
        engine clamps the partition count to the through-axis extent)."""
        if self.acq3d.get():
            self.n_partitions.set(int(min(256, self.get_max_slice_idx() + 1)))

    def _on_recon_press(self, event: object) -> None:
        """Click an MPR panel in the reconstruction view to move the crosshair (the
        other two planes follow). Uses matplotlib data coords; the sagittal panel is
        L–R flipped (see _display_reconstruction)."""
        axes = self._recon_mpr_axes
        if not (axes and self.recon_enabled.get() and self.recon_mode.get().startswith("MPR")):
            return
        ev_ax = getattr(event, "inaxes", None)
        xd = getattr(event, "xdata", None); yd = getattr(event, "ydata", None)
        if ev_ax is None or xd is None or yd is None:
            return
        nz, ny, nx = self._recon_block_shape

        def pct(v: float, n: int) -> int:
            return int(np.clip(round(v / max(1, n - 1) * 100.0), 0, 100))

        if ev_ax is axes.get("axial"):
            self.recon_x.set(pct(xd, nx)); self.recon_y.set(pct(yd, ny))
        elif ev_ax is axes.get("coronal"):
            self.recon_x.set(pct(xd, nx)); self.recon_z.set(pct(yd, nz))
        elif ev_ax is axes.get("sagittal"):
            self.recon_y.set(pct((ny - 1) - xd, ny)); self.recon_z.set(pct(yd, nz))
        else:
            return
        self.recalculate()

    def _display_multi_slice(self, params: dict) -> None:
        """Display 3x3 grid of adjacent slices."""
        self.fig.clear()
        axes = self.fig.subplots(3, 3)
        self.fig.subplots_adjust(wspace=0.05, hspace=0.15)

        orient = self.orientation.get()
        center_sl = self.slice_idx.get()
        max_sl = self.get_max_slice_idx()
        spacing = max(1, int(self.slice_thickness.get()))

        cmap = self.display_cmap.get()
        _asp = self._get_voxel_aspect(orient)
        for idx, ax in enumerate(axes.flat):
            ax.set_facecolor(C_CANVAS)
            sl = center_sl + (idx - 4) * spacing
            if 0 <= sl <= max_sl:
                image = self._simulate_single_slice(params, orient, sl)
                ax.imshow(image, cmap=cmap, origin="lower", aspect=_asp)
                ax.set_title(f"#{sl}", color="white", fontsize=8)
            ax.set_axis_off()

        self.canvas.draw()
        _, metrics = self.simulate_with_params(params)
        self.update_metrics(params, metrics)
        self.current_image = None

    # ------------------------------------------------------------------ #
    #  FOV planning: prescribed-group display + interactive scout
    # ------------------------------------------------------------------ #
    def _display_prescription(self, params: dict) -> None:
        """Show the prescribed slice group (montage) acquired with the boxed FOV."""
        import scan_geometry as sg
        self.fig.clear()
        orient = self.orientation.get()
        idxs = sg.prescribed_indices(orient, self.phantom_3d.shape,
                                     self.slice_idx.get(), self.n_slices.get(),
                                     self.slice_thickness.get(), self.slice_gap.get())
        n = len(idxs)
        cols = 1 if n == 1 else int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
        axes = self.fig.subplots(rows, cols, squeeze=False)
        self.fig.subplots_adjust(wspace=0.05, hspace=0.18)
        _asp = self._get_voxel_aspect(orient)
        for k, ax in enumerate(axes.flat):
            ax.set_facecolor(C_CANVAS); ax.set_axis_off()
            if k < n:
                img = self._simulate_single_slice(params, orient, idxs[k])
                ax.imshow(img, cmap=self.display_cmap.get(), origin="lower", aspect=_asp)
                ax.set_title(f"#{idxs[k]}", color="white", fontsize=8)
        self.fig.suptitle(f"{params['sequence']}  |  {n} slice{'s' if n != 1 else ''}  "
                          f"|  FOV {self.inplane_fov_pct.get()}%",
                          color="white", fontsize=10)
        self.canvas.draw()
        self.current_image = self._simulate_single_slice(params, orient, self.slice_idx.get()) if n == 1 else None

    # ------------------------------------------------------------------ #
    #  UI event helpers
    # ------------------------------------------------------------------ #
    def _refresh_slice_range(self) -> None:
        """Match the Slice slider's range to the current volume/orientation."""
        mx = self.get_max_slice_idx()
        s = self._slice_slider
        s.blockSignals(True)
        s.setMaximum(mx)
        if self.slice_idx.get() > mx:
            self.slice_idx.set(mx)
        s.setValue(int(self.slice_idx.get()))
        s.blockSignals(False)

    def _on_orient_radio(self, checked: bool, orient: str) -> None:
        if checked:
            self.orientation.set(orient)
            self.on_orientation_change()

    def _set_orientation(self, orient: str) -> None:
        """Programmatically switch the acquisition plane and sync both pickers
        (planning radios + series thumbnails) plus the slice range, without
        firing the per-widget callbacks. The caller is expected to recalculate."""
        if orient not in ("axial", "sagittal", "coronal"):
            return
        self.orientation.set(orient)
        rb = getattr(self, "_orient_radios", {}).get(orient)
        if rb is not None:
            rb.blockSignals(True); rb.setChecked(True); rb.blockSignals(False)
        for o, b in getattr(self, "_series_thumbs", {}).items():
            b.blockSignals(True); b.setChecked(o == orient); b.blockSignals(False)
        self.slice_idx.set(self.get_max_slice_idx() // 2)
        self._refresh_slice_range()

    def on_preset_change(self) -> None:
        name = self.preset_name.get()
        if name in ["(Custom)", ""]:
            self.desc_label.config(text=""); return
        p = get_preset(name)
        if not p: return
        region = get_preset_region(name)
        if region and region != self.region.get():
            self.region.set(region); self.on_region_change()
        # Switch to the plane this study is conventionally acquired in (on_region_change
        # forces axial for a new region, so apply the preset's plane afterwards).
        self._set_orientation(get_preset_plane(name))
        self.sequence_type.set(p["sequence"]); self.TR.set(float(p["TR"])); self.TE.set(float(p["TE"]))
        self.TI.set(float(p.get("TI", 150))); self.flip_angle.set(float(p.get("flip_angle", 90)))
        self.matrix_size.set(int(p.get("matrix_size", 256))); self.FOV.set(float(p.get("FOV", 240)))
        self.bandwidth.set(float(p.get("bandwidth", 125))); self.NEX.set(int(p.get("NEX", 1)))
        for k, v in [("b_value", self.b_value), ("diff_direction", self.diff_direction), ("diff_display", self.diff_display),
                     ("angio_type", self.angio_type), ("angio_mip_slab", self.angio_mip_slab),
                     ("fmri_display", self.fmri_display), ("fmri_volumes", self.fmri_volumes), ("fmri_threshold", self.fmri_threshold)]:
            if k in p: v.set(p[k])
        # Gadolinium: post-contrast presets enable it; reset to off otherwise so
        # switching back to a non-contrast preset clears it.
        self.contrast_enabled.set(bool(p.get("contrast_enabled", False)))
        if "contrast_dose" in p:
            self.contrast_dose.set(int(p["contrast_dose"]))
        # Spectral fat-sat and k-space trajectory: apply from the preset and reset
        # to the defaults otherwise, so switching presets clears them.
        self.fatsat_enabled.set(bool(p.get("fatsat_enabled", False)))
        self.trajectory.set(p.get("trajectory", "Cartesian"))
        if "radial_spokes" in p:
            self.radial_spokes.set(int(p["radial_spokes"]))
        # 3-D slab acquisition: enable for presets that prescribe it (3D MPRAGE,
        # CISS, etc.) and reset to off otherwise, so switching away from a 3-D
        # preset clears it. The engine only honours 3-D for SE/GRE/IR/bSSFP.
        self.acq3d.set(bool(p.get("acq3d", False)))
        if "n_partitions" in p:
            self.n_partitions.set(int(p["n_partitions"]))
        self.desc_label.config(text=p.get("description", ""))
        self.on_sequence_change()
        # on_sequence_change resets TR/TE/FA/etl for some sequences; re-apply the
        # preset's values so the preset stays authoritative.
        self.TR.set(float(p["TR"])); self.TE.set(float(p["TE"]))
        self.flip_angle.set(float(p.get("flip_angle", 90)))
        if "etl" in p: self.etl.set(int(p["etl"]))
        if "echo_spacing" in p: self.echo_spacing.set(float(p["echo_spacing"]))
        self.recalculate()

    def schedule_recalculate(self, *args: object) -> None:
        self._recalc_timer.start(150)

    def on_orientation_change(self) -> None:
        dims = {"axial": self.phantom_3d.shape[0], "sagittal": self.phantom_3d.shape[2], "coronal": self.phantom_3d.shape[1]}
        self.slice_idx.set(dims[self.orientation.get()] // 2)
        self._refresh_slice_range()
        self.recalculate()

    def on_sequence_change(self) -> None:
        seq = self.sequence_type.get()
        for frame in (self.ti_frame, self.fa_frame, self.fse_frame,
                      self.diff_frame, self.angio_frame, self.fmri_frame,
                      self.qmri_frame, self.epi_frame):
            frame.setVisible(False)
        if seq == "Inversion Recovery":
            self.ti_frame.setVisible(True)
        elif seq == "Gradient Echo":
            self.fa_frame.setVisible(True)
        elif seq == "Balanced SSFP":
            # Short TR, TE≈TR/2, moderate flip — the regime where bSSFP works.
            self.fa_frame.setVisible(True); self.TR.set(5.0); self.TE.set(2.5); self.flip_angle.set(45.0)
        elif seq == "FSE / TSE":
            self.fse_frame.setVisible(True); self.TR.set(4000.0); self.TE.set(80.0); self.etl.set(16)
        elif seq == "Diffusion (DWI)":
            self.diff_frame.setVisible(True)
        elif seq == "MR Angiography":
            self.angio_frame.setVisible(True); self.fa_frame.setVisible(True)
        elif seq == "fMRI (BOLD)":
            self.fmri_frame.setVisible(True)
        elif seq == "Quantitative (qMRI)":
            self.qmri_frame.setVisible(True)
        elif seq == "Echo Planar (EPI)":
            self.epi_frame.setVisible(True); self.fa_frame.setVisible(True)
        self.recalculate()

    def _get_native_fov(self) -> float:
        """Physical FOV (mm) represented by the current phantom's in-plane extent."""
        _map = {"Brain": 220.0, "Abdomen": 380.0, "Spine": 320.0, "Pelvis": 380.0,
                "Knee": 150.0, "Torso": 400.0}
        name = self.region.get()
        for key, fov in _map.items():
            if key in name:
                return fov
        # Loaded NIfTI: estimate from voxel count at ~1.5 mm/voxel
        return float(max(self.phantom_3d.shape[1], self.phantom_3d.shape[2]) * 1.5)

    def _get_voxel_aspect(self, orient: str) -> float:
        """imshow `aspect` (row_mm / col_mm) for true-scale display.

        All phantoms now have isotropic voxels — BrainWeb at 1 mm, the body
        atlases resampled to 1.5 mm isotropic in nifti_region.resample_labels_isotropic
        — so every orientation renders at 1:1 without stretching. (The old body
        atlases were thick-sliced and needed a ~5.9x row stretch on reformats;
        that no longer applies and would squish the image.)
        """
        return 1.0

    def _get_current_phantom_slice(self, orient: str, sl_idx: int, params: dict) -> np.ndarray:
        """Phantom label slice with FOV crop / oblique sampling (via controller)."""
        self._sync_sim()
        return self.sim._get_phantom_slice(orient, sl_idx, params)

    def get_max_slice_idx(self) -> int:
        dims = {"axial": self.phantom_3d.shape[0], "sagittal": self.phantom_3d.shape[2], "coronal": self.phantom_3d.shape[1]}
        return dims[self.orientation.get()] - 1

    # ------------------------------------------------------------------ #
    #  Export / Import
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self.show()
        # Default the controls/measurements split once real heights are known:
        # give Measurements ~300px and the parameter cards the rest.
        h = max(self.right_split.height(), 600)
        self.right_split.setSizes([h - 300, 300])
        # Offer the guided tour on the first launch (once the window is laid out).
        QTimer.singleShot(700, self._maybe_offer_tour)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)
    win = MRISimulator()
    win.run()
    sys.exit(app.exec())
