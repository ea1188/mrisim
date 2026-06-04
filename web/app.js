/* MRISim browser edition — control shell. Pyodide + the engine run in a web
   worker (worker.js); this file wires the HTML controls and talks to the worker
   over a small request/response protocol so renders never freeze the UI. */
"use strict";

const $ = (id) => document.getElementById(id);
let booted = false;

let compareMode = false;
let protocolA = null;       // snapshot payload for the "A" side of a comparison
let applyingPreset = false; // suppress the custom-reset while a preset populates
let winW = 1.0, winL = 0.5; // window/level (normalised), driven by image drag
let scoutPanels = [];       // per-panel click→slice geometry from the last scout

const SEQ_FA = new Set(["Gradient Echo", "Balanced SSFP", "MR Angiography", "Susceptibility (SWI)"]);
const SEQ_TI = new Set(["Inversion Recovery"]);
// Sequences needing the ~1-minute vessel-tree build the first time (see web_adapter).
const SEQ_SLOW_FIRST = new Set(["MR Angiography", "Susceptibility (SWI)"]);
const ACQ3D_SEQ = new Set(["Spin Echo", "Gradient Echo", "Inversion Recovery", "Balanced SSFP"]);

// --- Worker plumbing -------------------------------------------------------- //
const worker = new Worker("worker.js");
let reqId = 0;
const pending = new Map();           // id -> {resolve, reject}

function call(type, payload) {
  return new Promise((resolve, reject) => {
    const id = ++reqId;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, payload });
  });
}

// Region switch can lazy-fetch a real atlas (~20 MB the first time); show a note.
async function loadRegion(name) {
  $("hint").textContent = `Loading ${name} anatomy\u2026`;
  document.body.classList.add("busy");
  try { return await call("setRegion", name); }
  finally { document.body.classList.remove("busy"); $("hint").textContent = ""; }
}

worker.onmessage = (e) => {
  const m = e.data;
  if (m.type === "progress") { setSplash(m.pct, m.msg); return; }
  if (m.type === "ready") { onReady(m.info); return; }
  if (m.type === "error") { setSplash(100, "Failed to start: " + m.msg); return; }
  const p = pending.get(m.id);
  if (!p) return;
  pending.delete(m.id);
  if (m.error) p.reject(new Error(m.error)); else p.resolve(m.result);
};

function setSplash(pct, msg) {
  $("splash-bar").style.width = pct + "%";
  if (msg) $("splash-status").textContent = msg;
}

async function onReady(info) {
  buildControls(info);
  setSplash(100, "Ready");
  $("splash").style.display = "none";
  $("app").hidden = false;
  booted = true;
  await applyHashState();        // restore a shared prescription, if the URL has one
  render();
  maybeShowIntro();
}

// --- Shareable URL state + export ------------------------------------------- //
const HASH_KEYS = {
  region: () => curRegion(), seq: () => $("sequence").value, orient: () => curOrient(),
  slice: () => $("slice").value, field: () => $("field").value,
  tr: () => $("tr").value, te: () => $("te").value, ti: () => $("ti").value, fa: () => $("fa").value,
  matrix: () => $("matrix").value, bw: () => $("bw").value, nex: () => $("nex").value,
  bval: () => $("bval").value, etl: () => $("etl").value, thick: () => $("thick").value,
  fatsat: () => ($("fatsat").checked ? 1 : 0), gd: () => ($("gd").checked ? 1 : 0),
  flow: () => ($("flow").checked ? 1 : 0), acq3d: () => ($("acq3d").checked ? 1 : 0),
  np: () => $("np").value, kzpf: () => ($("kzpf").checked ? 1 : 0),
};

function stateToHash() {
  const q = Object.entries(HASH_KEYS).map(([k, f]) => `${k}=${encodeURIComponent(f())}`).join("&");
  history.replaceState(null, "", "#" + q);
}

