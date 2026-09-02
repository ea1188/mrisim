"""Pre-render each guided-lesson step's acquired image to a static PNG, so the
course can show lessons as fast illustrated readers (image + text boxes) without
loading Pyodide/the simulator for every lesson.

For each lesson step that carries a `state`, we build the same render payload the
web app's collectPayload() produces (the lesson state keys are the control ids),
call web_adapter's engine render, and write web/img/lessons/<slug>/<n>.png. Steps
with no `state` (reading/concept steps) get no image. Run by build_web.py; also
runnable standalone for local testing.
"""
import base64
import io
import json
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import web_adapter  # noqa: E402

OUT = os.path.join(ROOT, "web", "img", "lessons")

# Real body-region atlases the browser lazy-fetches from /data/regions; on the
# build host that path doesn't exist (load_region would fall back to a synthetic
# phantom), so inject the real cache the same way load_region would (L/R flip on
# axis 2 only — A-P is already correct; see web_adapter.load_region).
_BODY_SRC = {
    "Knee": "data/knee_kb3d/atlas.npy",
    "Spine": "data/spider_spine/atlas.npy",
    "Abdomen": "data/TotalsegmentatorMRI_dataset_v200/s0246/atlas_iso_adapt_256.npy",
    "Pelvis": "data/TotalsegmentatorMRI_dataset_v200/s0187/atlas_iso_adapt_256.npy",
    "Torso": "data/TotalsegmentatorMRI_dataset_v200/s0250/atlas_iso_adapt_256.npy",
}

# lesson state key -> render params key (mirrors collectPayload in web/app.js)
_PARAM_MAP = {
    "tr": "TR", "te": "TE", "ti": "TI", "fa": "flip_angle", "field": "field_strength",
    "matrix": "matrix_size", "bw": "bandwidth", "nex": "NEX", "thick": "slice_thickness",
    "nslices": "n_slices", "sgap": "slice_gap", "accel": "accel_factor", "pv": "pv_sigma",
    "bval": "b_value", "etl": "etl",
    "accelmethod": "accel_method", "motiontype": "motion_type", "angiotype": "angio_type",
    "diffdisp": "diff_display", "fmridisp": "fmri_display", "qmridisp": "qmri_display",
    "perfdisp": "perf_display", "perfdyndisp": "perf_dyn_display",
}


def slug(s):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", str(s).lower()))


def payload_for_state(st):
    st = st or {}
    params = {}
    if st.get("seq"):
        params["sequence"] = st["seq"]
    for k_state, k_param in _PARAM_MAP.items():
        if k_state in st:
            params[k_param] = st[k_state]
    params["fatsat_enabled"] = bool(st.get("fatsat"))
    params["contrast_enabled"] = bool(st.get("gd"))
    params["contrast_dose"] = 5 if st.get("gd") else 0
    params["flow_enabled"] = bool(st.get("flow"))
    params["motion_enabled"] = bool(st.get("motion"))
    params["chemical_shift_enabled"] = bool(st.get("chemshift"))
    params["susceptibility_enabled"] = bool(st.get("suscept"))
    if st.get("acq3d"):
        params["acq3d"] = True
        if "np" in st:
            params["n_partitions"] = st["np"]
        params["kz_pf"] = 0.75 if st.get("kzpf") else None
    payload = {
        "region": st.get("region", "Brain"),
        "orientation": st.get("orient", "axial"),
        "params": params,
        "label_anatomy": bool(st.get("labelanat")),
        "pathology": st.get("pathology", ""),
        "receive_coil": st.get("receivecoil", "uniform"),
    }
    if "slice" in st:
        payload["slice_idx"] = st["slice"]
    return payload


def step_payloads(lesson):
    """Yield (step_index, render_payload) for each stateful step of a lesson.

    Lesson steps carry *partial* state: the live player applies each step's keys
    on top of the controls as-left by the previous step. Mirror that here by
    accumulating state across the lesson, so a delta step like
    {"receivecoil": "surface"} keeps the region/sequence/TR/TE it inherited."""
    acc = {}
    for i, step in enumerate(lesson.get("steps", [])):
        st = step.get("state")
        if not st:
            continue                     # reading/concept step: text only, no image
        acc.update(st)
        yield i, payload_for_state(acc)


def ensure_region(host, region):
    """Load a region, injecting the real body atlas + texture + mixel with the
    SAME transforms web_adapter.load_region applies (straighten, then body L/R
    flip), so build images match the browser render exactly."""
    if region == "Brain" or region in host._region_cache:
        host.load_region(region)
        return
    src = _BODY_SRC.get(region)
    if src and os.path.exists(os.path.join(ROOT, src)):
        import region_orient
        vol = np.load(os.path.join(ROOT, src))
        tex_p = os.path.join(ROOT, src.replace("atlas", "texture"))
        mix_p = os.path.join(ROOT, src.replace("atlas", "mixel"))
        tex = np.load(tex_p).astype(np.float32) if os.path.exists(tex_p) else None
        mix = np.load(mix_p) if os.path.exists(mix_p) else None
        vol = region_orient.straighten(region, vol, 0)
        if tex is not None:
            tex = region_orient.straighten(region, tex, 1)
        if mix is not None:
            mix = np.stack([region_orient.straighten(region, mix[i], 0)
                            for i in range(mix.shape[0])])
        if region in web_adapter._BODY_REGIONS:
            vol = np.ascontiguousarray(np.flip(vol, axis=2))
            if tex is not None:
                tex = np.ascontiguousarray(np.flip(tex, axis=2))
            if mix is not None:
                mix = np.ascontiguousarray(np.flip(mix, axis=3))
        host._region_cache[region] = vol
        host._region_tex_cache[region] = tex
        host._region_mixel_cache[region] = mix
        host._region_aux_cache[region] = (None, None)
    host.load_region(region)


def main():
    lessons = json.load(open(os.path.join(ROOT, "data", "lessons.json")))["lessons"]
    host = web_adapter._host()
    n_imgs = 0
    for L in lessons:
        title = L.get("title", "")
        d = os.path.join(OUT, slug(title))
        for i, payload in step_payloads(L):
            try:
                ensure_region(host, payload["region"])
                res = host.render(payload)
                png = base64.b64decode(res["image"].split(",")[-1])
            except Exception as e:            # never fail the whole build on one step
                print(f"  lesson '{title}' step {i}: render skipped ({e})")
                continue
            os.makedirs(d, exist_ok=True)
            # These are photographic MR renders shown <=600px wide in the viewer, so
            # a resized/optimized JPEG is ~5x smaller than the raw PNG with no visible
            # loss on the teaching image or its annotations.
            im = Image.open(io.BytesIO(png)).convert("RGB")
            if im.width > 600:
                im = im.resize((600, round(im.height * 600 / im.width)), Image.LANCZOS)
            im.save(os.path.join(d, f"{i}.jpg"), format="JPEG", quality=85, optimize=True)
            n_imgs += 1
    print(f"pre-rendered {n_imgs} lesson step images -> web/img/lessons/")


if __name__ == "__main__":
    main()
