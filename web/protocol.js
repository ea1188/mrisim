/* MRISim — Protocol Planning workspace (scanner-console workflow).
 *
 * Reuses the existing Pyodide engine (worker.js + web_adapter): pick an exam → a
 * protocol queue loads → open a sequence → plan angles/FOV on the three scout
 * viewports + edit parameters → Apply to acquire → the image appears in a viewport.
 * Drag-between-viewports and append/re-run land in a follow-up.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const clampN = (v, a, b) => Math.max(a, Math.min(b, v));
const snapAngle = (v) => { for (const t of [0, 15, 30, 45, -15, -30, -45]) if (Math.abs(v - t) <= 2.5) return t; return v; };
const PLANES = ["sagittal", "coronal", "axial"];

// ---- engine worker bridge (mirrors app.js) -------------------------------- //
const worker = new Worker("worker.js");
let reqId = 0, booted = false, workerDead = false;
const pending = new Map();
function call(type, payload) {
  if (workerDead) return Promise.reject(new Error("the engine has stopped — please reload"));
  return new Promise((resolve, reject) => {
    const id = ++reqId; pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, payload });
  });
}
function onWorkerCrash(ev) {
  if (workerDead) return; workerDead = true;
  const msg = (ev && ev.message) || "the engine worker stopped";
  for (const [, p] of pending) p.reject(new Error(msg));
  pending.clear();
  $("splash-status").textContent = "The engine failed to start — please reload.";
}
worker.onerror = onWorkerCrash;
worker.onmessageerror = onWorkerCrash;
worker.onmessage = (e) => {
  const m = e.data;
  if (m.type === "progress") { $("splash-bar").style.width = m.pct + "%"; if (m.msg) $("splash-status").textContent = m.msg; return; }
  if (m.type === "ready") { onReady(); return; }
  if (m.type === "error") { $("splash-status").textContent = "Failed to start: " + m.msg; return; }
  const p = pending.get(m.id); if (!p) return;
  pending.delete(m.id);
  if (m.error) p.reject(new Error(m.error)); else p.resolve(m.result);
};

// ---- state ---------------------------------------------------------------- //
let exam = "Brain";
let region = "Brain";
let queue = [];          // [{id, preset, label, sequence, status, params, plan, image}]
let active = null;       // open queue item
let seq = 0;             // id counter
const vpGeom = {};       // plane -> last rendered panel geometry (for interaction)
let refreshTimer = null;
let lastSeriesPlane = null;   // viewport last hovered/scrolled (arrow keys page it)

// ---- boot ----------------------------------------------------------------- //
async function onReady() {
  booted = true;
  $("splash").hidden = true;
  $("pp-root").hidden = false;
  wireParamPanel();
  PLANES.forEach(wireViewport);
  await loadExam("Brain");
}

async function loadExam(name) {
  exam = name;
  const info = await call("protocols", name);
  // exam picker (first time)
  const sel = $("pp-exam");
  if (!sel.options.length) {
    info.exams.forEach((ex) => sel.add(new Option(ex, ex)));
    sel.value = name;
    sel.addEventListener("change", () => loadExam(sel.value));
  }
  region = name;                       // exam name == region name here (Brain)
  await call("setRegion", region);
  // build the queue
  seq = 0;
  queue = info.queue.map((it) => ({
    id: ++seq, preset: it.preset, label: it.label, sequence: it.sequence,
    status: "pending", params: null, plan: null, image: null,
  }));
  active = null;
  renderQueue();
  // open the localizer first so the scouts show immediately
  openItem(queue[0]);
}

// ---- protocol queue (right column) ---------------------------------------- //
function renderQueue() {
  const ol = $("pp-list");
  ol.innerHTML = "";
  queue.forEach((it, i) => {
    const li = document.createElement("li");
    li.className = (it === active ? "active " : "") + (it.status === "acquired" ? "acquired" : "");
    const dot = it.status === "acquired" ? "✓" : (it === active ? "▸" : "·");
    li.innerHTML = `<span class="q-num">${i + 1}</span>`
      + `<span class="q-label">${it.label}</span>`
      + `<span class="q-status">${dot}</span>`;
    li.addEventListener("click", () => openItem(it));
    if (it.status === "acquired") {           // re-run: append a fresh copy to the queue
      const add = document.createElement("button");
      add.className = "q-append"; add.title = "Append a copy to re-run with new parameters";
      add.textContent = "＋";
      add.addEventListener("click", (e) => { e.stopPropagation(); appendItem(it); });
      li.appendChild(add);
    }
    ol.appendChild(li);
  });
}

// Append a fresh, pending copy of an acquired sequence so it can be re-run with edits.
function appendItem(src) {
  const copy = {
    id: ++seq, preset: src.preset, label: src.label + " (re-run)", sequence: src.sequence,
    status: "pending", image: null,
    params: src.params ? { ...src.params } : null,
    plan: src.plan ? { ...src.plan } : null,
  };
  queue.push(copy);
  renderQueue();
  openItem(copy);
}

const LOCALIZER = "Localizer";
const isLocalizer = (it) => it && it.preset === LOCALIZER;

// ---- open a sequence ------------------------------------------------------ //
async function openItem(it) {
  active = it;
  PLANES.forEach((p) => { slotState[p] = { kind: "scout" }; });   // fresh planning view
  renderQueue();
  if (isLocalizer(it)) {
    it.plan = it.plan || { orientation: "axial", slice: null, tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100 };
    $("pp-seqname").textContent = "Localizer — 3-plane scout";
    $("pp-controls").hidden = true; $("pp-actions").hidden = true;
    await renderScouts();
    return;
  }
  if (!it.params) {                      // first open: resolve the preset
    const bundle = await call("preset", it.preset);
    it.params = bundle.params;
    // Surface geometry defaults the panel shows, so the engine and the panel agree
    // (presets don't carry slice thickness / count).
    it.params.slice_thickness = it.params.slice_thickness ?? 5;
    it.params.n_slices = it.params.n_slices ?? 1;
    it.plan = {
      orientation: bundle.orientation || "axial",
      slice: null,                       // null → mid slice (engine default)
      tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100,
    };
  }
  $("pp-seqname").textContent = `${it.label}  ·  ${it.sequence}`;
  $("pp-controls").hidden = false; $("pp-actions").hidden = false;
  paramsToPanel(it);
  await renderScouts();
  updatePlanReadout();
}

// ---- parameter panel ------------------------------------------------------ //
const NUMP = { "pp-tr": "TR", "pp-te": "TE", "pp-flip": "flip_angle", "pp-thk": "slice_thickness" };
const nslKey = (p) => (p.acq3d ? "n_partitions" : "n_slices");   // 3-D uses partitions
function paramsToPanel(it) {
  const p = it.params;
  $("pp-tr").value = p.TR ?? 500;
  $("pp-te").value = p.TE ?? 15;
  $("pp-flip").value = p.flip_angle ?? 90;
  $("pp-thk").value = p.slice_thickness ?? 5;
  $("pp-fov").value = it.plan.fov_pct;
  $("pp-tilt").value = it.plan.tilt;
  $("pp-rot").value = it.plan.rot;
  // Only the parameter that *defines* this sequence is shown beyond the basics.
  const isIR = it.sequence === "Inversion Recovery", isDWI = it.sequence === "Diffusion (DWI)";
  $("pp-ti-row").hidden = !isIR;
  $("pp-bval-row").hidden = !isDWI;
  if (isIR) $("pp-ti").value = p.TI ?? 2500;
  if (isDWI) $("pp-bval").value = p.b_value ?? 1000;
  // A 3-D acquisition is a slab of partitions, not a 2-D multi-slice group.
  $("pp-nsl-label").textContent = p.acq3d ? "Partitions" : "Slices";
  $("pp-nsl").value = p.acq3d ? (p.n_partitions ?? 32) : (p.n_slices ?? 1);
}
function wireParamPanel() {
  Object.entries(NUMP).forEach(([id, key]) => {
    $(id).addEventListener("input", () => {
      if (!active || isLocalizer(active)) return;
      active.params[key] = +$(id).value;
      scheduleScouts();
    });
  });
  $("pp-nsl").addEventListener("input", () => {
    if (!active || isLocalizer(active)) return;
    active.params[nslKey(active.params)] = +$("pp-nsl").value;
    scheduleScouts();
  });
  $("pp-ti").addEventListener("input", () => { if (active && !isLocalizer(active)) { active.params.TI = +$("pp-ti").value; scheduleScouts(); } });
  $("pp-bval").addEventListener("input", () => { if (active && !isLocalizer(active)) { active.params.b_value = +$("pp-bval").value; scheduleScouts(); } });
  $("pp-fov").addEventListener("input", () => { if (active) { active.plan.fov_pct = clampN(+$("pp-fov").value, 20, 100); scheduleScouts(); } });
  $("pp-tilt").addEventListener("input", () => { if (active) { active.plan.tilt = clampN(+$("pp-tilt").value, -45, 45); scheduleScouts(); } });
  $("pp-rot").addEventListener("input", () => { if (active) { active.plan.rot = clampN(+$("pp-rot").value, -45, 45); scheduleScouts(); } });
  $("pp-apply").addEventListener("click", applyAndAcquire);
  // ↑/↓ (←/→) page an acquired series, like the wheel.
  window.addEventListener("keydown", (e) => {
    if (e.target && /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (!lastSeriesPlane || slotState[lastSeriesPlane].kind !== "series") return;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") { e.preventDefault(); scrollSeries(lastSeriesPlane, 1); }
    else if (e.key === "ArrowDown" || e.key === "ArrowLeft") { e.preventDefault(); scrollSeries(lastSeriesPlane, -1); }
  });
}

// ---- viewports ------------------------------------------------------------ //
// Each of the three slots holds either the plane's scout (plannable) or an acquired
// series (view-only, draggable to another slot). The scout images are cached so a
// slot showing a series isn't clobbered when the scouts re-render.
const slotState = { sagittal: { kind: "scout" }, coronal: { kind: "scout" }, axial: { kind: "scout" } };
const scoutCache = {};   // plane -> {png, geom, label}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function scoutPayload() {
  const pl = active.plan;
  const out = {
    region, orientation: pl.orientation, inplane_fov_pct: pl.fov_pct,
    inplane_off: pl.inplane_off, tilt: pl.tilt, rot: pl.rot,
    params: isLocalizer(active) ? { sequence: "Spin Echo" } : active.params,
  };
  if (pl.slice != null) out.slice_idx = pl.slice;
  return out;
}
async function renderScouts() {
  const res = await call("scoutPanels", scoutPayload());
  PLANES.forEach((plane) => {
    const panel = res[plane]; if (!panel) return;
    scoutCache[plane] = { png: panel.png, geom: panel.geom || {}, label: cap(plane) };
  });
  PLANES.forEach(renderSlot);
}
function scheduleScouts() { updatePlanReadout(); clearTimeout(refreshTimer); refreshTimer = setTimeout(renderScouts, 90); }

function renderSlot(plane) {
  const st = slotState[plane];
  if (st.kind === "scout") {
    const sc = scoutCache[plane]; if (!sc) return;
    vpGeom[plane] = sc.geom;
    drawTile(plane, sc.png, sc.label, true, false);          // plannable, not draggable
  } else {                                                   // series: view-only, draggable
    const tag = (st.maxSlice ? `${st.label}  ·  ${st.slice}/${st.maxSlice}` : st.label) + "  ⠿";
    drawTile(plane, st.png, tag, false, true);
  }
}
function drawTile(plane, dataURL, tag, plannable, draggable) {
  const box = $("vp-" + plane);
  box.classList.toggle("plannable", !!plannable);
  let img = box.querySelector("img");
  if (!img) { img = document.createElement("img"); box.appendChild(img); }
  img.src = dataURL;
  img.draggable = !!draggable;
  box.querySelector(".vp-tag").textContent = tag;
  box._plannable = !!plannable;
}

// Drag a series from one slot to another; the source slot reverts to its scout.
function moveSeries(src, dst) {
  if (src === dst || slotState[src].kind !== "series") return;
  slotState[dst] = slotState[src];
  slotState[src] = { kind: "scout" };
  lastSeriesPlane = dst;
  renderSlot(src); renderSlot(dst);
}
function revertSlot(plane) {                 // double-click a series → bring the scout back
  if (slotState[plane].kind !== "series") return;
  slotState[plane] = { kind: "scout" };
  renderSlot(plane);
}

// ---- viewport planning interaction (per panel) ---------------------------- //
function imgFraction(img, cx, cy) {
  const r = img.getBoundingClientRect();
  if (!img.naturalWidth || !r.width) return null;
  const nAR = img.naturalWidth / img.naturalHeight, eAR = r.width / r.height;
  let cw, ch, ox, oy;
  if (eAR > nAR) { ch = r.height; cw = ch * nAR; ox = (r.width - cw) / 2; oy = 0; }
  else { cw = r.width; ch = cw / nAR; ox = 0; oy = (r.height - ch) / 2; }
  const fx = (cx - r.left - ox) / cw, fy = (cy - r.top - oy) / ch;
  return (fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1) ? { px: fx, py: fy } : null;
}
function bandLocal(p, slice) {
  const s = slice == null ? (p.n - 1) / 2 : slice;
  if (p.map === "row") return 1 - s / (p.n - 1);
  return (p.flip ? (p.n - 1 - s) : s) / (p.n - 1);
}
// Which CSS cursor signals each grabbable region (so it's obvious where to grab).
const cursorFor = (m) => ({
  recenter: "move", resize: "nwse-resize", oblique: "grab",
  slice: "ns-resize", slices: "row-resize",
}[m] || "crosshair");

// What does the pointer do at this spot on a scout panel? (shared by hover + drag)
function modeAt(p, loc) {
  if (!p || !active) return null;
  if (p.role === "acq") {                          // acquired plane: the FOV box
    const fb = p.fov_box; if (!fb) return "slice";
    const cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
    const edge = Math.max(Math.abs(loc.px - cx) / (fb[2] / 2 || 1), Math.abs(loc.py - cy) / (fb[3] / 2 || 1));
    return edge > 0.72 ? "resize" : "recenter";
  }
  if (p.slab && p.slab.half > 0.05) {              // near the slab rim → add / remove slices
    const perp = p.map === "row" ? loc.py : loc.px;
    if (Math.abs(Math.abs(perp - p.slab.c) - p.slab.half) < 0.035) return "slices";
  }
  const bp = bandLocal(p, active.plan.slice);      // near the band line → angle (if this panel tilts)
  const near = p.map === "row" ? Math.abs(loc.py - bp) < 0.08 : Math.abs(loc.px - bp) < 0.08;
  if (near && p.angle) return "oblique";
  return "slice";
}

function wireViewport(plane) {
  const box = $("vp-" + plane);
  let drag = null;
  const startDrag = (loc) => {
    const p = vpGeom[plane]; if (!p || !active) return null;
    const mode = modeAt(p, loc);
    const d = { mode, p };
    if (mode === "oblique") { d.l0 = loc; d.tilt0 = active.plan.tilt; d.rot0 = active.plan.rot; }
    if (mode === "slices") { d.half0 = p.slab.half; d.n0 = (+$("pp-nsl").value) || 1; }
    return d;
  };
  const applyDrag = (loc) => {
    if (!drag || !active) return;
    const p = drag.p, pl = active.plan;
    if (drag.mode === "slice") {                   // angles the *same way you drag* (engine parity)
      const s = p.map === "row" ? (1 - loc.py) * (p.n - 1) : (p.flip ? (1 - loc.px) : loc.px) * (p.n - 1);
      pl.slice = clampN(Math.round(s), 0, p.n - 1);
    } else if (drag.mode === "recenter") {
      const u = (p.ip_dir === "x" ? loc.px : loc.py) - 0.5;
      pl.inplane_off = p.ip_sign * u * p.ip_axis_len;
    } else if (drag.mode === "resize") {
      const fb = p.fov_box, cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
      const half = Math.max(Math.abs(loc.px - cx), Math.abs(loc.py - cy));
      pl.fov_pct = Math.round(clampN(2 * half, 0.3, 1.0) * 100 / 5) * 5;
      $("pp-fov").value = pl.fov_pct;
    } else if (drag.mode === "slices") {           // drag the slab rim → number of slices
      const perp = p.map === "row" ? loc.py : loc.px;
      const n = clampN(Math.round(drag.n0 * Math.abs(perp - p.slab.c) / (drag.half0 || 0.03)), 1, 32);
      active.params.n_slices = n; $("pp-nsl").value = n;
    } else if (drag.mode === "oblique") {
      const d = (p.map === "row" ? (loc.py - drag.l0.py) : (drag.l0.px - loc.px)) * 90;
      if (p.angle === "tilt") { pl.tilt = snapAngle(clampN(drag.tilt0 + d, -45, 45)); $("pp-tilt").value = pl.tilt; }
      else { pl.rot = snapAngle(clampN(drag.rot0 + d, -45, 45)); $("pp-rot").value = pl.rot; }
    }
    updatePlanReadout();
    scheduleScouts();
  };
  box.addEventListener("pointerdown", (e) => {
    const img = box.querySelector("img");
    if (!img || !box._plannable) return;          // acquired series → view-only / draggable
    const f = imgFraction(img, e.clientX, e.clientY); if (!f) return;
    drag = startDrag(f); if (drag) { applyDrag(f); e.preventDefault(); }
  });
  window.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const img = box.querySelector("img"); if (!img) return;
    const f = imgFraction(img, e.clientX, e.clientY); if (f) applyDrag(f);
  });
  window.addEventListener("pointerup", () => { drag = null; });
  window.addEventListener("pointercancel", () => { drag = null; });

  // Hover feedback: the cursor shows what each region does before you grab it.
  box.addEventListener("pointermove", (e) => {
    if (drag) return;
    const img = box.querySelector("img");
    if (!img || !box._plannable) { box.style.cursor = ""; return; }
    const f = imgFraction(img, e.clientX, e.clientY);
    box.style.cursor = f ? cursorFor(modeAt(vpGeom[plane], f)) : "";
  });

  // Scroll through the slices of an acquired series (wheel; arrow keys page the
  // last-touched series — see wireParamPanel).
  box.addEventListener("pointerenter", () => {
    if (slotState[plane].kind === "series") lastSeriesPlane = plane;
  });
  box.addEventListener("wheel", (e) => {
    if (slotState[plane].kind !== "series" || !slotState[plane].payload) return;
    e.preventDefault();
    scrollSeries(plane, e.deltaY < 0 ? 1 : -1);
  }, { passive: false });

  // Drag an acquired series between viewports; the source reverts to its scout.
  box.addEventListener("dragstart", (e) => {
    if (slotState[plane].kind !== "series") { e.preventDefault(); return; }
    e.dataTransfer.setData("text/plane", plane);
    e.dataTransfer.effectAllowed = "move";
  });
  box.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; });
  box.addEventListener("drop", (e) => {
    e.preventDefault();
    const src = e.dataTransfer.getData("text/plane");
    if (src) moveSeries(src, plane);
  });
  // Double-click: a series box brings its scout back; a scout box resets the
  // prescription (angles + FOV) to straight/full — parity with the main app.
  box.addEventListener("dblclick", () => {
    if (slotState[plane].kind === "series") { revertSlot(plane); return; }
    if (!active || isLocalizer(active)) return;
    Object.assign(active.plan, { tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100 });
    $("pp-tilt").value = 0; $("pp-rot").value = 0; $("pp-fov").value = 100;
    scheduleScouts();
  });
}

// ---- Apply & acquire ------------------------------------------------------ //
async function applyAndAcquire() {
  if (!active || isLocalizer(active)) return;
  const pl = active.plan;
  const payload = {
    region, orientation: pl.orientation, inplane_fov_pct: pl.fov_pct,
    inplane_off: pl.inplane_off, tilt: pl.tilt, rot: pl.rot, params: active.params,
  };
  if (pl.slice != null) payload.slice_idx = pl.slice;
  $("pp-apply").disabled = true;
  $("pp-readout").textContent = "Acquiring…";
  try {
    const r = await call("render", payload);
    active.image = r.image;
    active.status = "acquired";
    // the acquired series fills the acquired-plane viewport (drag it to any box;
    // double-click to bring the scout back; scroll to page through its slices)
    slotState[pl.orientation] = {
      kind: "series", itemId: active.id, png: r.image,
      label: `${active.label} (acquired)`, payload,
      slice: r.slice_idx, maxSlice: r.max_slice,
    };
    lastSeriesPlane = pl.orientation;            // arrow keys page it right away
    renderSlot(pl.orientation);
    $("pp-readout").textContent =
      `Acquired ✓ — scroll / ↑↓ to page through ${(r.max_slice ?? 0) + 1} slices, drag to any viewport, or open the next sequence.`;
    renderQueue();
  } catch (err) {
    $("pp-readout").textContent = "Acquisition failed: " + err.message;
  } finally {
    $("pp-apply").disabled = false;
  }
}

// Page through an acquired series' slices (debounced re-render at the new slice).
let scrollTimer = null;
function scrollSeries(plane, step) {
  const st = slotState[plane];
  const max = st.maxSlice || 0;
  st.slice = clampN((st.slice ?? Math.round(max / 2)) + step, 0, max);
  $("vp-" + plane).querySelector(".vp-tag").textContent = `${st.label}  ·  ${st.slice}/${max}`;
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(async () => {
    try {
      const r = await call("render", { ...st.payload, slice_idx: st.slice });
      if (slotState[plane] === st) { st.png = r.image; renderSlot(plane); }
    } catch (e) { /* keep the last frame on error */ }
  }, 60);
}

// Live prescription summary while planning.
function updatePlanReadout() {
  if (!active || isLocalizer(active)) { $("pp-readout").textContent = ""; return; }
  const pl = active.plan, p = active.params;
  const sl = pl.slice == null ? "mid" : pl.slice;
  $("pp-readout").textContent =
    `slice ${sl} · ${p.n_slices ?? 1}×${p.slice_thickness ?? 5} mm · tilt ${pl.tilt}° · rot ${pl.rot}° · FOV ${pl.fov_pct}%`;
}
