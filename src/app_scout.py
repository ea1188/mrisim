"""3-plane scout / FOV-planning and oblique interaction (ScoutMixin).

Split out of app_qt; mixed into MRISimulator. Renders the localizer and handles
the box / edge / angle drags that prescribe slice position, coverage, in-plane
FOV and obliquity.
"""
from typing import Any

import numpy as np

from phantom3d import simulate_slice
from app_theme import C_ACCENT, C_ACCENT_HI, C_CANVAS


class ScoutMixin:
    # Provided by the host window (MRISimulator); annotation-only, no runtime
    # effect (does not shadow the host's real attributes/methods).
    sim: Any
    orientation: Any
    slice_idx: Any
    slice_tilt: Any
    slice_rot: Any
    n_slices: Any
    slice_thickness: Any
    slice_gap: Any
    inplane_fov_pct: Any
    inplane_off: Any
    fov_planning: Any
    satband_enabled: Any
    satband_pos: Any
    satband_width: Any
    satband_angle: Any
    satband_angle2: Any
    _scout_satband_info: Any
    _scout_satband_ax: Any
    _scout_primary_plane: Any
    _scout_gizmo_center: Any
    phantom_3d: Any
    plan_frame: Any
    scout_canvas: Any
    scout_fig: Any
    scout_axes: Any
    _scout_plane_names: Any
    _scout_box_info: Any
    _scout_overlays: Any
    _scout_drag: Any
    _scout_angle_handles: Any
    _scout_primary_ax: Any
    get_current_params: Any
    recalculate: Any
    schedule_recalculate: Any
    _sync_sim: Any
    _ensure_1x2_layout: Any

    def _draw_scout(self, params: dict) -> None:
        """Render 3-plane localizer with acquisition prescription overlaid on each panel."""
        import scan_geometry as sg
        from matplotlib.patches import Rectangle
        from oblique import plane_from_angles, scout_band, three_scouts as _three_scouts
        self.scout_canvas.setVisible(True)
        acq = self.orientation.get()
        vol = self.phantom_3d
        tilt = self.slice_tilt.get()
        rot  = self.slice_rot.get()
        fov_frac = self.inplane_fov_pct.get() / 100.0

        # Role assignment: which of the 3 panel indices is primary/secondary/acq-plane
        _role_map = {
            "axial":    {"primary": 1, "secondary": 2, "acqplane": 0},
            "coronal":  {"primary": 0, "secondary": 2, "acqplane": 1},
            "sagittal": {"primary": 1, "secondary": 0, "acqplane": 2},
        }
        roles = _role_map[acq]

        # Slab centre in voxel-index space
        center = self._compute_slab_center()
        center_int = (int(round(center[0])), int(round(center[1])), int(round(center[2])))

        # Background images: slices through the planned centre
        scouts_bg = _three_scouts(vol, center_int)

        # Acquisition-plane dashed FOV box (unchanged for both modes)
        ip_box = sg.inplane_box(acq, vol.shape, fov_frac, self.inplane_off.get())

        is_oblique = abs(tilt) > 0.5 or abs(rot) > 0.5

        if is_oblique:
            normal, row_vec, col_vec = plane_from_angles(acq, tilt_deg=tilt, rot_deg=rot)
            band = scout_band(vol.shape, normal, center,
                              n_slices=self.n_slices.get(),
                              thickness_mm=self.slice_thickness.get(),
                              gap_mm=self.slice_gap.get(),
                              voxel_size=(1.0, 1.0, 1.0))
            self._scout_box_info = None
            self._scout_overlays = {}
            for i, plane in enumerate(self._scout_plane_names):
                if i == roles["primary"]:
                    self._scout_overlays[plane] = {"role": "primary",   "info": band[plane]}
                elif i == roles["secondary"]:
                    self._scout_overlays[plane] = {"role": "secondary", "info": band[plane]}
                else:
                    self._scout_overlays[plane] = {"role": "acqplane",  "info": ip_box}
        else:
            info = sg.box_rect(acq, vol.shape,
                               self.slice_idx.get(), self.n_slices.get(),
                               self.slice_thickness.get(), self.slice_gap.get(),
                               fov_frac, self.inplane_off.get())
            self._scout_box_info = info
            sec_plane = self._scout_plane_names[roles["secondary"]]
            sec_ov = sg.secondary_overlay(sec_plane, acq, vol.shape,
                                           self.slice_idx.get(), self.n_slices.get(),
                                           self.slice_thickness.get(), self.slice_gap.get(),
                                           fov_frac, self.inplane_off.get())
            self._scout_overlays = {}
            for i, plane in enumerate(self._scout_plane_names):
                if i == roles["primary"]:
                    self._scout_overlays[plane] = {"role": "primary",   "info": info}
                elif i == roles["secondary"]:
                    self._scout_overlays[plane] = {"role": "secondary", "info": sec_ov}
                else:
                    self._scout_overlays[plane] = {"role": "acqplane",  "info": ip_box}

        self._scout_primary_ax = self.scout_axes[roles["primary"]]
        self._scout_primary_plane = self._scout_plane_names[roles["primary"]]
        self.scout_ax = self._scout_primary_ax
        self._scout_gizmo_center = center

        # ── Draw each panel ──────────────────────────────────────────────────
        self._scout_angle_handles = []   # rebuilt every redraw
        for i, plane in enumerate(self._scout_plane_names):
            ax = self.scout_axes[i]
            ax.clear()
            ax.set_facecolor(C_CANVAS)
            ax.set_axis_off()

            # Background: slice through planned centre (sagittal needs LR flip)
            bg_raw = scouts_bg[plane]
            if plane == "sagittal":
                bg_raw = np.fliplr(bg_raw)
            ax.imshow(simulate_slice(bg_raw, 600, 12, "SE"),
                      cmap="gray", origin="lower", aspect="auto")

            role = self._scout_overlays[plane]["role"]
            ov_info = self._scout_overlays[plane]["info"]

            if role == "primary":
                color = "#ffdd44"
                if is_oblique:
                    cx, cy = self._display_center(plane, center)
                    _angle_var = self._ANGLE_MAP[acq]["primary"]
                    for seg in ov_info.get("edges", []):
                        if seg is not None:
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=2.5)
                            # Endpoint markers — grab anywhere on the line to rotate
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]], "D",
                                    color="#ff5533", markersize=6,
                                    markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (seg[0], seg[1], seg[2], seg[3], plane, _angle_var, cx, cy))
                    slices_segs = ov_info.get("slices", [])
                    mid_j = len(slices_segs) // 2
                    for j, seg in enumerate(slices_segs):
                        if seg is not None:
                            lw = 1.4 if j == mid_j else 0.7
                            alpha = 0.9 if j == mid_j else 0.55
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=lw, alpha=alpha)
                    ax.set_title(f"{plane.capitalize()}  [oblique — drag edge to angle]",
                                 color=color, fontsize=8, pad=2)
                else:
                    # Non-oblique: draw box + register through-edges as angle handles
                    x0, y0, w, h = ov_info["x0"], ov_info["y0"], ov_info["w"], ov_info["h"]
                    ax.add_patch(Rectangle((x0, y0), w, h,
                                           fill=False, edgecolor=color, linewidth=1.8))
                    # Corner handles so the box reads as resizable.
                    ax.plot([x0, x0 + w, x0, x0 + w], [y0, y0, y0 + h, y0 + h], "s",
                            color=color, markersize=4, markeredgecolor="#2a323c",
                            markeredgewidth=0.5)
                    for L in ov_info["lines"]:
                        if ov_info["line_axis"] == "y":
                            ax.plot([x0, x0 + w], [L, L], color=color, linewidth=0.6, alpha=0.6)
                        else:
                            ax.plot([L, L], [y0, y0 + h], color=color, linewidth=0.6, alpha=0.6)
                    # Angle handles on the through-direction edges (top/bottom or left/right)
                    cx_p, cy_p = self._display_center(plane, center)
                    _av = self._ANGLE_MAP[acq]["primary"]
                    if ov_info["through"] == "v":
                        ang_edges = [(x0, y0, x0 + w, y0), (x0, y0 + h, x0 + w, y0 + h)]
                    else:
                        ang_edges = [(x0, y0, x0, y0 + h), (x0 + w, y0, x0 + w, y0 + h)]
                    for seg in ang_edges:
                        ax.plot([seg[0], seg[2]], [seg[1], seg[3]], "D",
                                color="#ff5533", markersize=5,
                                markeredgecolor="white", markeredgewidth=0.7)
                        self._scout_angle_handles.append(
                            (seg[0], seg[1], seg[2], seg[3], plane, _av, cx_p, cy_p))
                    ax.set_title(f"{plane.capitalize()}  [drag edge to angle]",
                                 color=color, fontsize=8, pad=2)

            elif role == "secondary":
                color = C_ACCENT_HI
                if is_oblique:
                    cx, cy = self._display_center(plane, center)
                    _angle_var = self._ANGLE_MAP[acq]["secondary"]
                    for seg in ov_info.get("edges", []):
                        if seg is not None:
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=2.0, linestyle="--")
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]], "D",
                                    color=C_ACCENT, markersize=5,
                                    markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (seg[0], seg[1], seg[2], seg[3], plane, _angle_var, cx, cy))
                    slices_segs = ov_info.get("slices", [])
                    mid_j = len(slices_segs) // 2
                    for j, seg in enumerate(slices_segs):
                        if seg is not None:
                            lw = 1.4 if j == mid_j else 0.7
                            alpha = 0.9 if j == mid_j else 0.55
                            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                                    color=color, linewidth=lw, alpha=alpha)
                    ax.set_title(f"{plane.capitalize()}  [drag edge to angle]",
                                 color=color, fontsize=8, pad=2)
                elif ov_info:
                    lo, hi = ov_info["span"]
                    cx_s, cy_s = self._display_center(plane, center)
                    _av_s = self._ANGLE_MAP[acq]["secondary"]
                    mid_pos_idx = len(ov_info["positions"]) // 2
                    for j, pos in enumerate(ov_info["positions"]):
                        lw = 1.4 if j == mid_pos_idx else 0.7
                        alpha = 0.9 if j == mid_pos_idx else 0.55
                        if ov_info["orient"] == "h":
                            ax.plot([lo, hi], [pos, pos], color=color, lw=lw, alpha=alpha)
                            # Endpoint markers + register as angle handle
                            ax.plot([lo, hi], [pos, pos], "D", color=C_ACCENT,
                                    markersize=5, markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (lo, pos, hi, pos, plane, _av_s, cx_s, cy_s))
                        else:
                            ax.plot([pos, pos], [lo, hi], color=color, lw=lw, alpha=alpha)
                            ax.plot([pos, pos], [lo, hi], "D", color=C_ACCENT,
                                    markersize=5, markeredgecolor="white", markeredgewidth=0.7)
                            self._scout_angle_handles.append(
                                (pos, lo, pos, hi, plane, _av_s, cx_s, cy_s))
                    ax.set_title(f"{plane.capitalize()}  [drag edge to angle / move]",
                                 color=color, fontsize=8, pad=2)

            else:  # acqplane
                color = "#ff8844"
                ax.add_patch(Rectangle((ip_box["x0"], ip_box["y0"]),
                                       ip_box["w"], ip_box["h"],
                                       fill=False, edgecolor=color,
                                       linewidth=1.4, linestyle="--"))
                lbl = "oblique acq" if is_oblique else "acq plane"
                ax.set_title(f"{plane.capitalize()}  [{lbl}]",
                             color=color, fontsize=8, pad=2)

        self._draw_satband_on_scout()
        self._draw_angle_gizmo()
        self.scout_canvas.draw()

    def _draw_angle_gizmo(self) -> None:
        """Aesthetic angle gizmo on the primary panel: a centre pivot, a live degree
        readout, and an arc sweeping to the current oblique angle — so the rotation
        centre and amount are clear at a glance."""
        from matplotlib.patches import Arc
        ax = self._scout_primary_ax
        center = getattr(self, "_scout_gizmo_center", None)
        if ax is None or center is None:
            return
        tilt, rot = self.slice_tilt.get(), self.slice_rot.get()
        cx, cy = self._display_center(self._scout_primary_plane, center)
        ax.plot([cx], [cy], "o", color="#7fb8ff", markersize=5,
                markeredgecolor="white", markeredgewidth=0.6, zorder=6)
        if abs(tilt) > 0.5 or abs(rot) > 0.5:
            prim = tilt if self._ANGLE_MAP[self.orientation.get()]["primary"] == "tilt" else rot
            r = 16.0
            ax.add_patch(Arc((cx, cy), 2 * r, 2 * r, angle=0.0,
                             theta1=min(0.0, prim), theta2=max(0.0, prim),
                             color="#7fb8ff", lw=1.1, zorder=6))
            ax.plot([cx, cx + r], [cy, cy], color="#7fb8ff", lw=0.6, alpha=0.5, zorder=6)
            ax.text(cx + r + 3, cy, f"{tilt:+.0f}° / {rot:+.0f}°", color="#7fb8ff",
                    fontsize=7, va="center", ha="left", zorder=6)

    def _draw_satband_on_scout(self) -> None:
        """Draw the saturation band as the projected 3-D slab on every localizer panel
        — so the cross-plane angle is visible where it tilts (parity with the browser)
        — with the interactive handles on the acquired-plane panel: drag the body to
        move it (along its normal), an end handle to angle it in-plane. Stored geometry
        (`_scout_satband_info` + `_scout_satband_ax`) is what the press/hover hit-tests."""
        import math
        from matplotlib.patches import Polygon
        import scan_geometry as sg
        from oblique import sat_band_normal, scout_band
        self._scout_satband_info = None
        self._scout_satband_ax = None
        if not self.satband_enabled.get():
            return
        # The slab isn't applied on the oblique path, so don't draw a band that won't
        # saturate (the prescription readout warns instead).
        if abs(self.slice_tilt.get()) > 0.5 or abs(self.slice_rot.get()) > 0.5:
            return
        orient = self.orientation.get()
        vol = self.phantom_3d
        ny = vol.shape[1]
        normal = sat_band_normal(orient, self.satband_angle.get(), self.satband_angle2.get())
        rowax = sg._SLICE_AXES[orient][1]
        center = sg.sat_band_center(vol.shape, normal, self.satband_pos.get() / 100.0)
        thick = sg.sat_band_half_width(vol.shape[rowax], self.satband_width.get() / 100.0) * 2.0
        proj = scout_band(vol.shape, normal, tuple(center), n_slices=1,
                          thickness_mm=thick, gap_mm=0.0, voxel_size=(1.0, 1.0, 1.0))
        c0 = sg.sat_band_center(vol.shape, normal, 0.0)
        c1 = sg.sat_band_center(vol.shape, normal, 1.0)

        for ax, plane in zip(self.scout_axes, self._scout_plane_names, strict=True):
            sov = proj[plane]
            fc = (lambda x: ny - 1 - x) if plane == "sagittal" else (lambda x: x)
            e0, e1e = sov["edges"]
            if e0 and e1e:                          # tinted slab footprint
                ax.add_patch(Polygon(
                    [(fc(e0[0]), e0[1]), (fc(e0[2]), e0[3]),
                     (fc(e1e[2]), e1e[3]), (fc(e1e[0]), e1e[1])],
                    closed=True, facecolor="#e6b35a", alpha=0.22,
                    edgecolor="#e6b35a", linewidth=1.0))
            seg = (sov["slices"] or [None])[0]
            if seg is None:
                continue
            ax.plot([fc(seg[0]), fc(seg[2])], [seg[1], seg[3]],
                    color="#e6b35a", lw=0.9, alpha=0.7)
            if plane != orient:                     # cross panels are read-only
                continue
            # --- acquired-plane panel: the interactive band ---
            e1 = (fc(seg[0]), seg[1]); e2 = (fc(seg[2]), seg[3])
            cx, cy = (e1[0] + e2[0]) / 2.0, (e1[1] + e2[1]) / 2.0
            vx, vy = e2[0] - cx, e2[1] - cy
            ln = math.hypot(vx, vy) or 1.0
            d = (vx / ln, vy / ln); n = (-d[1], d[0])
            if e0 and e1e:                          # half thickness from the edge offset
                m0 = ((fc(e0[0]) + fc(e0[2])) / 2.0, (e0[1] + e0[3]) / 2.0)
                half_t = max(1.5, math.hypot(m0[0] - cx, m0[1] - cy))
            else:
                half_t = max(1.5, self.satband_width.get() / 100.0 * vol.shape[rowax] / 2.0)
            ax.plot([e1[0], e2[0]], [e1[1], e2[1]], "s", color="#ff7733", markersize=6,
                    markeredgecolor="white", markeredgewidth=0.7)
            ax.text(cx, cy, "SAT", color="#3a2a10", fontsize=7, ha="center",
                    va="center", fontweight="bold")
            p0 = self._display_center(plane, c0)    # the move-drag travel line (pos 0→100)
            p1 = self._display_center(plane, c1)
            self._scout_satband_ax = ax
            self._scout_satband_info = dict(cx=cx, cy=cy, d=d, n=n, ln=ln, half_t=half_t,
                                            e1=e1, e2=e2, p0=p0, p1=p1)

    # Which angle variable is controlled by dragging each panel role in oblique mode.
    # Derived from: rot_deg makes angled lines on primary panels; tilt_deg on secondary.
    # Exception: sagittal acquisition has them swapped.
    _ANGLE_MAP: dict[str, dict[str, str]] = {
        "axial":    {"primary": "rot",  "secondary": "tilt"},
        "coronal":  {"primary": "rot",  "secondary": "tilt"},
        "sagittal": {"primary": "tilt", "secondary": "rot"},
    }

    def _display_center(self, panel: str, center: np.ndarray) -> tuple:
        """Return (cx, cy) of the slab center in display coords for the given scout panel."""
        nY = self.phantom_3d.shape[1]
        cZ, cY, cX = float(center[0]), float(center[1]), float(center[2])
        if panel == "axial":
            return cX, cY
        elif panel == "coronal":
            return cX, cZ
        else:  # sagittal — Y axis is flipped
            return nY - 1.0 - cY, cZ

    def _compute_slab_center(self) -> np.ndarray:
        """(Z, Y, X) voxel-index centre of the prescribed slab (via controller)."""
        self._sync_sim()
        return self.sim._compute_slab_center(self.orientation.get(), self.slice_idx.get())

    def _reset_oblique(self) -> None:
        self.slice_tilt.set(0.0)
        self.slice_rot.set(0.0)
        self.inplane_fov_pct.set(100)
        self.inplane_off.set(0.0)
        if self.fov_planning.get():
            self._draw_scout(self.get_current_params())
        self.schedule_recalculate()

    @staticmethod
    def _scout_handle_points(info: dict) -> list:
        x0, y0, w, h = info["x0"], info["y0"], info["w"], info["h"]
        return [(x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)]

    def on_fov_planning_toggle(self) -> None:
        on = self.fov_planning.get()
        self.plan_frame.setVisible(on)
        if not on:
            self.scout_canvas.setVisible(False)
            self._ensure_1x2_layout()
        self.recalculate()

    # --- scout mouse interaction ---
    def _scout_hit_test(self, event: object) -> str | None:
        """Return 'move'|'resize_cov'|'resize_fov' for a press location, or None."""
        info = self._scout_box_info
        if info is None or event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return None
        x, y = event.xdata, event.ydata  # type: ignore[attr-defined]
        x0, y0, w, h = info["x0"], info["y0"], info["w"], info["h"]
        tol = max(4.0, 0.03 * max(info["through_len"], info["inplane_len"]))
        inside = (x0 - tol <= x <= x0 + w + tol) and (y0 - tol <= y <= y0 + h + tol)
        if not inside:
            return None

        through_v = info["through"] == "v"
        # The "coverage" dimension is the through direction; "fov" is in-plane.
        # Only register an edge grab if (a) the cursor is within tol of that edge
        # AND (b) the box is thick enough in that dimension to have a distinct
        # interior (otherwise a centre press on a thin slab is ambiguous -> move).
        cov_dim = h if through_v else w          # through extent on screen
        fov_dim = w if through_v else h          # in-plane extent on screen

        def near_edge(coord: float, lo: float, length: float) -> bool:
            return abs(coord - lo) < tol or abs(coord - (lo + length)) < tol

        if through_v:
            cov_edge = near_edge(y, y0, h) and cov_dim > 3 * tol
            fov_edge = near_edge(x, x0, w) and fov_dim > 3 * tol
        else:
            cov_edge = near_edge(x, x0, w) and cov_dim > 3 * tol
            fov_edge = near_edge(y, y0, h) and fov_dim > 3 * tol

        if cov_edge and not fov_edge:
            return "resize_cov"
        if fov_edge and not cov_edge:
            return "resize_fov"
        if cov_edge and fov_edge:
            # corner: prefer the dimension whose edge is closest
            return "resize_fov"
        return "move"

    # through/through_sign for secondary panel drag — depends only on acquisition
    _SEC_THROUGH: dict[str, tuple[str, int]] = {
        "axial":    ("v", +1),
        "coronal":  ("h", -1),
        "sagittal": ("h", +1),
    }

    # Common oblique angles the drag magnets onto (degrees), within _SNAP_TOL.
    _SNAP_TARGETS = (0.0, 15.0, 30.0, 45.0, -15.0, -30.0, -45.0)
    _SNAP_TOL = 2.5

    def _snap_angle(self, val: float) -> float:
        """Magnet the dragged angle onto a nearby common value (0/±15/±30/±45)."""
        for t in self._SNAP_TARGETS:
            if abs(val - t) <= self._SNAP_TOL:
                return t
        return val

    def _satband_hit(self, event: object) -> "str | None":
        """'satangle' near an end handle, 'satmove' inside the band body, else None."""
        import math
        sb = self._scout_satband_info
        if sb is None or event.inaxes is not self._scout_satband_ax:  # type: ignore[attr-defined]
            return None
        if event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return None
        px, py = event.xdata, event.ydata  # type: ignore[attr-defined]
        for ex, ey in (sb["e1"], sb["e2"]):
            if math.hypot(px - ex, py - ey) < 7.0:
                return "satangle"
        dx, dy = px - sb["cx"], py - sb["cy"]
        along = dx * sb["d"][0] + dy * sb["d"][1]
        perp = dx * sb["n"][0] + dy * sb["n"][1]
        if abs(perp) <= sb["half_t"] + 3.0 and abs(along) <= sb["ln"]:
            return "satmove"
        return None

    def _scout_press(self, event: object) -> None:
        if not self.fov_planning.get() or event.inaxes is None:  # type: ignore[attr-defined]
            return
        if event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return
        px, py = event.xdata, event.ydata  # type: ignore[attr-defined]

        # ── Saturation band takes priority (it sits inside the FOV box) ────
        sat = self._satband_hit(event)
        if sat is not None:
            self._scout_drag = dict(mode=sat, x=px, y=py)
            return

        # ── Edge-line hit test ─────────────────────────────────────────────
        # Outer 25% of each edge line  →  angle drag  (◆ endpoints)
        # Middle 50%                   →  fall through to normal move routing
        import math as _math
        line_tol = 7.0
        for (lx0, ly0, lx1, ly1, h_plane, angle_var, cx, cy) in self._scout_angle_handles:
            panel_idx = self._scout_plane_names.index(h_plane)
            if event.inaxes is not self.scout_axes[panel_idx]:  # type: ignore[attr-defined]
                continue
            ldx, ldy = lx1 - lx0, ly1 - ly0
            seg_len_sq = ldx * ldx + ldy * ldy
            if seg_len_sq < 1e-6:
                t, dist = 0.5, _math.hypot(px - lx0, py - ly0)
            else:
                t = max(0.0, min(1.0, ((px - lx0) * ldx + (py - ly0) * ldy) / seg_len_sq))
                dist = _math.hypot(px - (lx0 + t * ldx), py - (ly0 + t * ldy))
            if dist >= line_tol:
                continue
            if t < 0.25 or t > 0.75:
                # Near an endpoint → angle drag
                self._scout_drag = dict(mode="angle", x=px, y=py,
                                        angle_var=angle_var, cx=cx, cy=cy)
                return
            # Near the middle → stop checking handles, fall through to move routing
            break

        # ── Normal panel-role routing ──────────────────────────────────────
        clicked_plane: str | None = None
        for i, ax in enumerate(self.scout_axes):
            if event.inaxes is ax:  # type: ignore[attr-defined]
                clicked_plane = self._scout_plane_names[i]
                break
        if clicked_plane is None:
            return
        ov = self._scout_overlays.get(clicked_plane)
        if ov is None:
            return
        role = ov["role"]
        is_oblique = abs(self.slice_tilt.get()) > 0.5 or abs(self.slice_rot.get()) > 0.5
        acq = self.orientation.get()
        if role == "primary":
            if is_oblique:
                self._scout_drag = dict(mode="move", x=px, y=py,
                                        secondary=False, oblique=True)
            else:
                mode = self._scout_hit_test(event)
                if mode is None:
                    return
                self._scout_drag = dict(mode=mode, x=px, y=py,
                                        secondary=False, oblique=False)
        elif role == "secondary":
            through, sign = self._SEC_THROUGH.get(acq, ("v", 1))
            meta = {"through": through, "through_sign": sign}
            self._scout_drag = dict(mode="move", x=px, y=py,
                                    secondary=True, overlay=meta)

    def _scout_hover(self, event: object) -> None:
        """Change the cursor over the localizer so it's obvious what each region
        does: move the box, resize the FOV / coverage edges, or grab an edge to
        angle (oblique). Arrow elsewhere."""
        from PyQt6.QtCore import Qt
        import math as _math
        canvas = self.scout_canvas
        if (not self.fov_planning.get() or event.inaxes is None       # type: ignore[attr-defined]
                or event.xdata is None or event.ydata is None):       # type: ignore[attr-defined]
            canvas.unsetCursor(); return
        px, py = event.xdata, event.ydata                              # type: ignore[attr-defined]

        # 0) Saturation band (priority — it sits inside the FOV box).
        sat = self._satband_hit(event)
        if sat == "satangle":
            canvas.setCursor(Qt.CursorShape.PointingHandCursor); return
        if sat == "satmove":
            canvas.setCursor(Qt.CursorShape.SizeAllCursor); return

        # 1) Near an angle-handle endpoint → rotate affordance.
        for (lx0, ly0, lx1, ly1, h_plane, _av, _cx, _cy) in self._scout_angle_handles:
            pidx = self._scout_plane_names.index(h_plane)
            if event.inaxes is not self.scout_axes[pidx]:              # type: ignore[attr-defined]
                continue
            ldx, ldy = lx1 - lx0, ly1 - ly0
            seg = ldx * ldx + ldy * ldy
            t = 0.5 if seg < 1e-6 else max(0.0, min(1.0, ((px - lx0) * ldx + (py - ly0) * ldy) / seg))
            dist = _math.hypot(px - (lx0 + t * ldx), py - (ly0 + t * ldy))
            if dist < 7.0 and (t < 0.25 or t > 0.75):
                canvas.setCursor(Qt.CursorShape.PointingHandCursor); return

        # 2) Over the primary box → move / resize cursor by region.
        plane = None
        for i, ax in enumerate(self.scout_axes):
            if event.inaxes is ax:                                     # type: ignore[attr-defined]
                plane = self._scout_plane_names[i]; break
        ov = self._scout_overlays.get(plane) if plane else None
        if ov and ov["role"] == "primary" and self._scout_box_info is not None:
            mode = self._scout_hit_test(event)
            through_v = self._scout_box_info["through"] == "v"
            cur = {
                "move": Qt.CursorShape.SizeAllCursor,
                "resize_cov": Qt.CursorShape.SizeVerCursor if through_v else Qt.CursorShape.SizeHorCursor,
                "resize_fov": Qt.CursorShape.SizeHorCursor if through_v else Qt.CursorShape.SizeVerCursor,
            }.get(mode or "", Qt.CursorShape.ArrowCursor)
            canvas.setCursor(cur); return
        if ov and ov["role"] == "secondary":
            canvas.setCursor(Qt.CursorShape.SizeVerCursor); return
        canvas.unsetCursor()

    def _scout_motion(self, event: object) -> None:
        if self._scout_drag is None:
            self._scout_hover(event)            # cursor feedback while not dragging
            return
        if event.xdata is None or event.ydata is None:  # type: ignore[attr-defined]
            return
        import scan_geometry as sg
        import math
        d = self._scout_drag
        ex, ey = event.xdata, event.ydata  # type: ignore[attr-defined]
        dx = ex - d["x"]; dy = ey - d["y"]
        d["x"], d["y"] = ex, ey
        orient = self.orientation.get()

        if d.get("mode") in ("satmove", "satangle"):
            sb = self._scout_satband_info
            if sb is not None:
                if d["mode"] == "satmove":     # drag the body → move along the normal
                    p0, p1 = sb["p0"], sb["p1"]
                    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
                    t = ((ex - p0[0]) * vx + (ey - p0[1]) * vy) / ((vx * vx + vy * vy) or 1.0)
                    self.satband_pos.set(int(round(float(np.clip(t * 100.0, 0, 100)))))
                else:                          # drag an end handle → angle the band
                    ang = math.degrees(math.atan2(ey - sb["cy"], ex - sb["cx"]))
                    if ang > 90:
                        ang -= 180
                    elif ang < -90:
                        ang += 180
                    self.satband_angle.set(int(round(float(np.clip(ang, -90, 90)))))
                self._draw_scout(self.get_current_params())
                self.schedule_recalculate()
            return

        if d.get("mode") == "angle":
            # Angle drag: compute angular change from handle movement around slab centre
            cx, cy = d["cx"], d["cy"]
            prev_x, prev_y = ex - dx, ey - dy  # position before this event
            dist_prev = math.hypot(prev_x - cx, prev_y - cy)
            if dist_prev < 2.0:
                return  # too close to centre; skip to avoid large jumps
            angle_prev = math.atan2(prev_y - cy, prev_x - cx)
            angle_new  = math.atan2(ey - cy, ex - cx)
            d_angle = math.degrees(angle_new - angle_prev)
            # Clamp to avoid large jumps at wrap-around
            if d_angle > 90:
                d_angle -= 180
            elif d_angle < -90:
                d_angle += 180
            if d["angle_var"] == "tilt":
                new_val = self._snap_angle(float(np.clip(self.slice_tilt.get() + d_angle, -45, 45)))
                self.slice_tilt.set(new_val)
            else:
                new_val = self._snap_angle(float(np.clip(self.slice_rot.get() + d_angle, -45, 45)))
                self.slice_rot.set(new_val)
            self._draw_scout(self.get_current_params())
            self.schedule_recalculate()
            return

        if d.get("secondary"):
            # Secondary panel: only move through-axis position
            sec_meta = d["overlay"]
            if sec_meta:
                through = sec_meta["through"]
                sign = sec_meta["through_sign"]
                raw = dy if through == "v" else dx
                dx_through = raw * sign
                si, _, _, _ = sg.update_from_drag(
                    orient, self.phantom_3d.shape, "move", dx_through, 0.0,
                    self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
                    self.slice_gap.get(), self.inplane_fov_pct.get() / 100.0, self.inplane_off.get())
                self.slice_idx.set(int(round(si)))
        elif d.get("oblique"):
            # Oblique primary: translate slice centre using standard through-axis mapping
            import scan_geometry as _sg
            cfg = _sg.SCOUT[orient]
            raw = dy if cfg["through"] == "v" else dx
            si, _, _, _ = sg.update_from_drag(
                orient, self.phantom_3d.shape, "move", raw, 0.0,
                self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
                self.slice_gap.get(), self.inplane_fov_pct.get() / 100.0, self.inplane_off.get())
            self.slice_idx.set(int(round(si)))
        else:
            info = self._scout_box_info
            if info is None:
                return
            if info["through"] == "v":
                dx_through, d_inplane = dy, dx
            else:
                dx_through, d_inplane = dx, dy
            si, off, fr, n = sg.update_from_drag(
                orient, self.phantom_3d.shape, d["mode"], dx_through, d_inplane,
                self.slice_idx.get(), self.n_slices.get(), self.slice_thickness.get(),
                self.slice_gap.get(), self.inplane_fov_pct.get() / 100.0, self.inplane_off.get())
            self.slice_idx.set(int(round(si)))
            self.inplane_off.set(off)
            self.inplane_fov_pct.set(int(round(fr * 100)))
            self.n_slices.set(n)

        self._draw_scout(self.get_current_params())
        self.schedule_recalculate()

    def _scout_release(self, event: object) -> None:
        if self._scout_drag is not None:
            self._scout_drag = None
            self.recalculate()