// Apply a plain state object (short keys, same as the URL hash) to the controls.
// Only keys present are set, so callers can override a subset (presets, lessons,
// shared links). Booleans for the checkbox keys.
async function applyState(st) {
  applyingPreset = true;
  if (st.region && st.region !== curRegion()
      && [...$("region").options].some((o) => o.value === st.region)) {
    $("region").value = st.region;
    const d = await loadRegion(st.region);
    $("slice").max = d.max_slice;
  }
  if (st.seq) $("sequence").value = st.seq;
  if (st.orient) setOrient(st.orient);
  if (st.field) $("field").value = st.field;
  const sv = (key) => { if (st[key] !== undefined && st[key] !== null) { $(key).value = st[key]; const o = $(key + "-val"); if (o) o.value = $(key).value; } };
  ["slice", "tr", "te", "ti", "fa", "matrix", "bw", "nex", "thick", "bval", "etl", "np"].forEach(sv);
  ["fatsat", "gd", "flow", "acq3d", "kzpf"].forEach((k) => { if (st[k] !== undefined) $(k).checked = !!st[k]; });
  syncVisibility();
  applyingPreset = false;
}

async function applyHashState() {
  const h = location.hash.slice(1);
  if (!h) return false;
  const p = new URLSearchParams(h);
  const st = {};
  for (const [k, v] of p) st[k] = ["fatsat", "gd", "flow", "acq3d", "kzpf"].includes(k) ? v === "1" : v;
  await applyState(st);
  return true;
}

function flash(btn, msg) {
  const t = btn.textContent; btn.textContent = msg;
  setTimeout(() => { btn.textContent = t; }, 1200);
}

async function copyLink() {
  stateToHash();
  try { await navigator.clipboard.writeText(location.href); flash($("copylink"), "Copied!"); }
  catch (e) { flash($("copylink"), "Copy failed"); }
}

function downloadPNG() {
  const src = $("mainImage").src;
  if (!src || !src.startsWith("data:image")) return;
  const a = document.createElement("a");
  a.href = src;
  a.download = `mrisim_${$("sequence").value.replace(/\W+/g, "_")}_${curOrient()}_${$("slice").value}.png`;
  document.body.appendChild(a); a.click(); a.remove();
}

// --- Onboarding ------------------------------------------------------------- //
function showIntro() { $("intro").hidden = false; }
function hideIntro() { $("intro").hidden = true; localStorage.setItem("mrisim_seen", "1"); }
function maybeShowIntro() {
  $("intro-ok").addEventListener("click", hideIntro);
  $("help").addEventListener("click", showIntro);
  try { if (!localStorage.getItem("mrisim_seen")) showIntro(); } catch (e) { /* private mode */ }
}

