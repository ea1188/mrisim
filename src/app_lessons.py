"""Guided-lesson runner for the desktop app (LessonMixin).

Drives the same guided lessons as the browser, read from the shared
``data/lessons.json`` via :mod:`lessons`. A docked strip under the viewport shows
the current step's prose (rich text) with Back / Next / Exit; each step applies a
browser-style ``state`` dict through :meth:`_apply_lesson_state`, which translates
the browser control IDs onto the desktop ``Var`` names (the bound widgets follow
via their write-traces). Only lessons the desktop can faithfully reproduce are
offered (``lessons.desktop_supported``).
"""
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget,
                             QDialog)

import lessons
from app_theme import (C_ACCENT, C_ACCENT_HI, C_ACCENT_INK, C_BORDER, C_HEADER,
                       C_PANEL, C_RAISED, C_TEXT, C_TEXT_DIM)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow as _Base
else:
    _Base = object


class LessonMixin(_Base):
    # Host-window state these methods drive (annotation-only; no runtime effect).
    region: Any; sequence_type: Any; orientation: Any; field_strength: Any
    slice_idx: Any; TR: Any; TE: Any; TI: Any; flip_angle: Any; matrix_size: Any
    bandwidth: Any; NEX: Any; slice_thickness: Any; b_value: Any; etl: Any
    n_partitions: Any; n_slices: Any; slice_gap: Any; accel_factor: Any; pv_sigma: Any
    acq3d: Any; kz_pf_enabled: Any; fov_planning: Any; show_kspace: Any; show_psd: Any
    show_signal_curve: Any; show_tissue_overlay: Any; fatsat_enabled: Any
    contrast_enabled: Any; flow_enabled: Any; motion_enabled: Any
    chemical_shift_enabled: Any; susceptibility_enabled: Any; accel_method: Any
    diff_display: Any; qmri_display: Any; fmri_display: Any; motion_type: Any
    receive_coil: Any; pathology: Any; compare_mode: Any
    on_region_change: Any; on_sequence_change: Any; _set_orientation: Any
    _apply_brain_pathology: Any; set_protocol_a: Any; clear_compare: Any; recalculate: Any
    _lesson_panel: Any

    # ------------------------------------------------------------------ #
    #  Panel construction
    # ------------------------------------------------------------------ #
    def _build_lesson_panel(self) -> QFrame:
        """The docked lesson strip (hidden until a lesson starts)."""
        self._lessons: list[dict] = lessons.desktop_lessons()
        self._lesson_idx = -1
        self._lesson_step = 0

        panel = self._lesson_panel = QFrame()
        panel.setObjectName("lesson-panel")
        panel.setStyleSheet(
            f"QFrame#lesson-panel {{ background:{C_PANEL}; border-top:2px solid {C_ACCENT}; }}")
        panel.setVisible(False)
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 8, 12, 8); v.setSpacing(4)

        top = QHBoxLayout(); top.setSpacing(8)
        self._lesson_title = QLabel("")
        self._lesson_title.setStyleSheet(f"color:{C_ACCENT_HI}; font-size:13px; font-weight:bold;")
        self._lesson_progress = QLabel("")
        self._lesson_progress.setStyleSheet(f"color:{C_TEXT_DIM}; font-size:11px;")
        top.addWidget(self._lesson_title); top.addStretch(1); top.addWidget(self._lesson_progress)
        v.addLayout(top)

        self._lesson_text = QLabel("")
        self._lesson_text.setTextFormat(Qt.TextFormat.RichText)
        self._lesson_text.setWordWrap(True)
        self._lesson_text.setStyleSheet(f"color:{C_TEXT}; font-size:12px;")
        self._lesson_text.setMinimumHeight(48)
        v.addWidget(self._lesson_text)

        row = QHBoxLayout(); row.setSpacing(6)
        self._lesson_prev_btn = self._lesson_button("‹ Back", self._lesson_prev)
        self._lesson_next_btn = self._lesson_button("Next ›", self._lesson_next, accent=True)
        exit_btn = self._lesson_button("Exit", self._exit_lesson)
        row.addStretch(1)
        row.addWidget(exit_btn); row.addWidget(self._lesson_prev_btn); row.addWidget(self._lesson_next_btn)
        v.addLayout(row)
        return panel

    def _lesson_button(self, text: str, slot: Any, accent: bool = False) -> QPushButton:
        b = QPushButton(text)
        if accent:
            b.setStyleSheet(f"QPushButton {{ background:{C_ACCENT}; color:{C_ACCENT_INK}; "
                            f"border:none; border-radius:5px; padding:4px 14px; font-weight:bold; }}"
                            f"QPushButton:hover {{ background:{C_ACCENT_HI}; }}"
                            f"QPushButton:disabled {{ background:{C_RAISED}; color:{C_TEXT_DIM}; }}")
        else:
            b.setStyleSheet(f"QPushButton {{ background:{C_RAISED}; color:{C_TEXT_DIM}; "
                            f"border:1px solid {C_BORDER}; border-radius:5px; padding:4px 12px; }}"
                            f"QPushButton:hover {{ color:{C_ACCENT_HI}; border-color:{C_ACCENT}; }}"
                            f"QPushButton:disabled {{ color:{C_BORDER}; }}")
        b.clicked.connect(slot)
        return b

    # ------------------------------------------------------------------ #
    #  Picker
    # ------------------------------------------------------------------ #
    def _open_lesson_picker(self) -> None:
        """Modal list of the desktop-supported lessons; picking one starts it."""
        if not self._lessons:
            self.statusBar().showMessage("No guided lessons available (lessons.json missing).")  # type: ignore[union-attr]
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Guided lessons")
        dlg.resize(540, 600)
        dlg.setStyleSheet(f"QDialog {{ background:{C_HEADER}; }} QLabel {{ color:{C_TEXT}; }}")
        outer = QVBoxLayout(dlg)
        intro = QLabel("Step-by-step lessons — each one drives the controls for you. "
                       "Pick one to begin.")
        intro.setWordWrap(True); intro.setStyleSheet(f"color:{C_TEXT_DIM}; font-size:12px;")
        outer.addWidget(intro)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget(); host.setStyleSheet(f"background:{C_PANEL};")
        lv = QVBoxLayout(host); lv.setContentsMargins(6, 6, 6, 6); lv.setSpacing(4)
        first_beginner = first_advanced = True
        for i, L in enumerate(self._lessons):
            if L.get("beginner") and first_beginner:
                first_beginner = False
                lv.addWidget(self._lesson_section("New to MRI? Start here"))
            elif not L.get("beginner") and first_advanced:
                first_advanced = False
                lv.addWidget(self._lesson_section("Go deeper — the physics"))
            lv.addWidget(self._lesson_item(L, i, dlg))
        lv.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, stretch=1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject); bb.accepted.connect(dlg.reject)
        outer.addWidget(bb)
        dlg.exec()

    def _lesson_section(self, text: str) -> QLabel:
        h = QLabel(text)
        h.setStyleSheet(f"color:{C_ACCENT_HI}; font-size:11px; font-weight:bold; "
                        "padding:6px 2px 2px 2px;")
        return h

    def _lesson_item(self, lesson: dict, idx: int, dlg: QDialog) -> QPushButton:
        b = QPushButton()
        b.setText(lesson["title"] + "\n" + lesson.get("blurb", ""))
        b.setStyleSheet(
            f"QPushButton {{ text-align:left; background:{C_RAISED}; color:{C_TEXT}; "
            f"border:1px solid {C_BORDER}; border-radius:6px; padding:7px 10px; font-size:12px; }}"
            f"QPushButton:hover {{ border-color:{C_ACCENT}; }}")
        def pick() -> None:
            dlg.accept()
            self._start_lesson(idx)
        b.clicked.connect(pick)
        return b

    # ------------------------------------------------------------------ #
    #  Runner
    # ------------------------------------------------------------------ #
    def _start_lesson(self, idx: int) -> None:
        if not (0 <= idx < len(self._lessons)):
            return
        self._lesson_idx = idx
        self._lesson_step = 0
        if self.compare_mode.get():
            self.clear_compare()
        # Clean baseline so a lesson isn't polluted by leftover extras (mirrors
        # the browser's reset); lessons re-enable what they need.
        for v in (self.acq3d, self.kz_pf_enabled, self.fatsat_enabled, self.contrast_enabled):
            v.set(False)
        self._lesson_panel.setVisible(True)
        self._lesson_apply_step()

    def _exit_lesson(self) -> None:
        self._lesson_idx = -1
        self._lesson_panel.setVisible(False)
        if self.compare_mode.get():
            self.clear_compare()
            self.recalculate()

    def _lesson_prev(self) -> None:
        if self._lesson_step > 0:
            self._lesson_step -= 1
            self._lesson_apply_step()

    def _lesson_next(self) -> None:
        steps = self._lessons[self._lesson_idx]["steps"]
        if self._lesson_step < len(steps) - 1:
            self._lesson_step += 1
            self._lesson_apply_step()
        else:
            self._exit_lesson()

    def _lesson_apply_step(self) -> None:
        L = self._lessons[self._lesson_idx]
        step = L["steps"][self._lesson_step]
        n = len(L["steps"])
        self._lesson_title.setText(L["title"])
        self._lesson_text.setText(step.get("text", ""))
        self._lesson_progress.setText(f"Step {self._lesson_step + 1} / {n}")
        self._lesson_prev_btn.setEnabled(self._lesson_step > 0)
        last = self._lesson_step == n - 1
        self._lesson_next_btn.setText("Finish" if last else "Next ›")

        # Leave any comparison staged by a previous step.
        if self.compare_mode.get():
            self.clear_compare()
        self._apply_lesson_state(step.get("state") or {})
        if step.get("compareWith"):
            # state is panel A; compareWith is panel B (rendered side by side).
            self.set_protocol_a()
            self._apply_lesson_state(step["compareWith"])
        self.recalculate()

    def _apply_lesson_state(self, st: dict) -> None:
        """Apply a browser-style lesson state to the desktop controls. Structural
        keys (region/seq/orient/field) run first because they reset dependent
        values; the explicit numeric/enum values applied afterwards then win
        (the same ordering on_preset_change relies on)."""
        if st.get("region") and st["region"] != self.region.get():
            self.region.set(st["region"]); self.on_region_change()
        if st.get("seq"):
            self.sequence_type.set(st["seq"]); self.on_sequence_change()
        if st.get("orient"):
            self._set_orientation(st["orient"])
        if st.get("field"):
            self.field_strength.set(st["field"])
        for key, attr, cast in lessons.NUMERIC_KEYS:
            if st.get(key) is not None:
                getattr(self, attr).set(cast(st[key]))
        for key, attr in lessons.BOOL_KEYS:
            if key in st:
                getattr(self, attr).set(bool(st[key]))
        for key, attr in lessons.ENUM_KEYS:
            if key in st:
                getattr(self, attr).set(st[key])
        if "receivecoil" in st:
            self.receive_coil.set(lessons.COIL_LABEL.get(st["receivecoil"], "Uniform (ideal)"))
        if "pathology" in st:
            self.pathology.set(lessons.PATHOLOGY_LABEL.get(st["pathology"] or "", "None"))
            self._apply_brain_pathology()
