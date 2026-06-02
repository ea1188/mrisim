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

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QComboBox, QCheckBox, QRadioButton, QButtonGroup, QFrame, QScrollArea,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog, QSplitter,
    QDialog, QListWidget, QListWidgetItem, QProgressDialog,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from psd import draw_psd

from signal_engine import spin_echo_signal, gradient_echo_signal
from phantom3d import simulate_slice
import tissue_db
import rendering
from kspace import get_kspace_display
from brainweb_loader import get_brainweb_or_synthetic
from phantom3d_extended import (add_vessels_3d, add_activation_3d,
                                get_diffusion_properties_3d, load_real_tof_mra)
from presets import get_preset_names, get_preset, get_preset_region
from fse import compute_fse_echo_train
from simulator import Simulator, _B0_MAP, _PF_MAP

# SAR scaling factor per sequence type (relative to SE reference) — used by the
# metrics display's max-safe-FA hint (the simulation SAR lives in simulator.py).
_SAR_SEQ_FACTORS: dict[str, float] = {
    "Spin Echo": 1.5, "FSE / TSE": 1.5, "Gradient Echo": 0.5,
    "Inversion Recovery": 2.0, "Diffusion (DWI)": 1.5,
    "MR Angiography": 0.5, "fMRI (BOLD)": 0.5, "Echo Planar (EPI)": 0.5,
}


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


def _fmt(val: object) -> str:
    """Match the Tkinter slider label formatting."""
    if isinstance(val, float):
        return f"{val:.0f}"
    return str(val)


# --------------------------------------------------------------------------- #
#  Style
# --------------------------------------------------------------------------- #
GLOBAL_QSS = """
QMainWindow { background-color: #15181c; }
QLabel { color: #dfe3e8; font-family: Helvetica, Arial, sans-serif; }
QScrollArea { background-color: #1f242b; border: none; }
QWidget#controls-host { background: #1f242b; }
QSlider::groove:horizontal { height: 5px; background: #2a313a; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #1bb8ad; border-radius: 3px; }
QSlider::handle:horizontal { background: #1bb8ad; width: 16px; margin: -6px 0; border-radius: 8px; border: 2px solid #191d22; }
QSlider::handle:horizontal:hover { background: #2ad0c4; }
QComboBox { background: #262c34; border: 1px solid #3a424d; padding: 3px 6px; border-radius: 4px; color: #dfe3e8; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #1f242b; color: #dfe3e8; selection-background-color: #1bb8ad; }
QCheckBox, QRadioButton { color: #c4cad2; spacing: 6px; }
QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #3a424d; background: #262c34; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #1bb8ad; border-color: #1bb8ad; }
QPushButton { background: #2a313a; color: #dfe3e8; border: none; padding: 5px 10px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background: #3a424d; }
QPushButton:pressed { background: #313842; }
QPushButton#section-toggle { background: #191d22; color: #4fd6cb; font-size: 11px; font-weight: bold;
    text-align: left; border: none; border-left: 3px solid #1bb8ad;
    padding: 5px 10px; margin-top: 3px; border-radius: 0; }
QPushButton#section-toggle:hover { background: #262c34; color: #7fe2da; }
QPushButton#section-toggle:checked { border-left-color: #2ad0c4; }
QScrollBar:vertical { background: #191d22; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #3a424d; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QFrame#header-bar { background: #12161a; border-bottom: 2px solid #1bb8ad; }
QLabel#app-logo { background: #1bb8ad; color: #0f1216; font-weight: bold; font-size: 14px;
    border-radius: 5px; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }
QLabel#app-title { color: #f0f3f6; font-size: 15px; font-weight: bold; }
QLabel#app-sub { color: #6b7585; font-size: 9px; }
QFrame#chip { background: #1b2026; border: 1px solid #2a313a; border-radius: 5px; }
QLabel#chip-cap { color: #6b7585; font-size: 8px; font-weight: bold; }
QLabel#chip-val { color: #2ad0c4; font-size: 12px; font-weight: bold; }
QFrame#series-strip { background: #12161a; border-top: 1px solid #2a313a; }
QLabel#strip-cap { color: #6b7585; font-size: 9px; font-weight: bold; }
QPushButton#thumb { background: #1b2026; color: #9aa4b2; border: 1px solid #2a313a;
    border-radius: 5px; font-size: 10px; font-weight: bold; text-align: bottom; padding: 2px; }
QPushButton#thumb:hover { border-color: #3a424d; color: #c4cad2; }
QPushButton#thumb:checked { border: 2px solid #1bb8ad; color: #2ad0c4; background: #1a2329; }
QLabel#thumb-cap { color: #9aa4b2; font-size: 9px; font-weight: bold; }
"""


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
        self._body.setStyleSheet("background:#1f242b; border-left:3px solid #313842; margin-left:0;")
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

    @property
    def inner(self) -> QVBoxLayout:
        return self._inner


