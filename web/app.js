/* MRISim browser edition — boots Pyodide, loads the Qt-free engine (web_adapter),
   and wires the HTML controls to it. Python renders the image/curve to PNG and
   returns JSON metrics; this file is just the control shell. */
"use strict";

const $ = (id) => document.getElementById(id);
let pyodide = null;
let renderFn = null;        // PyProxy: web_adapter.render_json
let booted = false;

const SEQ_FA = new Set(["Gradient Echo", "Balanced SSFP", "MR Angiography"]);
const SEQ_TI = new Set(["Inversion Recovery"]);
// Sequences needing the ~1-minute TOF vessel build the first time (see web_adapter).
const SEQ_SLOW_FIRST = new Set(["MR Angiography"]);
const ACQ3D_SEQ = new Set(["Spin Echo", "Gradient Echo", "Inversion Recovery", "Balanced SSFP"]);

function setSplash(pct, msg) {
  $("splash-bar").style.width = pct + "%";
  if (msg) $("splash-status").textContent = msg;
}

async function boot() {
  setSplash(8, "Loading Pyodide…");
  pyodide = await loadPyodide();
  setSplash(30, "Loading numpy / scipy / matplotlib…");
  await pyodide.loadPackage(["numpy", "scipy", "matplotlib"]);

  setSplash(62, "Loading MRISim engine…");
  const zip = await (await fetch("mrisim_src.zip")).arrayBuffer();
  await pyodide.unpackArchive(zip, "zip", { extractDir: "/src" });

  setSplash(74, "Loading brain phantom…");
  pyodide.FS.mkdirTree("/data");
  const npy = new Uint8Array(await (await fetch("data/brainweb_sub04_anat.npy")).arrayBuffer());
  pyodide.FS.writeFile("/data/brainweb_sub04_anat.npy", npy);

  setSplash(86, "Starting engine…");
  pyodide.runPython("import sys; sys.path.insert(0, '/src')");
  const info = JSON.parse(pyodide.runPython("import json, web_adapter; json.dumps(web_adapter.init())"));
  renderFn = pyodide.runPython("web_adapter.render_json");

  buildControls(info);
  setSplash(100, "Ready");
  $("splash").style.display = "none";
  $("app").hidden = false;
  booted = true;
  render();
}

function buildControls(info) {
  const reg = $("region");
  info.regions.forEach((r) => reg.add(new Option(r, r)));
  // Sequences supported in the web build (engine + a manageable control set).
  const seqs = ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
    "Balanced SSFP", "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)",
    "Quantitative (qMRI)", "Echo Planar (EPI)"];
  const seq = $("sequence");
  seqs.forEach((s) => seq.add(new Option(s, s)));
  $("slice").max = info.max_slice;
  $("slice").value = Math.floor(info.max_slice / 2);

  // Sliders mirror their value to the <output> and trigger a debounced render.
  ["tr", "te", "ti", "fa", "np", "slice"].forEach((id) => {
    $(id).addEventListener("input", () => {
      const out = $(id + "-val"); if (out) out.value = $(id).value;
      schedule();
    });
  });
  [reg, seq, $("field")].forEach((el) => el.addEventListener("change", onSequenceOrRegion));
  ["fatsat", "gd", "flow", "acq3d", "kzpf"].forEach((id) =>
    $(id).addEventListener("change", () => { if (id === "acq3d") syncVisibility(); schedule(); }));
  $("orientation").querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      $("orientation").querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on"); schedule();
    }));
  syncVisibility();
}

function onSequenceOrRegion(e) {
  if (e.target.id === "region") {
    // Region change resizes the volume; refresh the slice range from the engine.
    const d = JSON.parse(pyodide.runPython(
      `import json; json.dumps(web_adapter.set_region(${JSON.stringify(curRegion())}))`));
    $("slice").max = d.max_slice;
    $("slice").value = Math.floor(d.max_slice / 2);
    setOrient("axial");
  }
  syncVisibility();
  schedule();
}

function syncVisibility() {
  const s = $("sequence").value;
  $("fa-row").hidden = !SEQ_FA.has(s);
  $("ti-row").hidden = !SEQ_TI.has(s);
  const is3d = ACQ3D_SEQ.has(s);
  $("acq3d").disabled = !is3d;
  if (!is3d) $("acq3d").checked = false;
  const on3d = is3d && $("acq3d").checked;
  $("np-row").hidden = !on3d;
  $("kzpf-row").hidden = !on3d;
}

