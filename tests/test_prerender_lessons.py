"""The course's lesson viewer shows pre-rendered step images, so the prerender
payload builder must mirror the live simulator: lesson steps carry *partial*
state (the live player applies each step on top of the previous one), and every
image-affecting control id must map into the render payload. A key that is
dropped here silently prerenders the wrong image (e.g. the receive-coil lesson
shipped three identical pictures)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from prerender_lessons import payload_for_state, step_payloads  # noqa: E402


def test_receivecoil_maps_to_payload():
    p = payload_for_state({"region": "Brain", "seq": "Spin Echo", "receivecoil": "surface"})
    assert p["receive_coil"] == "surface"


def test_artifact_and_display_keys_map():
    p = payload_for_state({
        "seq": "Diffusion (DWI)", "chemshift": True, "suscept": True,
        "motion": True, "motiontype": "pulsatile", "diffdisp": "ADC map",
        "angiotype": "Phase Contrast", "accelmethod": "GRAPPA",
    })
    prm = p["params"]
    assert prm["chemical_shift_enabled"] and prm["susceptibility_enabled"]
    assert prm["motion_enabled"] and prm["motion_type"] == "pulsatile"
    assert prm["diff_display"] == "ADC map"
    assert prm["angio_type"] == "Phase Contrast"
    assert prm["accel_method"] == "GRAPPA"


def test_step_payloads_accumulate_like_the_live_player():
    lesson = {"title": "t", "steps": [
        {"text": "a", "state": {"region": "Brain", "seq": "Gradient Echo",
                                "orient": "axial", "slice": 90, "tr": 150, "te": 5, "fa": 10}},
        {"text": "concept step, no state"},
        {"text": "b", "state": {"fa": 35}},
        {"text": "c", "state": {"receivecoil": "head8"}},
    ]}
    out = dict(step_payloads(lesson))
    assert sorted(out) == [0, 2, 3]          # stateless step renders no image
    # the delta step keeps everything set earlier, changing only what it names
    assert out[2]["params"]["sequence"] == "Gradient Echo"
    assert out[2]["params"]["TR"] == 150
    assert out[2]["params"]["flip_angle"] == 35
    assert out[2]["slice_idx"] == 90
    # and the coil step keeps the flip-angle change from the step before it
    assert out[3]["params"]["flip_angle"] == 35
    assert out[3]["receive_coil"] == "head8"