// --- Guided lessons --------------------------------------------------------- //
const LESSONS = [
  {
    title: "T1, T2 & PD contrast",
    blurb: "Why CSF flips from dark to bright as you change TR and TE.",
    steps: [
      { text: "<b>T1-weighted.</b> Short TR / short TE on a spin echo. Short-T1 tissues (fat, white matter) recover fast and look bright; fluid (CSF) recovers slowly and stays <b>dark</b>.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 12 } },
      { text: "<b>T2-weighted.</b> Lengthen TR (drop T1 weighting) and TE (add T2 weighting). Fluid has a long T2, so <b>CSF is now the brightest</b> — the classic flip. Watch the ventricles.",
        state: { tr: 4000, te: 100 } },
      { text: "<b>Proton-density.</b> Long TR, short TE — little T1 or T2 weighting, so contrast tracks tissue water content. Gray matter is slightly brighter than white. The 'in-between' weighting.",
        state: { tr: 4000, te: 12 } },
    ],
  },
  {
    title: "Nulling a tissue: FLAIR & STIR",
    blurb: "Inversion recovery and choosing TI to zero out CSF or fat.",
    steps: [
      { text: "<b>Inversion recovery</b> flips the magnetization 180°, then waits a time <b>TI</b> before imaging. Each tissue crosses zero signal at TI ≈ T1·ln2 — pick TI to <b>null</b> a tissue.",
        state: { region: "Brain", seq: "Inversion Recovery", orient: "axial", slice: 90, tr: 9000, ti: 2548, te: 100 } },
      { text: "<b>FLAIR.</b> At 3 T, TI ≈ 2550 ms nulls CSF — fluid goes dark while T2 contrast remains, so periventricular lesions stand out against black CSF. The workhorse brain sequence.",
        state: { tr: 9000, ti: 2548, te: 100 } },
      { text: "<b>STIR.</b> Drop TI to ~265 ms and shorten TR — now <b>fat</b> is nulled instead (short-T1 inversion recovery), used to suppress fat and reveal edema.",
        state: { tr: 6000, ti: 265, te: 30 } },
    ],
  },
  {
    title: "SNR vs. scan time",
    blurb: "The fundamental tradeoff — averaging, matrix, bandwidth.",
    steps: [
      { text: "Watch the <b>SNR</b> and <b>scan time</b> readouts on the right. Baseline: one average, 256 matrix.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 15, nex: 1, matrix: 256, bw: 125 } },
      { text: "<b>Averaging (NEX = 4).</b> SNR rises by √4 = <b>2×</b>, but scan time grows <b>4×</b>. Averaging buys SNR at a steep time cost.",
        state: { nex: 4 } },
      { text: "<b>Resolution.</b> Back to NEX 1, matrix 128: faster and higher SNR per (larger) voxel, but coarser detail. Resolution, SNR and time are always in tension.",
        state: { nex: 1, matrix: 128 } },
    ],
  },
  {
    title: "3D slab acquisition & reformat",
    blurb: "Acquire a slab once, then view any plane.",
    steps: [
      { text: "Enable <b>3D slab acquisition</b> on a gradient echo. The slab is phase-encoded through-plane (kz) and acquired <b>once</b> — note the <code>3D SLAB</code> badge.",
        state: { region: "Brain", seq: "Gradient Echo", orient: "axial", slice: 90, acq3d: true, np: 32 } },
      { text: "Switch to <b>coronal</b>: the same acquired slab is <b>reformatted live</b> — no re-scan (see the <code>REFORMAT</code> tag). That's the headline of 3D imaging.",
        state: { orient: "coronal", slice: 110 } },
      { text: "And <b>sagittal</b>, still from the one acquisition. 3D gives thin contiguous partitions and a √Nz SNR advantage over single 2D slices.",
        state: { orient: "sagittal", slice: 90 } },
    ],
  },
];

let lessonIdx = -1, stepIdx = 0;

function wireLessons() {
  const list = $("lesson-list");
  LESSONS.forEach((L, i) => {
    const b = document.createElement("button");
    b.className = "lesson-item";
    b.innerHTML = `<b>${L.title}</b><span>${L.blurb}</span>`;
    b.addEventListener("click", () => { $("lesson-picker").hidden = true; startLesson(i); });
    list.appendChild(b);
  });
  $("lessons-btn").addEventListener("click", () => { $("lesson-picker").hidden = false; });
  $("lesson-picker-close").addEventListener("click", () => { $("lesson-picker").hidden = true; });
  $("lesson-exit").addEventListener("click", exitLesson);
  $("lesson-prev").addEventListener("click", () => { if (stepIdx > 0) { stepIdx--; applyStep(); } });
  $("lesson-next").addEventListener("click", () => {
    if (stepIdx < LESSONS[lessonIdx].steps.length - 1) { stepIdx++; applyStep(); } else exitLesson();
  });
}

function startLesson(i) {
  lessonIdx = i; stepIdx = 0;
  if (compareMode) setCompare(false);
  ["gd", "flow", "fatsat", "acq3d", "kzpf"].forEach((id) => { $(id).checked = false; });  // clean baseline
  $("lesson-panel").hidden = false;
  applyStep();
}
function exitLesson() { lessonIdx = -1; $("lesson-panel").hidden = true; }

async function applyStep() {
  const L = LESSONS[lessonIdx], s = L.steps[stepIdx];
  $("lesson-title").textContent = L.title;
  $("lesson-step").innerHTML = s.text;
  $("lesson-progress").textContent = `Step ${stepIdx + 1} / ${L.steps.length}`;
  $("lesson-prev").disabled = stepIdx === 0;
  $("lesson-next").textContent = stepIdx === L.steps.length - 1 ? "Finish" : "Next ›";
  await applyState(s.state);
  render();
}

// --- Keyboard + wheel slice navigation -------------------------------------- //
function setSlice(v) {
  const sl = $("slice");
  v = Math.max(0, Math.min(+sl.max, v));
  if (v === +sl.value) return;
  sl.value = v; $("slice-val").value = v; schedule();
}

function wireKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (!$("intro").hidden && e.key === "Escape") { hideIntro(); return; }
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "")) return;
    const k = e.key.toLowerCase();
    let step = null;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") step = 1;
    else if (e.key === "ArrowDown" || e.key === "ArrowLeft") step = -1;
    else if (e.key === "PageUp") step = 5;
    else if (e.key === "PageDown") step = -5;
    else if (k === "r") { winW = 1.0; winL = 0.5; schedule(); e.preventDefault(); return; }
    else if (k === "f") { const c = $("fovplan"); c.checked = !c.checked; c.dispatchEvent(new Event("change")); e.preventDefault(); return; }
    if (step === null) return;
    e.preventDefault();
    setSlice(+$("slice").value + step);
  });
  $("mainImage").addEventListener("wheel", (e) => {
    e.preventDefault();
    setSlice(+$("slice").value + (e.deltaY < 0 ? 1 : -1));
  }, { passive: false });
}

