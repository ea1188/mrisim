---
title: MRI Simulator
emoji: 🧲
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 6.15.2
app_file: app.py
pinned: false
license: mit
---

# MRI Simulator

Interactive MRI physics in your browser — no install. Adjust pulse-sequence
parameters and watch the reconstructed image update in real time over a
validated physics engine.

**Three guided lessons:**

- **What TR does** — watch gray–white contrast flatten as TR lengthens
  (T1-weighted → proton-density).
- **Nulling fat with STIR** — slide the inversion time to the fat null and watch
  subcutaneous and visceral fat darken, then brighten as you move away.
- **SE vs FSE** — the same T2-weighted brain at matched contrast, but
  conventional spin echo takes roughly sixteen times longer than fast spin echo.

Plus **Free Explore** (drive every control yourself) and **Compare mode** (two
parameter sets side by side). Live annotations narrate the dominant teaching
point — "Fat is nulled.", "Fluid is nulled.", "T1-weighted" — as parameters
change.

> This Space runs the Gradio web front-end (`app.py`) over the physics library
> in `src/`. The full project, the tested physics modules, and the desktop
> PyQt6 app live on [GitHub](https://github.com/ea1188/mrisim).
