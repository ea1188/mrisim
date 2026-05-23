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

# Force matplotlib's Qt backend onto PyQt6 before it is imported.
os.environ.setdefault("QT_API", "PyQt6")

import numpy as np

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QComboBox, QCheckBox, QRadioButton, QButtonGroup, QFrame, QScrollArea,
    QVBoxLayout, QHBoxLayout, QFileDialog,
    QDialog, QListWidget, QListWidgetItem, QProgressDialog,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from psd import draw_psd

from signal_engine import spin_echo_signal, gradient_echo_signal, inversion_recovery_signal
from phantom3d import get_slice, simulate_slice, TISSUE_PROPERTIES_3D
from kspace import simulate_acquisition, get_kspace_display
from brainweb_loader import get_brainweb_or_synthetic
from phantom3d_extended import (add_vessels_3d, add_activation_3d,
                                simulate_diffusion_3d_slice, simulate_adc_map_3d, simulate_fa_map_3d,
                                simulate_tof_3d_slice, simulate_fmri_3d_slice,
                                compute_activation_map_3d, compute_tstat_map_3d,
                                get_diffusion_properties_3d, load_real_tof_mra, simulate_tof_with_real_data)
from fmri import compute_temporal_snr
from presets import PRESETS, get_preset_names, get_preset, estimate_sar
from artifacts import (add_motion_artifact, add_chemical_shift_artifact,
                       add_susceptibility_artifact, add_zipper_artifact,
                       calculate_chemical_shift_pixels)
from fse import simulate_fse_image, fse_scan_time, compute_fse_echo_train
from acceleration import apply_parallel_imaging, compute_acceleration_metrics, apply_compressed_sensing


# --------------------------------------------------------------------------- #
#  Compatibility shims
# --------------------------------------------------------------------------- #
class Var:
    """Drop-in replacement for tk.*Var. Holds a value and notifies callbacks."""
    __slots__ = ("_value", "_callbacks")

    def __init__(self, value):
        self._value = value
        self._callbacks = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for cb in self._callbacks:
            cb()

    def trace_add(self, _mode, callback):
        # tk passes (name, index, mode) to the callback; we ignore them.
        self._callbacks.append(lambda: callback())


class DLabel(QLabel):
    """QLabel with a tk-style .config(text=, fg=) method and a preserved base style."""
    def __init__(self, text="", base_style="", parent=None):
        super().__init__(text, parent)
        self._base = base_style
        if base_style:
            self.setStyleSheet(base_style)

    def config(self, text=None, fg=None):
        if text is not None:
            self.setText(text)
        if fg is not None:
            self.setStyleSheet(self._base + f"color:{fg};")


def _fmt(val):
    """Match the Tkinter slider label formatting."""
    if isinstance(val, float):
        return f"{val:.0f}"
    return str(val)


