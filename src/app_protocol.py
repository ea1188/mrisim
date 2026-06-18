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
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QWidget)

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
        if 0 <= idx < len(self.pp_queue):
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
        e["status"] = "acquired"
        self._pp_render_list()
        t = self._pp_fmt_time(metrics.get("scan_time"))
        snr = int(round(metrics.get("snr_wm", 0)))
        # advance to the next still-pending sequence, then show the acquire confirmation
        # (set last so opening the next item doesn't overwrite it).
        nxt = next((q for q in self.pp_queue if q["status"] == "pending"
                    and not self._is_localizer(q)), None)
        if nxt:
            self._pp_open(nxt)
        self.pp_readout.setText(
            f"Acquired {e['label'].strip()} ✓ · {t} · SNR {snr}"
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