// --- Controls --------------------------------------------------------------- //
function buildControls(info) {
  const reg = $("region");
  info.regions.forEach((r) => reg.add(new Option(r, r)));
  const seqs = ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
    "Balanced SSFP", "Diffusion (DWI)", "MR Angiography", "Susceptibility (SWI)",
    "fMRI (BOLD)", "Quantitative (qMRI)", "Echo Planar (EPI)"];
  const seq = $("sequence");
  seqs.forEach((s) => seq.add(new Option(s, s)));
  const presetSel = $("preset");
  info.presets.forEach((p) => presetSel.add(new Option(p, p)));
  $("slice").max = info.max_slice;
  $("slice").value = Math.floor(info.max_slice / 2);

  presetSel.addEventListener("change", onPreset);
  $("setA").addEventListener("click", setProtocolA);
  $("compare").addEventListener("click", () => setCompare(!compareMode));
  $("exitAB").addEventListener("click", () => setCompare(false));
  $("fovplan").addEventListener("change", () => {
    $("scoutwrap").hidden = !$("fovplan").checked;
    if ($("fovplan").checked) render();
  });
  wireWindowLevel();
  wireScout();
  wireKeyboard();
  wireLessons();

  ["tr", "te", "ti", "fa", "np", "slice", "matrix", "bw", "nex", "thick", "bval", "etl"].forEach((id) => {
    $(id).addEventListener("input", () => {
      const out = $(id + "-val"); if (out) out.value = $(id).value;
      schedule();
    });
  });
  $("copylink").addEventListener("click", copyLink);
  $("download").addEventListener("click", downloadPNG);
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

async function onSequenceOrRegion(e) {
  if (e.target.id === "region") {
    const d = await loadRegion(curRegion());   // resizes the volume (may fetch a real atlas)
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
  $("bval-row").hidden = s !== "Diffusion (DWI)";
  $("etl-row").hidden = s !== "FSE / TSE";
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
    matrix_size: +$("matrix").value, bandwidth: +$("bw").value, NEX: +$("nex").value,
    slice_thickness: +$("thick").value,
    fatsat_enabled: $("fatsat").checked,
    contrast_enabled: $("gd").checked, contrast_dose: $("gd").checked ? 5 : 0,
    flow_enabled: $("flow").checked,
  };
  if (s === "Diffusion (DWI)") params.b_value = +$("bval").value;
  if (s === "FSE / TSE") params.etl = +$("etl").value;
  if (ACQ3D_SEQ.has(s) && $("acq3d").checked) {
    params.acq3d = true;
    params.n_partitions = +$("np").value;
    params.kz_pf = $("kzpf").checked ? 0.75 : null;
  }
  return {
    region: curRegion(), orientation: curOrient(),
    slice_idx: +$("slice").value, curve_mode: "TE decay",
    window_width: winW, window_level: winL, params,
  };
}