# --------------------------------------------------------------------------- #
#  Style
# --------------------------------------------------------------------------- #
GLOBAL_QSS = """
QMainWindow { background-color: #1e1e1e; }
QLabel { color: #e0e0e0; font-family: Helvetica, Arial, sans-serif; }
QScrollArea { background-color: #2d2d2d; border: none; }
QSlider::groove:horizontal { height: 4px; background: #555555; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4a9eff; border-radius: 2px; }
QSlider::handle:horizontal { background: #4a9eff; width: 14px; margin: -6px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #6cb2ff; }
QComboBox { background: #3a3a3a; border: 1px solid #555; padding: 3px 6px; border-radius: 3px; color: white; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #2d2d2d; color: white; selection-background-color: #4a9eff; }
QCheckBox, QRadioButton { color: #e0e0e0; spacing: 5px; }
QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; }
QPushButton { background: #4a4a4a; color: white; border: none; padding: 5px 8px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background: #5a5a5a; }
QPushButton:pressed { background: #3a3a3a; }
QScrollBar:vertical { background: #2d2d2d; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #555; border-radius: 5px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class MRISimulator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MRI Simulation Platform")
        self.resize(1400, 850)

        print("Loading 3D phantom...")
        self.phantom_3d, self.phantom_source = get_brainweb_or_synthetic()
        self.phantom_3d_vessels = add_vessels_3d(self.phantom_3d)
        self.activation_3d = add_activation_3d(self.phantom_3d)
        self.real_tof = load_real_tof_mra()
        print(f"Ready. ({self.phantom_source})")

        # Region registry: add body tissue properties to the engine, cache the
        # loaded brain volume, and lazily build other regions on first use.
        import body_phantoms
        self._body_phantoms = body_phantoms
        body_phantoms.merge_into_engine()
        self._brain_volume = self.phantom_3d
        self._region_cache = {"Brain": self.phantom_3d}
        self._region_sequences = {}

        # --- State variables (Var shim instead of tk.*Var) ---
        self.region = Var("Brain")
        self.sequence_type = Var("Spin Echo")
        self.preset_name = Var("")
        self.TR = Var(500.0)
        self.TE = Var(15.0)
        self.TI = Var(150.0)
        self.flip_angle = Var(90.0)
        self.NEX = Var(1)
        self.matrix_size = Var(256)
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
        self.inplane_fov_frac = Var(1.0)
        self.inplane_off = Var(0.0)

        self.orientation = Var("axial")
        self.slice_idx = Var(90)

        # FSE
        self.etl = Var(1)
        self.echo_spacing = Var(10.0)

        # Acceleration
        self.accel_factor = Var(1)
        self.accel_method = Var("SENSE")

        # Diffusion
        self.b_value = Var(1000.0)
        self.diff_direction = Var("Left-Right")
        self.diff_display = Var("DWI")

        # MRA
        self.angio_type = Var("TOF")
        self.angio_mip_slab = Var(20)
        self.venc = Var(80.0)
        self.flow_velocity = Var(60.0)
        self.angio_display = Var("Magnitude")

        # fMRI
        self.fmri_display = Var("EPI Image")
        self.fmri_volumes = Var(100)
        self.fmri_threshold = Var(3.0)

        # Artifacts
        self.motion_enabled = Var(False)
        self.motion_amplitude = Var(3.0)
        self.motion_type = Var("periodic")
        self.chemical_shift_enabled = Var(False)
        self.susceptibility_enabled = Var(False)
        self.susceptibility_strength = Var(3.0)
        self.zipper_enabled = Var(False)

        # Comparison
        self.compare_mode = Var(False)
        self.compare_params = None

        # Debounced recalculate timer (replaces root.after)
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.timeout.connect(self.recalculate)

        # Window/level
        self.window_width = 1.0
        self.window_level = 0.5
        self.current_image = None
        self.current_title = ""
        self.wl_dragging = False
        self.wl_start_x = 0
        self.wl_start_y = 0

        # Reference protocol for the physical SNR model: the "Noise Level"
        # slider equals the tissue-average SNR at this protocol, and every
        # other parameter scales SNR relative to it via real proportionalities.
        self._VOX_REF = (240.0 / 256.0) ** 2 * 5.0   # ~4.39 mm^3 (240 FOV, 256 matrix, 5 mm)
        self._BW_REF = 125000.0                       # 125 kHz receiver bandwidth (Hz)

        self.build_ui()

    # ------------------------------------------------------------------ #
    #  Layout
    # ------------------------------------------------------------------ #
    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(2, 2, 2, 2)
        root_layout.setSpacing(2)

        # Left panel — scrollable controls
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setFixedWidth(290)
        self.left_scroll.setStyleSheet("QScrollArea { background:#2d2d2d; border:none; }")
        self.controls_host = QWidget()
        self.controls_host.setStyleSheet("background:#2d2d2d;")
        self.controls_layout = QVBoxLayout(self.controls_host)
        self.controls_layout.setContentsMargins(6, 6, 6, 6)
        self.controls_layout.setSpacing(3)
        self.left_scroll.setWidget(self.controls_host)

        # Center panel — image + PSD canvases
        self.center_panel = QWidget()
        self.center_panel.setStyleSheet("background:#1e1e1e;")
        self.center_layout = QHBoxLayout(self.center_panel)
        self.center_layout.setContentsMargins(4, 4, 4, 4)
        self.center_layout.setSpacing(4)

        # Right panel — metrics
        self.right_panel = QWidget()
        self.right_panel.setFixedWidth(260)
        self.right_panel.setStyleSheet("background:#2d2d2d;")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(8, 8, 8, 8)
        self.right_layout.setSpacing(2)

        root_layout.addWidget(self.left_scroll)
        root_layout.addWidget(self.center_panel, stretch=1)
        root_layout.addWidget(self.right_panel)

        self.build_image_display()
        self.build_metrics_panel()
        self.build_controls()
        self.recalculate()

    def build_image_display(self):
        # Scout / FOV-planning figure (left of the main image, hidden by default)
        self.scout_fig = Figure(figsize=(3.5, 5), facecolor="#1e1e1e")
        self.scout_ax = self.scout_fig.add_subplot(111)
        self.scout_ax.set_facecolor("#1e1e1e")
        self.scout_canvas = FigureCanvas(self.scout_fig)
        self.scout_canvas.setVisible(False)
        self.center_layout.addWidget(self.scout_canvas, stretch=2)
        self.scout_canvas.mpl_connect("button_press_event", self._scout_press)
        self.scout_canvas.mpl_connect("motion_notify_event", self._scout_motion)
        self.scout_canvas.mpl_connect("button_release_event", self._scout_release)
        self._scout_drag = None      # active drag state dict
        self._scout_box_info = None   # last drawn box geometry (for hit-testing)

        # Main image figure
        self.fig = Figure(figsize=(10, 5), facecolor="#1e1e1e")
        self.axes = self.fig.subplots(1, 2)
        self.fig.subplots_adjust(wspace=0.3)
        for ax in self.axes:
            ax.set_facecolor("#1e1e1e")
        self.canvas = FigureCanvas(self.fig)
        self.center_layout.addWidget(self.canvas, stretch=3)

        # PSD figure (conditionally shown)
        self.psd_fig = Figure(figsize=(4, 5), facecolor="#1e1e1e")
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
        self.statusBar().setStyleSheet("color:#cccccc; background:#262626;")
        self._set_status_default()

    def _ensure_1x2_layout(self):
        """Restore the normal 1x2 subplot layout if the figure has a different configuration."""
        if len(self.fig.axes) != 2:
            self.fig.clear()
            self.axes = self.fig.subplots(1, 2)
            self.fig.subplots_adjust(wspace=0.3)
            for ax in self.axes:
                ax.set_facecolor("#1e1e1e")

    # --- Window/level (matplotlib event handlers) ---
    def _on_press(self, event):
        # Double-click left = reset
        if event.button == 1 and getattr(event, "dblclick", False):
            self.window_width = 1.0
            self.window_level = 0.5
            if self.current_image is not None:
                self.apply_window_level()
            return
        ctrl = False
        try:
            if event.guiEvent is not None:
                ctrl = bool(event.guiEvent.modifiers() & Qt.KeyboardModifier.ControlModifier)
        except Exception:
            ctrl = False
        # Middle / right drag, or Ctrl+left drag, adjusts W/L
        if event.button in (2, 3) or (event.button == 1 and ctrl):
            self.wl_dragging = True
            self.wl_start_x = event.x
            self.wl_start_y = event.y

    def _on_motion(self, event):
        # Live cursor readout (only over the main image axis) when not dragging
        if not self.wl_dragging:
            self._update_readout(event)
            return
        if self.current_image is None:
            return
        if event.x is None or event.y is None:
            return
        self.window_width += (event.x - self.wl_start_x) * 0.005
        # matplotlib's y grows upward (opposite of Tk), so '+=' preserves drag direction
        self.window_level += (event.y - self.wl_start_y) * 0.003
        self.window_width = np.clip(self.window_width, 0.05, 3.0)
        self.window_level = np.clip(self.window_level, 0.0, 1.0)
        self.wl_start_x = event.x
        self.wl_start_y = event.y
        self.apply_window_level()

    def _on_release(self, event):
        self.wl_dragging = False

    # --- Workstation navigation -------------------------------------------- #
    def _change_slice(self, delta):
        """Step the current slice by +/- delta, clamped to the volume bounds."""
        max_sl = self.get_max_slice_idx()
        new_idx = int(np.clip(self.slice_idx.get() + delta, 0, max_sl))
        if new_idx != self.slice_idx.get():
            self.slice_idx.set(new_idx)   # updates the slider via its trace
            self.recalculate()             # immediate feedback while scrolling

    def _on_scroll(self, event):
        # Wheel up = next slice, wheel down = previous (radiology convention)
        step = 1 if event.button == "up" else -1
        # event.step carries magnitude on trackpads; use its sign if present
        if getattr(event, "step", 0):
            step = 1 if event.step > 0 else -1
        self._change_slice(step)

    def _on_key(self, event):
        k = (event.key or "").lower()
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

    def _set_status_default(self):
        self.statusBar().showMessage(
            "Wheel / \u2191\u2193 : slice   \u2022   Ctrl+drag : window/level   \u2022   "
            "double-click : reset   \u2022   k / m / p : k-space / multi / PSD")

    def _update_readout(self, event):
        if self.current_image is None or event.inaxes is not self.axes[0]:
            self._set_status_default()
            return
        if event.xdata is None or event.ydata is None:
            return
        img = self.current_image
        H, W = img.shape[:2]
        col = int(np.clip(round(event.xdata), 0, W - 1))
        row = int(np.clip(round(event.ydata), 0, H - 1))
        signal = float(img[row, col])

        # Map the cursor's fractional position onto the phantom label volume,
        # which may differ in matrix size from the reconstructed image.
        tissue = ""
        try:
            ph = get_slice(self.phantom_3d, self.orientation.get(), self.slice_idx.get())
            py = int(np.clip(round(event.ydata / H * ph.shape[0]), 0, ph.shape[0] - 1))
            px = int(np.clip(round(event.xdata / W * ph.shape[1]), 0, ph.shape[1] - 1))
            label = int(round(float(ph[py, px])))
            import phantom3d
            props = phantom3d.TISSUE_PROPERTIES_3D.get(label)
            tissue = props["name"] if props else f"Tissue {label}"
        except Exception:
            tissue = "n/a"

        self.statusBar().showMessage(
            f"({col}, {row})   \u2022   {tissue}   \u2022   signal: {signal:.3f}   "
            f"\u2022   slice {self.slice_idx.get()}/{self.get_max_slice_idx()}")

    def apply_window_level(self):
        if self.current_image is None:
            return
        img = self.current_image
        max_val = np.max(img) if np.max(img) > 0 else 1
        center = self.window_level * max_val
        width = self.window_width * max_val
        self.axes[0].clear()
        self.axes[0].imshow(img, cmap="gray", origin="lower", vmin=center - width / 2, vmax=center + width / 2)
        self.axes[0].set_title(self.current_title, color="white", fontsize=10)
        self.axes[0].set_axis_off()
        self.axes[0].text(0.02, 0.02, f"W:{width:.3f} L:{center:.3f}", transform=self.axes[0].transAxes,
                          color="yellow", fontsize=8, va="bottom")
        self.canvas.draw()

    # ------------------------------------------------------------------ #
    #  Widget factory helpers
    # ------------------------------------------------------------------ #
    def _section_label(self, parent_layout, text, big=False):
        if big:
            style = "font-size:15px; font-weight:bold; color:white;"
        else:
            style = "font-size:11px; font-weight:bold; color:#aaaaaa;"
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        parent_layout.addWidget(lbl)
        return lbl

    def _separator(self, parent_layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background:#555; max-height:1px; border:none;")
        parent_layout.addWidget(line)

    def _slider(self, parent_layout, label, var, mn, mx):
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(4, 1, 4, 1)
        v.setSpacing(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("color:#cccccc; font-size:11px;")
        val_lbl = QLabel(_fmt(var.get()))
        val_lbl.setStyleSheet("color:white; font-size:11px; font-weight:bold;")
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

        def on_change(value):
            var.set(float(value) if is_float else int(value))
            val_lbl.setText(_fmt(var.get()))
            self.schedule_recalculate()

        s.valueChanged.connect(on_change)

        def sync():
            iv = int(round(var.get()))
            if s.value() != iv:
                s.blockSignals(True)
                s.setValue(iv)
                s.blockSignals(False)
            val_lbl.setText(_fmt(var.get()))

        var.trace_add("write", sync)
        parent_layout.addWidget(container)
        container._qslider = s
        return container

    def _dropdown(self, parent_layout, label, var, options, on_select, inline=False):
        container = QWidget()
        if inline:
            lay = QHBoxLayout(container)
            lay.setContentsMargins(4, 1, 4, 1)
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#cccccc; font-size:11px;")
            lay.addWidget(lbl)
            lay.addStretch(1)
        else:
            lay = QVBoxLayout(container)
            lay.setContentsMargins(4, 2, 4, 2)
            lay.setSpacing(1)
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#cccccc; font-size:11px;")
            lay.addWidget(lbl)

        combo = QComboBox()
        combo.addItems(list(options))
        if var.get() in options:
            combo.setCurrentText(var.get())
        if inline:
            combo.setMaximumWidth(120)
        lay.addWidget(combo)

        def on_text(text):
            var.set(text)
            on_select()

        combo.currentTextChanged.connect(on_text)

        def sync():
            if combo.currentText() != var.get() and var.get() in options:
                combo.blockSignals(True)
                combo.setCurrentText(var.get())
                combo.blockSignals(False)

        var.trace_add("write", sync)
        parent_layout.addWidget(container)
        container._combo = combo
        return container

    def _checkbox(self, parent_layout, text, var):
        cb = QCheckBox(text)
        cb.setChecked(bool(var.get()))

        def on_toggle(checked):
            var.set(bool(checked))
            self.schedule_recalculate()

        cb.toggled.connect(on_toggle)

        def sync():
            if cb.isChecked() != bool(var.get()):
                cb.blockSignals(True)
                cb.setChecked(bool(var.get()))
                cb.blockSignals(False)

        var.trace_add("write", sync)
        parent_layout.addWidget(cb)
        return cb

    def _button(self, parent_layout_or_row, text, command, color="#4a4a4a"):
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
    def build_controls(self):
        L = self.controls_layout

        self._section_label(L, "MRI Simulator", big=True)
        self._dropdown(L, "Preset", self.preset_name, ["(Custom)"] + get_preset_names(), self.on_preset_change)
        self._seq_dropdown = self._dropdown(L, "Sequence", self.sequence_type,
                       ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
                        "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)"], self.on_sequence_change)
        self.desc_label = DLabel("", base_style="color:#888888; font-size:9px;")
        self.desc_label.setWordWrap(True)
        L.addWidget(self.desc_label)

        self._separator(L)
        self._section_label(L, "Comparison")
        crow = QHBoxLayout()
        self._button(crow, "Set as A", self.set_protocol_a, color="#4a9eff")
        self._button(crow, "Compare A\u2194B", self.toggle_compare)
        self._button(crow, "Clear", self.clear_compare)
        cwrap = QWidget(); cwrap.setLayout(crow); crow.setContentsMargins(4, 2, 4, 2)
        L.addWidget(cwrap)
        self.compare_status = DLabel("No comparison set", base_style="color:#666666; font-size:9px;")
        L.addWidget(self.compare_status)

        self._separator(L)
        self._section_label(L, "3D Navigation")
        self._region_dd = self._dropdown(L, "Region", self.region, self._body_phantoms.REGION_NAMES,
                       self.on_region_change, inline=True)
        rl_row = QHBoxLayout(); rl_row.setContentsMargins(4, 0, 4, 2)
        self._button(rl_row, "Browse Masks\u2026", self.browse_masks, color="#4a9eff")
        self._button(rl_row, "Load File\u2026", self.load_nifti_region)
        rlwrap = QWidget(); rlwrap.setLayout(rl_row); L.addWidget(rlwrap)
        orow = QHBoxLayout()
        orow.setContentsMargins(4, 2, 4, 2)
        self._orient_group = QButtonGroup(self)
        for orient, label in [("axial", "Ax"), ("sagittal", "Sag"), ("coronal", "Cor")]:
            rb = QRadioButton(label)
            rb.setChecked(self.orientation.get() == orient)
            rb.toggled.connect(lambda checked, o=orient: self._on_orient_radio(checked, o))
            self._orient_group.addButton(rb)
            orow.addWidget(rb)
        orow.addStretch(1)
        owrap = QWidget(); owrap.setLayout(orow)
        L.addWidget(owrap)
        self._slice_slider = self._slider(L, "Slice", self.slice_idx, 0, 180)._qslider
        self._checkbox(L, "Multi-slice (3x3 grid)", self.multi_slice)
        self._checkbox(L, "FOV Planning (scout)", self.fov_planning)
        self.fov_planning.trace_add("write", self.on_fov_planning_toggle)
        self.plan_frame = QWidget()
        plan_l = QVBoxLayout(self.plan_frame)
        plan_l.setContentsMargins(0, 0, 0, 0); plan_l.setSpacing(1)
        self._slider(plan_l, "# Slices", self.n_slices, 1, 32)
        self._slider(plan_l, "Slice Gap (vox)", self.slice_gap, 0, 20)
        hint2 = QLabel("Scout: drag box = move \u2022 edges = FOV / coverage")
        hint2.setStyleSheet("color:#666666; font-size:9px;")
        plan_l.addWidget(hint2)
        L.addWidget(self.plan_frame)
        self.plan_frame.setVisible(False)

        self._separator(L)
        self._section_label(L, "Timing")
        self.tr_slider = self._slider(L, "TR (ms)", self.TR, 50, 10000)
        self.te_slider = self._slider(L, "TE (ms)", self.TE, 5, 300)
        self.ti_frame = self._slider(L, "TI (ms)", self.TI, 50, 4000)
        self.fa_frame = self._slider(L, "Flip Angle", self.flip_angle, 1, 90)

        # FSE controls
        self.fse_frame = QWidget()
        fse_l = QVBoxLayout(self.fse_frame); fse_l.setContentsMargins(0, 0, 0, 0); fse_l.setSpacing(1)
        self._slider(fse_l, "Echo Train Length", self.etl, 1, 32)
        self._slider(fse_l, "Echo Spacing (ms)", self.echo_spacing, 5, 20)
        L.addWidget(self.fse_frame)

        # Diffusion controls
        self.diff_frame = QWidget()
        diff_l = QVBoxLayout(self.diff_frame); diff_l.setContentsMargins(0, 0, 0, 0); diff_l.setSpacing(1)
        self._slider(diff_l, "b-value (s/mm\u00b2)", self.b_value, 0, 3000)
        self._dropdown(diff_l, "Direction", self.diff_direction, ["Left-Right", "Up-Down", "Diagonal"], self.schedule_recalculate)
        self._dropdown(diff_l, "Display", self.diff_display, ["DWI", "ADC Map", "FA Map"], self.schedule_recalculate)
        L.addWidget(self.diff_frame)

        # MRA controls
        self.angio_frame = QWidget()
        angio_l = QVBoxLayout(self.angio_frame); angio_l.setContentsMargins(0, 0, 0, 0); angio_l.setSpacing(1)
        self._dropdown(angio_l, "MRA Type", self.angio_type, ["TOF", "Phase Contrast"], self.schedule_recalculate)
        self._slider(angio_l, "MIP Slab", self.angio_mip_slab, 1, 50)
        self._slider(angio_l, "VENC (cm/s)", self.venc, 10, 200)
        self._slider(angio_l, "Flow Velocity", self.flow_velocity, 10, 150)
        self._dropdown(angio_l, "Display", self.angio_display, ["Magnitude", "Phase", "Speed"], self.schedule_recalculate)
        L.addWidget(self.angio_frame)

        # fMRI controls
        self.fmri_frame = QWidget()
        fmri_l = QVBoxLayout(self.fmri_frame); fmri_l.setContentsMargins(0, 0, 0, 0); fmri_l.setSpacing(1)
        self._dropdown(fmri_l, "Display", self.fmri_display, ["EPI Image", "Activation Map", "T-statistic Map"], self.schedule_recalculate)
        self._slider(fmri_l, "Num Volumes", self.fmri_volumes, 20, 500)
        self._slider(fmri_l, "T-threshold", self.fmri_threshold, 1, 8)
        L.addWidget(self.fmri_frame)

        self._separator(L)
        self._section_label(L, "Spatial / Acquisition")
        self._slider(L, "Matrix Size", self.matrix_size, 32, 256)
        self._slider(L, "FOV Coverage (%)", self.fov_fraction, 50, 100)
        self._slider(L, "FOV (mm)", self.FOV, 100, 500)
        self._slider(L, "Slice Thickness (mm)", self.slice_thickness, 1, 15)
        self._slider(L, "Bandwidth (kHz)", self.bandwidth, 10, 500)
        self._slider(L, "NEX", self.NEX, 1, 8)
        self._slider(L, "Acceleration (R)", self.accel_factor, 1, 4)
        self._dropdown(L, "Accel Method", self.accel_method, ["SENSE", "GRAPPA", "CS"], self.schedule_recalculate, inline=True)

        self._separator(L)
        self._section_label(L, "Artifacts")
        self._checkbox(L, "Motion (ghosting)", self.motion_enabled)
        self._slider(L, "Motion Amplitude", self.motion_amplitude, 1, 15)
        self._dropdown(L, "Motion Type", self.motion_type, ["periodic", "random", "linear"], self.schedule_recalculate, inline=True)
        self._checkbox(L, "Chemical Shift", self.chemical_shift_enabled)
        self._checkbox(L, "Susceptibility", self.susceptibility_enabled)
        self._slider(L, "Susceptibility Strength", self.susceptibility_strength, 1, 10)
        self._checkbox(L, "Zipper (RF leak)", self.zipper_enabled)

        self._separator(L)
        self._section_label(L, "Display")
        self._slider(L, "Noise Level (SNR)", self.snr_level, 5, 100)
        self._checkbox(L, "Show k-space", self.show_kspace)
        hint = QLabel("Wheel/\u2191\u2193: slice | Ctrl+drag: W/L | dbl-click/R: reset")
        hint.setStyleSheet("color:#666666; font-size:9px;")
        L.addWidget(hint)
        self._checkbox(L, "Show Pulse Sequence Diagram", self.show_psd)

        erow = QHBoxLayout()
        erow.setContentsMargins(4, 4, 4, 4)
        self._button(erow, "Save Img", self.export_current_image)
        self._button(erow, "Save Proto", self.export_current_protocol)
        self._button(erow, "PDF", self.export_current_report)
        self._button(erow, "Load", self.load_protocol_file)
        ewrap = QWidget(); ewrap.setLayout(erow)
        L.addWidget(ewrap)

        L.addStretch(1)
        self.on_sequence_change()

    def build_metrics_panel(self):
        title = QLabel("Metrics")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:white;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.right_layout.addWidget(title)

        self.metrics_labels = {}
        for dn, key in [("Scan Time", "scan_time"), ("Resolution", "resolution"), ("Voxel Size", "voxel_size"),
                        ("SNR (WM)", "snr_wm"), ("SNR (GM)", "snr_gm"), ("CNR", "cnr"), ("BW/pixel", "bw_pixel"),
                        ("SAR (W/kg)", "sar"), ("Weighting", "weighting"), ("Matrix", "matrix_display"),
                        ("Slice", "slice_info"), ("ETL / Accel", "etl_accel"), ("Artifacts", "artifacts")]:
            name = QLabel(dn)
            name.setStyleSheet("color:#aaaaaa; font-size:10px;")
            self.right_layout.addWidget(name)
            value = DLabel("--", base_style="font-size:14px; font-weight:bold; color:#4a9eff;")
            self.right_layout.addWidget(value)
            self.metrics_labels[key] = value

        self._separator(self.right_layout)
        self.compare_metrics_label = DLabel("", base_style="color:#aaaaaa; font-size:10px;")
        self.compare_metrics_label.setWordWrap(True)
        self.right_layout.addWidget(self.compare_metrics_label)
        self.right_layout.addStretch(1)

    # ------------------------------------------------------------------ #
    #  Core (unchanged from Tkinter version)
    # ------------------------------------------------------------------ #
    def get_current_params(self):
        return {"sequence": self.sequence_type.get(), "TR": self.TR.get(), "TE": self.TE.get(), "TI": self.TI.get(),
                "flip_angle": self.flip_angle.get(), "matrix_size": self.matrix_size.get(), "FOV": self.FOV.get(),
                "fov_fraction": self.fov_fraction.get(), "bandwidth": self.bandwidth.get(), "NEX": self.NEX.get(),
                "etl": self.etl.get(), "echo_spacing": self.echo_spacing.get(), "accel_factor": self.accel_factor.get(),
                "accel_method": self.accel_method.get(), "b_value": self.b_value.get(),
                "diff_direction": self.diff_direction.get(), "diff_display": self.diff_display.get(),
                "angio_type": self.angio_type.get(), "angio_mip_slab": self.angio_mip_slab.get(),
                "fmri_display": self.fmri_display.get(), "fmri_volumes": self.fmri_volumes.get(),
                "fmri_threshold": self.fmri_threshold.get()}

    def set_protocol_a(self):
        self.compare_params = self.get_current_params()
        self.compare_status.config(text=f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", fg="#4a9eff")
        self.compare_mode.set(True); self.recalculate()

    def toggle_compare(self):
        if not self.compare_params:
            self.compare_status.config(text="Set A first!", fg="#ff6b6b"); return
        self.compare_mode.set(not self.compare_mode.get()); self.recalculate()

    def clear_compare(self):
        self.compare_params = None; self.compare_mode.set(False)
        self.compare_status.config(text="No comparison set", fg="#666666")
        self.compare_metrics_label.config(text=""); self.recalculate()

    def _simulate_single_slice(self, params, orient, sl_idx):
        seq = params["sequence"]; TR = params["TR"]; TE = params["TE"]; TI = params["TI"]; FA = params["flip_angle"]
        if TE >= TR:
            TE = TR - 5
        phantom_slice = get_slice(self.phantom_3d, orient, sl_idx)

        # Graphic FOV prescription: crop the source slice to the boxed field
        # of view so every sequence below inherits the zoom/position.
        if self.fov_planning.get() and self.inplane_fov_frac.get() < 0.999:
            import scan_geometry as sg
            phantom_slice = sg.fov_crop(orient, phantom_slice,
                                        self.inplane_fov_frac.get(),
                                        self.inplane_off.get())

        if seq == "Spin Echo":
            return simulate_slice(phantom_slice, TR, TE, 'SE')
        elif seq == "FSE / TSE":
            return simulate_fse_image(phantom_slice, TR, TE, params["etl"], params["echo_spacing"], TISSUE_PROPERTIES_3D)
        elif seq == "Gradient Echo":
            return simulate_slice(phantom_slice, TR, TE, 'GRE', flip_angle=FA)
        elif seq == "Inversion Recovery":
            return simulate_slice(phantom_slice, TR, TE, 'IR', TI=TI)
        elif seq == "Diffusion (DWI)":
            direction = {"Left-Right": [1, 0], "Up-Down": [0, 1], "Diagonal": [0.707, 0.707]}[params["diff_direction"]]
            if params["diff_display"] == "DWI":
                return simulate_diffusion_3d_slice(phantom_slice, params["b_value"], direction, TR, TE)
            elif params["diff_display"] == "ADC Map":
                return simulate_adc_map_3d(phantom_slice)
            elif params["diff_display"] == "FA Map":
                return simulate_fa_map_3d(phantom_slice)
        elif seq == "MR Angiography":
            if self.real_tof is not None and params["angio_type"] == "TOF":
                return simulate_tof_with_real_data(self.real_tof, orient, sl_idx, TR, TE, FA, params["angio_mip_slab"])
            return simulate_tof_3d_slice(get_slice(self.phantom_3d_vessels, orient, sl_idx), TR, TE, FA)
        elif seq == "fMRI (BOLD)":
            act = get_slice(self.activation_3d, orient, sl_idx)
            if params["fmri_display"] == "EPI Image":
                return simulate_fmri_3d_slice(phantom_slice, act, TR, TE, FA, True)
            elif params["fmri_display"] == "Activation Map":
                return compute_activation_map_3d(phantom_slice, act, TR, TE, FA)
            elif params["fmri_display"] == "T-statistic Map":
                img = compute_tstat_map_3d(phantom_slice, act, TR, TE, FA, params["fmri_volumes"])
                return np.where(img > params["fmri_threshold"], img, 0)
        return np.zeros((181, 181), dtype=float)

    @staticmethod
    def _resize_nn(arr, shape):
        """Nearest-neighbor resize of a label map to `shape` (no scipy needed)."""
        if arr.shape == tuple(shape):
            return arr
        ys = np.clip(np.linspace(0, arr.shape[0] - 1, shape[0]).round().astype(int), 0, arr.shape[0] - 1)
        xs = np.clip(np.linspace(0, arr.shape[1] - 1, shape[1]).round().astype(int), 0, arr.shape[1] - 1)
        return arr[np.ix_(ys, xs)]

    def _aligned_labels(self, recon, phantom_slice):
        """Phantom label map resampled (nearest) to the reconstructed image grid."""
        if phantom_slice.shape == recon.shape:
            return phantom_slice
        return self._resize_nn(phantom_slice, recon.shape)

    def _tissue_ref_signal(self, recon, phantom_slice):
        """Mean signal over brain tissue (CSF/GM/WM) used as the SNR reference level."""
        labels = self._aligned_labels(recon, phantom_slice)
        mask = np.isin(labels, (1, 2, 3))
        if np.any(mask):
            val = float(recon[mask].mean())
            if val > 0:
                return val
        # Fallbacks for non-brain data (e.g. real TOF) with no matching labels
        bright = recon[recon > 0]
        if bright.size:
            return float(bright.mean())
        mx = float(np.max(recon))
        return mx * 0.5 if mx > 0 else 0.0

    def _measure_snr(self, recon, phantom_slice):
        """
        Measure SNR the console way: mean signal in a tissue ROI divided by the
        true noise sigma estimated from a signal-free (air) region.

        In a magnitude image, background noise is Rayleigh-distributed with
        std = sigma * sqrt(2 - pi/2), so we divide by that factor to recover the
        underlying Gaussian sigma. Robust to matrix downsampling (labels are
        resampled to the reconstructed grid) and to data without a background.
        """
        RAYLEIGH = np.sqrt(2.0 - np.pi / 2.0)  # ~0.6551
        labels = self._aligned_labels(recon, phantom_slice)

        bg = recon[labels == 0]
        sigma = None
        if bg.size > 50 and bg.std() > 0:
            sigma = bg.std() / RAYLEIGH
        if sigma is None or sigma <= 0:
            # No usable background: estimate from the dimmest pixels in the frame
            flat = np.sort(recon.ravel())
            low = flat[: max(50, flat.size // 20)]
            sigma = (low.std() / RAYLEIGH) if low.std() > 0 else max(1e-6, float(np.max(recon)) * 1e-3)

        out = {"sigma": float(sigma), "wm": 0.0, "gm": 0.0}
        for name, lab in (("wm", 3), ("gm", 2)):
            roi = recon[labels == lab]
            if roi.size and sigma > 0:
                out[name] = float(roi.mean() / sigma)
        return out

    def simulate_with_params(self, params):
        orient = self.orientation.get(); sl_idx = self.slice_idx.get()
        matrix = params["matrix_size"]; fov_frac = params["fov_fraction"] / 100.0
        thickness = int(self.slice_thickness.get()); R = params["accel_factor"]
        max_sl = self.get_max_slice_idx()

        if thickness > 1 and params["sequence"] not in ["MR Angiography"]:
            start = max(0, sl_idx - thickness // 2); end = min(max_sl, sl_idx + thickness // 2)
            image = np.mean([self._simulate_single_slice(params, orient, s) for s in range(start, end + 1)], axis=0)
        else:
            image = self._simulate_single_slice(params, orient, sl_idx)

        phantom_slice = get_slice(self.phantom_3d, orient, sl_idx)
        is_map = params["sequence"] == "Diffusion (DWI)" and params["diff_display"] in ["ADC Map", "FA Map"]
        is_map = is_map or (params["sequence"] == "fMRI (BOLD)" and params["fmri_display"] in ["Activation Map", "T-statistic Map"])

        if not is_map:
            if self.motion_enabled.get():
                image = add_motion_artifact(image, self.motion_type.get(), self.motion_amplitude.get(), 3)
            if self.chemical_shift_enabled.get() and phantom_slice.shape == image.shape:
                image = add_chemical_shift_artifact(image, phantom_slice, calculate_chemical_shift_pixels(params["bandwidth"] * 1000 / matrix))
            if self.susceptibility_enabled.get() and phantom_slice.shape == image.shape:
                image = add_susceptibility_artifact(image, phantom_slice, self.susceptibility_strength.get() / 10.0)

            reconstructed, _ = simulate_acquisition(image, matrix, fov_frac)

            # Acceleration
            if R > 1:
                method = params["accel_method"]
                if method == "CS":
                    reconstructed = apply_compressed_sensing(reconstructed, R)
                else:
                    reconstructed, _ = apply_parallel_imaging(reconstructed, R, method)

            # --- Physical noise model -------------------------------------
            # Effective image SNR follows standard MRI proportionalities,
            # scaled so the "Noise Level" slider equals the tissue-average SNR
            # at the reference protocol. Then we set the Rician noise sigma so
            # the reconstructed image actually carries that SNR, which lets us
            # MEASURE it back out below the way a tech does on the console.
            res_mm = params["FOV"] / matrix
            vox_vol = res_mm * res_mm * max(1, thickness)
            BW_hz = max(1.0, params["bandwidth"] * 1000.0)
            g_factor = 1.0 + 0.15 * (R - 1) if R > 1 else 1.0
            eff_snr = (self.snr_level.get()
                       * (vox_vol / self._VOX_REF)            # SNR proportional to voxel volume
                       * np.sqrt(max(1, params["NEX"]))       # SNR proportional to sqrt(NEX)
                       * np.sqrt(self._BW_REF / BW_hz)         # SNR proportional to 1/sqrt(receiver BW)
                       / (g_factor * np.sqrt(R)))             # parallel-imaging penalty (g * sqrt(R))
            eff_snr = float(np.clip(eff_snr, 1.0, 1e4))
            tissue_ref = self._tissue_ref_signal(reconstructed, phantom_slice)
            if tissue_ref > 0:
                sigma = tissue_ref / eff_snr
                reconstructed = np.sqrt(
                    (reconstructed + np.random.normal(0, sigma, reconstructed.shape)) ** 2
                    + np.random.normal(0, sigma, reconstructed.shape) ** 2)
            if self.zipper_enabled.get():
                reconstructed = add_zipper_artifact(reconstructed, 0.3, 0.12)
        else:
            reconstructed = image

        # Metrics
        TR, TE, FA = params["TR"], params["TE"], params["flip_angle"]
        FOV, NEX, BW = params["FOV"], params["NEX"], params["bandwidth"] * 1000
        ETL = params["etl"] if params["sequence"] == "FSE / TSE" else 1
        resolution = FOV / matrix; voxel_vol = resolution * resolution * thickness
        scan_time = TR * matrix * NEX / (ETL * R) / 1000
        seq_map = {"Spin Echo": "SE", "FSE / TSE": "SE", "Gradient Echo": "GRE", "Inversion Recovery": "IR",
                   "Diffusion (DWI)": "Diffusion", "MR Angiography": "GRE", "fMRI (BOLD)": "EPI"}
        sar = estimate_sar(FA, TR, sequence=seq_map.get(params["sequence"], "SE"))
        metrics = {"scan_time": scan_time, "resolution": resolution, "snr_wm": 0, "snr_gm": 0,
                   "sar_head": sar["head"], "sar_exceeds": sar["exceeds_limit"]}
        if not is_map:
            snr = self._measure_snr(reconstructed, phantom_slice)
            metrics["snr_wm"] = snr["wm"]
            metrics["snr_gm"] = snr["gm"]
            metrics["noise_sigma"] = snr["sigma"]
        return reconstructed, metrics

    # --- Display ---
    def recalculate(self, *args):
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

        if self.compare_mode.get() and self.compare_params:
            image_a, metrics_a = self.simulate_with_params(self.compare_params)
            self.axes[0].imshow(image_a, cmap="gray", origin="lower")
            self.axes[0].set_title(f"A: {self.compare_params['sequence']} TR={self.compare_params['TR']:.0f}", color="white", fontsize=10); self.axes[0].set_axis_off()
            self.axes[1].imshow(image_b, cmap="gray", origin="lower")
            self.axes[1].set_title(f"B: {current_params['sequence']} TR={current_params['TR']:.0f}", color="white", fontsize=10); self.axes[1].set_axis_off()
            self.update_compare_metrics(metrics_a, metrics_b)
            self.current_image = None
        else:
            self.current_image = image_b
            orient = self.orientation.get(); sl_idx = self.slice_idx.get()
            self.current_title = f"{current_params['sequence']} | TR={current_params['TR']:.0f} TE={current_params['TE']:.0f} | {orient.capitalize()} #{sl_idx}"
            max_val = np.max(image_b) if np.max(image_b) > 0 else 1
            center = self.window_level * max_val; width = self.window_width * max_val
            self.axes[0].imshow(image_b, cmap="gray", origin="lower", vmin=center - width / 2, vmax=center + width / 2)
            self.axes[0].set_title(self.current_title, color="white", fontsize=10); self.axes[0].set_axis_off()
            if self.show_kspace.get():
                from kspace import image_to_kspace
                self.axes[1].imshow(get_kspace_display(image_to_kspace(image_b)), cmap="hot", origin="lower")
                self.axes[1].set_title("k-Space", color="white", fontsize=11); self.axes[1].set_axis_off()
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

    def _display_multi_slice(self, params):
        """Display 3x3 grid of adjacent slices."""
        self.fig.clear()
        axes = self.fig.subplots(3, 3)
        self.fig.subplots_adjust(wspace=0.05, hspace=0.15)

        orient = self.orientation.get()
        center_sl = self.slice_idx.get()
        max_sl = self.get_max_slice_idx()
        spacing = max(1, int(self.slice_thickness.get()))

        for idx, ax in enumerate(axes.flat):
            ax.set_facecolor("#1e1e1e")
            sl = center_sl + (idx - 4) * spacing
            if 0 <= sl <= max_sl:
                image = self._simulate_single_slice(params, orient, sl)
                ax.imshow(image, cmap="gray", origin="lower")
                ax.set_title(f"#{sl}", color="white", fontsize=8)
            ax.set_axis_off()

        self.canvas.draw()
        _, metrics = self.simulate_with_params(params)
        self.update_metrics(params, metrics)
        self.current_image = None

    # ------------------------------------------------------------------ #
    #  FOV planning: prescribed-group display + interactive scout
    # ------------------------------------------------------------------ #
    def _display_prescription(self, params):
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
        for k, ax in enumerate(axes.flat):
            ax.set_facecolor("#1e1e1e"); ax.set_axis_off()
            if k < n:
                img = self._simulate_single_slice(params, orient, idxs[k])
                ax.imshow(img, cmap="gray", origin="lower")
                ax.set_title(f"#{idxs[k]}", color="white", fontsize=8)
        self.fig.suptitle(f"{params['sequence']}  |  {n} slice{'s' if n != 1 else ''}  "
                          f"|  FOV {int(self.inplane_fov_frac.get() * 100)}%",
                          color="white", fontsize=10)
        self.canvas.draw()
        self.current_image = self._simulate_single_slice(params, orient, self.slice_idx.get()) if n == 1 else None

    def _draw_scout(self, params):
        """Render the localizer in an orthogonal plane with the FOV box overlaid."""
        import scan_geometry as sg
        from matplotlib.patches import Rectangle
        self.scout_canvas.setVisible(True)
        sslice, cfg, depth = sg.scout_slice(self.phantom_3d, self.orientation.get())
        # anatomical-looking localizer: quick balanced SE render of the scout label slice
        scout_img = simulate_slice(sslice, 600, 12, 'SE')

        ax = self.scout_ax
        ax.clear(); ax.set_facecolor("#1e1e1e")
        ax.imshow(scout_img, cmap="gray", origin="lower", aspect="auto")
        ax.set_title(f"Scout ({cfg['scout']})  \u2014  drag to prescribe",
                     color="white", fontsize=9)
        ax.set_axis_off()

        info = sg.box_rect(self.orientation.get(), self.phantom_3d.shape,
                           self.slice_idx.get(), self.n_slices.get(),
                           self.slice_thickness.get(), self.slice_gap.get(),
                           self.inplane_fov_frac.get(), self.inplane_off.get())
        self._scout_box_info = info

        # FOV box
        ax.add_patch(Rectangle((info["x0"], info["y0"]), info["w"], info["h"],
                               fill=False, edgecolor="#34d4ff", linewidth=1.8))
        # Individual slice lines within the group
        for L in info["lines"]:
            if info["line_axis"] == "y":
                ax.plot([info["x0"], info["x0"] + info["w"]], [L, L],
                        color="#34d4ff", linewidth=0.5, alpha=0.55)
            else:
                ax.plot([L, L], [info["y0"], info["y0"] + info["h"]],
                        color="#34d4ff", linewidth=0.5, alpha=0.55)
        # corner handles
        for hx, hy in self._scout_handle_points(info):
            ax.plot(hx, hy, "s", color="#34d4ff", markersize=4)
        self.scout_canvas.draw()

    @staticmethod
    def _scout_handle_points(info):
        x0, y0, w, h = info["x0"], info["y0"], info["w"], info["h"]
        return [(x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)]

    def on_fov_planning_toggle(self):
        on = self.fov_planning.get()
        self.plan_frame.setVisible(on)
        if not on:
            self.scout_canvas.setVisible(False)
            self._ensure_1x2_layout()
        self.recalculate()

    # --- scout mouse interaction ---
    def _scout_hit_test(self, event):
        """Return 'move'|'resize_cov'|'resize_fov' for a press location, or None."""
        info = self._scout_box_info
        if info is None or event.xdata is None or event.ydata is None:
            return None
        x, y = event.xdata, event.ydata
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

        def near_edge(coord, lo, length):
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

    def _scout_press(self, event):
        if not self.fov_planning.get() or event.inaxes is not self.scout_ax:
            return
        mode = self._scout_hit_test(event)
        if mode is None:
            return
        self._scout_drag = dict(mode=mode, x=event.xdata, y=event.ydata)

    def _scout_motion(self, event):
        if self._scout_drag is None or event.xdata is None or event.ydata is None:
            return
        import scan_geometry as sg
        d = self._scout_drag
        dx = event.xdata - d["x"]; dy = event.ydata - d["y"]
        d["x"], d["y"] = event.xdata, event.ydata
        orient = self.orientation.get()
        info = self._scout_box_info
        # Map screen dx/dy onto through vs in-plane drag depending on orientation
        if info["through"] == "v":
            dx_through, d_inplane = dy, dx
        else:
            dx_through, d_inplane = dx, dy
        si, off, fr, n = sg.update_from_drag(
            orient, self.phantom_3d.shape, d["mode"], dx_through, d_inplane,
            self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
            self.slice_gap.get(), self.inplane_fov_frac.get(), self.inplane_off.get())
        self.slice_idx.set(int(round(si)))
        self.inplane_off.set(off)
        self.inplane_fov_frac.set(fr)
        self.n_slices.set(n)
        # redraw box immediately; debounce the heavier acquisition render
        self._draw_scout(self.get_current_params())
        self.schedule_recalculate()

    def _scout_release(self, event):
        if self._scout_drag is not None:
            self._scout_drag = None
            self.recalculate()

    def _plot_curves(self, params):
        seq, TR, TE, TI, FA = params["sequence"], params["TR"], params["TE"], params["TI"], params["flip_angle"]
        from signal_engine import TISSUES
        if seq == "FSE / TSE":
            for tn, color, T1, T2, PD in [("WM", '#ff6b6b', 830, 80, 0.65), ("GM", '#69db7c', 1330, 100, 0.8), ("CSF", '#74c0fc', 4500, 2200, 1.0)]:
                te_vals, sigs = compute_fse_echo_train(T1, T2, PD, TR, params["etl"], params["echo_spacing"])
                self.axes[1].plot(te_vals, sigs, color=color, linewidth=2, label=tn, marker='o', markersize=3)
            self.axes[1].axvline(x=TE, color='yellow', linestyle='--', alpha=0.7, label=f'TE_eff={TE:.0f}')
            self.axes[1].set_xlabel('Echo Time (ms)', color='white'); self.axes[1].set_title('Echo Train Decay', color='white', fontsize=11)
        elif seq == "Diffusion (DWI)":
            b_range = np.arange(0, 3001, 50); dp = get_diffusion_properties_3d(None)
            for name, color, label in [("WM", '#ff6b6b', 3), ("GM", '#69db7c', 2), ("CSF", '#74c0fc', 1)]:
                props = TISSUES[name.lower().replace("wm", "white_matter").replace("gm", "gray_matter")]
                S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
                self.axes[1].plot(b_range, S0 * np.exp(-b_range * dp[label]["ADC"] * 1e-3), color=color, linewidth=2, label=name)
            self.axes[1].axvline(x=params["b_value"], color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('b-value', color='white'); self.axes[1].set_title('Signal vs b-value', color='white', fontsize=11)
        elif seq == "MR Angiography":
            fa_range = np.arange(1, 91, 1)
            for name, color, T1, PD in [("Brain", '#69db7c', 1330, 0.8), ("Blood", '#ff6b6b', 1930, 0.9)]:
                if "Blood" in name:
                    self.axes[1].plot(fa_range, PD * np.sin(np.radians(fa_range)) * np.exp(-TE / 50), color=color, linewidth=2, label=name)
                else:
                    self.axes[1].plot(fa_range, [gradient_echo_signal(T1, 50, PD, TR, TE, fa) for fa in fa_range], color=color, linewidth=2, label=name)
            self.axes[1].axvline(x=FA, color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('FA', color='white'); self.axes[1].set_title('TOF Signal', color='white', fontsize=11)
        elif seq == "fMRI (BOLD)":
            te_range = np.arange(5, 100, 1); bs = te_range * np.exp(-te_range / 60); bs /= bs.max()
            self.axes[1].plot(te_range, bs, color='#ff6b6b', linewidth=2, label='BOLD')
            self.axes[1].plot(te_range, np.exp(-te_range / 60), color='#69db7c', linewidth=2, label='Signal')
            self.axes[1].axvline(x=TE, color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('TE', color='white'); self.axes[1].set_title('BOLD Sensitivity', color='white', fontsize=11)
        else:
            te_range = np.arange(5, min(300, TR), 2)
            for tn, color in [("white_matter", '#ff6b6b'), ("gray_matter", '#69db7c'), ("csf", '#74c0fc')]:
                props = TISSUES[tn]
                if seq == "Spin Echo":
                    sig = props["PD"] * (1 - np.exp(-TR / props["T1"])) * np.exp(-te_range / props["T2"])
                elif seq == "Gradient Echo":
                    a = np.radians(FA); E1 = np.exp(-TR / props["T1"])
                    sig = props["PD"] * np.sin(a) * (1 - E1) / (1 - np.cos(a) * E1) * np.exp(-te_range / (props["T2"] * 0.6))
                else:
                    sig = props["PD"] * np.abs(1 - 2 * np.exp(-TI / props["T1"]) + np.exp(-TR / props["T1"])) * np.exp(-te_range / props["T2"])
                self.axes[1].plot(te_range, sig, color=color, linewidth=2, label=tn.replace("_", " ").title())
            self.axes[1].axvline(x=TE, color='yellow', linestyle='--', alpha=0.7)
            self.axes[1].set_xlabel('TE (ms)', color='white'); self.axes[1].set_title('Signal vs TE', color='white', fontsize=11)
        self.axes[1].set_ylabel('Signal', color='white')
        self.axes[1].legend(fontsize=8, facecolor='#2d2d2d', labelcolor='white')
        self.axes[1].tick_params(colors='white'); self.axes[1].set_facecolor('#1e1e1e')

    def update_compare_metrics(self, ma, mb):
        up, down = "\u2191", "\u2193"

        def d(a, b, u="", f=".1f"):
            diff = b - a; pct = (diff / a * 100) if a != 0 else 0
            arrow = up if diff > 0 else down if diff < 0 else "="
            return f"{arrow} {abs(diff):{f}}{u} ({abs(pct):.0f}%)"
        rule = "\u2500\u2500"
        text = f"{rule} A vs B {rule}\nTime: {d(ma['scan_time'], mb['scan_time'], 's')}\nSNR: {d(ma['snr_wm'], mb['snr_wm'])}\n"
        text += f"Res: {d(ma['resolution'], mb['resolution'], 'mm', '.2f')}\nSAR: A={ma['sar_head']:.1f} B={mb['sar_head']:.1f}"
        self.compare_metrics_label.config(text=text, fg="#ffcc00")

    def update_metrics(self, params, metrics):
        orient = self.orientation.get(); sl_idx = self.slice_idx.get()
        matrix = params["matrix_size"]; thickness = int(self.slice_thickness.get())
        R = params["accel_factor"]; ETL = params["etl"] if params["sequence"] == "FSE / TSE" else 1
        resolution = metrics["resolution"]
        self.metrics_labels["resolution"].config(text=f"{resolution:.2f} mm")
        self.metrics_labels["voxel_size"].config(text=f"{resolution:.2f}x{resolution:.2f}x{thickness}mm")
        self.metrics_labels["matrix_display"].config(text=f"{matrix}x{matrix}")
        self.metrics_labels["slice_info"].config(text=f"{orient.capitalize()} #{sl_idx}")
        st = metrics["scan_time"]; self.metrics_labels["scan_time"].config(text=f"{int(st // 60)}:{int(st % 60):02d}")
        self.metrics_labels["bw_pixel"].config(text=f"{params['bandwidth'] * 1000 / matrix:.1f}")
        self.metrics_labels["snr_wm"].config(text=f"{metrics['snr_wm']:.1f}")
        self.metrics_labels["snr_gm"].config(text=f"{metrics['snr_gm']:.1f}")
        self.metrics_labels["cnr"].config(text=f"{abs(metrics['snr_wm'] - metrics['snr_gm']):.1f}")
        self.metrics_labels["sar"].config(text=f"{metrics['sar_head']:.1f}" + (" \u26a0\ufe0f" if metrics['sar_exceeds'] else ""),
                                          fg='#ff6b6b' if metrics['sar_exceeds'] else '#4a9eff')
        self.metrics_labels["weighting"].config(text=self.determine_weighting(params["TR"], params["TE"], params["sequence"]))
        etl_text = f"ETL={ETL}" if ETL > 1 else ""; accel_text = f"R={R}" if R > 1 else ""
        self.metrics_labels["etl_accel"].config(text=f"{etl_text} {accel_text}".strip() or "None")
        active = []
        if self.motion_enabled.get(): active.append("Motion")
        if self.chemical_shift_enabled.get(): active.append("ChemShift")
        if self.susceptibility_enabled.get(): active.append("Suscept.")
        if self.zipper_enabled.get(): active.append("Zipper")
        if params["fov_fraction"] < 100: active.append("Aliasing")
        if matrix < 128: active.append("Blur")
        if metrics['sar_exceeds']: active.append("SAR!")
        self.metrics_labels["artifacts"].config(text=", ".join(active) if active else "None", fg='#ff6b6b' if active else '#4a9eff')

    def determine_weighting(self, TR, TE, seq):
        if seq == "Diffusion (DWI)": return "Diffusion"
        if seq == "MR Angiography": return "Flow"
        if seq == "fMRI (BOLD)": return "T2* (BOLD)"
        if TR < 800 and TE < 30: return "T1-weighted"
        elif TR > 2000 and TE > 60: return "T2-weighted"
        elif TR > 2000 and TE < 30: return "PD-weighted"
        return "Mixed"

    # ------------------------------------------------------------------ #
    #  UI event helpers
    # ------------------------------------------------------------------ #
    def _refresh_slice_range(self):
        """Match the Slice slider's range to the current volume/orientation."""
        mx = self.get_max_slice_idx()
        s = self._slice_slider
        s.blockSignals(True)
        s.setMaximum(mx)
        if self.slice_idx.get() > mx:
            self.slice_idx.set(mx)
        s.setValue(int(self.slice_idx.get()))
        s.blockSignals(False)

    def on_region_change(self):
        name = self.region.get()
        if name not in self._region_cache:
            self.statusBar().showMessage(f"Building {name} phantom\u2026")
            QApplication.processEvents()
            self._region_cache[name] = self._body_phantoms.build_region(name)
        self.phantom_3d = self._region_cache[name]

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
        self._set_status_default()
        self.on_sequence_change()

    def load_nifti_region(self):
        """Load a single segmented NIfTI label mask via a file dialog."""
        fp, _ = QFileDialog.getOpenFileName(
            self, "Load segmented NIfTI mask", os.path.expanduser("~"),
            "NIfTI (*.nii *.nii.gz);;All Files (*.*)")
        if fp:
            self._load_mask_path(fp)

    def _load_mask_path(self, fp, label=None, scheme="auto"):
        """Shared loader: remap a mask file into a region and make it active."""
        try:
            import nifti_region as nrg
            self.statusBar().showMessage("Loading segmentation\u2026"); QApplication.processEvents()
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
            self.statusBar().showMessage(f"Loaded {name}  {vol.shape}")
        except ImportError:
            self.statusBar().showMessage("Install nibabel:  pip3 install --user nibabel")
        except Exception as e:
            self.statusBar().showMessage(f"Load failed: {str(e)[:60]}")

    def browse_masks(self):
        """Pick a mask folder, index it by body region, and choose from a list."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder of NIfTI masks", os.path.expanduser("~"))
        if not folder:
            return
        try:
            import region_index as rix
        except ImportError:
            self.statusBar().showMessage("region_index.py missing"); return

        # Scan with a cancelable progress dialog (cache makes re-scans instant)
        files = rix._mask_files(folder)
        if not files:
            self.statusBar().showMessage("No .nii/.nii.gz files in that folder"); return
        prog = QProgressDialog("Indexing masks by body region\u2026", "Cancel", 0, len(files), self)
        prog.setWindowTitle("Scanning"); prog.setMinimumDuration(0)
        cancelled = {"v": False}

        def cb(i, total, fn):
            prog.setValue(i); prog.setLabelText(f"Scanning {fn}  ({i}/{total})")
            QApplication.processEvents()
            if prog.wasCanceled():
                cancelled["v"] = True
                raise KeyboardInterrupt
        try:
            entries = rix.build_index(folder, progress=cb)
        except KeyboardInterrupt:
            self.statusBar().showMessage("Indexing cancelled"); return
        finally:
            prog.setValue(len(files))
        if cancelled["v"]:
            return
        self._show_mask_picker(entries)

    def _show_mask_picker(self, entries):
        """Modal dialog: filter masks by region and load the chosen one."""
        import region_index as rix
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose a mask by body region")
        dlg.resize(560, 520)
        dlg.setStyleSheet("QDialog{background:#2d2d2d;} QLabel{color:#ddd;}")
        v = QVBoxLayout(dlg)

        counts = rix.regions_summary(entries)
        regions = ["All"] + list(counts.keys())
        filt = QComboBox()
        filt.addItems([r if r == "All" else f"{r}  ({counts[r]})" for r in regions])
        v.addWidget(QLabel("Filter by region:")); v.addWidget(filt)

        listw = QListWidget()
        listw.setStyleSheet("QListWidget{background:#222;color:#eee;} "
                            "QListWidget::item:selected{background:#4a9eff;}")
        v.addWidget(listw, stretch=1)

        def populate():
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
        load_btn.setStyleSheet("background:#4a9eff;color:white;padding:6px;border-radius:4px;")
        cancel_btn.setStyleSheet("background:#4a4a4a;color:white;padding:6px;border-radius:4px;")
        btn_row.addStretch(1); btn_row.addWidget(cancel_btn); btn_row.addWidget(load_btn)
        v.addLayout(btn_row)

        chosen = {"path": None, "region": None, "scheme": "auto"}

        def do_load():
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
                                 scheme=chosen["scheme"])

    def _on_orient_radio(self, checked, orient):
        if checked:
            self.orientation.set(orient)
            self.on_orientation_change()

    def on_preset_change(self):
        name = self.preset_name.get()
        if name in ["(Custom)", ""]:
            self.desc_label.config(text=""); return
        p = get_preset(name)
        if not p: return
        self.sequence_type.set(p["sequence"]); self.TR.set(float(p["TR"])); self.TE.set(float(p["TE"]))
        self.TI.set(float(p.get("TI", 150))); self.flip_angle.set(float(p.get("flip_angle", 90)))
        self.matrix_size.set(int(p.get("matrix_size", 256))); self.FOV.set(float(p.get("FOV", 240)))
        self.bandwidth.set(float(p.get("bandwidth", 125))); self.NEX.set(int(p.get("NEX", 1)))
        for k, v in [("b_value", self.b_value), ("diff_direction", self.diff_direction), ("diff_display", self.diff_display),
                     ("angio_type", self.angio_type), ("angio_mip_slab", self.angio_mip_slab),
                     ("fmri_display", self.fmri_display), ("fmri_volumes", self.fmri_volumes), ("fmri_threshold", self.fmri_threshold)]:
            if k in p: v.set(p[k])
        self.desc_label.config(text=p.get("description", "")); self.on_sequence_change()

    def schedule_recalculate(self, *args):
        self._recalc_timer.start(150)

    def on_orientation_change(self):
        dims = {"axial": self.phantom_3d.shape[0], "sagittal": self.phantom_3d.shape[2], "coronal": self.phantom_3d.shape[1]}
        self.slice_idx.set(dims[self.orientation.get()] // 2)
        self._refresh_slice_range()
        self.recalculate()

    def on_sequence_change(self):
        seq = self.sequence_type.get()
        for frame in (self.ti_frame, self.fa_frame, self.fse_frame,
                      self.diff_frame, self.angio_frame, self.fmri_frame):
            frame.setVisible(False)
        if seq == "Inversion Recovery":
            self.ti_frame.setVisible(True)
        elif seq == "Gradient Echo":
            self.fa_frame.setVisible(True)
        elif seq == "FSE / TSE":
            self.fse_frame.setVisible(True); self.TR.set(4000.0); self.TE.set(80.0); self.etl.set(16)
        elif seq == "Diffusion (DWI)":
            self.diff_frame.setVisible(True)
        elif seq == "MR Angiography":
            self.angio_frame.setVisible(True); self.fa_frame.setVisible(True)
        elif seq == "fMRI (BOLD)":
            self.fmri_frame.setVisible(True)
        self.recalculate()

    def get_max_slice_idx(self):
        dims = {"axial": self.phantom_3d.shape[0], "sagittal": self.phantom_3d.shape[2], "coronal": self.phantom_3d.shape[1]}
        return dims[self.orientation.get()] - 1

    # ------------------------------------------------------------------ #
    #  Export / Import
    # ------------------------------------------------------------------ #
    def export_current_image(self):
        from export import export_image
        img, _ = self.simulate_with_params(self.get_current_params())
        self.compare_status.config(text=f"Saved: {os.path.basename(export_image(img, params=self.get_current_params()))}", fg='#69db7c')

    def export_current_protocol(self):
        from export import export_protocol
        self.compare_status.config(text=f"Saved: {os.path.basename(export_protocol(self.get_current_params()))}", fg='#69db7c')

    def export_current_report(self):
        from export import export_report
        p = self.get_current_params(); img, m = self.simulate_with_params(p)
        self.compare_status.config(text=f"Saved: {os.path.basename(export_report(img, p, m))}", fg='#69db7c')

    def load_protocol_file(self):
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

    def run(self):
        self.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)
    win = MRISimulator()
    win.run()
    sys.exit(app.exec())
