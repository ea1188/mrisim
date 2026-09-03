"""Tests for the OSCE target derivation (scripts/derive_osce_targets.py).

The high-standard contract: every numeric grading target is derived from atlas
geometry or engine physics, through the engine's own functions. These tests pin
that contract:

- a synthetic volume with a KNOWN plane angle round-trips through the
  PCA + solver to within 1 degree;
- the spine derivation finds exactly 7 discs with the lordotic tilt
  progression (steepest at the caudal end, where L5-S1 lives);
- the derived inversion times reproduce the engine's own preset TIs
  (STIR 265, FLAIR 2548) from tissue_db alone;
- the script's constants stay in sync with web_adapter's;
- the generated web/osce.json is complete and consistent with presets.py
  and protocols.py.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import derive_osce_targets as dot  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestSolver:
    def test_synthetic_plane_round_trips_within_one_degree(self):
        from oblique import plane_from_angles
        n_true = plane_from_angles("axial", tilt_deg=12.0, rot_deg=0.0)[0]
        ctr = np.array([32.0, 32.0, 32.0])
        idx = np.argwhere(np.ones((64, 64, 64), dtype=bool)).astype(np.float64)
        d = (idx - ctr) @ n_true
        inplane = np.linalg.norm((idx - ctr) - np.outer(d, n_true), axis=1)
        voxels = idx[(np.abs(d) < 1.5) & (inplane < 20)]
        tilt, rot = dot.solve_angles("axial", dot.plane_normal(voxels))
        assert abs(tilt - 12.0) < 1.0
        assert abs(rot) < 1.0

    def test_solver_recovers_a_steep_two_angle_plane(self):
        # Both angles at once, outside the coarse grid's optimum, so the refine
        # walk has to travel: still recovered to within a degree.
        from oblique import plane_from_angles
        n_true = plane_from_angles("axial", tilt_deg=55.0, rot_deg=10.0)[0]
        tilt, rot = dot.solve_angles("axial", n_true)
        n_got = plane_from_angles("axial", tilt_deg=tilt, rot_deg=rot)[0]
        angle = np.degrees(np.arccos(min(1.0, abs(float(np.dot(n_got, n_true))))))
        assert angle < 1.0


class TestSpineDerivation:
    @pytest.fixture(scope="class")
    def spine(self):
        return dot.load_volume("Spine")

    def test_exactly_seven_discs(self, spine):
        comps = dot.components(spine, 15)
        assert len(comps) == 7

    def test_lordotic_tilt_progression(self, spine):
        comps = dot.components(spine, 15)
        tilts = []
        for c in comps:
            t, _r = dot.solve_angles("axial", dot.plane_normal(c["voxels"]))
            tilts.append(t)
        # Caudal end (rank 0) is the steep L5-S1 disc; tilts decrease toward the
        # thoracolumbar junction, within a small tolerance for the edge-clipped
        # top component.
        assert tilts[0] == max(tilts)
        assert tilts[0] > 20.0
        for a, b in zip(tilts, tilts[1:], strict=False):
            assert b <= a + 1.0

    def test_l4l5_is_tilt_only(self, spine):
        comps = dot.components(spine, 15)
        _t, rot = dot.solve_angles("axial", dot.plane_normal(comps[1]["voxels"]))
        assert abs(rot) < 3.0


class TestPhysicsTargets:
    def test_stir_ti_reproduces_engine_preset(self):
        # Spine STIR preset: TI 265 at TR 4000. The derivation must land there
        # from tissue_db's fat T1 alone.
        assert abs(dot.null_ti(4, 4000.0) - 265.0) < 2.0

    def test_flair_ti_reproduces_engine_preset(self):
        # Brain FLAIR preset docstring: TI = 2548 at TR 9000 from CSF T1.
        assert abs(dot.null_ti(1, 9000.0) - 2548.0) < 2.0


class TestConstantsInSync:
    def test_native_fov_matches_web_adapter(self):
        import web_adapter
        assert dot.NATIVE_FOV == web_adapter._NATIVE_FOV

    def test_acq_axis_matches_scout_convention(self):
        # oblique.scout_band's scouts dict: fixed axis per orientation.
        assert dot.ACQ_AXIS == {"axial": 0, "coronal": 1, "sagittal": 2}


class TestGeneratedFile:
    @pytest.fixture(scope="class")
    def osce(self):
        return json.load(open(os.path.join(ROOT, "web", "osce.json")))

    def test_every_derive_resolved(self, osce):
        for s in osce["scenarios"]:
            for c in s["criteria"]:
                assert "derive" not in c, f"{s['id']}/{c['id']} unresolved"
                if c["type"] in ("angulation", "slice", "coverage"):
                    assert "target" in c, f"{s['id']}/{c['id']} missing target"

    def test_presets_exist_and_are_offered_by_the_exam(self, osce):
        import presets
        import protocols
        for s in osce["scenarios"]:
            queue = protocols.PROTOCOLS[s["exam"]]
            for c in s["criteria"]:
                assert presets.get_preset(c["preset"]), c["preset"]
                assert c["preset"] in queue, f"{c['preset']} not offered by {s['exam']}"

    def test_feedback_covers_reachable_verdicts(self, osce):
        can_partial = {"angulation", "coverage", "param"}
        for s in osce["scenarios"]:
            for c in s["criteria"]:
                assert c["feedback"].get("pass") and c["feedback"].get("fail"), c["id"]
                if c["type"] in can_partial:
                    assert c["feedback"].get("partial"), f"{c['id']} lacks partial text"

    def test_regions_carry_geometry(self, osce):
        for s in osce["scenarios"]:
            r = osce["regions"][s["region"]]
            assert len(r["shape"]) == 3 and r["voxel_mm"] > 0

    def test_points_are_positive_ints(self, osce):
        for s in osce["scenarios"]:
            for c in s["criteria"]:
                assert isinstance(c["points"], int) and c["points"] > 0
