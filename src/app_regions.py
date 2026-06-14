"""Anatomy / region loading and switching (RegionMixin).

Brain-subject loading, region switching, and loading external TotalSegmentator
NIfTI masks — a single file, or one browsed/indexed from a folder via a picker.
"""
import os
from typing import TYPE_CHECKING, Any

import numpy as np

from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
                             QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QProgressDialog, QPushButton, QVBoxLayout)

from phantom3d_extended import add_activation_3d
from app_theme import C_ACCENT, C_ACCENT_INK, C_PANEL, C_RAISED, C_TEXT

# Typed as a QMainWindow for the checker (so self.statusBar() etc. resolve and
# `self` is accepted as a QWidget parent), but a plain mixin at runtime.
if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow as _Base
else:
    _Base = object


class RegionMixin(_Base):
    # Provided by the host window (MRISimulator); annotation-only, no runtime effect.
    region: Any
    brain_subject: Any
    sequence_type: Any
    orientation: Any
    slice_idx: Any
    FOV: Any
    pathology: Any
    phantom_3d: Any
    texture_3d: Any
    _brain_volume: Any
    _lesion_vol_cache: Any
    _PATHOLOGY_KIND: Any
    _region_cache: Any
    _region_sequences: Any
    _region_texture_cache: Any
    _region_dd: Any
    _seq_dropdown: Any
    _body_phantoms: Any
    _BODY_REGIONS: Any
    _fov_slider: Any
    get_max_slice_idx: Any
    on_sequence_change: Any
    recalculate: Any
    _set_orientation: Any
    _set_status_default: Any
    _refresh_slice_range: Any
    _get_native_fov: Any

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
        self._lesion_vol_cache.clear()   # painted brains are subject-specific

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
            vol = self._body_phantoms.build_region(name)
            tex = self._body_phantoms.build_region_texture(name, vol)
            # The body phantoms are built patient-right on the viewer's right
            # (neurological). Mirror L/R (axis 2) so they display radiological \u2014
            # patient-right on the viewer's left \u2014 consistent with the brain.
            if name in self._BODY_REGIONS:
                vol = np.ascontiguousarray(np.flip(vol, axis=2))
                if tex is not None:
                    tex = np.ascontiguousarray(np.flip(tex, axis=2))
            self._region_cache[name] = vol
            self._region_texture_cache[name] = tex
        self.phantom_3d = self._region_cache[name]
        self.texture_3d = self._region_texture_cache.get(name)
        self._apply_brain_pathology()   # overlay a demo lesion if Brain + pathology

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

        # Recentre to a sensible slice for the new volume and refresh ranges.
        # Default to the region's canonical plane (spine/knee read best sagittal);
        # _set_orientation also recentres the slice and refreshes ranges.
        _plane = {"Spine": "sagittal", "Knee": "sagittal"}.get(name, "axial")
        if self.orientation.get() != _plane:
            self._set_orientation(_plane)
        else:
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

    def _apply_brain_pathology(self) -> None:
        """If Brain is active and a demo pathology is selected, swap phantom_3d for a
        brain volume with the lesion painted in (labels 23–28, which render via the
        field-synced tissue table). Cached per kind; a no-op for body regions."""
        if self.region.get() != "Brain":
            return
        kind = self._PATHOLOGY_KIND.get(self.pathology.get(), "")
        base = self._region_cache["Brain"]
        if not kind:
            self.phantom_3d = base
            return
        vol = self._lesion_vol_cache.get(kind)
        if vol is None:
            import rendering
            vol = rendering.paint_brain_pathology(base, kind)
            self._lesion_vol_cache[kind] = vol
        self.phantom_3d = vol

    def on_pathology_change(self) -> None:
        """Repaint the brain with the chosen demo lesion and re-render."""
        self._apply_brain_pathology()
        self.recalculate()

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
        listw.setStyleSheet(f"QListWidget{{background:{C_PANEL};color:{C_TEXT};}} "
                            f"QListWidget::item:selected{{background:{C_ACCENT};color:{C_ACCENT_INK};}}")
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
        load_btn.setStyleSheet(f"background:{C_ACCENT};color:{C_ACCENT_INK};padding:6px;border-radius:4px;font-weight:bold;")
        cancel_btn.setStyleSheet(f"background:{C_RAISED};color:{C_TEXT};padding:6px;border-radius:4px;")
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
