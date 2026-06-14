"""Teaching map panels for the desktop app (MapsMixin).

Three optional side panels that visualise *why* the image looks the way it does,
at parity with the browser's teaching panels:

* **Contrast map** — |S_a − S_b| for a representative tissue pair across the whole
  TR×TE plane (the same signal equations as the curve), with the current protocol
  marked, so you can see where contrast lives rather than reading one curve.
* **B0 map** — the susceptibility-driven off-resonance field (Hz) of the current
  slice — the inhomogeneity that warps EPI and shifts fat.
* **g-factor map** — local SENSE noise amplification from parallel-imaging
  unfolding, which grows with the acceleration R.

The data all comes from the shared engine (``_curve_signal``,
``Simulator._b0_field_slice``, ``coil.g_factor_map``) — only the drawing is
desktop-native (matching the app theme).
"""
from typing import TYPE_CHECKING, Any

import numpy as np

import tissue_db
from app_theme import C_PANEL, C_TEXT_DIM

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow as _Base
else:
    _Base = object

# Region → (label_a, label_b): the representative tissue pair whose contrast the
# TR×TE map plots (shared with the browser's _CMAP_PAIR).
CONTRAST_PAIR = {"Brain": (2, 3), "Knee": (4, 1), "Spine": (1, 14),
                 "Abdomen": (4, 1), "Pelvis": (4, 1), "Torso": (4, 1)}


