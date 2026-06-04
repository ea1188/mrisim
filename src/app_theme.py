"""Shared visual theme for the PyQt app: palette tokens, the global stylesheet,
and a helper to paint a solid background reliably (including the offscreen
platform, where a QSS objectName background may not render).

Kept in its own module so the main window and the UI mixins can all import a
single source of truth for the colours and stylesheet.
"""
from typing import Any

from PyQt6.QtGui import QColor, QPalette

# Palette tokens live in the Qt-free theme_colors module; re-export them here so
# the desktop UI's `from app_theme import C_*` continues to work unchanged.
from theme_colors import (  # noqa: F401  (re-exported for the UI mixins)
    C_CANVAS, C_PANEL, C_RAISED, C_BEZEL, C_HEADER, C_CHIP, C_BORDER,
    C_BORDER_SOFT, C_BORDER_HI, C_TEXT, C_TEXT_DIM, C_TEXT_FAINT, C_ACCENT,
    C_ACCENT_HI, C_ACCENT_DK, C_ACCENT_INK)


def _solid_bg(widget: Any, hex_color: str) -> None:
    """Paint a solid background via the palette (reliable everywhere, including
    the offscreen platform where a QSS objectName background may not render)."""
    widget.setAutoFillBackground(True)
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(hex_color))
    widget.setPalette(pal)


GLOBAL_QSS = f"""
QWidget {{ font-family: "SF Pro Text", "Helvetica Neue", "Segoe UI", "Inter", Helvetica, Arial, sans-serif; }}
QMainWindow {{ background-color: {C_CANVAS}; }}
QLabel {{ color: {C_TEXT}; }}
QToolTip {{ background: {C_RAISED}; color: {C_TEXT}; border: 1px solid {C_ACCENT}; padding: 4px 7px; border-radius: 5px; }}
QScrollArea {{ background-color: {C_PANEL}; border: none; }}
QWidget#controls-host {{ background: {C_PANEL}; }}

QSlider::groove:horizontal {{ height: 4px; background: #1c2027; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {C_ACCENT}, stop:1 {C_ACCENT_HI}); border-radius: 2px; }}
QSlider::add-page:horizontal {{ background: #1c2027; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #eaf1fb; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; border: 2px solid {C_ACCENT}; }}
QSlider::handle:horizontal:hover {{ background: #ffffff; border-color: {C_ACCENT_HI}; }}

QComboBox {{ background: {C_RAISED}; border: 1px solid {C_BORDER}; padding: 5px 9px; border-radius: 6px; color: {C_TEXT}; min-height: 15px; }}
QComboBox:hover {{ border-color: {C_BORDER_HI}; }}
QComboBox:focus {{ border-color: {C_ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; selection-background-color: {C_ACCENT}; selection-color: {C_ACCENT_INK}; outline: none; padding: 2px; }}

QCheckBox, QRadioButton {{ color: #c4cad2; spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; border: 1px solid {C_BORDER}; background: {C_RAISED}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {C_ACCENT}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}

QPushButton {{ background: {C_RAISED}; color: {C_TEXT}; border: 1px solid {C_BORDER}; padding: 6px 12px; border-radius: 6px; font-weight: bold; }}
QPushButton:hover {{ background: #2b333d; border-color: {C_BORDER_HI}; }}
QPushButton:pressed {{ background: #14191f; }}

QPushButton#section-toggle {{ background: transparent; color: #cfd6df; font-size: 11px; font-weight: bold;
    text-align: left; border: none; border-left: 2px solid {C_BORDER}; padding: 7px 10px; margin-top: 4px; border-radius: 0; }}
QPushButton#section-toggle:hover {{ background: #20262e; color: {C_ACCENT_HI}; }}
QPushButton#section-toggle:checked {{ color: {C_ACCENT_HI}; border-left-color: {C_ACCENT}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a323b; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {C_BORDER_HI}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QFrame#header-bar {{ background: {C_HEADER}; border-bottom: 1px solid {C_BORDER_SOFT}; }}
QLabel#app-logo {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {C_ACCENT_HI}, stop:1 {C_ACCENT_DK}); color: {C_ACCENT_INK}; font-weight: bold; font-size: 14px;
    border-radius: 8px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; }}
QLabel#app-title {{ color: #f2f5f8; font-size: 18px; font-weight: bold; }}
QFrame#chip {{ background: {C_CHIP}; border: 1px solid {C_BORDER_SOFT}; border-radius: 7px; }}
QLabel#chip-cap {{ color: {C_TEXT_FAINT}; font-size: 8px; font-weight: bold; }}
QLabel#chip-val {{ color: {C_ACCENT_HI}; font-size: 12px; font-weight: bold; }}
QFrame#series-strip {{ background: {C_HEADER}; border-top: 1px solid {C_BORDER_SOFT}; }}
QLabel#strip-cap {{ color: {C_TEXT_FAINT}; font-size: 9px; font-weight: bold; }}
QPushButton#thumb {{ background: {C_CHIP}; color: {C_TEXT_DIM}; border: 1px solid {C_BORDER_SOFT};
    border-radius: 7px; font-size: 10px; font-weight: bold; text-align: bottom; padding: 2px; }}
QPushButton#thumb:hover {{ border-color: {C_BORDER_HI}; color: #c4cad2; }}
QPushButton#thumb:checked {{ border: 2px solid {C_ACCENT}; color: {C_ACCENT_HI}; background: #142231; }}
QLabel#thumb-cap {{ color: {C_TEXT_DIM}; font-size: 9px; font-weight: bold; }}
"""