class MRISimulator(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        from version import __version__
        self.setWindowTitle(f"MRI Simulation Platform  v{__version__}")
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
        self.multi_slice = Var(False)
        self.show_psd = Var(False)

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
        self.center_panel.setStyleSheet("background:#0f1216;")
        self.center_layout = QHBoxLayout(self.center_panel)
        self.center_layout.setContentsMargins(4, 4, 4, 4)
        self.center_layout.setSpacing(4)

        # Right dock — scrollable parameter cards stacked above the metrics panel
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setStyleSheet("QScrollArea { background:#1f242b; border:none; }")
        self.controls_host = QWidget()
        self.controls_host.setObjectName("controls-host")
        self.controls_host.setStyleSheet("background:#1f242b;")
        self.controls_layout = QVBoxLayout(self.controls_host)
        self.controls_layout.setContentsMargins(6, 8, 6, 6)
        self.controls_layout.setSpacing(0)
        self.left_scroll.setWidget(self.controls_host)

        self.right_panel = QWidget()
        self.right_panel.setStyleSheet("background:#1f242b;")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(8, 6, 8, 8)
        self.right_layout.setSpacing(2)

        # The Measurements panel lives in its own scroll area so the splitter can
        # shrink it (its content scrolls) without its size hint blocking the drag.
        self.measurements_scroll = QScrollArea()
        self.measurements_scroll.setWidgetResizable(True)
        self.measurements_scroll.setStyleSheet("QScrollArea { background:#1f242b; border:none; }")
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
            "QSplitter#right-split::handle { background:#2c333c; margin:1px 8px; "
            "border-radius:2px; } "
            "QSplitter#right-split::handle:hover { background:#1bb8ad; }")
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
        h = QHBoxLayout(bar); h.setContentsMargins(12, 6, 14, 6); h.setSpacing(10)

        logo = QLabel("MR"); logo.setObjectName("app-logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(logo)

        tbox = QVBoxLayout(); tbox.setSpacing(0); tbox.setContentsMargins(0, 0, 0, 0)
        title = QLabel("MRI Simulation Platform"); title.setObjectName("app-title")
        sub = QLabel("Educational MR Scanner Console"); sub.setObjectName("app-sub")
        tbox.addWidget(title); tbox.addWidget(sub)
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
        self.scout_fig = Figure(figsize=(3.5, 10), facecolor="#0f1216")
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
            ax.set_facecolor("#0f1216")
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
        self.fig = Figure(figsize=(10, 5), facecolor="#0f1216")
        self.axes = self.fig.subplots(1, 2)
        self.fig.subplots_adjust(wspace=0.25)
        for ax in self.axes:
            ax.set_facecolor("#0f1216")
        self.canvas = FigureCanvas(self.fig)
        self.center_layout.addWidget(self.canvas, stretch=3)

        # PSD figure (conditionally shown)
        self.psd_fig = Figure(figsize=(4, 5), facecolor="#0f1216")
        self.psd_canvas = FigureCanvas(self.psd_fig)
        self.psd_canvas.setVisible(False)
        self.center_layout.addWidget(self.psd_canvas, stretch=2)

        # Window/level interaction via matplotlib's backend-agnostic events
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        # Workstation interactions: wheel = scroll slices, keys = navigate/toggle
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("key_press_event", self._on_key)
        self.canvas.mpl_connect("axes_leave_event", lambda e: self._set_status_default())
        # Allow the canvas to receive keyboard focus for arrow-key navigation
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Status bar for the live cursor readout
        self.statusBar().setStyleSheet("color:#9aa4b2; background:#0f1216; border-top:1px solid #313842;")  # type: ignore[union-attr]
        self._set_status_default()

    def _ensure_1x2_layout(self) -> None:
        """Restore the normal 1x2 subplot layout if the figure has a different configuration."""
        if len(self.fig.axes) != 2:
            self.fig.clear()
            self.axes = self.fig.subplots(1, 2)
            self.fig.subplots_adjust(wspace=0.25)
            for ax in self.axes:
                ax.set_facecolor("#0f1216")

    # --- Window/level (matplotlib event handlers) ---
    def _on_press(self, event: object) -> None:
        # Double-click left = reset
        if event.button == 1 and getattr(event, "dblclick", False):  # type: ignore[attr-defined]
            self.window_width = 1.0
            self.window_level = 0.5
            if self.current_image is not None:
                self.apply_window_level()
            return
        ctrl = False
        try:
            if event.guiEvent is not None:  # type: ignore[attr-defined]
                ctrl = bool(event.guiEvent.modifiers() & Qt.KeyboardModifier.ControlModifier)  # type: ignore[attr-defined]
        except Exception:
            ctrl = False
        # Plain left-drag over the MRA MIP spins the angiogram (azimuth/elevation).
        if (event.button == 1 and not ctrl  # type: ignore[attr-defined]
                and self.sequence_type.get() == "MR Angiography"
                and event.x is not None):  # type: ignore[attr-defined]
            self._mra_dragging = True
            self._mra_rotating = True          # request the fast (downsampled) MIP
            self._mra_start_x = event.x        # type: ignore[attr-defined]
            self._mra_start_y = event.y        # type: ignore[attr-defined]
            return
        # Middle / right drag, or Ctrl+left drag, adjusts W/L
        if event.button in (2, 3) or (event.button == 1 and ctrl):  # type: ignore[attr-defined]
            self.wl_dragging = True
            self.wl_start_x = event.x  # type: ignore[attr-defined]
            self.wl_start_y = event.y  # type: ignore[attr-defined]

    def _on_motion(self, event: object) -> None:
        # MRA rotate: horizontal drag = azimuth, vertical drag = elevation.
        if getattr(self, "_mra_dragging", False):
            if event.x is None or event.y is None:  # type: ignore[attr-defined]
                return
            daz = (event.x - self._mra_start_x) * 0.5    # type: ignore[attr-defined]
            dele = (event.y - self._mra_start_y) * 0.4   # type: ignore[attr-defined]  # mpl y grows up
            self.angio_azimuth.set(int(round(self.angio_azimuth.get() + daz)) % 360)
            self.angio_elevation.set(int(np.clip(self.angio_elevation.get() + dele, -60, 60)))
            self._mra_start_x = event.x  # type: ignore[attr-defined]
            self._mra_start_y = event.y  # type: ignore[attr-defined]
            self.recalculate()
            return
        # Live cursor readout (only over the main image axis) when not dragging
        if not self.wl_dragging:
            self._update_readout(event)
            return
        if self.current_image is None:
            return
        if event.x is None or event.y is None:  # type: ignore[attr-defined]
            return
        self.window_width += (event.x - self.wl_start_x) * 0.005  # type: ignore[attr-defined]
        # matplotlib's y grows upward (opposite of Tk), so '+=' preserves drag direction
        self.window_level += (event.y - self.wl_start_y) * 0.003  # type: ignore[attr-defined]
        self.window_width = np.clip(self.window_width, 0.05, 3.0)
        self.window_level = np.clip(self.window_level, 0.0, 1.0)
        self.wl_start_x = event.x  # type: ignore[attr-defined]
        self.wl_start_y = event.y  # type: ignore[attr-defined]
        self.apply_window_level()

    def _on_release(self, event: object) -> None:
        self.wl_dragging = False
        if getattr(self, "_mra_dragging", False):
            self._mra_dragging = False
            self._mra_rotating = False   # back to full-resolution MIP
            self.recalculate()

    # --- Workstation navigation -------------------------------------------- #
    def _change_slice(self, delta: int) -> None:
        """Step the current slice by +/- delta, clamped to the volume bounds."""
        max_sl = self.get_max_slice_idx()
        new_idx = int(np.clip(self.slice_idx.get() + delta, 0, max_sl))
        if new_idx != self.slice_idx.get():
            self.slice_idx.set(new_idx)   # updates the slider via its trace
            self.recalculate()             # immediate feedback while scrolling

    def _on_scroll(self, event: object) -> None:
        # Wheel up = next slice, wheel down = previous (radiology convention)
        step = 1 if event.button == "up" else -1  # type: ignore[attr-defined]
        # event.step carries magnitude on trackpads; use its sign if present
        if getattr(event, "step", 0):
            step = 1 if event.step > 0 else -1  # type: ignore[attr-defined]
        self._change_slice(step)

    def _on_key(self, event: object) -> None:
        k = (event.key or "").lower()  # type: ignore[attr-defined]
        if k in ("up", "right", "+", "="):
            self._change_slice(1)
        elif k in ("down", "left", "-"):
            self._change_slice(-1)
        elif k == "pageup":
            self._change_slice(5)
        elif k == "pagedown":
            self._change_slice(-5)
        elif k == "k":
            self.show_kspace.set(not self.show_kspace.get()); self.recalculate()
        elif k == "m":
            self.multi_slice.set(not self.multi_slice.get()); self.recalculate()
        elif k == "p":
            self.show_psd.set(not self.show_psd.get()); self.recalculate()
        elif k == "r":  # reset window/level
            self.window_width = 1.0; self.window_level = 0.5
            if self.current_image is not None:
                self.apply_window_level()

    # --- Cursor readout ----------------------------------------------------- #
    TISSUE_LABELS = {0: "Background", 1: "CSF", 2: "Gray Matter", 3: "White Matter",
                     4: "Fat", 5: "Muscle/Skin", 6: "Skull", 7: "Vessel", 8: "Marrow"}

    def _set_status_default(self) -> None:
        self.statusBar().showMessage(  # type: ignore[union-attr]
            "Wheel / \u2191\u2193 : slice   \u2022   Ctrl+drag : window/level   \u2022   "
            "double-click : reset   \u2022   k / m / p : k-space / multi / PSD")

    def _update_readout(self, event: object) -> None:
        if self.current_image is None or event.inaxes is not self.axes[0]:  # type: ignore[attr-defined]
            self._set_status_default()
            return
        if event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return
        img = self.current_image
        H, W = img.shape[:2]
        col = int(np.clip(round(event.xdata), 0, W - 1))  # type: ignore[attr-defined]
        row = int(np.clip(round(event.ydata), 0, H - 1))  # type: ignore[attr-defined]
        signal = float(img[row, col])

        # Map the cursor's fractional position onto the phantom label volume,
        # which may differ in matrix size from the reconstructed image.
        tissue = ""
        try:
            ph = self._get_current_phantom_slice(
                self.orientation.get(), self.slice_idx.get(), self.get_current_params())
            py = int(np.clip(round(event.ydata / H * ph.shape[0]), 0, ph.shape[0] - 1))  # type: ignore[attr-defined]
            px = int(np.clip(round(event.xdata / W * ph.shape[1]), 0, ph.shape[1] - 1))  # type: ignore[attr-defined]
            label = int(round(float(ph[py, px])))
            props = tissue_db.properties(self.field_strength.get()).get(label)
            tissue = props["name"] if props else f"Tissue {label}"
        except Exception:
            tissue = "n/a"

        self.statusBar().showMessage(  # type: ignore[union-attr]
            f"({col}, {row})   \u2022   {tissue}   \u2022   signal: {signal:.3f}   "
            f"\u2022   slice {self.slice_idx.get()}/{self.get_max_slice_idx()}")

    # RGBA colours for each tissue label (R, G, B, A) — used by the overlay.
    _TISSUE_COLORS: dict[int, tuple[int, int, int, int]] = {
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

    def _make_tissue_overlay(self, label_map: np.ndarray,
                              target_shape: tuple[int, int]) -> np.ndarray:
        """Return an RGBA image mapping each label to a translucent colour."""
        if label_map.shape != target_shape:
            from scipy.ndimage import zoom
            scale = (target_shape[0] / label_map.shape[0],
                     target_shape[1] / label_map.shape[1])
            label_map = zoom(label_map, scale, order=0)
        rgba = np.zeros((*target_shape, 4), dtype=np.uint8)
        for lab, color in self._TISSUE_COLORS.items():
            mask = label_map == lab
            if mask.any():
                rgba[mask] = color
        return rgba

    def apply_window_level(self) -> None:
        if self.current_image is None:
            return
        img = self.current_image
        max_val = np.max(img) if np.max(img) > 0 else 1
        center = self.window_level * max_val
        width = self.window_width * max_val
        cmap = self.display_cmap.get()
        _asp = self._get_voxel_aspect(self.orientation.get())
        self.axes[0].clear()
        self.axes[0].imshow(img, cmap=cmap, origin="lower",
                            vmin=center - width / 2, vmax=center + width / 2,
                            aspect=_asp)
        if self.show_tissue_overlay.get():
            orient = self.orientation.get(); sl_idx = self.slice_idx.get()
            ph_slice = self._get_current_phantom_slice(orient, sl_idx, self.get_current_params())
            self.axes[0].imshow(self._make_tissue_overlay(ph_slice, img.shape),
                                origin="lower", aspect="auto")
        self.axes[0].set_title(self.current_title, color="white", fontsize=10)
        self.axes[0].set_axis_off()
        self.axes[0].text(0.02, 0.02, f"W:{width:.3f} L:{center:.3f}",
                          transform=self.axes[0].transAxes,
                          color="yellow", fontsize=8, va="bottom")
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

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("color:#9aa4b2; font-size:11px;")
        val_lbl = QLabel(_fmt(var.get()))
        val_lbl.setStyleSheet("color:white; font-size:12px; font-weight:bold;")
        row.addWidget(name_lbl)
        row.addStretch(1)
        row.addWidget(val_lbl)
        v.addLayout(row)

        s = QSlider(Qt.Orientation.Horizontal)
        s.setMinimum(int(mn))
        s.setMaximum(int(mx))
        s.setValue(int(round(var.get())))
        v.addWidget(s)

        is_float = isinstance(var.get(), float)

        def on_change(value: int) -> None:
            var.set(float(value) if is_float else int(value))
            val_lbl.setText(_fmt(var.get()))
            self.schedule_recalculate()

        s.valueChanged.connect(on_change)

        def sync() -> None:
            iv = int(round(var.get()))
            if s.value() != iv:
                s.blockSignals(True)
                s.setValue(iv)
                s.blockSignals(False)
            val_lbl.setText(_fmt(var.get()))

        var.trace_add("write", sync)
        parent_layout.addWidget(container)
        container._qslider = s  # type: ignore[attr-defined]
        return container

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

    def _button(self, parent_layout_or_row: Any, text: str, command: Any, color: str = "#4a4a4a") -> QPushButton:
        b = QPushButton(text)
        b.setStyleSheet(f"QPushButton {{ background:{color}; color:white; border:none; "
                        f"padding:5px 8px; border-radius:4px; font-weight:bold; }}"
                        f"QPushButton:hover {{ background:#5a5a5a; }}")
        b.clicked.connect(command)
        parent_layout_or_row.addWidget(b)
        return b

    # ------------------------------------------------------------------ #
    #  Controls
    # ------------------------------------------------------------------ #
    def build_controls(self) -> None:
        L = self.controls_layout

        # \u2500\u2500 App header \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        hdr = QLabel("ACQUISITION")
        hdr.setStyleSheet("font-size:11px; font-weight:bold; color:#6b7585; "
                          "letter-spacing:1px; padding:4px 6px 4px 6px;")
        L.addWidget(hdr)

        # \u2500\u2500 Sequence & Protocol \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        seq_sec = CollapsibleSection("Sequence & Protocol")
        L.addWidget(seq_sec)
        SL = seq_sec.inner
        self._dropdown(SL, "Preset", self.preset_name, ["(Custom)"] + get_preset_names(), self.on_preset_change)
        self._dropdown(SL, "Field Strength", self.field_strength,
                       list(_B0_MAP.keys()), self.schedule_recalculate, inline=True)
        self._seq_dropdown = self._dropdown(SL, "Sequence", self.sequence_type,
                       ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
                        "Balanced SSFP",
                        "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)",
                        "Quantitative (qMRI)", "Echo Planar (EPI)"], self.on_sequence_change)
        self.desc_label = DLabel("", base_style="color:#6b7585; font-size:9px; padding:2px 2px;")
        self.desc_label.setWordWrap(True)
        SL.addWidget(self.desc_label)

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
        rl_row = QHBoxLayout(); rl_row.setContentsMargins(0, 0, 0, 2)
        self._button(rl_row, "Browse Masks\u2026", self.browse_masks, color="#2255aa")
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
        self._checkbox(NL, "FOV Planning (scout)", self.fov_planning)
        self.fov_planning.trace_add("write", self.on_fov_planning_toggle)
        self.plan_frame = QWidget()
        plan_l = QVBoxLayout(self.plan_frame); plan_l.setContentsMargins(0, 0, 0, 0); plan_l.setSpacing(1)
        self._slider(plan_l, "# Slices", self.n_slices, 1, 32)
        self._slider(plan_l, "Slice Gap (vox)", self.slice_gap, 0, 20)
        self._slider(plan_l, "In-plane FOV (%)", self.inplane_fov_pct, 10, 100)
        self._slider(plan_l, "Tilt (\u00b0)", self.slice_tilt, -45, 45)
        self._slider(plan_l, "Rotation (\u00b0)", self.slice_rot, -45, 45)
        _reset_row = QHBoxLayout(); _reset_row.setContentsMargins(4, 2, 4, 2)
        _reset_btn = QPushButton("Reset Angles & FOV")
        _reset_btn.setStyleSheet("font-size:10px; padding:3px 6px; background:#313842; color:#c4cad2; border:1px solid #313842;")
        _reset_btn.clicked.connect(self._reset_oblique)
        _reset_row.addWidget(_reset_btn)
        _reset_wrap = QWidget(); _reset_wrap.setLayout(_reset_row); plan_l.addWidget(_reset_wrap)
        hint2 = QLabel("Scout: drag box = move \u2022 edges = FOV / coverage \u2022 Tilt/Rot = oblique")
        hint2.setStyleSheet("color:#586273; font-size:9px;")
        plan_l.addWidget(hint2)
        NL.addWidget(self.plan_frame)
        self.plan_frame.setVisible(False)

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
        self._slider(SPL, "Bandwidth (kHz)", self.bandwidth, 10, 500)
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
        self._checkbox(DL, "Show k-space", self.show_kspace)
        self._checkbox(DL, "Show Pulse Sequence Diagram", self.show_psd)
        self._dropdown(DL, "Signal Curve", self.plot_curve_mode,
                       ["TE decay", "TR recovery", "TI sweep", "Contrast Map", "Histogram"],
                       self.schedule_recalculate, inline=True)
        hint = QLabel("Wheel/\u2191\u2193: slice \u2022 Ctrl+drag: W/L \u2022 dbl-click/R: reset")
        hint.setStyleSheet("color:#586273; font-size:9px;")
        DL.addWidget(hint)

        # \u2500\u2500 Comparison (collapsed by default) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        cmp_sec = CollapsibleSection("Comparison", collapsed=True)
        L.addWidget(cmp_sec)
        CL = cmp_sec.inner
        crow = QHBoxLayout(); crow.setContentsMargins(0, 0, 0, 0)
        self._button(crow, "Set as A", self.set_protocol_a, color="#2255aa")
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

        def _card(key: str, label: str, value_color: str = "#1bb8ad") -> QWidget:
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
                "fatsat_enabled": self.fatsat_enabled.get()}

    def set_protocol_a(self) -> None:
        self.compare_params = self.get_current_params()
        self.compare_status.config(text=f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", fg="#1bb8ad")
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

    # --- Display ---
    def recalculate(self, *args: object) -> None:
        current_params = self.get_current_params()

        # FOV planning takes over the main view with the prescribed slice group
        if self.fov_planning.get() and not self.compare_mode.get():
            self._display_prescription(current_params)
            self._draw_scout(current_params)
            self.update_metrics(current_params,
                                self.simulate_with_params(current_params)[1])
            return

        if self.multi_slice.get() and not self.compare_mode.get():
            self._display_multi_slice(current_params)
            return

        # Restore 1x2 layout if coming back from multi-slice 3x3 grid
        self._ensure_1x2_layout()

        image_b, metrics_b = self.simulate_with_params(current_params)
        self.axes[0].clear(); self.axes[1].clear()

        cmap = self.display_cmap.get()
        _asp = self._get_voxel_aspect(self.orientation.get())
        if self.compare_mode.get() and self.compare_params:
            image_a, metrics_a = self.simulate_with_params(self.compare_params)
            self.axes[0].imshow(image_a, cmap=cmap, origin="lower", aspect=_asp)
            self.axes[0].set_title(f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", color="white", fontsize=10); self.axes[0].set_axis_off()
            self.axes[1].imshow(image_b, cmap=cmap, origin="lower", aspect=_asp)
            self.axes[1].set_title(f"B: {current_params['sequence']} TR={current_params['TR']:.0f}", color="white", fontsize=10); self.axes[1].set_axis_off()
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
            self.axes[0].imshow(image_b, cmap=cmap, origin="lower",
                                vmin=center - width / 2, vmax=center + width / 2,
                                aspect=_asp)
            if self.show_tissue_overlay.get():
                ph_slice = self._get_current_phantom_slice(orient, sl_idx, current_params)
                self.axes[0].imshow(
                    self._make_tissue_overlay(ph_slice, image_b.shape),
                    origin="lower", aspect="auto")
            self.axes[0].set_title(self.current_title, color="white", fontsize=10); self.axes[0].set_axis_off()
            if self.show_kspace.get():
                ks = self._last_kspace if self._last_kspace is not None else None
                if ks is None:
                    from kspace import image_to_kspace
                    ks = image_to_kspace(image_b)
                self.axes[1].imshow(get_kspace_display(ks), cmap="hot", origin="lower")
                self.axes[1].set_title("k-Space (acquired)", color="white", fontsize=11); self.axes[1].set_axis_off()
            else:
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
            ax.set_facecolor("#15181c")
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
            ax.set_facecolor("#15181c"); ax.set_axis_off()
            if k < n:
                img = self._simulate_single_slice(params, orient, idxs[k])
                ax.imshow(img, cmap=self.display_cmap.get(), origin="lower", aspect=_asp)
                ax.set_title(f"#{idxs[k]}", color="white", fontsize=8)
        self.fig.suptitle(f"{params['sequence']}  |  {n} slice{'s' if n != 1 else ''}  "
                          f"|  FOV {self.inplane_fov_pct.get()}%",
                          color="white", fontsize=10)
        self.canvas.draw()
        self.current_image = self._simulate_single_slice(params, orient, self.slice_idx.get()) if n == 1 else None

    def _draw_scout(self, params: dict) -> None:
        """Render 3-plane localizer with acquisition prescription overlaid on each panel."""
        import scan_geometry as sg
        from matplotlib.patches import Rectangle
        from oblique import plane_from_angles, scout_band, three_scouts as _three_scouts
        self.scout_canvas.setVisible(True)
        acq = self.orientation.get()
        vol = self.phantom_3d
        tilt = self.slice_tilt.get()
        rot  = self.slice_rot.get()
        fov_frac = self.inplane_fov_pct.get() / 100.0

        # Role assignment: which of the 3 panel indices is primary/secondary/acq-plane
        _role_map = {
            "axial":    {"primary": 1, "secondary": 2, "acqplane": 0},
            "coronal":  {"primary": 0, "secondary": 2, "acqplane": 1},
            "sagittal": {"primary": 1, "secondary": 0, "acqplane": 2},
        }
        roles = _role_map[acq]

        # Slab centre in voxel-index space
        center = self._compute_slab_center()
        center_int = (int(round(center[0])), int(round(center[1])), int(round(center[2])))

        # Background images: slices through the planned centre
        scouts_bg = _three_scouts(vol, center_int)

        # Acquisition-plane dashed FOV box (unchanged for both modes)
        ip_box = sg.inplane_box(acq, vol.shape, fov_frac, self.inplane_off.get())

        is_oblique = abs(tilt) > 0.5 or abs(rot) > 0.5

        if is_oblique:
            normal, row_vec, col_vec = plane_from_angles(acq, tilt_deg=tilt, rot_deg=rot)
            band = scout_band(vol.shape, normal, center,
                              n_slices=self.n_slices.get(),
                              thickness_mm=self.slice_thickness.get(),
                              gap_mm=self.slice_gap.get(),
                              voxel_size=(1.0, 1.0, 1.0))
            self._scout_box_info = None
            self._scout_overlays = {}
            for i, plane in enumerate(self._scout_plane_names):
                if i == roles["primary"]:
                    self._scout_overlays[plane] = {"role": "primary",   "info": band[plane]}
                elif i == roles["secondary"]:
                    self._scout_overlays[plane] = {"role": "secondary", "info": band[plane]}
                else:
                    self._scout_overlays[plane] = {"role": "acqplane",  "info": ip_box}
        else:
            info = sg.box_rect(acq, vol.shape,
                               self.slice_idx.get(), self.n_slices.get(),
                               self.slice_thickness.get(), self.slice_gap.get(),
                               fov_frac, self.inplane_off.get())
            self._scout_box_info = info
            sec_plane = self._scout_plane_names[roles["secondary"]]
            sec_ov = sg.secondary_overlay(sec_plane, acq, vol.shape,
                                           self.slice_idx.get(), self.n_slices.get(),
                                           self.slice_thickness.get(), self.slice_gap.get(),
                                           fov_frac, self.inplane_off.get())
            self._scout_overlays = {}
            for i, plane in enumerate(self._scout_plane_names):
                if i == roles["primary"]:
                    self._scout_overlays[plane] = {"role": "primary",   "info": info}
                elif i == roles["secondary"]:
                    self._scout_overlays[plane] = {"role": "secondary", "info": sec_ov}
                else:
                    self._scout_overlays[plane] = {"role": "acqplane",  "info": ip_box}

        self._scout_primary_ax = self.scout_axes[roles["primary"]]
        self.scout_ax = self._scout_primary_ax

        # ── Draw each panel ──────────────────────────────────────────────────
        self._scout_angle_handles = []   # rebuilt every redraw
        for i, plane in enumerate(self._scout_plane_names):
            ax = self.scout_axes[i]
            ax.clear()
            ax.set_facecolor("#0f1216")
            ax.set_axis_off()

            # Background: slice through planned centre (sagittal needs LR flip)
            bg_raw = scouts_bg[plane]
            if plane == "sagittal":
                bg_raw = np.fliplr(bg_raw)
            ax.imshow(simulate_slice(bg_raw, 600, 12, "SE"),
                      cmap="gray", origin="lower", aspect="auto")

            role = self._scout_overlays[plane]["role"]
            ov_info = self._scout_overlays[plane]["info"]

            if role == "primary":
                color = "#ffdd44"
                if is_oblique:
                    cx, cy = self._display_center(plane, center)
                    _angle_var = self._ANGLE_MAP[acq]["primary"]
                    for seg in ov_info.get("edges", []):
                        if seg is not None:
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=2.5)
                            # Endpoint markers — grab anywhere on the line to rotate
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]], "D",
                                    color="#ff5533", markersize=6,
                                    markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (seg[0], seg[1], seg[2], seg[3], plane, _angle_var, cx, cy))
                    slices_segs = ov_info.get("slices", [])
                    mid_j = len(slices_segs) // 2
                    for j, seg in enumerate(slices_segs):
                        if seg is not None:
                            lw = 1.4 if j == mid_j else 0.7
                            alpha = 0.9 if j == mid_j else 0.55
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=lw, alpha=alpha)
                    ax.set_title(f"{plane.capitalize()}  [oblique — drag edge to angle]",
                                 color=color, fontsize=8, pad=2)
                else:
                    # Non-oblique: draw box + register through-edges as angle handles
                    x0, y0, w, h = ov_info["x0"], ov_info["y0"], ov_info["w"], ov_info["h"]
                    ax.add_patch(Rectangle((x0, y0), w, h,
                                           fill=False, edgecolor=color, linewidth=1.8))
                    for L in ov_info["lines"]:
                        if ov_info["line_axis"] == "y":
                            ax.plot([x0, x0 + w], [L, L], color=color, linewidth=0.6, alpha=0.6)
                        else:
                            ax.plot([L, L], [y0, y0 + h], color=color, linewidth=0.6, alpha=0.6)
                    # Angle handles on the through-direction edges (top/bottom or left/right)
                    cx_p, cy_p = self._display_center(plane, center)
                    _av = self._ANGLE_MAP[acq]["primary"]
                    if ov_info["through"] == "v":
                        ang_edges = [(x0, y0, x0 + w, y0), (x0, y0 + h, x0 + w, y0 + h)]
                    else:
                        ang_edges = [(x0, y0, x0, y0 + h), (x0 + w, y0, x0 + w, y0 + h)]
                    for seg in ang_edges:
                        ax.plot([seg[0], seg[2]], [seg[1], seg[3]], "D",
                                color="#ff5533", markersize=5,
                                markeredgecolor="white", markeredgewidth=0.7)
                        self._scout_angle_handles.append(
                            (seg[0], seg[1], seg[2], seg[3], plane, _av, cx_p, cy_p))
                    ax.set_title(f"{plane.capitalize()}  [drag edge to angle]",
                                 color=color, fontsize=8, pad=2)

            elif role == "secondary":
                color = "#2ad0c4"
                if is_oblique:
                    cx, cy = self._display_center(plane, center)
                    _angle_var = self._ANGLE_MAP[acq]["secondary"]
                    for seg in ov_info.get("edges", []):
                        if seg is not None:
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=2.0, linestyle="--")
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]], "D",
                                    color="#1bb8ad", markersize=5,
                                    markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (seg[0], seg[1], seg[2], seg[3], plane, _angle_var, cx, cy))
                    slices_segs = ov_info.get("slices", [])
                    mid_j = len(slices_segs) // 2
                    for j, seg in enumerate(slices_segs):
                        if seg is not None:
                            lw = 1.4 if j == mid_j else 0.7
                            alpha = 0.9 if j == mid_j else 0.55
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=lw, alpha=alpha)
                    ax.set_title(f"{plane.capitalize()}  [drag edge to angle]",
                                 color=color, fontsize=8, pad=2)
                elif ov_info:
                    lo, hi = ov_info["span"]
                    cx_s, cy_s = self._display_center(plane, center)
                    _av_s = self._ANGLE_MAP[acq]["secondary"]
                    mid_pos_idx = len(ov_info["positions"]) // 2
                    for j, pos in enumerate(ov_info["positions"]):
                        lw = 1.4 if j == mid_pos_idx else 0.7
                        alpha = 0.9 if j == mid_pos_idx else 0.55
                        if ov_info["orient"] == "h":
                            ax.plot([lo, hi], [pos, pos], color=color, lw=lw, alpha=alpha)
                            # Endpoint markers + register as angle handle
                            ax.plot([lo, hi], [pos, pos], "D", color="#1bb8ad",
                                    markersize=5, markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (lo, pos, hi, pos, plane, _av_s, cx_s, cy_s))
                        else:
                            ax.plot([pos, pos], [lo, hi], color=color, lw=lw, alpha=alpha)
                            ax.plot([pos, pos], [lo, hi], "D", color="#1bb8ad",
                                    markersize=5, markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (pos, lo, pos, hi, plane, _av_s, cx_s, cy_s))
                    ax.set_title(f"{plane.capitalize()}  [drag edge to angle / move]",
                                 color=color, fontsize=8, pad=2)

            else:  # acqplane
                color = "#ff8844"
                ax.add_patch(Rectangle((ip_box["x0"], ip_box["y0"]),
                                       ip_box["w"], ip_box["h"],
                                       fill=False, edgecolor=color,
                                       linewidth=1.4, linestyle="--"))
                lbl = "oblique acq" if is_oblique else "acq plane"
                ax.set_title(f"{plane.capitalize()}  [{lbl}]",
                             color=color, fontsize=8, pad=2)

        self.scout_canvas.draw()

    # Which angle variable is controlled by dragging each panel role in oblique mode.
    # Derived from: rot_deg makes angled lines on primary panels; tilt_deg on secondary.
    # Exception: sagittal acquisition has them swapped.
    _ANGLE_MAP: dict[str, dict[str, str]] = {
        "axial":    {"primary": "rot",  "secondary": "tilt"},
        "coronal":  {"primary": "rot",  "secondary": "tilt"},
        "sagittal": {"primary": "tilt", "secondary": "rot"},
    }

    def _display_center(self, panel: str, center: np.ndarray) -> tuple:
        """Return (cx, cy) of the slab center in display coords for the given scout panel."""
        nY = self.phantom_3d.shape[1]
        cZ, cY, cX = float(center[0]), float(center[1]), float(center[2])
        if panel == "axial":
            return cX, cY
        elif panel == "coronal":
            return cX, cZ
        else:  # sagittal — Y axis is flipped
            return nY - 1.0 - cY, cZ

    def _compute_slab_center(self) -> np.ndarray:
        """(Z, Y, X) voxel-index centre of the prescribed slab (via controller)."""
        self._sync_sim()
        return self.sim._compute_slab_center(self.orientation.get(), self.slice_idx.get())

    def _reset_oblique(self) -> None:
        self.slice_tilt.set(0.0)
        self.slice_rot.set(0.0)
        self.inplane_fov_pct.set(100)
        self.inplane_off.set(0.0)
        if self.fov_planning.get():
            self._draw_scout(self.get_current_params())
        self.schedule_recalculate()

    @staticmethod
    def _scout_handle_points(info: dict) -> list:
        x0, y0, w, h = info["x0"], info["y0"], info["w"], info["h"]
        return [(x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)]

    def on_fov_planning_toggle(self) -> None:
        on = self.fov_planning.get()
        self.plan_frame.setVisible(on)
        if not on:
            self.scout_canvas.setVisible(False)
            self._ensure_1x2_layout()
        self.recalculate()

    # --- scout mouse interaction ---
    def _scout_hit_test(self, event: object) -> str | None:
        """Return 'move'|'resize_cov'|'resize_fov' for a press location, or None."""
        info = self._scout_box_info
        if info is None or event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return None
        x, y = event.xdata, event.ydata  # type: ignore[attr-defined]
        x0, y0, w, h = info["x0"], info["y0"], info["w"], info["h"]
        tol = max(4.0, 0.03 * max(info["through_len"], info["inplane_len"]))
        inside = (x0 - tol <= x <= x0 + w + tol) and (y0 - tol <= y <= y0 + h + tol)
        if not inside:
            return None

        through_v = info["through"] == "v"
        # The "coverage" dimension is the through direction; "fov" is in-plane.
        # Only register an edge grab if (a) the cursor is within tol of that edge
        # AND (b) the box is thick enough in that dimension to have a distinct
        # interior (otherwise a centre press on a thin slab is ambiguous -> move).
        cov_dim = h if through_v else w          # through extent on screen
        fov_dim = w if through_v else h          # in-plane extent on screen

        def near_edge(coord: float, lo: float, length: float) -> bool:
            return abs(coord - lo) < tol or abs(coord - (lo + length)) < tol

        if through_v:
            cov_edge = near_edge(y, y0, h) and cov_dim > 3 * tol
            fov_edge = near_edge(x, x0, w) and fov_dim > 3 * tol
        else:
            cov_edge = near_edge(x, x0, w) and cov_dim > 3 * tol
            fov_edge = near_edge(y, y0, h) and fov_dim > 3 * tol

        if cov_edge and not fov_edge:
            return "resize_cov"
        if fov_edge and not cov_edge:
            return "resize_fov"
        if cov_edge and fov_edge:
            # corner: prefer the dimension whose edge is closest
            return "resize_fov"
        return "move"

    # through/through_sign for secondary panel drag — depends only on acquisition
    _SEC_THROUGH: dict[str, tuple[str, int]] = {
        "axial":    ("v", +1),
        "coronal":  ("h", -1),
        "sagittal": ("h", +1),
    }

    def _scout_press(self, event: object) -> None:
        if not self.fov_planning.get() or event.inaxes is None:  # type: ignore[attr-defined]
            return
        if event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return
        px, py = event.xdata, event.ydata  # type: ignore[attr-defined]

        # ── Edge-line hit test ─────────────────────────────────────────────
        # Outer 25% of each edge line  →  angle drag  (◆ endpoints)
        # Middle 50%                   →  fall through to normal move routing
        import math as _math
        line_tol = 7.0
        for (lx0, ly0, lx1, ly1, h_plane, angle_var, cx, cy) in self._scout_angle_handles:
            panel_idx = self._scout_plane_names.index(h_plane)
            if event.inaxes is not self.scout_axes[panel_idx]:  # type: ignore[attr-defined]
                continue
            ldx, ldy = lx1 - lx0, ly1 - ly0
            seg_len_sq = ldx * ldx + ldy * ldy
            if seg_len_sq < 1e-6:
                t, dist = 0.5, _math.hypot(px - lx0, py - ly0)
            else:
                t = max(0.0, min(1.0, ((px - lx0) * ldx + (py - ly0) * ldy) / seg_len_sq))
                dist = _math.hypot(px - (lx0 + t * ldx), py - (ly0 + t * ldy))
            if dist >= line_tol:
                continue
            if t < 0.25 or t > 0.75:
                # Near an endpoint → angle drag
                self._scout_drag = dict(mode="angle", x=px, y=py,
                                        angle_var=angle_var, cx=cx, cy=cy)
                return
            # Near the middle → stop checking handles, fall through to move routing
            break

        # ── Normal panel-role routing ──────────────────────────────────────
        clicked_plane: str | None = None
        for i, ax in enumerate(self.scout_axes):
            if event.inaxes is ax:  # type: ignore[attr-defined]
                clicked_plane = self._scout_plane_names[i]
                break
        if clicked_plane is None:
            return
        ov = self._scout_overlays.get(clicked_plane)
        if ov is None:
            return
        role = ov["role"]
        is_oblique = abs(self.slice_tilt.get()) > 0.5 or abs(self.slice_rot.get()) > 0.5
        acq = self.orientation.get()
        if role == "primary":
            if is_oblique:
                self._scout_drag = dict(mode="move", x=px, y=py,
                                        secondary=False, oblique=True)
            else:
                mode = self._scout_hit_test(event)
                if mode is None:
                    return
                self._scout_drag = dict(mode=mode, x=px, y=py,
                                        secondary=False, oblique=False)
        elif role == "secondary":
            through, sign = self._SEC_THROUGH.get(acq, ("v", 1))
            meta = {"through": through, "through_sign": sign}
            self._scout_drag = dict(mode="move", x=px, y=py,
                                    secondary=True, overlay=meta)

    def _scout_motion(self, event: object) -> None:
        if self._scout_drag is None or event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return
        import scan_geometry as sg
        import math
        d = self._scout_drag
        ex, ey = event.xdata, event.ydata  # type: ignore[attr-defined]
        dx = ex - d["x"]; dy = ey - d["y"]
        d["x"], d["y"] = ex, ey
        orient = self.orientation.get()

        if d.get("mode") == "angle":
            # Angle drag: compute angular change from handle movement around slab centre
            cx, cy = d["cx"], d["cy"]
            prev_x, prev_y = ex - dx, ey - dy  # position before this event
            dist_prev = math.hypot(prev_x - cx, prev_y - cy)
            if dist_prev < 2.0:
                return  # too close to centre; skip to avoid large jumps
            angle_prev = math.atan2(prev_y - cy, prev_x - cx)
            angle_new  = math.atan2(ey - cy, ex - cx)
            d_angle = math.degrees(angle_new - angle_prev)
            # Clamp to avoid large jumps at wrap-around
            if d_angle > 90:
                d_angle -= 180
            elif d_angle < -90:
                d_angle += 180
            if d["angle_var"] == "tilt":
                new_val = float(np.clip(self.slice_tilt.get() + d_angle, -45, 45))
                self.slice_tilt.set(new_val)
            else:
                new_val = float(np.clip(self.slice_rot.get() + d_angle, -45, 45))
                self.slice_rot.set(new_val)
            self._draw_scout(self.get_current_params())
            self.schedule_recalculate()
            return

        if d.get("secondary"):
            # Secondary panel: only move through-axis position
            sec_meta = d["overlay"]
            if sec_meta:
                through = sec_meta["through"]
                sign = sec_meta["through_sign"]
                raw = dy if through == "v" else dx
                dx_through = raw * sign
                si, _, _, _ = sg.update_from_drag(
                    orient, self.phantom_3d.shape, "move", dx_through, 0.0,
                    self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
                    self.slice_gap.get(), self.inplane_fov_pct.get() / 100.0, self.inplane_off.get())
                self.slice_idx.set(int(round(si)))
        elif d.get("oblique"):
            # Oblique primary: translate slice centre using standard through-axis mapping
            import scan_geometry as _sg
            cfg = _sg.SCOUT[orient]
            raw = dy if cfg["through"] == "v" else dx
            si, _, _, _ = sg.update_from_drag(
                orient, self.phantom_3d.shape, "move", raw, 0.0,
                self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
                self.slice_gap.get(), self.inplane_fov_pct.get() / 100.0, self.inplane_off.get())
            self.slice_idx.set(int(round(si)))
        else:
            info = self._scout_box_info
            if info is None:
                return
            if info["through"] == "v":
                dx_through, d_inplane = dy, dx
            else:
                dx_through, d_inplane = dx, dy
            si, off, fr, n = sg.update_from_drag(
                orient, self.phantom_3d.shape, d["mode"], dx_through, d_inplane,
                self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
                self.slice_gap.get(), self.inplane_fov_pct.get() / 100.0, self.inplane_off.get())
            self.slice_idx.set(int(round(si)))
            self.inplane_off.set(off)
            self.inplane_fov_pct.set(int(round(fr * 100)))
            self.n_slices.set(n)

        self._draw_scout(self.get_current_params())
        self.schedule_recalculate()

    def _scout_release(self, event: object) -> None:
        if self._scout_drag is not None:
            self._scout_drag = None
            self.recalculate()

    def _plot_curves(self, params: dict) -> None:
        seq, TR, TE, TI, FA = params["sequence"], params["TR"], params["TE"], params["TI"], params["flip_angle"]
        ax = self.axes[1]
        mode = self.plot_curve_mode.get()

        # Tissue curves read from the measured field-strength table (tissue_db),
        # keyed by the names this method uses.
        _tdb = tissue_db.properties(params.get("field_strength", "3T"))
        _NAME2LABEL = {"white_matter": 3, "gray_matter": 2, "csf": 1, "fat": 4, "muscle": 6}
        TISSUES_B0 = {name: _tdb[lab] for name, lab in _NAME2LABEL.items()}

        # --- Sequences with fixed curve type (ignore mode toggle) ----------
        if seq == "FSE / TSE":
            for tn, color, T1, T2, PD in [("WM", '#ff6b6b', 830, 80, 0.65),
                                           ("GM", '#69db7c', 1330, 100, 0.8),
                                           ("CSF", '#74c0fc', 4500, 2200, 1.0)]:
                te_vals, sigs = compute_fse_echo_train(T1, T2, PD, TR, params["etl"], params["echo_spacing"])
                ax.plot(te_vals, sigs, color=color, linewidth=2, label=tn, marker='o', markersize=3)
            ax.axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE_eff={TE:.0f}')
            ax.set_xlabel('Echo Time (ms)', color='white')
            ax.set_title('FSE Echo Train Decay', color='white', fontsize=11)

        elif seq == "Diffusion (DWI)":
            b_range = np.arange(0, 3001, 50); dp = get_diffusion_properties_3d(None)
            for name, color, label in [("WM", '#ff6b6b', 3), ("GM", '#69db7c', 2), ("CSF", '#74c0fc', 1)]:
                props = TISSUES_B0[name.lower().replace("wm", "white_matter").replace("gm", "gray_matter")]
                S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
                ax.plot(b_range, S0 * np.exp(-b_range * dp[label]["ADC"] * 1e-3), color=color, linewidth=2, label=name)
            ax.axvline(x=params["b_value"], color='yellow', linestyle='--', alpha=0.7)
            ax.set_xlabel('b-value (s/mm²)', color='white')
            ax.set_title('Signal vs b-value', color='white', fontsize=11)

        elif seq == "MR Angiography":
            fa_range = np.arange(1, 91, 1)
            for name, color, T1, PD in [("Brain", '#69db7c', 1330, 0.8), ("Blood", '#ff6b6b', 1930, 0.9)]:
                if "Blood" in name:
                    ax.plot(fa_range, PD * np.sin(np.radians(fa_range)) * np.exp(-TE / 50),
                            color=color, linewidth=2, label=name)
                else:
                    ax.plot(fa_range, [gradient_echo_signal(T1, 50, PD, TR, TE, float(fa)) for fa in fa_range],
                            color=color, linewidth=2, label=name)
            ax.axvline(x=FA, color='yellow', linestyle='--', alpha=0.7, label=f'FA={FA:.0f}°')
            # Ernst angle for brain tissue
            ernst_brain = float(np.degrees(np.arccos(np.exp(-TR / 1330))))
            ax.axvline(x=ernst_brain, color='#9aa4b2', linestyle=':', alpha=0.6, label=f'Ernst={ernst_brain:.0f}°')
            ax.set_xlabel('Flip Angle (°)', color='white')
            ax.set_title('TOF Signal vs Flip Angle', color='white', fontsize=11)

        elif seq == "fMRI (BOLD)":
            te_range = np.arange(5, 100, 1, dtype=float)
            bs = te_range * np.exp(-te_range / 60); bs /= bs.max()
            ax.plot(te_range, bs, color='#ff6b6b', linewidth=2, label='BOLD sensitivity')
            ax.plot(te_range, np.exp(-te_range / 60), color='#69db7c', linewidth=2, label='GRE signal')
            ax.axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE={TE:.0f}')
            ax.set_xlabel('TE (ms)', color='white')
            ax.set_title('BOLD Sensitivity vs TE', color='white', fontsize=11)

        # --- SE / GRE / IR with mode toggle --------------------------------
        elif mode == "TR recovery":
            tr_range = np.arange(100, 8001, 50, dtype=float)
            _tissue_rows = [("White Matter", '#ff6b6b', "white_matter"),
                            ("Gray Matter",  '#69db7c', "gray_matter"),
                            ("CSF",          '#74c0fc', "csf")]
            for tlabel, color, key in _tissue_rows:
                props = TISSUES_B0[key]
                if seq == "Spin Echo":
                    sig = props["PD"] * (1 - np.exp(-tr_range / props["T1"])) * np.exp(-TE / props["T2"])
                elif seq == "Gradient Echo":
                    a = np.radians(FA); E1v = np.exp(-tr_range / props["T1"])
                    denom = np.where(np.abs(1 - np.cos(a) * E1v) < 1e-9, 1e-9, 1 - np.cos(a) * E1v)
                    sig = props["PD"] * np.sin(a) * (1 - E1v) / denom * np.exp(-TE / (props["T2"] * 0.6))
                else:  # IR
                    sig = props["PD"] * np.abs(1 - 2 * np.exp(-TI / props["T1"]) + np.exp(-tr_range / props["T1"])) * np.exp(-TE / props["T2"])
                ax.plot(tr_range, sig, color=color, linewidth=2, label=tlabel)
            ax.axvline(x=TR, color='yellow', linestyle='--', alpha=0.7, label=f'TR={TR:.0f}')
            ax.set_xlabel('TR (ms)', color='white')
            ax.set_ylabel('Signal (a.u.)', color='white')
            ax.set_title('T1 Recovery  (signal vs TR)', color='white', fontsize=11)
            ax.legend(fontsize=8, facecolor='#1f242b', labelcolor='white')

        elif mode == "TI sweep":
            # Signal vs TI — most useful for IR/STIR/FLAIR education
            ti_max = min(max(TR * 0.99, 500), 5000)
            ti_range = np.arange(50, ti_max, 10, dtype=float)
            _ir_tissues = [("White Matter", '#ff6b6b', "white_matter"),
                           ("Gray Matter",  '#69db7c', "gray_matter"),
                           ("CSF",          '#74c0fc', "csf"),
                           ("Fat",          '#ffd43b', "fat")]
            for tlabel, color, key in _ir_tissues:
                if key not in TISSUES_B0:
                    continue
                props = TISSUES_B0[key]
                signed = props["PD"] * (1 - 2 * np.exp(-ti_range / props["T1"]) + np.exp(-TR / props["T1"])) * np.exp(-TE / props["T2"])
                mag = np.abs(signed)
                ax.plot(ti_range, signed, color=color, linewidth=1, linestyle='--', alpha=0.35)
                ax.plot(ti_range, mag, color=color, linewidth=2, label=tlabel)
                # Null point
                denom_null = 1 + np.exp(-TR / props["T1"])
                if denom_null > 1e-9:
                    null_ti = props["T1"] * np.log(2.0 / denom_null)
                    if 50 < null_ti < ti_max:
                        ax.axvline(x=null_ti, color=color, linestyle=':', alpha=0.55, linewidth=1)
                        ax.text(null_ti + ti_max * 0.01, ax.get_ylim()[1] * 0.02 if ax.get_ylim()[1] > 0 else 0.01,
                                f"null\n{null_ti:.0f}ms", color=color, fontsize=7, va='bottom')
            ax.axhline(y=0, color='#3a424d', linewidth=0.8, alpha=0.5)
            ax.axvline(x=TI, color='yellow', linestyle='--', alpha=0.8, label=f'TI={TI:.0f}')
            ax.set_xlabel('TI (ms)', color='white')
            ax.set_ylabel('Signal (a.u.)', color='white')
            ax.set_title('IR Signal vs TI  (— magnitude · - - signed)', color='white', fontsize=10)
            ax.legend(fontsize=8, facecolor='#1f242b', labelcolor='white')

        elif mode == "Contrast Map":
            # 2-D WM–GM CNR heat map vs TR and TE for the current sequence
            tr_vals = np.logspace(np.log10(200), np.log10(6000), 80)
            te_vals = np.linspace(5, 200, 60)
            TR_g, TE_g = np.meshgrid(tr_vals, te_vals)
            wm = TISSUES_B0["white_matter"]; gm = TISSUES_B0["gray_matter"]
            TISSUES_B0["csf"]
            if seq == "Gradient Echo":
                a = np.radians(FA)
                def gre_sig(p: dict, TRg: np.ndarray, TEg: np.ndarray) -> np.ndarray:
                    E1g = np.exp(-TRg / p["T1"])
                    d = np.where(np.abs(1 - np.cos(a) * E1g) < 1e-9, 1e-9, 1 - np.cos(a) * E1g)
                    return p["PD"] * np.sin(a) * (1 - E1g) / d * np.exp(-TEg / (p["T2"] * 0.6))
                s_wm = gre_sig(wm, TR_g, TE_g); s_gm = gre_sig(gm, TR_g, TE_g)
            elif seq == "Inversion Recovery":
                s_wm = wm["PD"] * np.abs(1 - 2*np.exp(-TI/wm["T1"]) + np.exp(-TR_g/wm["T1"])) * np.exp(-TE_g/wm["T2"])
                s_gm = gm["PD"] * np.abs(1 - 2*np.exp(-TI/gm["T1"]) + np.exp(-TR_g/gm["T1"])) * np.exp(-TE_g/gm["T2"])
            else:  # SE / FSE
                s_wm = wm["PD"] * (1 - np.exp(-TR_g / wm["T1"])) * np.exp(-TE_g / wm["T2"])
                s_gm = gm["PD"] * (1 - np.exp(-TR_g / gm["T1"])) * np.exp(-TE_g / gm["T2"])
            cnr_map = np.abs(s_wm - s_gm)
            ax.imshow(cnr_map, origin='lower', aspect='auto', cmap='hot',
                      extent=[np.log10(200), np.log10(6000), 5, 200], vmin=0)
            ax.plot([np.log10(TR)], [TE], 'c+', markersize=12, markeredgewidth=2, label=f'TR={TR:.0f} TE={TE:.0f}')
            tick_trs = [200, 500, 1000, 2000, 4000]
            ax.set_xticks([np.log10(v) for v in tick_trs])
            ax.set_xticklabels([str(v) for v in tick_trs])
            ax.set_xlabel('TR (ms, log scale)', color='white')
            ax.set_ylabel('TE (ms)', color='white')
            ax.set_title('WM–GM CNR map  (brighter = better contrast)', color='white', fontsize=10)
            ax.legend(fontsize=8, facecolor='#1f242b', labelcolor='white')

        elif mode == "Histogram":
            img = self.current_image
            if img is not None and img.size > 0:
                img_pos = img.ravel()
                img_pos = img_pos[img_pos > 0]
                if img_pos.size > 0:
                    ax.hist(img_pos, bins=80, color='#1bb8ad', alpha=0.7, density=True)
                    # Annotate tissue ROI means using TISSUES_B0
                    _tissue_rows = [("WM", '#ff6b6b', "white_matter"),
                                    ("GM", '#69db7c', "gray_matter"),
                                    ("CSF", '#74c0fc', "csf")]
                    ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1.0
                    for tlabel, color, key in _tissue_rows:
                        props = TISSUES_B0[key]
                        if seq == "Spin Echo":
                            mean_sig = props["PD"] * (1 - np.exp(-TR / props["T1"])) * np.exp(-TE / props["T2"])
                        elif seq == "Gradient Echo":
                            a = np.radians(FA); E1 = np.exp(-TR / props["T1"])
                            denom = 1 - np.cos(a) * E1
                            mean_sig = (props["PD"] * np.sin(a) * (1 - E1) / max(abs(denom), 1e-9)
                                        * np.exp(-TE / (props["T2"] * 0.6)))
                        else:
                            mean_sig = (props["PD"] * abs(1 - 2*np.exp(-TI/props["T1"]) + np.exp(-TR/props["T1"]))
                                        * np.exp(-TE / props["T2"]))
                        ax.axvline(x=mean_sig, color=color, linestyle='--', linewidth=1.5, alpha=0.85,
                                   label=f'{tlabel}≈{mean_sig:.3f}')
                    ax.set_xlabel('Pixel Value', color='white')
                    ax.set_ylabel('Density', color='white')
                    ax.set_title('Image Histogram  (dashed = tissue signal prediction)',
                                 color='white', fontsize=10)
                    ax.legend(fontsize=8, facecolor='#1f242b', labelcolor='white')
                else:
                    ax.text(0.5, 0.5, 'No image data', ha='center', va='center',
                            transform=ax.transAxes, color='white')
            else:
                ax.text(0.5, 0.5, 'Run simulation first', ha='center', va='center',
                        transform=ax.transAxes, color='white')

        else:  # TE decay (default)
            te_range = np.arange(5, min(300, TR), 2)
            _tissue_rows = [("White Matter", '#ff6b6b', "white_matter"),
                            ("Gray Matter",  '#69db7c', "gray_matter"),
                            ("CSF",          '#74c0fc', "csf")]
            for tlabel, color, key in _tissue_rows:
                props = TISSUES_B0[key]
                if seq == "Spin Echo":
                    sig = props["PD"] * (1 - np.exp(-TR / props["T1"])) * np.exp(-te_range / props["T2"])
                elif seq == "Gradient Echo":
                    a = np.radians(FA); E1 = np.exp(-TR / props["T1"])
                    denom = 1 - np.cos(a) * E1
                    sig = (props["PD"] * np.sin(a) * (1 - E1) / max(abs(denom), 1e-9)
                           * np.exp(-te_range / (props["T2"] * 0.6)))
                else:  # IR — show the magnitude decay at current TI
                    sig = (props["PD"] * abs(1 - 2*np.exp(-TI/props["T1"]) + np.exp(-TR/props["T1"]))
                           * np.exp(-te_range / props["T2"]))
                ax.plot(te_range, sig, color=color, linewidth=2, label=tlabel)

            ax.axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE={TE:.0f}')
            if seq == "Gradient Echo":
                ernst_gm = float(np.degrees(np.arccos(np.clip(np.exp(-TR / 1330), -1.0, 1.0))))
                ax.set_title(f'GRE T2* Decay  (Ernst≈{ernst_gm:.0f}° for GM at this TR)',
                             color='white', fontsize=10)
            elif seq == "Inversion Recovery":
                ax.set_title(f'IR T2 Decay at TI={TI:.0f}ms  (use TI sweep for null points)',
                             color='white', fontsize=10)
            else:
                ax.set_title('T2 Decay  (signal vs TE)', color='white', fontsize=11)
            ax.set_xlabel('TE (ms)', color='white')
            ax.set_ylabel('Signal (a.u.)', color='white')
            ax.legend(fontsize=8, facecolor='#1f242b', labelcolor='white')
        self.axes[1].tick_params(colors='white'); self.axes[1].set_facecolor('#15181c')

    def update_compare_metrics(self, ma: dict, mb: dict) -> None:
        up, down = "\u2191", "\u2193"

        def d(a: float, b: float, u: str = "", f: str = ".1f") -> str:
            diff = b - a; pct = (diff / a * 100) if a != 0 else 0
            arrow = up if diff > 0 else down if diff < 0 else "="
            return f"{arrow} {abs(diff):{f}}{u} ({abs(pct):.0f}%)"
        rule = "\u2500\u2500"
        cnr_a = abs(ma["snr_wm"] - ma["snr_gm"]); cnr_b = abs(mb["snr_wm"] - mb["snr_gm"])
        text = f"{rule} A vs B {rule}\nTime: {d(ma['scan_time'], mb['scan_time'], 's')}\n"
        text += f"SNR WM: {d(ma['snr_wm'], mb['snr_wm'])}\nCNR: {d(cnr_a, cnr_b)}\n"
        text += f"Res: {d(ma['resolution'], mb['resolution'], 'mm', '.2f')}\nSAR: A={ma['sar_head']:.1f} B={mb['sar_head']:.1f} W/kg"
        self.compare_metrics_label.config(text=text, fg="#ffcc00")

    def update_metrics(self, params: dict, metrics: dict) -> None:
        orient = self.orientation.get(); sl_idx = self.slice_idx.get()
        matrix = params["matrix_size"]
        thickness = int(params.get("slice_thickness", self.slice_thickness.get()))
        R = params["accel_factor"]; ETL = params["etl"] if params["sequence"] == "FSE / TSE" else 1
        pf_on = params.get("pf_enabled", False)
        pf_label = params.get("pf_fraction", "Full") if pf_on else ""
        resolution = metrics["resolution"]

        self.metrics_labels["resolution"].config(text=f"{resolution:.2f} mm")
        self.metrics_labels["voxel_size"].config(text=f"{resolution:.2f}x{resolution:.2f}x{thickness}mm")
        self.metrics_labels["matrix_display"].config(text=f"{matrix}x{matrix}")
        self.metrics_labels["slice_info"].config(text=f"{orient.capitalize()} #{sl_idx}")

        # Scan time with per-factor breakdown
        st = metrics["scan_time"]
        parts = [p for p in [
            f"\u00f7ETL{ETL}" if ETL > 1 else "",
            f"\u00f7R{R}" if R > 1 else "",
            f"\u00d7PF{pf_label}" if pf_on and pf_label != "Full" else "",
        ] if p]
        st_text = f"{int(st // 60)}:{int(st % 60):02d}"
        if parts:
            st_text += "  [" + " ".join(parts) + "]"
        self.metrics_labels["scan_time"].config(text=st_text)

        self.metrics_labels["bw_pixel"].config(text=f"{params['bandwidth'] * 1000 / matrix:.1f}")
        self.metrics_labels["snr_wm"].config(text=f"{metrics['snr_wm']:.1f}")
        self.metrics_labels["snr_gm"].config(text=f"{metrics['snr_gm']:.1f}")
        self.metrics_labels["cnr"].config(text=f"{abs(metrics['snr_wm'] - metrics['snr_gm']):.1f}")
        self.metrics_labels["snr_eff"].config(text=f"{metrics.get('snr_eff', 0):.1f}")

        # SAR: show max safe FA when limit exceeded
        if metrics["sar_exceeds"]:
            sf = _SAR_SEQ_FACTORS.get(params["sequence"], 1.0)
            fa_max = int(np.clip(90 * np.sqrt(3.2 * max(params["TR"], 10) / (2500.0 * sf)), 1, 90))
            sar_text = f"{metrics['sar_head']:.1f} W/kg  \u26a0\ufe0f (safe \u2264{fa_max}\u00b0)"
        else:
            sar_text = f"{metrics['sar_head']:.1f} W/kg"
        self.metrics_labels["sar"].config(text=sar_text, fg="#ff6b6b" if metrics["sar_exceeds"] else "#1bb8ad")

        self.metrics_labels["weighting"].config(
            text=self.determine_weighting(params["TR"], params["TE"], params["sequence"]))
        self.metrics_labels["field_disp"].config(text=params.get("field_strength", "3T"))

        # Fat-water phase (GRE only; SE refocuses chemical-shift phase)
        _B0_fw = _B0_MAP.get(params.get("field_strength", "3T"), 3.0)
        if params["sequence"] in ("Gradient Echo", "MR Angiography"):
            fw_lbl = rendering.gre_fw_phase_label(params["TE"], _B0_fw)
            fw_col = "#69db7c" if fw_lbl == "In-phase" else ("#ff6b6b" if fw_lbl == "Opposed" else "#ffcc00")
            self.metrics_labels["fw_phase"].config(text=fw_lbl, fg=fw_col)
        else:
            self.metrics_labels["fw_phase"].config(text="N/A (SE)", fg="#586273")

        # ETL / Accel / PF summary line (R shown with its real SENSE g-factor)
        tokens = [t for t in [
            f"ETL={ETL}" if ETL > 1 else "",
            f"R={R} (g={metrics.get('g_factor', 1.0):.2f})" if R > 1 else "",
            f"PF={pf_label}" if pf_on else "",
        ] if t]
        self.metrics_labels["etl_accel"].config(text=" ".join(tokens) or "None")

        # Active effects list
        active = []
        if params.get("motion_enabled", self.motion_enabled.get()): active.append("Motion")
        if params.get("chemical_shift_enabled", self.chemical_shift_enabled.get()): active.append("ChemShift")
        if params.get("susceptibility_enabled", self.susceptibility_enabled.get()): active.append("Suscept.")
        if params.get("zipper_enabled", self.zipper_enabled.get()): active.append("Zipper")
        if params.get("contrast_enabled"): active.append(f"Gd×{params.get('contrast_dose',1)*0.1:.1f}mmol/kg")
        if params["fov_fraction"] < 100: active.append("Aliasing")
        if pf_on: active.append(f"PF({pf_label})")
        if params.get("kspace_filter_enabled"): active.append(f"Filter({params.get('kspace_filter_window','')})")
        if matrix < 128: active.append("Blur")
        if metrics["sar_exceeds"]: active.append("SAR!")
        self.metrics_labels["artifacts"].config(
            text=", ".join(active) if active else "None",
            fg="#ff6b6b" if active else "#1bb8ad")

        self._update_header()

    def determine_weighting(self, TR: float, TE: float, seq: str) -> str:
        if seq == "Diffusion (DWI)": return "Diffusion"
        if seq == "MR Angiography": return "Flow"
        if seq == "fMRI (BOLD)": return "T2* (BOLD)"
        if seq == "Quantitative (qMRI)": return "Quantitative"
        if seq == "Echo Planar (EPI)": return "T2* (EPI)"
        if seq == "Balanced SSFP": return "T2/T1 (bSSFP)"
        if TR < 800 and TE < 30: return "T1-weighted"
        elif TR > 2000 and TE > 60: return "T2-weighted"
        elif TR > 2000 and TE < 30: return "PD-weighted"
        return "Mixed"

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

    def _load_brain(self, subject_num: int) -> np.ndarray:
        """Load a BrainWeb subject's labelled volume, falling back to synthetic."""
        try:
            from brainweb_loader import load_brainweb_phantom
            return load_brainweb_phantom(subject_num)
        except Exception as exc:
            print(f"subject {subject_num} load failed ({exc}); using synthetic brain")
            from phantom3d import generate_synthetic_3d_brain
            return generate_synthetic_3d_brain()

    def on_subject_change(self) -> None:
        """Switch the Brain phantom to a different BrainWeb subject."""
        n = int(self.brain_subject.get())
        self.statusBar().showMessage(f"Loading BrainWeb subject {n:02d}…")  # type: ignore[union-attr]
        QApplication.processEvents()
        vol = self._load_brain(n)
        self._region_cache["Brain"] = vol
        self._brain_volume = vol
        # fMRI activation is placed in this brain's cortex (cheap to rebuild);
        # the synthetic TOF vessel tree is reused (it is not subject-specific).
        self.activation_3d = add_activation_3d(vol)
        if self.region.get() != "Brain":
            self.region.set("Brain")
            self._region_dd._combo.setCurrentText("Brain")
        self.on_region_change()   # picks up the updated Brain cache + refreshes

    def on_region_change(self) -> None:
        name = self.region.get()
        if name not in self._region_cache:
            self.statusBar().showMessage(f"Building {name} phantom\u2026")  # type: ignore[union-attr]
            QApplication.processEvents()
            self._region_cache[name] = self._body_phantoms.build_region(name)
            self._region_texture_cache[name] = self._body_phantoms.build_region_texture(name)
        self.phantom_3d = self._region_cache[name]
        self.texture_3d = self._region_texture_cache.get(name)

        # Restrict the Sequence list to what this region supports (loaded real
        # volumes register their own list in _region_sequences).
        supported = self._region_sequences.get(name) or \
            self._body_phantoms.REGION_SEQUENCES.get(name)
        if supported:
            combo = self._seq_dropdown._combo
            combo.blockSignals(True)
            combo.clear(); combo.addItems(supported)
            if self.sequence_type.get() not in supported:
                self.sequence_type.set(supported[0])
            combo.setCurrentText(self.sequence_type.get())
            combo.blockSignals(False)

        # Recentre to a sensible slice for the new volume and refresh ranges
        if self.orientation.get() != "axial":
            self.orientation.set("axial")
            for b in self._orient_group.buttons():
                if b.text() == "Ax":
                    b.blockSignals(True); b.setChecked(True); b.blockSignals(False)
        self.slice_idx.set(self.get_max_slice_idx() // 2)
        self._refresh_slice_range()

        # Sync FOV slider range and default to the native physical extent of the new region
        if self._fov_slider is not None:
            native = self._get_native_fov()
            lo = max(50, int(native * 0.2))
            hi = max(500, int(native * 1.5))
            self._fov_slider.blockSignals(True)
            self._fov_slider.setMinimum(lo)
            self._fov_slider.setMaximum(hi)
            self._fov_slider.blockSignals(False)
            self.FOV.set(float(native))

        self._set_status_default()
        self.on_sequence_change()

    def load_nifti_region(self) -> None:
        """Load a single segmented NIfTI label mask via a file dialog."""
        fp, _ = QFileDialog.getOpenFileName(
            self, "Load segmented NIfTI mask", os.path.expanduser("~"),
            "NIfTI (*.nii *.nii.gz);;All Files (*.*)")
        if fp:
            self._load_mask_path(fp)

    def _load_mask_path(self, fp: str, label: str | None = None, scheme: str = "auto") -> None:
        """Shared loader: remap a mask file into a region and make it active."""
        try:
            import nifti_region as nrg
            self.statusBar().showMessage("Loading segmentation\u2026"); QApplication.processEvents()  # type: ignore[union-attr]
            nrg.register_properties()
            vol = nrg.load_segmented_nifti(fp, scheme=scheme)
            base = os.path.basename(fp).split(".")[0]
            name = "Real: " + (f"{label} ({base})" if label else base)
            self._region_cache[name] = vol
            self._region_sequences[name] = ["Spin Echo", "FSE / TSE",
                                            "Gradient Echo", "Inversion Recovery"]
            combo = self._region_dd._combo
            if combo.findText(name) < 0:
                combo.addItem(name)
            combo.setCurrentText(name)
            self.region.set(name)
            self.on_region_change()
            self.statusBar().showMessage(f"Loaded {name}  {vol.shape}")  # type: ignore[union-attr]
        except ImportError:
            self.statusBar().showMessage("Install nibabel:  pip3 install --user nibabel")  # type: ignore[union-attr]
        except Exception as e:
            self.statusBar().showMessage(f"Load failed: {str(e)[:60]}")  # type: ignore[union-attr]

    def browse_masks(self) -> None:
        """Pick a mask folder, index it by body region, and choose from a list."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder of NIfTI masks", os.path.expanduser("~"))
        if not folder:
            return
        try:
            import region_index as rix
        except ImportError:
            self.statusBar().showMessage("region_index.py missing"); return  # type: ignore[union-attr]

        # Scan with a cancelable progress dialog (cache makes re-scans instant)
        files = rix._mask_files(folder)
        if not files:
            self.statusBar().showMessage("No .nii/.nii.gz files in that folder"); return  # type: ignore[union-attr]
        prog = QProgressDialog("Indexing masks by body region\u2026", "Cancel", 0, len(files), self)
        prog.setWindowTitle("Scanning"); prog.setMinimumDuration(0)
        cancelled = {"v": False}

        def cb(i: int, total: int, fn: str) -> None:
            prog.setValue(i); prog.setLabelText(f"Scanning {fn}  ({i}/{total})")
            QApplication.processEvents()
            if prog.wasCanceled():
                cancelled["v"] = True
                raise KeyboardInterrupt
        try:
            entries = rix.build_index(folder, progress=cb)
        except KeyboardInterrupt:
            self.statusBar().showMessage("Indexing cancelled"); return  # type: ignore[union-attr]
        finally:
            prog.setValue(len(files))
        if cancelled["v"]:
            return
        self._show_mask_picker(entries)

    def _show_mask_picker(self, entries: list) -> None:
        """Modal dialog: filter masks by region and load the chosen one."""
        import region_index as rix
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose a mask by body region")
        dlg.resize(560, 520)
        dlg.setStyleSheet("QDialog{background:#1f242b;} QLabel{color:#dfe3e8;}")
        v = QVBoxLayout(dlg)

        counts = rix.regions_summary(entries)
        regions = ["All"] + list(counts.keys())
        filt = QComboBox()
        filt.addItems([r if r == "All" else f"{r}  ({counts[r]})" for r in regions])
        v.addWidget(QLabel("Filter by region:")); v.addWidget(filt)

        listw = QListWidget()
        listw.setStyleSheet("QListWidget{background:#15181c;color:#dfe3e8;} "
                            "QListWidget::item:selected{background:#1bb8ad;}")
        v.addWidget(listw, stretch=1)

        def populate() -> None:
            listw.clear()
            sel = regions[filt.currentIndex()]
            for e in entries:
                if sel != "All" and e["region"] != sel:
                    continue
                it = QListWidgetItem(f"[{e['region']}]  {e['file']}\n      {e['anatomy']}")
                it.setData(0x0100, e["path"])   # Qt.UserRole
                listw.addItem(it)
            v_label.setText(f"{listw.count()} mask(s)")

        v_label = QLabel("")
        v.addWidget(v_label)
        filt.currentIndexChanged.connect(populate)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Load selected"); cancel_btn = QPushButton("Cancel")
        load_btn.setStyleSheet("background:#1bb8ad;color:white;padding:6px;border-radius:4px;")
        cancel_btn.setStyleSheet("background:#4a4a4a;color:white;padding:6px;border-radius:4px;")
        btn_row.addStretch(1); btn_row.addWidget(cancel_btn); btn_row.addWidget(load_btn)
        v.addLayout(btn_row)

        chosen = {"path": None, "region": None, "scheme": "auto"}

        def do_load() -> None:
            it = listw.currentItem()
            if it is None:
                return
            chosen["path"] = it.data(0x0100)
            for e in entries:
                if e["path"] == chosen["path"]:
                    chosen["region"] = e["region"]
                    chosen["scheme"] = e.get("scheme", "auto")
                    break
            dlg.accept()

        load_btn.clicked.connect(do_load)
        cancel_btn.clicked.connect(dlg.reject)
        listw.itemDoubleClicked.connect(lambda _it: do_load())
        populate()
        if dlg.exec() and chosen["path"]:
            self._load_mask_path(chosen["path"], label=chosen["region"],
                                 scheme=str(chosen["scheme"]))

    def _on_orient_radio(self, checked: bool, orient: str) -> None:
        if checked:
            self.orientation.set(orient)
            self.on_orientation_change()

    def on_preset_change(self) -> None:
        name = self.preset_name.get()
        if name in ["(Custom)", ""]:
            self.desc_label.config(text=""); return
        p = get_preset(name)
        if not p: return
        region = get_preset_region(name)
        if region and region != self.region.get():
            self.region.set(region); self.on_region_change()
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
        self.desc_label.config(text=p.get("description", ""))
        self.on_sequence_change()
        # on_sequence_change resets TR/TE/etl for FSE; re-apply preset values
        self.TR.set(float(p["TR"])); self.TE.set(float(p["TE"]))
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
        _map = {"Brain": 220.0, "Abdomen": 380.0, "Spine": 380.0, "Pelvis": 380.0,
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
    def export_current_image(self) -> None:
        from export import export_image
        img, _ = self.simulate_with_params(self.get_current_params())
        self.compare_status.config(text=f"Saved: {os.path.basename(export_image(img, params=self.get_current_params()))}", fg='#69db7c')

    def export_current_protocol(self) -> None:
        from export import export_protocol
        self.compare_status.config(text=f"Saved: {os.path.basename(export_protocol(self.get_current_params()))}", fg='#69db7c')

    def export_current_report(self) -> None:
        from export import export_report
        p = self.get_current_params(); img, m = self.simulate_with_params(p)
        self.compare_status.config(text=f"Saved: {os.path.basename(export_report(img, p, m))}", fg='#69db7c')

    def load_protocol_file(self) -> None:
        from export import load_protocol
        fp, _ = QFileDialog.getOpenFileName(self, "Load Protocol",
                                            os.path.expanduser('~/mrisim/exports'),
                                            "JSON (*.json);;All Files (*.*)")
        if not fp:
            return
        try:
            p = load_protocol(fp)
            for k, v in [("sequence", self.sequence_type), ("TR", self.TR), ("TE", self.TE), ("TI", self.TI),
                         ("flip_angle", self.flip_angle), ("matrix_size", self.matrix_size), ("FOV", self.FOV),
                         ("fov_fraction", self.fov_fraction), ("bandwidth", self.bandwidth), ("NEX", self.NEX),
                         ("b_value", self.b_value), ("diff_direction", self.diff_direction), ("diff_display", self.diff_display),
                         ("angio_type", self.angio_type), ("angio_mip_slab", self.angio_mip_slab),
                         ("fmri_display", self.fmri_display), ("fmri_volumes", self.fmri_volumes), ("fmri_threshold", self.fmri_threshold)]:
                if k in p:
                    v.set(p[k])
            self.compare_status.config(text=f"Loaded: {os.path.basename(fp)}", fg='#69db7c'); self.on_sequence_change()
        except Exception as e:
            self.compare_status.config(text=f"Error: {str(e)[:30]}", fg='#ff6b6b')

    def run(self) -> None:
        self.show()
        # Default the controls/measurements split once real heights are known:
        # give Measurements ~300px and the parameter cards the rest.
        h = max(self.right_split.height(), 600)
        self.right_split.setSizes([h - 300, 300])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)
    win = MRISimulator()
    win.run()
    sys.exit(app.exec())