// --- Presets ---------------------------------------------------------------- //
async function onPreset() {
  const name = $("preset").value;
  if (!name) return;                  // "— custom —"
  const bundle = await call("preset", name);
  applyingPreset = true;
  if (bundle.region && bundle.region !== curRegion()
      && [...$("region").options].some((o) => o.value === bundle.region)) {
    $("region").value = bundle.region;
    const d = await loadRegion(bundle.region);
    $("slice").max = d.max_slice;
    $("slice").value = Math.floor(d.max_slice / 2);
  }
  setOrient(bundle.orientation || "axial");
  const p = bundle.params || {};
  const set = (id, v) => { if (v !== undefined && v !== null) { $(id).value = v; const o = $(id + "-val"); if (o) o.value = v; } };
  if (p.sequence) $("sequence").value = p.sequence;
  set("tr", p.TR); set("te", p.TE); set("ti", p.TI); set("fa", p.flip_angle);
  set("matrix", p.matrix_size); set("bw", p.bandwidth); set("nex", p.NEX);
  set("bval", p.b_value); set("etl", p.etl); set("thick", p.slice_thickness);
  if (p.field_strength) $("field").value = p.field_strength;
  $("fatsat").checked = !!p.fatsat_enabled;
  $("gd").checked = !!p.contrast_enabled;
  $("flow").checked = !!p.flow_enabled;
  $("acq3d").checked = !!p.acq3d;
  syncVisibility();
  applyingPreset = false;
  $("preset").value = name;           // keep the chosen preset shown
  render();
}

// --- A/B compare ------------------------------------------------------------ //
function setProtocolA() {
  protocolA = collectPayload();
  $("setA").classList.add("on");
  if (!compareMode) setCompare(true); else render();
}

function setCompare(on) {
  compareMode = on;
  if (on && !protocolA) protocolA = collectPayload();
  $("compare").classList.toggle("on", on);
  $("exitAB").hidden = !on;
  $("wrapB").hidden = !on;
  $("tagA").hidden = !on;
  if (!on) { $("abdelta").textContent = ""; $("setA").classList.remove("on"); }
  render();
}

function showDelta(mA, mB) {
  const arrow = (a, b) => (b > a ? "↑" : b < a ? "↓" : "=");
  const pct = (a, b) => (a ? Math.round(Math.abs(b - a) / a * 100) : 0);
  const cnr = (m) => Math.abs(m.snr_wm - m.snr_gm);
  $("abdelta").innerHTML =
    `B vs A — SNR ${arrow(mA.snr_wm, mB.snr_wm)} ${pct(mA.snr_wm, mB.snr_wm)}% · ` +
    `CNR ${arrow(cnr(mA), cnr(mB))} ${pct(cnr(mA), cnr(mB))}% · ` +
    `time ${arrow(mA.scan_time, mB.scan_time)} ${pct(mA.scan_time, mB.scan_time)}%`;
}

// --- Window/level drag on the main image ------------------------------------ //
function wireWindowLevel() {
  const img = $("mainImage");
  let dragging = false, lx = 0, ly = 0;
  img.addEventListener("mousedown", (e) => {
    if (compareMode) return;           // A/B images are fixed-W/L
    dragging = true; lx = e.clientX; ly = e.clientY; e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    winW = Math.min(3, Math.max(0.05, winW + (e.clientX - lx) * 0.004));
    winL = Math.min(1, Math.max(0, winL - (e.clientY - ly) * 0.003));
    lx = e.clientX; ly = e.clientY;
    schedule();
  });
  window.addEventListener("mouseup", () => { dragging = false; });
  img.addEventListener("dblclick", () => { winW = 1.0; winL = 0.5; schedule(); });
}

// --- Interactive scout: click/drag a localizer panel to move the slice ------- //
function imgFraction(img, cx, cy) {
  const r = img.getBoundingClientRect();
  if (!img.naturalWidth || !r.width) return null;
  const nAR = img.naturalWidth / img.naturalHeight, eAR = r.width / r.height;
  let cw, ch, ox, oy;            // the image content box within the element (object-fit: contain)
  if (eAR > nAR) { ch = r.height; cw = ch * nAR; ox = (r.width - cw) / 2; oy = 0; }
  else { cw = r.width; ch = cw / nAR; ox = 0; oy = (r.height - ch) / 2; }
  const fx = (cx - r.left - ox) / cw, fy = (cy - r.top - oy) / ch;
  return (fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1) ? { fx, fy } : null;
}

