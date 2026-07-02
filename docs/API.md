# Headless API — scripting MRISim for research

The simulation engine is Qt-free. `src/simulator.py` exposes a `Simulator`
class and a `default_params()` factory: give the simulator a label volume and
a parameter dict, and `simulate()` returns `(image, metrics)`. Everything the
desktop GUI and the browser edition display goes through this same path, so a
scripted result is exactly what the interactive apps would show.

A complete worked example lives at
[`examples/headless_demo.py`](../examples/headless_demo.py) (protocol montage,
TE sweep, ADC map — run `python examples/headless_demo.py`). This page
documents the contract it relies on.

## Quickstart

```python
import sys; sys.path.insert(0, "src")   # engine modules import by bare name

import simulator
from brainweb_loader import get_brainweb_or_synthetic

sim = simulator.Simulator()
sim.volume, source = get_brainweb_or_synthetic()   # real BrainWeb if bundled
sim.native_fov = 220.0                             # mm, brain
sim.orientation = "axial"                          # "axial" | "coronal" | "sagittal"
sim.slice_idx = sim.volume.shape[0] // 2

img, metrics = sim.simulate(simulator.default_params(
    sequence="