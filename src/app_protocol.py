"""Desktop Protocol Planning — a scanner-console workflow layered on the existing
interactive scout + FOV-planning acquire.

Pick an exam → a protocol queue of prebuilt sequences loads → open a sequence to plan it
on the existing 3-plane scout (oblique / FOV / slice drag) → **Acquire** snapshots the
prescribed image (with scan time + SNR) and marks the sequence done; re-run appends a
fresh copy. Reuses ``protocols.py``, ``apply_preset_by_name`` and the whole FOV-planning
acquire path — this mixin is just the queue on top.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QScrollArea,
                             QToolButton, QWidget)

import protocols


class ProtocolMixin:
    """Adds the Protocol queue section + workflow to the main window."""

    # --- attributes / methods provided by MRISimulator (for type-checkers) - #
    region: Any
    fov_planning: Any
    orientation: Any
    slice_idx: Any
    current_image: Any
    apply_preset_by_name: Any
    on_region_change: Any
    get_current_params: Any
    simulate_with_params: Any
    _simulate_single_slice: Any
    fig: Any
    canvas: Any
    display_cmap: Any
    update_metrics: Any
    _recalc_timer: Any
    _wl_bounds: Any
    _get_voxel_aspect: Any
    _ensure_1x2_layout: Any
    _annotate_image: Any

    _LOCALIZER = protocols.LOCALIZER

    # --- UI ---------------------------------------------------------------- #
    def _build_protocol_section(self) -> QWidget:
        """The Protocol collapsible section (exam picker + queue + Acquire)."""
        from app_qt import CollapsibleSection   # lazy: app_qt imports this module
        sec = CollapsibleSection("Protocol")
        inner = sec.inner

        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Exam"))
        self.pp_exam = QComboBox()
        for ex in protocols.exam_names():
            self.pp_exam.addItem(ex)
        self.pp_exam.currentTextChanged.connect(self._pp_load_exam)
        row.addWidget(self.pp_exam, 1)
        _rw = QWidget(); _rw.setLayout(row); inner.addWidget(_rw)

        self.pp_list = QListWidget()
        self.pp_list.setMinimumHeight(150)
        self.pp_list.itemClicked.connect(self._pp_item_clicked)
        inner.addWidget(self.pp_list)

        brow = QHBoxLayout(); brow.setContentsMargins(0, 0, 0, 0)
        self.pp_acquire_btn = QPushButton("Acquire ▸")
        self.pp_acquire_btn.clicked.connect(self._pp_acquire)
        self.pp_rerun_btn = QPushButton("＋ Re-run")
        self.pp_rerun_btn.setToolTip("Append a fresh copy of the selected acquired sequence")
        self.pp_rerun_btn.clicked.connect(self._pp_rerun)
        brow.addWidget(self.pp_acquire_btn, 1); brow.addWidget(self.pp_rerun_btn)
        _bw = QWidget(); _bw.setLayout(brow); inner.addWidget(_bw)

        self.pp_readout = QLabel(""); self.pp_readout.setWordWrap(True)
        self.pp_readout.setStyleSheet("color:#9aa4b2; font-size:11px;")
        inner.addWidget(self.pp_readout)

        # Acquired-series review: a thumbnail strip of what you've acquired so far —
        # click a thumbnail (or an acquired queue row) to review it full-size.
        self.pp_thumbs_label = QLabel("Acquired series")
        self.pp_thumbs_label.setStyleSheet("color:#6f7886; font-size:10px;")
        self.pp_thumbs_label.setVisible(False)
        inner.addWidget(self.pp_thumbs_label)
        self.pp_thumbs_scroll = QScrollArea()
        self.pp_thumbs_scroll.setWidgetResizable(True)
        self.pp_thumbs_scroll.setFixedHeight(92)
        self.pp_thumbs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pp_thumbs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pp_thumbs_scroll.setStyleSheet("QScrollArea{border:none;}")
        self.pp_thumbs_scroll.setVisible(False)
        self.pp_thumbs_host = QWidget()
        self.pp_thumbs_layout = QHBoxLayout(self.pp_thumbs_host)
        self.pp_thumbs_layout.setContentsMargins(2, 2, 2, 2); self.pp_thumbs_layout.setSpacing(4)
        self.pp_thumbs_layout.addStretch(1)
        self.pp_thumbs_scroll.setWidget(self.pp_thumbs_host)
        inner.addWidget(self.pp_thumbs_scroll)
        self._pp_thumb_refs: list = []     # keep QImage buffers alive

        # state
        self.pp_queue: list[dict] = []
        self.pp_active: dict | None = None
        self._pp_load_exam(self.pp_exam.currentText())
        return sec

    # --- queue building ---------------------------------------------------- #
    def _pp_load_exam(self, exam: str) -> None:
        if not exam:
            return
        if self.region.get() != exam:
            self.region.set(exam)
            self.on_region_change()
        self.pp_queue = [
            {**it, "status": "pending", "image": None, "metrics": None}
            for it in protocols.get_protocol(exam)
        ]
        self.pp_active = None
        self._pp_render_list()
        self._pp_render_thumbs()
        self.pp_readout.setText("Open a sequence to plan it on the scout, then Acquire.")

    def _pp_render_list(self) -> None:
        self.pp_list.clear()
        for i, e in enumerate(self.pp_queue):
            dot = "✓" if e["status"] == "acquired" else ("▸" if e is self.pp_active else "·")
            extra = ""
            m = e.get("metrics")
            if m:
                extra = f"   {self._pp_fmt_time(m.get('scan_time'))}"
            it = QListWidgetItem(f"{i + 1:>2}  {e['label']:<14}{extra}   {dot}")
            self.pp_list.addItem(it)

    @staticmethod
    def _pp_fmt_time(s: float | None) -> str:
        s = int(round(s or 0))
        return f"{s // 60}:{s % 60:02d}"

    @staticmethod
    def _is_localizer(e: dict | None) -> bool:
        return e is not None and e["preset"] == ProtocolMixin._LOCALIZER

    # --- open / acquire / re-run ------------------------------------------- #
    def _pp_item_clicked(self, item: QListWidgetItem) -> None:
        idx = self.pp_list.row(item)
        if not (0 <= idx < len(self.pp_queue)):
            return
        entry = self.pp_queue[idx]
        # An acquired row → review the stored image; a pending row → open it to plan.
        if entry["status"] == "acquired" and entry.get("image") is not None:
            self._pp_review(entry)
        else:
            self._pp_open(self.pp_queue[idx])

    def _pp_open(self, entry: dict) -> None:
        """Open a queue item: apply its preset (if any) and turn on FOV planning so the
        scout + prescribed image show for planning."""
        self.pp_active = entry
        if not self._is_localizer(entry):
            self.apply_preset_by_name(entry["preset"])
        self.fov_planning.set(True)              # show the interactive scout + acquire view
        self._pp_render_list()
        self.pp_acquire_btn.setEnabled(not self._is_localizer(entry))
        self.pp_readout.setText(
            "Localizer — the 3-plane scout." if self._is_localizer(entry)
            else f"Planning {entry['label']} · {entry['sequence']} — drag the scout to "
                 "angle / move the FOV / set the slice, then Acquire.")

    def _pp_acquire(self) -> None:
        e = self.pp_active
        if not e or self._is_localizer(e):
            return
        params = self.get_current_params()
        # Snapshot the prescribed slice (always one image, even for a multi-slice group)
        # and the metrics the acquisition already computes.
        img = np.asarray(self._simulate_single_slice(
            params, self.orientation.get(), int(self.slice_idx.get())))
        _, metrics = self.simulate_with_params(params)
        e["image"] = img
        e["metrics"] = metrics
        e["params"] = dict(params)
        e["orientation"] = self.orientation.get()    # for faithful review / thumbnail
        e["slice"] = int(self.slice_idx.get())
        e["status"] = "acquired"
        self._pp_render_list()
        self._pp_render_thumbs()
        t = self._pp_fmt_time(metrics.get("scan_time"))
        # The SNR metrics are brain-tissue-keyed (white/grey matter); body exams
        # (Knee, Abdomen) have neither, so only show an SNR term when it's available.
        snr = int(round(metrics.get("snr_wm") or metrics.get("snr")
                        or metrics.get("snr_gm") or metrics.get("snr_eff") or 0))
        snr_txt = f" · SNR {snr}" if snr > 0 else ""
        # advance to the next still-pending sequence, then show the acquire confirmation
        # (set last so opening the next item doesn't overwrite it).
        nxt = next((q for q in self.pp_queue if q["status"] == "pending"
                    and not self._is_localizer(q)), None)
        if nxt:
            self._pp_open(nxt)
        self.pp_readout.setText(
            f"Acquired {e['label'].strip()} ✓ · {t}{snr_txt}"
            + (f" — now planning {nxt['label'].strip()}." if nxt else " — protocol complete."))

    def _pp_rerun(self) -> None:
        """Append a fresh, pending copy of the selected acquired sequence and open it."""
        idx = self.pp_list.currentRow()
        if not (0 <= idx < len(self.pp_queue)):
            return
        src = self.pp_queue[idx]
        if src["status"] != "acquired":
            return
        copy = {"preset": src["preset"], "label": src["label"] + " (re-run)",
                "sequence": src["sequence"], "status": "pending",
                "image": None, "metrics": None}
        self.pp_queue.append(copy)
        self._pp_render_list()
        self._pp_open(copy)

    # --- acquired-series review -------------------------------------------- #
    def _pp_thumb_pixmap(self, img: Any, orient: str, size: int = 70) -> QPixmap:
        """A small grayscale thumbnail of an acquired image, windowed to its robust
        range and oriented to match the main viewport (sagittal flipped, origin-lower
        flipped to QImage's top-left)."""
        a = np.asarray(img, dtype=float)
        fg = a[a > 1e-6]
        lo, hi = ((float(v) for v in np.percentile(fg, (1, 99))) if fg.size
                  else (0.0, float(a.max() or 1.0)))
        g = (np.clip((a - lo) / ((hi - lo) or 1.0), 0, 1) * 255).astype(np.uint8)
        # No sagittal L-R flip: the stored image already carries the radiological
        # convention (get_slice), matching the viewport, which no longer inverts.
        g = np.ascontiguousarray(np.flipud(g))
        self._pp_thumb_refs.append(g)                      # QImage shares the buffer
        h, w = g.shape
        qi = QImage(g.data, w, h, w, QImage.Format.Format_Grayscale8)  # type: ignore[call-overload]
        return QPixmap.fromImage(qi).scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

    def _pp_render_thumbs(self) -> None:
        """Rebuild the acquired-series thumbnail strip from the queue."""
        while self.pp_thumbs_layout.count() > 1:           # keep the trailing stretch
            item = self.pp_thumbs_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._pp_thumb_refs = []
        acquired = [e for e in self.pp_queue
                    if e["status"] == "acquired" and e.get("image") is not None]
        self.pp_thumbs_label.setVisible(bool(acquired))
        self.pp_thumbs_scroll.setVisible(bool(acquired))
        for e in acquired:
            orient = e.get("orientation", "axial")
            btn = QToolButton()
            btn.setIcon(QIcon(self._pp_thumb_pixmap(e["image"], orient)))
            btn.setIconSize(QSize(70, 70))
            btn.setToolTip(f"{e['label'].strip()} · {e['sequence']} — click to review")
            btn.setStyleSheet("QToolButton{border:1px solid #2a323c;border-radius:3px;"
                              "padding:1px;background:#05070a;}"
                              "QToolButton:hover{border-color:#4f9cf9;}")
            btn.clicked.connect(lambda _=False, ent=e: self._pp_review(ent))
            self.pp_thumbs_layout.insertWidget(self.pp_thumbs_layout.count() - 1, btn)

    def _pp_review(self, entry: dict) -> None:
        """Show a stored acquired image full-size on the main viewport (review mode —
        no re-simulation). Leaves FOV planning, then draws the snapshot over the canvas."""
        import render_overlay
        img = entry.get("image")
        if img is None:
            return
        self.pp_active = entry
        if self.fov_planning.get():
            self.fov_planning.set(False)         # on_fov_planning_toggle recalcs synchronously…
        self._recalc_timer.stop()                # …and cancel any debounced recalc, then draw
        self._ensure_1x2_layout()
        self.current_image = np.asarray(img)
        params = entry.get("params") or self.get_current_params()
        orient = entry.get("orientation", self.orientation.get())
        sl = int(entry.get("slice", params.get("slice_idx", self.slice_idx.get())))
        vlo, vhi = self._wl_bounds(self.current_image)
        center, width = (vlo + vhi) / 2.0, max(1e-6, vhi - vlo)
        for i, ax in enumerate(self.fig.axes):
            ax.clear()
            if i > 0:
                ax.set_axis_off()
        ax = self.fig.axes[0]
        ax.imshow(self.current_image, cmap=self.display_cmap.get(), origin="lower",
                  aspect=self._get_voxel_aspect(orient), vmin=vlo, vmax=vhi)
        render_overlay.frame_image_axes(ax)
        self._annotate_image(ax, params, orient, sl, width, center)
        # No sagittal invert: the viewport no longer flips sagittal (get_slice already
        # renders it anterior-left), so the review image matches without inverting.
        self.canvas.draw()
        if entry.get("metrics"):
            self.update_metrics(params, entry["metrics"])
        self._pp_render_list()
        t = self._pp_fmt_time((entry.get("metrics") or {}).get("scan_time"))
        self.pp_readout.setText(
            f"Reviewing {entry['label'].strip()} ✓ · {t} — click a thumbnail to review "
            "another, or a pending row to plan.")