function wireScout() {
  const img = $("scoutImage");
  img.style.cursor = "crosshair";
  let dragging = false;
  const apply = (e) => {
    const f = imgFraction(img, e.clientX, e.clientY);
    if (!f) return;
    for (const p of scoutPanels) {
      if (p.map === "none") continue;
      const [l, t, r, b] = p.box;
      if (f.fx < l || f.fx > r || f.fy < t || f.fy > b) continue;
      let slice;
      if (p.map === "row") {                       // y → slice (origin at bottom)
        slice = Math.round(((b - f.fy) / (b - t)) * (p.n - 1));
      } else {                                     // x → slice (flip for sagittal Y)
        const col = ((f.fx - l) / (r - l)) * (p.n - 1);
        slice = Math.round(p.flip ? (p.n - 1 - col) : col);
      }
      slice = Math.max(0, Math.min(p.n - 1, slice));
      $("slice").value = slice; $("slice-val").value = slice;
      schedule();
      return;
    }
  };
  img.addEventListener("mousedown", (e) => { dragging = true; apply(e); e.preventDefault(); });
  window.addEventListener("mousemove", (e) => { if (dragging) apply(e); });
  window.addEventListener("mouseup", () => { dragging = false; });
}

// --- Render orchestration (async, via the worker) --------------------------- //
let timer = null, pending2 = false, running = false;
function schedule() {
  if (!booted) return;
  if (!applyingPreset) $("preset").value = "";   // manual tweak → "custom"
  clearTimeout(timer);
  timer = setTimeout(render, 90);    // debounce; the worker keeps the UI free
}

async function render() {
  if (running) { pending2 = true; return; }      // coalesce overlapping renders
  running = true;
  if (SEQ_SLOW_FIRST.has($("sequence").value)) {
    $("hint").textContent = "Building vessel model (one-time, may take ~1 min)…";
  }
  document.body.classList.add("busy");
  try {
    if (compareMode) {
      const B = collectPayload();
      const resA = await call("render", protocolA || B);
      const resB = await call("render", B);
      $("mainImage").src = resA.image;
      $("mainImageB").src = resB.image;
      $("curveImage").src = resB.curve;
      setMetrics(resB);
      syncSlice(resB);
      showDelta(resA.metrics, resB.metrics);
    } else {
      applyResult(await call("render", collectPayload()));
    }
    if ($("fovplan").checked) {
      const p = collectPayload();
      const s = await call("scout",
        { region: p.region, orientation: p.orientation, slice_idx: p.slice_idx });
      $("scoutImage").src = s.scout;
      scoutPanels = s.panels || [];
    }
    if (!compareMode) stateToHash();   // keep the URL shareable/current
  } catch (err) {
    $("hint").textContent = "Render error: " + err.message;
    console.error(err);
  } finally {
    document.body.classList.remove("busy");
    running = false;
    if (pending2) { pending2 = false; schedule(); }
  }
}

function fmtTime(s) {
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function syncSlice(res) {
  $("slice").max = res.max_slice;
  if (+$("slice").value !== res.slice_idx) $("slice").value = res.slice_idx;
  $("slice-val").value = res.slice_idx;
}

function setMetrics(res) {
  const m = res.metrics;
  $("x-res").textContent = m.resolution.toFixed(2) + " mm";
  $("x-scan").textContent = fmtTime(m.scan_time);
  $("x-snr").textContent = `${m.snr_wm.toFixed(1)} / ${m.snr_gm.toFixed(1)}`;
  $("x-cnr").textContent = Math.abs(m.snr_wm - m.snr_gm).toFixed(1);
  $("x-sar").textContent = m.sar_head.toFixed(1) + " W/kg" + (m.sar_exceeds ? " ⚠" : "");
  $("m-scan").textContent = fmtTime(m.scan_time);
  $("m-snrwm").textContent = m.snr_wm.toFixed(1);
  $("m-weight").textContent = weighting($("sequence").value, +$("tr").value, +$("te").value);
  if (!SEQ_SLOW_FIRST.has($("sequence").value)) $("hint").textContent = "";
}

function applyResult(res) {
  $("mainImage").src = res.image;
  $("curveImage").src = res.curve;
  syncSlice(res);
  setMetrics(res);
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
