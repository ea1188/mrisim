"""SWI through the Simulator: the 'Susceptibility (SWI)' sequence renders a GRE
magnitude darkened by the venous phase mask. Uses a small synthetic volume + a
vessel stripe so the test stays fast."""
import numpy as np
import pytest

from simulator import Simulator, default_params


def _vol_and_vessels(Z=24, Y=48, X=48):
    """A WM block with a vessel stripe painted as blood (label 11) in the vessel
    volume only — so the SWI magnitude sees WM there, the phase sees a vein."""
    vol = np.zeros((Z, Y, X), dtype=np.uint8)
    vol[:, 8:40, 8:40] = 3                     # white-matter block
    vessels = vol.copy()
    vessels[:, 23:25, 14:34] = 11              # a thin venous stripe through the block
    return vol, vessels


@pytest.fixture(scope="module")
def sim():
    s = Simulator()
    vol, vessels = _vol_and_vessels()
    s.volume = vol
    s.vessels = vessels
    s.orientation = "axial"; s.slice_idx = 12
    return s


def _p(**kw):
    base = dict(TR=40, TE=20, flip_angle=20, matrix_size=48, snr_level=400)
    base.update(kw)
    return default_params(**base)


def test_swi_renders_finite_nonblank(sim):
    img, m = sim.simulate(_p(sequence="Susceptibility (SWI)"))
    assert img.ndim == 2 and np.all(np.isfinite(img)) and float(img.max()) > 0
    assert m["scan_time"] > 0


def test_swi_darkens_veins_vs_gre(sim):
    """The venous phase mask darkens tissue near the vein relative to plain GRE
    (the dipole field blooms around the vessel), with net darkening overall and a
    clearly-darkened region — while never brightening."""
    swi_img = sim.simulate(_p(sequence="Susceptibility (SWI)", TE=30))[0]
    gre_img = sim.simulate(_p(sequence="Gradient Echo", TE=30))[0]
    assert not np.allclose(swi_img, gre_img), "SWI mask had no effect"
    tissue = gre_img > 0.5 * gre_img.max()          # the WM block
    ratio = swi_img[tissue] / gre_img[tissue]
    assert ratio.mean() < 0.99, "the phase mask should net-darken tissue near the vein"
    assert ratio.min() < 0.5, "no voxel clearly darkened by venous phase"


def test_swi_minip_projects_a_vein_from_a_neighbouring_slice():
    """A vein present only on neighbouring slices (not the imaged one) still darkens
    the displayed SWI, because it is read as a thin-slab minimum-intensity venogram —
    the whole point of the slab. A single-slice render would miss it."""
    import simulator as sim_mod
    Z, Y, X = 24, 48, 48
    vol = np.zeros((Z, Y, X), dtype=np.uint8)
    vol[:, 8:40, 8:40] = 3
    vessels = vol.copy()
    # A vein on the slabs *around* slice 12 but not on 12 itself.
    for z in (10, 11, 13, 14):
        vessels[z, 23:25, 14:34] = 11
    s = Simulator()
    s.volume = vol; s.vessels = vessels
    s.orientation = "axial"; s.slice_idx = 12

    old = sim_mod._SWI_MINIP_SLAB
    try:
        sim_mod._SWI_MINIP_SLAB = 1
        single = s.simulate(_p(sequence="Susceptibility (SWI)", TE=30))[0]
        sim_mod._SWI_MINIP_SLAB = 5
        slab = s.simulate(_p(sequence="Susceptibility (SWI)", TE=30))[0]
    finally:
        sim_mod._SWI_MINIP_SLAB = old
    # The off-slice vein pulls the slab venogram darker than the single slice, and
    # never brighter (min-projection).
    assert slab.mean() < single.mean(), "slab MinIP did not project the off-slice vein"
    assert np.all(slab <= single + 1e-6), "MinIP brightened a voxel"


def test_swi_darkens_microhaemorrhage_via_phase():
    """A microhaemorrhage (label 25) accrues negative phase like venous blood, so it
    darkens under the SWI phase mask — not only via magnitude T2*. Compared against
    the same bleed with the phase mask absent (a plain GRE), SWI must be darker over
    the bleed."""
    Z, Y, X = 24, 48, 48
    vol = np.zeros((Z, Y, X), dtype=np.uint8)
    vol[:, 8:40, 8:40] = 3
    vol[:, 22:26, 22:26] = 25                   # a microbleed block, all slices
    s = Simulator()
    s.volume = vol; s.vessels = vol.copy()      # bleed is in the labelled vessel vol
    s.orientation = "axial"; s.slice_idx = 12
    swi_img = s.simulate(_p(sequence="Susceptibility (SWI)", TE=30))[0]
    gre_img = s.simulate(_p(sequence="Gradient Echo", TE=30))[0]
    bleed = gre_img[22:26, 22:26]
    assert swi_img[22:26, 22:26].mean() < bleed.mean(), \
        "the phase mask should darken the microbleed below plain GRE"


def test_swi_without_vessels_still_renders():
    """No vessel tree (e.g. a body region): SWI falls back to the tissue field and
    still produces a finite image."""
    s = Simulator()
    s.volume = _vol_and_vessels()[0]
    s.vessels = None
    s.orientation = "axial"; s.slice_idx = 12
    img, _ = s.simulate(_p(sequence="Susceptibility (SWI)"))
    assert np.all(np.isfinite(img)) and float(img.max()) > 0
