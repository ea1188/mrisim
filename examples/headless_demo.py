"""Headless research demo — drive the MRI simulator without the GUI.

The simulation engine (src/simulator.py) is Qt-free: you give it a label volume
plus a parameter dict and it returns (image, metrics). This script shows the
scripting workflow a researcher would use — render named protocols, sweep a
parameter, and reconstruct a quantitative map — saving PNGs and printing metrics.
No display required.

Run:
    python examples/headless_demo.py                # default output: examples/output
    python examples/headless_demo.py --out /tmp/mri --slice 90
"""
import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")                      # headless: no display
import matplotlib.pyplot as plt

# Make the engine importable (modules import each other by bare name).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import simulator
from brainweb_loader import get_brainweb_or_synthetic
from phantom3d import get_slice


def build_simulator(slice_idx: int | None = None) -> simulator.Simulator:
    """A Simulator wired to a brain volume, viewing an axial mid-slice."""
    volume, source = get_brainweb_or_synthetic()
    sim = simulator.Simulator()
    sim.volume = volume
    sim.native_fov = 220.0                 # brain FOV (mm)
    sim.orientation = "axial"
    sim.slice_idx = slice_idx if slice_idx is not None else volume.shape[0] // 2
    print(f"Volume: {source}  shape={volume.shape}  axial slice {sim.slice_idx}")
    return sim


def _print_metrics(name: str, m: dict) -> None:
    st = m["scan_time"]
    print(f"  {name:18s} | {int(st // 60)}:{int(st % 60):02d}  "
          f"SNR(WM)={m['snr_wm']:5.1f}  CNR={abs(m['snr_wm'] - m['snr_gm']):4.1f}  "
          f"SAR={m['sar_head']:.1f} W/kg  res={m['resolution']:.2f} mm")


def demo_sequence_comparison(sim, out: str) -> None:
    """Render three contrasts of the same slice and save a montage."""
    print("\n[1] Sequence comparison (T1w / T2w / FLAIR)")
    protocols = {
        "T1w SE":  dict(sequence="Spin Echo", TR=500, TE=15),
        "T2w SE":  dict(sequence="Spin Echo", TR=4000, TE=100),
        "FLAIR":   dict(sequence="Inversion Recovery", TR=9000, TE=90, TI=2548),
    }
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for ax, (name, over) in zip(axes, protocols.items()):
        img, metrics = sim.simulate(simulator.default_params(**over))
        _print_metrics(name, metrics)
        ax.imshow(img, cmap="gray", origin="lower")
        ax.set_title(name); ax.set_axis_off()
    fig.tight_layout()
    path = os.path.join(out, "sequence_comparison.png")
    fig.savefig(path, dpi=110, facecolor="white"); plt.close(fig)
    print(f"  saved {path}")


def demo_te_sweep(sim, out: str) -> None:
    """Sweep echo time to show T2 weighting build up (the research workflow)."""
    print("\n[2] TE sweep (T2 contrast vs echo time, TR=4000 SE)")
    tes = [15, 40, 80, 120, 160]
    fig, axes = plt.subplots(1, len(tes), figsize=(3 * len(tes), 3.4))
    for ax, te in zip(axes, tes):
        img, _ = sim.simulate(simulator.default_params(sequence="Spin Echo", TR=4000, TE=te))
        ax.imshow(img, cmap="gray", origin="lower")
        ax.set_title(f"TE = {te} ms"); ax.set_axis_off()
    fig.suptitle("Spin echo, TR = 4000 ms — CSF/fluid brightens as TE increases")
    fig.tight_layout()
    path = os.path.join(out, "te_sweep.png")
    fig.savefig(path, dpi=110, facecolor="white"); plt.close(fig)
    print(f"  saved {path}")


def demo_quantitative_map(sim, out: str) -> None:
    """Reconstruct a quantitative T1 map (VFA) and save it with a ms colorbar."""
    print("\n[3] Quantitative T1 map (variable flip angle)")
    t1, _ = sim.simulate(simulator.default_params(
        sequence="Quantitative (qMRI)", qmri_display="T1 Map (VFA)"))
    fig, ax = plt.subplots(figsize=(5, 5))
    im = ax.imshow(t1, cmap="viridis", origin="lower", vmin=0, vmax=4500)
    ax.set_title("T1 map (VFA)"); ax.set_axis_off()
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("T1 (ms)")
    fig.tight_layout()
    path = os.path.join(out, "t1_map.png")
    fig.savefig(path, dpi=110, facecolor="white"); plt.close(fig)
    # Read recovered values back at the true tissue labels (1=CSF, 3=WM).
    labels = get_slice(sim.volume, sim.orientation, sim.slice_idx)
    wm = np.median(t1[labels == 3]); csf = np.median(t1[labels == 1])
    print(f"  recovered T1: WM≈{wm:.0f} ms, CSF≈{csf:.0f} ms  (tissue_db 3T: 830 / 4500)")
    print(f"  saved {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Headless MRI simulation demo.")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "output"),
                    help="output directory for PNGs")
    ap.add_argument("--slice", type=int, default=None, help="axial slice index")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    sim = build_simulator(args.slice)
    demo_sequence_comparison(sim, args.out)
    demo_te_sweep(sim, args.out)
    demo_quantitative_map(sim, args.out)
    print(f"\nDone. Images in {args.out}")


if __name__ == "__main__":
    main()
