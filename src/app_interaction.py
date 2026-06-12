"""Mouse / keyboard interaction on the image viewport (InteractionMixin).

Window/level drag, slice scroll, keyboard navigation, the MRA rotate vs W/L
routing, and the live cursor tissue/signal readout.
"""
from typing import TYPE_CHECKING, Any

import numpy as np

from PyQt6.QtCore import Qt

import tissue_db

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow as _Base
else:
    _Base = object


class InteractionMixin(_Base):
    # Provided by the host window (MRISimulator); annotation-only, no runtime effect.
    axes: Any
    current_image: Any
    window_width: Any
    window_level: Any
    wl_dragging: Any
    wl_start_x: Any
    wl_start_y: Any
    sequence_type: Any
    field_strength: Any
    orientation: Any
    slice_idx: Any
    slice_thickness: Any
    acq3d: Any
    _ACQ3D_SEQUENCES: Any
    angio_azimuth: Any
    angio_elevation: Any
    show_kspace: Any
    multi_slice: Any
    show_psd: Any
    _mra_dragging: Any
    _mra_rotating: Any
    _mra_start_x: Any
    _mra_start_y: Any
    apply_window_level: Any
    compare_mode: Any
    _apply_window_level_compare: Any
    recalculate: Any
    get_max_slice_idx: Any
    get_current_params: Any
    _get_current_phantom_slice: Any

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
        # Plain left-drag over the MRA MIP spins the angiogram (azimuth/elevation);
        # the MIP is a rotatable projection, so left-drag rotates there. Hold Ctrl
        # to window/level an MRA image instead.
        if (event.button == 1 and not ctrl  # type: ignore[attr-defined]
                and self.sequence_type.get() == "MR Angiography"
                and event.x is not None):  # type: ignore[attr-defined]
            self._mra_dragging = True
            self._mra_rotating = True          # request the fast (downsampled) MIP
            self._mra_start_x = event.x        # type: ignore[attr-defined]
            self._mra_start_y = event.y        # type: ignore[attr-defined]
            return
        # Any other drag — plain left (the default now), middle or right — adjusts W/L.
        if event.button in (1, 2, 3):  # type: ignore[attr-defined]
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
        in_compare = bool(self.compare_mode.get())
        # In compare there's no single current_image, but both panels still window.
        if self.current_image is None and not in_compare:
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
        if in_compare:
            self._apply_window_level_compare()   # re-window both A and B together
        else:
            self.apply_window_level()

    def _on_release(self, event: object) -> None:
        self.wl_dragging = False
        if getattr(self, "_mra_dragging", False):
            self._mra_dragging = False
            self._mra_rotating = False   # back to full-resolution MIP
            self.recalculate()

    # --- Workstation navigation -------------------------------------------- #
    def _slice_step(self) -> int:
        """Voxels advanced per slice-step. In the normal 2-D path one step is a
        whole slice-thickness, so the wheel/arrows flip through *contiguous*
        slices the way a PACS series does (a 5 mm slice advances 5 voxels, not 1).
        Reformatting a 3-D slab steps one partition, and MRA (which ignores slice
        thickness) steps one voxel."""
        seq = self.sequence_type.get()
        if self.acq3d.get() and seq in self._ACQ3D_SEQUENCES:
            return 1
        if seq == "MR Angiography":
            return 1
        return max(1, int(round(self.slice_thickness.get())))

    def _change_slice(self, n_slices: int) -> None:
        """Step by +/- n_slices, where each slice is one slice-thickness of
        voxels (see _slice_step), clamped to the volume bounds."""
        max_sl = self.get_max_slice_idx()
        new_idx = int(np.clip(self.slice_idx.get() + n_slices * self._slice_step(), 0, max_sl))
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
            "Wheel / \u2191\u2193 : slice   \u2022   drag : window/level   \u2022   "
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