const curRegion = () => $("region").value;
function setOrient(v) {
  $("orientation").querySelectorAll("button").forEach((b) =>
    b.classList.toggle("on", b.dataset.v === v));
}
function curOrient() {
  return $("orientation").querySelector("button.on").dataset.v;
}

function collectPayload() {
  const s = $("sequence").value;
  const params = {
    sequence: s,
    TR: +$("tr").value, TE: +$("te").value, TI: +$("ti").value,
    flip_angle: +$("fa").value, field_strength: $("field").value,
    fatsat_enabled: $("fatsat").checked,
    contrast_enabled: $("gd").checked, contrast_dose: $("gd").checked ? 5 : 0,
    flow_enabled: $("flow").checked,
  };
  if (ACQ3D_SEQ.has(s) && $("acq3d").checked) {
    params.acq3d = true;
    params.n_partitions = +$("np").value;
    params.kz_pf = $("kzpf").checked ? 0.75 : null;
  }
  return {
    region: curRegion(), orientation: curOrient(),
    slice_idx: +$("slice").value, curve_mode: "TE decay", params,
  };
}

let timer = null, pending = false, running = false;
function schedule() {
  if (!booted) return;
  clearTimeout(timer);
  timer = setTimeout(render, 120);   // debounce rapid slider input
}

async function render() {
  if (running) { pending = true; return; }     // coalesce overlapping renders
  running = true;
  const payload = collectPayload();
  if (SEQ_SLOW_FIRST.has(payload.params.sequence)) {
    $("hint").textContent = "Building vessel model (one-time, may take ~1 min)…";
  }
  document.body.classList.add("busy");
  // Yield so the busy state + hint paint before the (blocking) Pyodide render.
  await new Promise((r) => setTimeout(r, 0));
  try {
    const res = JSON.parse(renderFn(JSON.stringify(payload)));
    applyResult(res);
  } catch (err) {
    $("hint").textContent = "Render error: " + err;
    console.error(err);
  } finally {
    document.body.classList.remove("busy");
    running = false;
    if (pending) { pending = false; schedule(); }
  }
}

function fmtTime(s) {
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function applyResult(res) {
  $("mainImage").src = res.image;
  $("curveImage").src = res.curve;
  const m = res.metrics;
  $("slice").max = res.max_slice;
  if (+$("slice").value !== res.slice_idx) $("slice").value = res.slice_idx;
  $("slice-val").value = res.slice_idx;
  // Metrics panel
  $("x-res").textContent = m.resolution.toFixed(2) + " mm";
  $("x-scan").textContent = fmtTime(m.scan_time);
  $("x-snr").textContent = `${m.snr_wm.toFixed(1)} / ${m.snr_gm.toFixed(1)}`;
  $("x-cnr").textContent = Math.abs(m.snr_wm - m.snr_gm).toFixed(1);
  $("x-sar").textContent = m.sar_head.toFixed(1) + " W/kg" + (m.sar_exceeds ? " ⚠" : "");
  // Top chips
  $("m-scan").textContent = fmtTime(m.scan_time);
  $("m-snrwm").textContent = m.snr_wm.toFixed(1);
  $("m-weight").textContent = weighting($("sequence").value, +$("tr").value, +$("te").value);
  if (!SEQ_SLOW_FIRST.has($("sequence").value)) $("hint").textContent = "";
}

function weighting(seq, tr, te) {
  const map = {
    "Diffusion (DWI)": "Diffusion", "MR Angiography": "Flow", "fMRI (BOLD)": "T2* (BOLD)",
    "Quantitative (qMRI)": "Quantitative", "Echo Planar (EPI)": "T2* (EPI)",
    "Balanced SSFP": "T2/T1",
  };
  if (map[seq]) return map[seq];
  if (tr < 800 && te < 30) return "T1";
  if (tr > 2000 && te > 60) return "T2";
  if (tr > 2000 && te < 30) return "PD";
  return "Mixed";
}

boot().catch((e) => { setSplash(100, "Failed to start: " + e); console.error(e); });
