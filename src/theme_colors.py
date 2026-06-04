"""Palette tokens (clinical near-black + medical blue) — plain strings, no Qt.

Split out of ``app_theme`` so Qt-free consumers (the headless renderers and the
browser/Pyodide adapter) can import the colours without pulling in PyQt6.
``app_theme`` re-exports these, so existing ``from app_theme import C_*`` keeps
working for the desktop UI.
"""

C_CANVAS   = "#050607"   # image / graph viewport — the "screen" (deepest black)
C_PANEL    = "#171c23"   # control + measurement panels (lifted for separation)
C_RAISED   = "#222932"   # cards, combos, buttons
C_BEZEL    = "#2a323c"   # thin frame around the viewport screen
C_HEADER   = "#0d1014"   # header bar, series strip, chip backgrounds
C_CHIP     = "#11151a"
C_BORDER   = "#252c34"
C_BORDER_SOFT = "#1b222a"
C_BORDER_HI   = "#323b46"
C_TEXT     = "#dfe5ec"
C_TEXT_DIM = "#9aa4b2"
C_TEXT_FAINT = "#6b7585"
C_ACCENT   = "#4f9cf9"
C_ACCENT_HI = "#7fb8ff"
C_ACCENT_DK = "#2f6fd6"     # darker accent for gradients / pressed states
C_ACCENT_INK = "#081019"    # text on an accent fill