class MapsMixin(_Base):
    # Host-window state these methods read (annotation-only; no runtime effect).
    region: Any; orientation: Any; slice_idx: Any
    sim: Any; _curve_signal: Any
    contrast_fig: Any; contrast_ax: Any; contrast_canvas: Any
    b0map_fig: Any; b0map_ax: Any; b0map_canvas: Any; _b0map_cbar: Any
    gfactor_fig: Any; gfactor_ax: Any; gfactor_canvas: Any; _gfactor_cbar: Any

    def _draw_contrast_map(self, params: dict) -> None:
        """TR×TE contrast landscape for the region's representative tissue pair."""
        seq = params["sequence"]
        ti, fa = params.get("TI", 150), params.get("flip_angle", 90)
        tdb = tissue_db.properties(params.get("field_strength", "3T"))
        la, lb = CONTRAST_PAIR.get(self.region.get(), (2, 3))
        pa, pb = tdb.get(la), tdb.get(lb)
        ax = self.contrast_ax
        ax.clear(); ax.set_facecolor(C_PANEL)
        ax.tick_params(colors="#c4cad2", labelsize=7)
        if pa and pb:
            trv = np.linspace(50.0, 5000.0, 150)
            tev = np.linspace(2.0, 200.0, 150)
            sa = np.abs(np.asarray(self._curve_signal(seq, pa, trv[:, None], tev[None, :], ti, fa)))
            sb = np.abs(np.asarray(self._curve_signal(seq, pb, trv[:, None], tev[None, :], ti, fa)))
            cnr = np.abs(sa - sb)
            mx = float(cnr.max()) or 1.0
            ax.imshow(cnr / mx, origin="lower", aspect="auto", cmap="magma", vmin=0, vmax=1,
                      extent=(float(tev[0]), float(tev[-1]), float(trv[0]), float(trv[-1])))
            ax.plot(params["TE"], params["TR"], "o", mfc="none", mec="#7fb8ff", ms=11, mew=2.2)
            ax.axvline(params["TE"], color="#7fb8ff", lw=0.5, alpha=0.5)
            ax.axhline(params["TR"], color="#7fb8ff", lw=0.5, alpha=0.5)
            ax.set_xlabel("TE (ms)", color="#c4cad2", fontsize=8)
            ax.set_ylabel("TR (ms)", color="#c4cad2", fontsize=8)
            ax.set_title(f"Contrast  {pa['name']} vs {pb['name']}  ·  {seq}\n(bright = high contrast)",
                         color="#9aa4b2", fontsize=8)
        else:
            ax.text(0.5, 0.5, "contrast map n/a for this region", color="#6b7585",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        self.contrast_fig.subplots_adjust(left=0.16, right=0.97, top=0.84, bottom=0.12)
        self.contrast_canvas.draw()

    def _draw_b0map(self, params: dict) -> None:
        """B0 off-resonance field (Hz) of the current slice."""
        b0 = {"1.5T": 1.5, "3T": 3.0, "7T": 7.0}.get(params.get("field_strength", "3T"), 3.0)
        orient, sl = self.orientation.get(), int(self.slice_idx.get())
        ax = self.b0map_ax
        ax.clear(); ax.set_axis_off()
        if getattr(self, "_b0map_cbar", None) is not None:
            try:
                self._b0map_cbar.remove()
            except Exception:
                pass
            self._b0map_cbar = None
        try:
            field = np.asarray(self.sim._b0_field_slice(orient, sl, params, b0))
        except Exception:
            ax.text(0.5, 0.5, "field map n/a", color="#6b7585", ha="center",
                    va="center", transform=ax.transAxes)
            self.b0map_canvas.draw(); return
        lim = float(max(1.0, np.percentile(np.abs(field), 99)))
        im = ax.imshow(field, cmap="RdBu_r", origin="lower", vmin=-lim, vmax=lim)
        ax.set_title("B0 off-resonance (Hz)", color=C_TEXT_DIM, fontsize=9, pad=3)
        self._b0map_cbar = self.b0map_fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        self._b0map_cbar.ax.tick_params(colors="#c4cad2", labelsize=7)
        self.b0map_fig.subplots_adjust(left=0.02, right=0.9, top=0.92, bottom=0.02)
        self.b0map_canvas.draw()

    def _draw_gfactor(self, params: dict) -> None:
        """SENSE g-factor map — parallel-imaging noise amplification (needs R>1)."""
        import coil
        ax = self.gfactor_ax
        ax.clear(); ax.set_axis_off()
        if getattr(self, "_gfactor_cbar", None) is not None:
            try:
                self._gfactor_cbar.remove()
            except Exception:
                pass
            self._gfactor_cbar = None
        r = int(params.get("accel_factor", 1))
        if r <= 1 or params.get("accel_method") not in ("SENSE", "GRAPPA"):
            ax.text(0.5, 0.5, "g-factor map shows parallel-imaging\nnoise — set Acceleration R > 1 (SENSE)",
                    color="#6b7585", ha="center", va="center", transform=ax.transAxes, fontsize=9)
            self.gfactor_canvas.draw(); return
        orient, sl = self.orientation.get(), int(self.slice_idx.get())
        lab = np.asarray(self.sim._b0_field_slice(orient, sl, params, 3.0))   # slice geometry
        h, w = lab.shape
        ht = (h // r) * r
        sens = coil.head_coil_array((ht, w), n_coils=8)
        g = coil.g_factor_map(sens, r)
        im = ax.imshow(g, cmap="viridis", origin="lower", vmin=1.0,
                       vmax=float(max(1.2, np.percentile(g, 99))))
        ax.set_title(f"g-factor map (R={r})", color=C_TEXT_DIM, fontsize=9, pad=3)
        self._gfactor_cbar = self.gfactor_fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        self._gfactor_cbar.ax.tick_params(colors="#c4cad2", labelsize=7)
        self.gfactor_fig.subplots_adjust(left=0.02, right=0.9, top=0.92, bottom=0.02)
        self.gfactor_canvas.draw()

    def _draw_teaching_maps(self, params: dict) -> None:
        """Render/hide the three optional teaching-map canvases per their toggles."""
        for show, canvas, draw in (
            (self.show_contrast_map, self.contrast_canvas, self._draw_contrast_map),
            (self.show_b0map, self.b0map_canvas, self._draw_b0map),
            (self.show_gfactor, self.gfactor_canvas, self._draw_gfactor),
        ):
            if show.get():
                canvas.setVisible(True)
                draw(params)
            else:
                canvas.setVisible(False)

    # Toggle Vars (provided by the host window).
    show_contrast_map: Any
    show_b0map: Any
    show_gfactor: Any
