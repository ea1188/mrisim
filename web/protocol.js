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
const snapAngle = (v) => { for (const t of [0, 15, 30, 45, 60, 75, 90, -15, -30, -45, -60, -75, -90]) if (Math.abs(v - t) <= 2.5) return t; return v; };
const fmtTime = (s) => { s = Math.round(s || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
// Perpendicular distance from a point to the segment a→b (all in [0,1] panel fractions).
const segDist = (px, py, a, b) => {
  const dx = b[0] - a[0], dy = b[1] - a[1], len2 = dx * dx + dy * dy || 1e-9;
  const t = Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / len2));
  return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy));
};
const PLANES = ["sagittal", "coronal", "axial"];

// ---- engine worker bridge (mirrors app.js) -------------------------------- //
const worker = new Worker("worker.js");
let reqId = 0, workerDead = false;
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
let region = "Brain";
let queue = [];          // [{id, preset, label, sequence, status, params, plan, image}]
let active = null;       // open queue item
let seq = 0;             // id counter
const vpGeom = {};       // plane -> last rendered panel geometry (for interaction)
let lastSeriesPlane = null;   // viewport last hovered/scrolled (arrow keys page it)

// ---- image-library exams (no engine: static scouts + example images) -------- //
// A lightweight "fake scanner" / positioning trainer: static scout images you can
// angle on (illustrative — the angle is cosmetic), and a static example image per
// sequence that pops up on Acquire. The acquired image is an example, NOT derived
// from the prescription. Drop real (properly-licensed) images into
// web/img/exams/<part>/ — see that folder's README — and they replace the
// labelled placeholders automatically; no code change needed.
let imageExam = null;    // active image-exam data, or null for engine (simulated) exams

function placeholderImg(title, sub, tint) {
  const svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320'>" +
    "<rect width='320' height='320' fill='#0a0d12'/>" +
    `<rect x='8' y='8' width='304' height='304' rx='6' fill='none' stroke='${tint}' stroke-opacity='0.5'/>` +
    `<text x='160' y='150' fill='${tint}' font-family='sans-serif' font-size='22' font-weight='bold' text-anchor='middle'>${title}</text>` +
    `<text x='160' y='180' fill='#9aa4b2' font-family='sans-serif' font-size='14' text-anchor='middle'>${sub}</text>` +
    "<text x='160' y='300' fill='#5b6470' font-family='sans-serif' font-size='11' text-anchor='middle'>placeholder - drop in a real image</text>" +
    "</svg>";
  // unicode-safe base64 (btoa is Latin1-only), so non-ASCII titles can't throw at load
  return "data:image/svg+xml;base64," + btoa(encodeURIComponent(svg).replace(
    /%([0-9A-F]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16))));
}

// Each image is a file under web/img/exams/<part>/<file>.png. If the file isn't
// there yet it shows a labelled placeholder instead — so you can drop images in
// one at a time (zero code) and the menu always works. See web/img/exams/README.
function buildImageExam(part, sequences, credit) {
  const slug = part.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  const dir = `img/exams/${slug}`;
  // try .png first, then the JPEGs radiology sites serve natively; placeholder last.
  const f = (file, ph) => ({
    src: `${dir}/${file}.png`, alts: [`${dir}/${file}.jpg`, `${dir}/${file}.jpeg`], ph,
  });
  return {
    credit: credit || null,
    scouts: {
      axial:    f("scout_axial",    placeholderImg(part, "Axial scout", "#7fb8ff")),
      coronal:  f("scout_coronal",  placeholderImg(part, "Coronal scout", "#7fb8ff")),
      sagittal: f("scout_sagittal", placeholderImg(part, "Sagittal scout", "#7fb8ff")),
    },
    sequences: sequences.map((s) => ({
      label: s.label, plane: s.plane, ...f(s.file, placeholderImg(part, s.label, "#ffdd44")),
    })),
  };
}
// Radiopaedia attribution line (CC BY-NC-SA 3.0) shown while an exam is open.
const RP = (id, who) =>
  `Images: case courtesy of ${who}, <a href="https://radiopaedia.org/cases/${id}" ` +
  `target="_blank" rel="noopener">Radiopaedia.org rID ${id}</a> · CC BY-NC-SA 3.0`;
// Sequence lists are per part — each matches the slices actually saved for that case
// (filename = the file: field, plane = which viewport the example opens in).
const ANKLE = [
  { label: "PD Axial",       plane: "axial",    file: "pd_axial" },
  { label: "PD Sagittal",    plane: "sagittal", file: "pd_sag" },
  { label: "PD FS Axial",    plane: "axial",    file: "pdfs_ax" },
  { label: "PD FS Coronal",  plane: "coronal",  file: "pdfs_cor" },
  { label: "PD FS Sagittal", plane: "sagittal", file: "pdfs_sag" },
];
const WRIST = [
  { label: "PD Axial",       plane: "axial",    file: "pd_ax" },
  { label: "PD Coronal",     plane: "coronal",  file: "pd_cor" },
  { label: "PD FS Axial",    plane: "axial",    file: "pdfs_ax" },
  { label: "PD FS Coronal",  plane: "coronal",  file: "pdfs_cor" },
  { label: "PD FS Sagittal", plane: "sagittal", file: "pdfs_sag" },
];
const SHOULDER = [
  { label: "PD Axial",      plane: "axial",    file: "pd_ax" },
  { label: "PD Coronal",    plane: "coronal",  file: "pd_cor" },
  { label: "PD Sagittal",   plane: "sagittal", file: "pd_sag" },
  { label: "PD FS Axial",   plane: "axial",    file: "pdfs_ax" },
  { label: "PD FS Coronal", plane: "coronal",  file: "pdfs_cor" },
];
const FOOT = [
  { label: "T1 Axial",       plane: "axial",    file: "t1_ax" },
  { label: "T1 Sagittal",    plane: "sagittal", file: "t1_sag" },
  { label: "T2 FS Sagittal", plane: "sagittal", file: "t12fs_sag" },
  { label: "PD FS Axial",    plane: "axial",    file: "pdfs_ax" },
  { label: "PD FS Sagittal", plane: "sagittal", file: "pdfs_sag" },
  { label: "T1 FS Coronal",  plane: "coronal",  file: "t1fs_cor" },
  { label: "T2 Coronal",     plane: "coronal",  file: "t2_cor" },
];
const HAND = [
  { label: "T1 Sagittal",    plane: "sagittal", file: "t1_sag" },
  { label: "T1 Coronal",     plane: "coronal",  file: "t1_cor" },
  { label: "T2 Axial",       plane: "axial",    file: "t2_ax" },
  { label: "PD FS Axial",    plane: "axial",    file: "pdfs_ax" },
  { label: "PD FS Coronal",  plane: "coronal",  file: "pdfs_cor" },
  { label: "PD FS Sagittal", plane: "sagittal", file: "pdfs_sag" },
];
// Spine cases (sequence labels derived from the supplied images; axial weightings
// are best-effort). Cervical combines a sagittal case and an axial case.
const CERVICAL = [
  { label: "T1 Sagittal",               plane: "sagittal", file: "t1_sag" },
  { label: "T2 Sagittal",               plane: "sagittal", file: "t2_sag" },
  { label: "STIR Sagittal",             plane: "sagittal", file: "stir_sag" },
  { label: "T1 Axial",                  plane: "axial",    file: "t1_ax" },
  { label: "T1 Axial (lower)",          plane: "axial",    file: "t1_ax_lower" },
];
const THORACIC = [
  { label: "T2 Sagittal", plane: "sagittal", file: "t2_sag" },
  { label: "T1 Sagittal", plane: "sagittal", file: "t1_sag" },
  { label: "T2 Axial",    plane: "axial",    file: "t2_ax" },
];
const LUMBAR = [
  { label: "T1 Sagittal",   plane: "sagittal", file: "t1_sag" },
  { label: "T2 Sagittal",   plane: "sagittal", file: "t2_sag" },
  { label: "STIR Sagittal", plane: "sagittal", file: "stir_sag" },
  { label: "T2 Axial",      plane: "axial",    file: "t2_ax" },
];
const TOTAL_SPINE = [
  { label: "T1 Sagittal (upper)", plane: "sagittal", file: "t1_sag_upper" },
  { label: "T1 Sagittal (lower)", plane: "sagittal", file: "t1_sag_lower" },
  { label: "T2 Sagittal (upper)", plane: "sagittal", file: "t2_sag_upper" },
  { label: "T2 Sagittal (lower)", plane: "sagittal", file: "t2_sag_lower" },
  { label: "T2 Axial",            plane: "axial",    file: "t2_ax" },
];
const HIP = [
  { label: "PD FS Coronal", plane: "coronal",  file: "pdfs_cor" },
  { label: "PD Coronal",    plane: "coronal",  file: "pd_cor" },
  { label: "PD FS Sagittal", plane: "sagittal", file: "pdfs_sag" },
  { label: "T2 FS Axial",   plane: "axial",    file: "t2fs_ax" },
];
// Cervical draws sagittals from rID 38418 and axials from rID 53916 (same author).
const RP_CERVICAL =
  'Images: cases courtesy of Bruno Di Muzio, '
  + '<a href="https://radiopaedia.org/cases/38418" target="_blank" rel="noopener">rID 38418</a> and '
  + '<a href="https://radiopaedia.org/cases/53916" target="_blank" rel="noopener">rID 53916</a> · CC BY-NC-SA 3.0';
const IMAGE_EXAMS = {
  Shoulder: buildImageExam("Shoulder", SHOULDER, RP(43115, "Andrew Dixon")),
  Wrist:    buildImageExam("Wrist", WRIST, RP(42982, "Andrew Dixon")),
  Hand:     buildImageExam("Hand", HAND, RP(161538, "Mohd Radhwan Bin Abidin")),
  Ankle:    buildImageExam("Ankle", ANKLE, RP(43117, "Andrew Dixon")),
  Foot:     buildImageExam("Foot", FOOT, RP(163787, "Mohd Radhwan Bin Abidin")),
  "Cervical Spine": buildImageExam("Cervical Spine", CERVICAL, RP_CERVICAL),
  "Thoracic Spine": buildImageExam("Thoracic Spine", THORACIC, RP(41033, "Bruno Di Muzio")),
  "Lumbar Spine":   buildImageExam("Lumbar Spine", LUMBAR, RP(47857, "Ian Bickle")),
  "Total Spine":    buildImageExam("Total Spine", TOTAL_SPINE, RP(181868, "Yahya Baba")),
  Hip:              buildImageExam("Hip", HIP, null),
};

// Reference "correct slice prescription" images (web/img/angles/), keyed by the
// current region + the sequence's plane. Shown as an optional toggled strip while
// planning. Missing combos simply have no reference. Foot uses radiology plane
// names (coronal = long axis, axial = short axis).
const ANGLE_REFS = {
  Brain:    { sagittal: "brain_sagittal.jpg", axial: "brain_axial.jpg" },
  Knee:     { sagittal: "knee_sagittal.jpg", coronal: "knee_coronal.jpg", axial: "knee_axial.jpg" },
  Shoulder: { sagittal: "shoulder_sagittal.jpg", coronal: "shoulder_coronal.jpg", axial: "shoulder_axial.jpg" },
  Wrist:    { sagittal: "wrist_sagittal.jpg", coronal: "wrist_coronal.jpg", axial: "wrist_axial.jpg" },
  Ankle:    { sagittal: "ankle_sagittal.jpg", coronal: "ankle_coronal.jpg", axial: "ankle_axial.jpg" },
  Foot:     { sagittal: "foot_sagittal.jpg", coronal: "foot_coronal_long_axis.jpg", axial: "foot_short_axis.jpg" },
};
["Spine", "Cervical Spine", "Thoracic Spine", "Lumbar Spine", "Total Spine"].forEach((r) => {
  ANGLE_REFS[r] = { sagittal: "spine_sagittal.jpg", axial: "spine_axial.jpg" };
});
let angleRefOpen = false;   // sticky across sequences; the strip only shows when a ref exists

function loadImageExam(name) {
  imageExam = IMAGE_EXAMS[name];
  region = name;
  seq = 0;
  queue = [{ id: ++seq, preset: LOCALIZER, label: "Localizer", sequence: null,
             status: "pending", image: null, plan: null }]
    .concat(imageExam.sequences.map((s) => ({
      id: ++seq, preset: s.label, label: s.label, sequence: s.plane || "", status: "pending",
      exampleImage: s.src, exampleAlts: s.alts, examplePh: s.ph,
      examplePlane: s.plane || "axial", plan: null,
    })));
  active = null;
  renderQueue();
  showCredit(imageExam.credit);
  openItem(queue[0]);
}
function showCredit(html) {
  const el = $("pp-credit");
  if (html) { el.innerHTML = html; el.hidden = false; } else { el.textContent = ""; el.hidden = true; }
}
const DEFAULT_IMG_FOV = [0.22, 0.22, 0.56, 0.56];   // in-plane FOV box: [x, y, w, h] fractions
// A sequence's prescription starts oriented to its acquired plane: on each cross scout the
// slice band depicts where the acquired plane cuts that scout (axial → horizontal line,
// coronal/sagittal → the orthogonal line). The user can then angle it freely from there.
// Maps [scout plane][acquired plane] → band direction (unit vector); in-plane uses the box.
const PRESET_DIR = {
  sagittal: { axial: [1, 0], coronal: [0, 1] },
  coronal:  { axial: [1, 0], sagittal: [0, 1] },
  axial:    { coronal: [1, 0], sagittal: [0, 1] },
};
function presetImgDir(scout, acq) {
  return (acq && PRESET_DIR[scout] && PRESET_DIR[scout][acq]) || [1, 0];
}
function imageScoutGeom(plane) {
  // The scout matching the sequence's plane shows an in-plane FOV box you can move/resize
  // (like a scanner's graphic prescription); the other two scouts show a cosmetic angle band.
  if (active && active.examplePlane === plane && !isLocalizer(active)) {
    const fb = (active.plan && active.plan.imgFov) || DEFAULT_IMG_FOV;
    return { name: plane, role: "acq", map: "row", n: 100, center: [0.5, 0.5], fov_box: fb };
  }
  const pl = active && active.plan;
  const c = (pl && pl.imgCtr && pl.imgCtr[plane]) || [0.5, 0.5];   // movable slice centre
  const d = (pl && pl.imgDir && pl.imgDir[plane])                 // user angle, else preset estimate
            || presetImgDir(plane, active && active.examplePlane);
  const L = Math.hypot(d[0], d[1]) || 1, ux = d[0] / L * 0.42, uy = d[1] / L * 0.42;
  return { name: plane, role: "cross", map: "row", n: 100, flip: false, angle: "tilt",
           center: c, band: [[c[0] - ux, c[1] - uy], [c[0] + ux, c[1] + uy]] };
}
function renderImageScouts() {
  PLANES.forEach((plane) => {
    const sc = imageExam.scouts[plane];
    scoutCache[plane] = { png: sc.src, alts: sc.alts, fallback: sc.ph,
                          geom: imageScoutGeom(plane), label: cap(plane) };
  });
  PLANES.forEach(renderSlot);
}
function acquireImageExample() {
  active.status = "acquired"; active.metrics = {};
  const plane = active.examplePlane || "axial";
  slotState[plane] = { kind: "series", itemId: active.id, png: active.exampleImage,
                       alts: active.exampleAlts, fallback: active.examplePh,
                       label: `${active.label} (example)`, wl: { b: 1, c: 1 } };
  lastSeriesPlane = plane;
  renderSlot(plane);
  $("pp-readout").textContent =
    `Acquired ${active.label} ✓ — example image (illustrative). ↻ Re-prescribe to change the plane and acquire again.`;
  $("pp-replan").hidden = false;                  // let them set it up again
  renderQueue();
}

// --- Guided feature tour (spotlight coachmarks over the real controls) ------- //
const TOUR = [
  { el: "#pp-exam", title: "Pick an exam",
    text: "Choose a protocol. The simulated exams (Brain, Knee, …) run the real engine; the <b>Image library</b> exams (Ankle, Wrist, Shoulder, Foot, Hand, Hip, and Cervical/Thoracic/Lumbar/Total spine) are positioning examples on real MRI images." },
  { el: "#pp-list", title: "The protocol queue",
    text: "Every sequence in the exam, in order. Click one to open it and prescribe it; the status dot fills in as you acquire. The Localizer at the top is your 3-plane scout." },
  { el: "#pp-views", title: "Prescribe on the scouts",
    text: "The three scout planes. <b>Drag a band end</b> to angle the slice, <b>drag the centre</b> to move it, and on the in-plane view <b>drag the FOV box</b> (corner to resize, inside to move), like a scanner's graphic prescription." },
  { el: "#pp-params", title: "Set parameters & acquire",
    text: "For simulated exams, tweak <b>TR / TE / flip / FOV / slices</b> here, then <b>Apply &amp; acquire</b>: the slice is reconstructed with scan time and SNR. For image-library exams, Acquire pops up the example image for that sequence." },
  { el: "#pp-tour-btn", title: "That's it",
    text: "Open a sequence and try it. You can re-open this tour anytime from <b>Tour</b>, or head <b>← Back to the simulator</b> for the single-slice workspace." },
];
// The tour engine lives in web/tour.js (shared with the main app); this page supplies
// the steps above and starts it with its own storage key.
const startPpTour = () => Tour.start(TOUR, { storageKey: "mrisim_pp_tour" });

// ---- boot ----------------------------------------------------------------- //
async function onReady() {
  $("splash").hidden = true;
  $("pp-root").hidden = false;
  wireParamPanel();
  $("pp-angleref-btn").addEventListener("click", () => { angleRefOpen = !angleRefOpen; updateAngleRef(); });
  $("pp-tour-btn").addEventListener("click", startPpTour);
  Tour.wire();
  PLANES.forEach(wireViewport);
  window.addEventListener("resize", () => PLANES.forEach((p) => drawOverlay(p, null)));
  await loadExam("Brain");
  let seen = false;
  try { seen = localStorage.getItem("mrisim_pp_tour") === "1"; } catch (e) { /* private mode */ }
  if (!seen) setTimeout(startPpTour, 600);          // auto-start once, after the first exam loads
}

async function loadExam(name) {
  if (name in IMAGE_EXAMS) { loadImageExam(name); return; }
  imageExam = null;
  showCredit(null);
  const info = await call("protocols", name);
  // exam picker (first time): simulated exams, then the image-library exams
  const sel = $("pp-exam");
  if (!sel.options.length) {
    info.exams.forEach((ex) => sel.add(new Option(ex, ex)));
    const og = document.createElement("optgroup");      // image-library exams, grouped + labelled
    og.label = "Image library (examples)";
    Object.keys(IMAGE_EXAMS).forEach((ex) => og.appendChild(new Option(ex, ex)));
    sel.add(og);
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
  let total = 0;
  queue.forEach((it, i) => {
    const li = document.createElement("li");
    li.className = (it === active ? "active " : "") + (it.status === "acquired" ? "acquired" : "");
    const dot = it.status === "acquired" ? "✓" : (it === active ? "▸" : "·");
    const t = it.metrics && it.metrics.scan_time;
    if (t) total += t;
    li.innerHTML = `<span class="q-num">${i + 1}</span>`
      + `<span class="q-label">${it.label}</span>`
      + (t ? `<span class="q-time">${fmtTime(t)}</span>` : "")
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
  const acq = queue.filter((it) => it.status === "acquired").length;
  $("pp-total").textContent = acq ? `acquired ${acq}/${queue.length} · ${fmtTime(total)}` : "";
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

// ---- reference-angulation overlay ----------------------------------------- //
// The matching "correct slice prescription" image for the open sequence, or null.
function angleRefFor(it) {
  if (!it || isLocalizer(it)) return null;
  const plane = imageExam ? (it.examplePlane || it.sequence) : (it.plan && it.plan.orientation);
  const m = ANGLE_REFS[region];
  const file = m && plane && m[plane];
  return file ? { file, plane } : null;
}
function updateAngleRef() {
  const ref = angleRefFor(active);
  const btn = $("pp-angleref-btn"), box = $("pp-angleref");
  if (!btn || !box) return;
  if (!ref) { btn.hidden = true; box.hidden = true; return; }
  btn.hidden = false;
  btn.textContent = "Reference angulation " + (angleRefOpen ? "▾" : "▸");
  if (!angleRefOpen) { box.hidden = true; return; }
  $("pp-angleref-img").src = "img/angles/" + ref.file;
  $("pp-angleref-label").textContent = "Recommended: " + region + " " + ref.plane;
  box.hidden = false;
}

// ---- open a sequence ------------------------------------------------------ //
async function openItem(it) {
  active = it;
  $("pp-replan").hidden = true;                                   // we're in planning mode now
  PLANES.forEach((p) => { slotState[p] = { kind: "scout" }; });   // fresh planning view
  renderQueue();
  if (imageExam) {                                  // image-library exam: static scouts only
    it.plan = it.plan || { orientation: "axial", tilt: 0, rot: 0, fov_pct: 100, imgDir: {} };
    const loc = isLocalizer(it);
    $("pp-seqname").textContent = loc ? "Localizer — 3-plane scout" : `${it.label}  ·  example image`;
    $("pp-controls").hidden = true;                 // no simulated parameters
    $("pp-actions").hidden = loc;                   // Acquire shown only for sequences
    renderImageScouts();
    $("pp-readout").textContent = loc ? ""
      : "Position the FOV box on the in-plane scout; on the others drag the centre to move "
        + "the slice or an end to angle it (illustrative). Acquire to see the example image.";
    updateAngleRef();
    return;
  }
  if (isLocalizer(it)) {
    it.plan = it.plan || { orientation: "axial", slice: null, tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100 };
    $("pp-seqname").textContent = "Localizer — 3-plane scout";
    $("pp-controls").hidden = true; $("pp-actions").hidden = true;
    await renderScouts();
    updateAngleRef();
    return;
  }
  // Provisional plan set synchronously, so hovers / refreshes during the preset
  // fetch never see a null active.plan.
  it.plan = it.plan || { orientation: "axial", slice: null, tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100 };
  if (!it.params) {                      // first open: resolve the preset
    const bundle = await call("preset", it.preset);
    if (active !== it) return;           // a newer open superseded this one — bail
    it.params = bundle.params;
    // Surface geometry defaults the panel shows, so the engine and the panel agree
    // (presets don't carry slice thickness / count).
    it.params.slice_thickness = it.params.slice_thickness ?? 5;
    it.params.n_slices = it.params.n_slices ?? 1;
    it.plan.orientation = bundle.orientation || "axial";
  }
  if (active !== it) return;
  $("pp-seqname").textContent = `${it.label}  ·  ${it.sequence}`;
  $("pp-controls").hidden = false; $("pp-actions").hidden = false;
  paramsToPanel(it);
  await renderScouts();
  updatePlanReadout();
  updateAngleRef();
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
      scheduleParamRender();
    });
  });
  $("pp-nsl").addEventListener("input", () => {
    if (!active || isLocalizer(active)) return;
    active.params[nslKey(active.params)] = +$("pp-nsl").value;
    scheduleParamRender();
  });
  $("pp-ti").addEventListener("input", () => { if (active && !isLocalizer(active)) { active.params.TI = +$("pp-ti").value; scheduleParamRender(); } });
  $("pp-bval").addEventListener("input", () => { if (active && !isLocalizer(active)) { active.params.b_value = +$("pp-bval").value; scheduleParamRender(); } });
  $("pp-fov").addEventListener("input", () => { if (active) { active.plan.fov_pct = clampN(+$("pp-fov").value, 20, 100); scheduleParamRender(); } });
  $("pp-tilt").addEventListener("input", () => { if (active) { active.plan.tilt = clampN(+$("pp-tilt").value, -90, 90); scheduleParamRender(); } });
  $("pp-rot").addEventListener("input", () => { if (active) { active.plan.rot = clampN(+$("pp-rot").value, -90, 90); scheduleParamRender(); } });
  $("pp-apply").addEventListener("click", applyAndAcquire);
  // Re-prescribe: restore the full 3-plane planning view for the acquired sequence
  // (all scouts at the saved prescription) so the angle / FOV can be changed and it
  // can be acquired again. openItem already rebuilds the scouts from active.plan.
  $("pp-replan").addEventListener("click", () => { if (active) openItem(active); });
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
    region, orientation: pl.orientation, fov_planning: true, inplane_fov_pct: pl.fov_pct,
    inplane_off: pl.inplane_off, tilt: pl.tilt, rot: pl.rot,
    params: isLocalizer(active) ? { sequence: "Spin Echo" } : active.params,
  };
  if (pl.slice != null) out.slice_idx = pl.slice;
  return out;
}
// Coalesced: only one scoutPanels render in flight; bursts collapse to a single
// follow-up render when it returns (no debounce lag, no pile-up).
let scoutBusy = false, scoutDirty = false;
async function renderScouts() {
  if (imageExam) { renderImageScouts(); return; }   // static scouts, no engine
  if (scoutBusy) { scoutDirty = true; return; }
  scoutBusy = true;
  try {
    do {
      scoutDirty = false;
      if (!active || !active.plan) return;
      if (!isLocalizer(active) && !active.params) return;   // params still resolving
      const res = await call("scoutPanels", scoutPayload());
      PLANES.forEach((plane) => {
        const panel = res[plane]; if (!panel) return;
        scoutCache[plane] = { png: panel.png, geom: panel.geom || {}, label: cap(plane) };
      });
      PLANES.forEach(renderSlot);
    } while (scoutDirty);
  } finally { scoutBusy = false; }
}
function scheduleScouts() { updatePlanReadout(); renderScouts(); }
// Typed/spun parameter edits: update the readout now, but debounce the engine render so
// "2200" fires one render, not four (2 → 22 → 220 → 2200).
let _paramTimer = 0;
function scheduleParamRender() {
  updatePlanReadout();
  clearTimeout(_paramTimer);
  _paramTimer = setTimeout(renderScouts, 180);
}

function renderSlot(plane) {
  const st = slotState[plane];
  if (st.kind === "scout") {
    const sc = scoutCache[plane]; if (!sc) return;
    vpGeom[plane] = sc.geom;
    window.vpGeom = vpGeom;        // exposed for the headless smoke's drag targeting
    drawTile(plane, sc.png, sc.label, true, false, sc.fallback, sc.alts);   // plannable, not draggable
    drawOverlay(plane);                                            // crisp interactive handles
  } else {                                                   // series: view-only, draggable
    const tag = (st.maxSlice ? `${st.label}  ·  ${st.slice}/${st.maxSlice}` : st.label) + "  ⠿";
    drawTile(plane, st.png, tag, false, true, st.fallback, st.alts);
    const img = $("vp-" + plane).querySelector("img");       // keep its window/level
    if (img && st.wl) img.style.filter = `brightness(${st.wl.b}) contrast(${st.wl.c})`;
  }
}
function drawTile(plane, dataURL, tag, plannable, draggable, fallback, alts) {
  const box = $("vp-" + plane);
  box.classList.toggle("plannable", !!plannable);
  let img = box.querySelector("img");
  if (!img) { img = document.createElement("img"); box.appendChild(img); }
  // image-library files may be absent or a different extension → try .jpg/.jpeg, then the
  // labelled placeholder, walking the chain on each load error.
  const chain = [...(alts || []), ...(fallback ? [fallback] : [])];
  let ci = 0;
  img.onerror = chain.length
    ? () => { if (ci < chain.length) img.src = chain[ci++]; else img.onerror = null; }
    : null;
  img.src = dataURL;
  img.draggable = !!draggable;
  img.style.filter = "";                                     // reset (series reapply theirs)
  box.querySelector(".vp-tag").textContent = tag;
  box._plannable = !!plannable;
  const svg = ensureOverlay(box);
  if (plannable) img.onload = () => drawOverlay(plane);       // reposition once decoded
  else { svg.replaceChildren(); svg.style.display = "none"; img.onload = null; }
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
// The displayed image is letterboxed inside its element; this returns the actual
// pixel rectangle (so the SVG overlay and the fraction math agree exactly).
function imgContentRect(img) {
  const r = img.getBoundingClientRect();
  if (!img.naturalWidth || !r.width) return null;
  const nAR = img.naturalWidth / img.naturalHeight, eAR = r.width / r.height;
  let cw, ch, ox, oy;
  if (eAR > nAR) { ch = r.height; cw = ch * nAR; ox = (r.width - cw) / 2; oy = 0; }
  else { cw = r.width; ch = cw / nAR; ox = 0; oy = (r.height - ch) / 2; }
  return { ox, oy, cw, ch, left: r.left, top: r.top };
}
function imgFraction(img, cx, cy) {
  const c = imgContentRect(img); if (!c) return null;
  const fx = (cx - c.left - c.ox) / c.cw, fy = (cy - c.top - c.oy) / c.ch;
  return (fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1) ? { px: fx, py: fy } : null;
}

// ---- client-side SVG planning overlay (band / FOV box / handles) ----------- //
// Drawn live over the grayscale scout background so dragging is instant (no server
// round-trip) and the grab points are crisp and labelled. Geometry comes from the
// panel geom (web_adapter); during a drag the band/box follow the cursor directly.
const SVGNS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
// The two points where the infinite line through P (direction D) crosses the
// [0,W]×[0,H] rect — so a live band stays inside its panel instead of overshooting.
function clipLine(P, D, W, H) {
  const cand = [];
  for (const [num, den] of [[-P[0], D[0]], [W - P[0], D[0]], [-P[1], D[1]], [H - P[1], D[1]]]) {
    if (Math.abs(den) < 1e-9) continue;
    const t = num / den, x = P[0] + t * D[0], y = P[1] + t * D[1];
    if (x >= -0.5 && x <= W + 0.5 && y >= -0.5 && y <= H + 0.5) cand.push(t);
  }
  if (cand.length < 2) return null;
  const lo = Math.min(...cand), hi = Math.max(...cand);
  return [[P[0] + lo * D[0], P[1] + lo * D[1]], [P[0] + hi * D[0], P[1] + hi * D[1]]];
}
function ensureOverlay(box) {
  let svg = box.querySelector("svg.pp-ov");
  if (!svg) {
    svg = el("svg", { class: "pp-ov", preserveAspectRatio: "none" });
    box.appendChild(svg);
  }
  return svg;
}
// Position the overlay over the image's actual pixels and set its viewBox to the
// pixel size, so geom fractions map to px (uniform, undistorted handles).
function placeOverlay(box, img, svg) {
  const c = imgContentRect(img), br = box.getBoundingClientRect();
  if (!c) { svg.style.display = "none"; return null; }
  svg.style.display = "";
  svg.style.left = (c.left - br.left + c.ox) + "px";
  svg.style.top = (c.top - br.top + c.oy) + "px";
  svg.style.width = c.cw + "px";
  svg.style.height = c.ch + "px";
  svg.setAttribute("viewBox", `0 0 ${c.cw} ${c.ch}`);
  return c;
}
// Pointer events fire faster than the display refreshes; coalesce overlay redraws to one
// per frame so a drag/hover does a single SVG rebuild per frame instead of per event.
const _ovPending = {};
let _ovRaf = 0;
function scheduleOverlay(plane, hoverMode, live) {
  _ovPending[plane] = { hoverMode, live };
  if (!_ovRaf) _ovRaf = requestAnimationFrame(() => {
    _ovRaf = 0;
    for (const pl of Object.keys(_ovPending)) {
      const a = _ovPending[pl]; delete _ovPending[pl];
      drawOverlay(pl, a.hoverMode, a.live);
    }
  });
}
// Draw the overlay for a scout panel. `live` (optional) overrides band/box during a
// drag: { bandDir:[ux,uy] } points the band at the cursor; { fovBox:[x,y,w,h] }.
function drawOverlay(plane, hoverMode, live) {
  const box = $("vp-" + plane), svg = box.querySelector("svg.pp-ov");
  if (!svg) return;
  const st = slotState[plane];
  const img = box.querySelector("img");
  const g = vpGeom[plane];
  if (st.kind !== "scout" || !box._plannable || !img || !g || !active || !active.plan) {
    svg.replaceChildren(); svg.style.display = "none"; return;
  }
  const c = placeOverlay(box, img, svg); if (!c) return;
  const W = c.cw, H = c.ch, hov = hoverMode, els = [];
  const px = (f) => [f[0] * W, f[1] * H];
  const HANDLE = "#ffdd44", LINE = "#ffdd44", FOV = "#7fb8ff", DIM = "#8a93a0";

  if (g.center) {                                   // faint crosshair through the centre
    const [cx, cy] = px(g.center);
    els.push(el("line", { x1: cx, y1: 0, x2: cx, y2: H, stroke: DIM, "stroke-width": 0.6, "stroke-opacity": 0.35 }));
    els.push(el("line", { x1: 0, y1: cy, x2: W, y2: cy, stroke: DIM, "stroke-width": 0.6, "stroke-opacity": 0.35 }));
  }
  // Cross panel: the slice band + diamond end-handles (grab to angle).
  if (g.role === "cross") {
    let a, b;
    if (live && live.bandDir && g.center) {         // angle drag: point the band at the cursor
      const seg = clipLine(px(g.center), [live.bandDir[0] * W, live.bandDir[1] * H], W, H);
      if (seg) { a = seg[0]; b = seg[1]; }          // clipped to the panel, aspect-correct
    } else if (live && live.band) { a = px(live.band[0]); b = px(live.band[1]); }  // slide
    else if (g.band) { a = px(g.band[0]); b = px(g.band[1]); }
    if (g.slab_edges && !(live && (live.bandDir || live.band))) {   // coverage rim + slice handles
      const e0 = g.slab_edges[0], e1 = g.slab_edges[1];
      if (e0 && e1) {                                // translucent slab fill (the slice coverage)
        const quad = [px(e0[0]), px(e0[1]), px(e1[1]), px(e1[0])];
        els.push(el("polygon", { points: quad.map((q) => q.join(",")).join(" "),
          fill: LINE, "fill-opacity": 0.07, stroke: "none" }));
      }
      for (const e2 of g.slab_edges) {
        const p0 = px(e2[0]), p1 = px(e2[1]);
        els.push(el("line", { x1: p0[0], y1: p0[1], x2: p1[0], y2: p1[1], stroke: LINE, "stroke-width": 1, "stroke-opacity": 0.5, "stroke-dasharray": "3 3" }));
        const mx = (p0[0] + p1[0]) / 2, my = (p0[1] + p1[1]) / 2, hw = hov === "slices" ? 7 : 5;
        const bar = el("rect", { x: mx - hw, y: my - 2.5, width: 2 * hw, height: 5, rx: 1.5, fill: LINE, "fill-opacity": hov === "slices" ? 0.95 : 0.7, stroke: "#1a1f26", "stroke-width": 0.8 });
        bar.appendChild(el("title", {})).textContent = "Drag the rim to add / remove slices";
        els.push(bar);
      }
    }
    if (a && b) {
      els.push(el("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: LINE, "stroke-width": 1.8, "stroke-opacity": 0.95 }));
      if (g.angle) for (const e2 of [a, b]) {        // angle handles at the ends only
        const r = hov === "oblique" ? 6 : 4.5;
        const d = el("rect", { x: e2[0] - r, y: e2[1] - r, width: 2 * r, height: 2 * r,
          transform: `rotate(45 ${e2[0]} ${e2[1]})`, fill: HANDLE, stroke: "#1a1f26", "stroke-width": 1 });
        d.appendChild(el("title", {})).textContent = "Drag an end to angle the plane";
        els.push(d);
      }
      const mc = (live && live.band)                 // centre handle: grab to slide the slices
        ? [(live.band[0][0] + live.band[1][0]) / 2, (live.band[0][1] + live.band[1][1]) / 2]
        : g.center;
      if (mc && !(live && live.bandDir)) {
        const [mx, my] = px(mc), r = hov === "slice" ? 5.5 : 4;
        const md = el("circle", { cx: mx, cy: my, r, fill: "#0b0e13", stroke: LINE, "stroke-width": 1.6 });
        md.appendChild(el("title", {})).textContent = "Drag the centre to move the slice position";
        els.push(md);
      }
    }
  }
  // Acquired plane: the FOV box, corner resize handles, and a move dot.
  if (g.role === "acq") {
    const fb = (live && live.fovBox) || g.fov_box;
    if (fb) {
      const x = fb[0] * W, y = fb[1] * H, w = fb[2] * W, h = fb[3] * H;
      els.push(el("rect", { x, y, width: w, height: h, fill: "none", stroke: FOV, "stroke-width": 1.6, "stroke-dasharray": "5 3" }));
      const corners = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]];
      for (const [hx, hy] of corners) {
        const r = hov === "resize" ? 5 : 3.5;
        const sq = el("rect", { x: hx - r, y: hy - r, width: 2 * r, height: 2 * r, fill: FOV, stroke: "#1a1f26", "stroke-width": 1 });
        sq.appendChild(el("title", {})).textContent = "Drag a corner to resize the FOV";
        els.push(sq);
      }
      const cd = el("circle", { cx: x + w / 2, cy: y + h / 2, r: hov === "recenter" ? 5 : 3.5, fill: FOV, stroke: "#1a1f26", "stroke-width": 1 });
      cd.appendChild(el("title", {})).textContent = "Drag to move the FOV";
      els.push(cd);
    }
  }
  svg.replaceChildren(...els);
}
function bandLocal(p, slice) {
  const s = slice == null ? (p.n - 1) / 2 : slice;
  if (p.map === "row") return 1 - s / (p.n - 1);
  return (p.flip ? (p.n - 1 - s) : s) / (p.n - 1);
}
// Which CSS cursor signals each grabbable region (so it's obvious where to grab).
const cursorFor = (m) => ({
  recenter: "move", resize: "nwse-resize", oblique: "grab",
  slice: "move", slices: "row-resize",
}[m] || "crosshair");

// What does the pointer do at this spot on a scout panel? (shared by hover + drag)
function modeAt(p, loc) {
  if (!p || !active || !active.plan) return null;
  if (imageExam) {                                 // image scouts (engine-free)
    if (p.role === "acq" && p.fov_box) {           // in-plane FOV box: corner → resize, inside → move
      const fb = p.fov_box, cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
      const edge = Math.max(Math.abs(loc.px - cx) / (fb[2] / 2 || 1), Math.abs(loc.py - cy) / (fb[3] / 2 || 1));
      return edge > 0.72 ? "resize" : "recenter";
    }
    const cc = p.center || [0.5, 0.5];             // cross scout: centre → move slice, outer → angle
    return Math.hypot(loc.px - cc[0], loc.py - cc[1]) < 0.16 ? "slice" : "oblique";
  }
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
  // On the band line: grab toward an END to angle, the CENTRE to slide the slice package.
  // Test the ACTUAL (possibly already-tilted) band — `p.band` is the rendered line, in the
  // same panel-fraction space as `loc`. The old test used the STRAIGHT bandLocal position,
  // so once you angled the plane the tilted band fell outside it → "rotate once, then it
  // locks" (every later grab read as a slice move). Falls back to bandLocal if no geometry.
  const cc = p.center || [0.5, 0.5];
  if (p.angle && p.band) {
    if (segDist(loc.px, loc.py, p.band[0], p.band[1]) < 0.07) {
      return Math.hypot(loc.px - cc[0], loc.py - cc[1]) > 0.16 ? "oblique" : "slice";
    }
    return "slice";
  }
  const bp = bandLocal(p, active.plan.slice);
  const along = p.map === "row" ? loc.px : loc.py;
  const perp = p.map === "row" ? loc.py : loc.px;
  if (Math.abs(perp - bp) < 0.08) {
    const cAlong = p.map === "row" ? cc[0] : cc[1];
    if (p.angle && Math.abs(along - cAlong) > 0.2) return "oblique";   // near an end → angle
    return "slice";                                                    // near the centre → move
  }
  return "slice";
}

// Per-(acquired orientation, cross-panel) sign so a grabbed band end follows the
// cursor. The direction a panel's slice band rotates for +tilt / +rot depends on the
// plane geometry, so a single global sign feels reversed in some panels (e.g. angling
// a Knee/sagittal acquisition on its axial panel). These signs were derived by
// checking the actual band-end motion from oblique.plane_from_angles + scout_band for
// every orientation×panel — stable across volume shapes. (+1 = the base formula is
// already correct; only the two rot-on-axial-panel cases need flipping.)
const OBLIQUE_SIGN = {
  axial:    { coronal: 1, sagittal: 1 },
  sagittal: { axial: -1, coronal: 1 },
  coronal:  { axial: -1, sagittal: 1 },
};

// Per-mode drag application. Each returns the live overlay override the drag should show
// ({band} | {fovBox} | {bandDir}) or null, and mutates the open item's plan/params as a
// side effect. `d` is the in-flight drag (mode, geom `p`, and per-mode start state).
const DRAG_APPLY = {
  slice(d, loc, plane) {
    const p = d.p, pl = active.plan;
    if (imageExam) {                                // image scout: move the slice centre to the cursor
      const cx = clampN(loc.px, 0.12, 0.88), cy = clampN(loc.py, 0.12, 0.88);
      pl.imgCtr = pl.imgCtr || {};
      pl.imgCtr[plane] = [cx, cy];
      const dir = (pl.imgDir && pl.imgDir[plane]) || [1, 0];
      const L = Math.hypot(dir[0], dir[1]) || 1, ux = dir[0] / L * 0.42, uy = dir[1] / L * 0.42;
      return { band: [[cx - ux, cy - uy], [cx + ux, cy + uy]] };
    }
    const s = p.map === "row" ? (1 - loc.py) * (p.n - 1) : (p.flip ? (1 - loc.px) : loc.px) * (p.n - 1);
    pl.slice = clampN(Math.round(s), 0, p.n - 1);
    if (!p.band) return null;                       // optimistic: the band follows the cursor
    const isRow = p.map === "row";
    const bc = p.center || [(p.band[0][0] + p.band[1][0]) / 2, (p.band[0][1] + p.band[1][1]) / 2];
    const off = isRow ? loc.py - bc[1] : loc.px - bc[0], sh = isRow ? [0, off] : [off, 0];
    return { band: [[p.band[0][0] + sh[0], p.band[0][1] + sh[1]], [p.band[1][0] + sh[0], p.band[1][1] + sh[1]]] };
  },
  recenter(d, loc) {
    const p = d.p, pl = active.plan, fb = d.box0;
    if (imageExam) {                                // move the in-plane FOV box to the cursor
      const nx = clampN(loc.px - fb[2] / 2, 0, 1 - fb[2]), ny = clampN(loc.py - fb[3] / 2, 0, 1 - fb[3]);
      pl.imgFov = [nx, ny, fb[2], fb[3]];
      return { fovBox: pl.imgFov };
    }
    const u = (p.ip_dir === "x" ? loc.px : loc.py) - 0.5;
    pl.inplane_off = p.ip_sign * u * p.ip_axis_len;
    if (!fb) return null;
    return { fovBox: p.ip_dir === "x"               // optimistic: the box follows the cursor
      ? [clampN(loc.px - fb[2] / 2, 0, 1 - fb[2]), fb[1], fb[2], fb[3]]
      : [fb[0], clampN(loc.py - fb[3] / 2, 0, 1 - fb[3]), fb[2], fb[3]] };
  },
  resize(d, loc) {
    const pl = active.plan, fb = d.box0, cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
    if (imageExam) {                                // resize the in-plane FOV box around its centre
      const hx = Math.min(Math.abs(loc.px - cx), cx, 1 - cx), hy = Math.min(Math.abs(loc.py - cy), cy, 1 - cy);
      const w = Math.max(2 * hx, 0.12), h = Math.max(2 * hy, 0.12);
      pl.imgFov = [cx - w / 2, cy - h / 2, w, h];
      return { fovBox: pl.imgFov };
    }
    const half = Math.max(Math.abs(loc.px - cx), Math.abs(loc.py - cy));
    pl.fov_pct = Math.round(clampN(2 * half, 0.3, 1.0) * 100 / 5) * 5;
    $("pp-fov").value = pl.fov_pct;
    const s = pl.fov_pct / (d.pct0 || 100);         // scale the box around its centre
    return { fovBox: [cx - fb[2] / 2 * s, cy - fb[3] / 2 * s, fb[2] * s, fb[3] * s] };
  },
  slices(d, loc) {                                  // drag the slab rim → number of slices
    const p = d.p, perp = p.map === "row" ? loc.py : loc.px;
    active.params.n_slices = clampN(Math.round(d.n0 * Math.abs(perp - p.slab.c) / (d.half0 || 0.03)), 1, 32);
    $("pp-nsl").value = active.params.n_slices;
    return null;
  },
  oblique(d, loc, plane) {                          // band tracks the cursor, locked to the applied angle
    const p = d.p, pl = active.plan;
    const sgn = (OBLIQUE_SIGN[pl.orientation] || {})[p.name] ?? 1;
    let dth = Math.atan2(d.c[1] - loc.py, loc.px - d.c[0]) - d.theta0;   // y-up
    dth = Math.atan2(Math.sin(dth), Math.cos(dth));                     // wrap to (−π, π]
    const val = snapAngle(clampN(d.a0 + dth * 180 / Math.PI * sgn, -90, 90));
    if (p.angle === "tilt") { pl.tilt = val; $("pp-tilt").value = val; }
    else { pl.rot = val; $("pp-rot").value = val; }
    // Draw at the *applied* angle (snapped + clamped), not the raw cursor: the band visibly
    // snaps, never overshoots ±45°, and doesn't jump when the server render lands.
    const yup = d.theta0 + ((val - d.a0) * sgn) * Math.PI / 180;
    const bandDir = [Math.cos(yup), -Math.sin(yup)];
    if (imageExam) { pl.imgDir = pl.imgDir || {}; pl.imgDir[plane] = bandDir; }   // persist cosmetic angle
    return { bandDir };
  },
};

// Plan a scout on a viewport: drag to angle / move / resize / set slices, with hover
// affordances. (Acquired-series viewing — scroll, window/level, DnD — is wireSeriesViewer.)
function wirePlanningDrag(plane, box) {
  let drag = null;
  const startDrag = (loc) => {
    const p = vpGeom[plane]; if (!p || !active) return null;
    const mode = modeAt(p, loc);
    const d = { mode, p };
    if (mode === "oblique") {                       // polar: track the cursor angle round the pivot
      d.c = p.center || [0.5, 0.5];
      d.a0 = p.angle === "tilt" ? active.plan.tilt : active.plan.rot;
      d.theta0 = Math.atan2(d.c[1] - loc.py, loc.px - d.c[0]);   // y-up screen angle
    }
    if (mode === "resize") { d.box0 = p.fov_box; d.pct0 = active.plan.fov_pct || 100; }
    if (mode === "recenter") { d.box0 = p.fov_box; }
    if (mode === "slices") { d.half0 = p.slab.half; d.n0 = (+$("pp-nsl").value) || 1; }
    return d;
  };
  const applyDrag = (loc) => {
    if (!drag || !active) return;
    const fn = DRAG_APPLY[drag.mode];
    const live = fn ? fn(drag, loc, plane) : null;
    updatePlanReadout();
    scheduleOverlay(plane, null, live);             // rAF-coalesced client-side feedback
    drag.moved = true;                              // sync exact backgrounds + geometry on release
  };
  const endDrag = () => {
    if (drag) { box.style.cursor = ""; delete _ovPending[plane]; if (drag.moved) scheduleScouts(); }
    drag = null;
  };
  box.addEventListener("pointerdown", (e) => {
    const img = box.querySelector("img");
    if (!img || !box._plannable) return;            // acquired series → view-only / draggable
    const f = imgFraction(img, e.clientX, e.clientY); if (!f) return;
    drag = startDrag(f);
    if (drag) {
      if (drag.mode === "oblique") box.style.cursor = "grabbing";
      try { box.setPointerCapture(e.pointerId); } catch (_) { /* unsupported */ }
      applyDrag(f); e.preventDefault();
    }
  });
  window.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const img = box.querySelector("img"); if (!img) return;
    const f = imgFraction(img, e.clientX, e.clientY); if (f) applyDrag(f);
  });
  window.addEventListener("pointerup", endDrag);
  window.addEventListener("pointercancel", endDrag);

  // Hover: cursor + highlight the handle under the pointer before you grab it.
  box.addEventListener("pointermove", (e) => {
    if (drag) return;
    const img = box.querySelector("img");
    if (!img || !box._plannable) { box.style.cursor = ""; return; }
    const f = imgFraction(img, e.clientX, e.clientY);
    const mode = f ? modeAt(vpGeom[plane], f) : null;
    box.style.cursor = f ? cursorFor(mode) : "";
    scheduleOverlay(plane, mode);
  });
  box.addEventListener("pointerleave", () => { if (!drag) scheduleOverlay(plane, null); });
}

// View an acquired series on a viewport: wheel/arrow paging, right-drag window/level,
// drag-between-viewports, and double-click reset.
function wireSeriesViewer(plane, box) {
  box.addEventListener("pointerenter", () => {      // arrow keys page the last-touched series
    if (slotState[plane].kind === "series") lastSeriesPlane = plane;
  });
  box.addEventListener("wheel", (e) => {            // scroll through the series' slices
    if (slotState[plane].kind !== "series" || !slotState[plane].payload) return;
    e.preventDefault();
    scrollSeries(plane, e.deltaY < 0 ? 1 : -1);
  }, { passive: false });

  // Right-drag → window / level (PACS): horizontal = window (contrast), vertical = level
  // (brightness). Pure client-side CSS filter.
  let wl = null;
  box.addEventListener("contextmenu", (e) => { if (slotState[plane].kind === "series") e.preventDefault(); });
  box.addEventListener("pointerdown", (e) => {
    if (e.button !== 2 || slotState[plane].kind !== "series") return;
    const st = slotState[plane];
    wl = { lx: e.clientX, ly: e.clientY, b0: st.wl.b, c0: st.wl.c };
    e.preventDefault();
  });
  window.addEventListener("pointermove", (e) => {
    if (!wl) return;
    const st = slotState[plane]; if (st.kind !== "series") { wl = null; return; }
    st.wl.c = clampN(wl.c0 + (e.clientX - wl.lx) * 0.005, 0.2, 4);
    st.wl.b = clampN(wl.b0 - (e.clientY - wl.ly) * 0.004, 0.2, 3);
    const img = box.querySelector("img");
    if (img) img.style.filter = `brightness(${st.wl.b}) contrast(${st.wl.c})`;
  });
  window.addEventListener("pointerup", () => { wl = null; });

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
  // Double-click: a series box brings its scout back; a scout box resets the prescription
  // (angles + FOV) to straight / full — parity with the main app.
  box.addEventListener("dblclick", () => {
    if (slotState[plane].kind === "series") { revertSlot(plane); return; }
    if (!active || isLocalizer(active)) return;
    Object.assign(active.plan, { tilt: 0, rot: 0, inplane_off: 0, fov_pct: 100 });
    $("pp-tilt").value = 0; $("pp-rot").value = 0; $("pp-fov").value = 100;
    scheduleScouts();
  });
}

function wireViewport(plane) {
  const box = $("vp-" + plane);
  wirePlanningDrag(plane, box);   // scout planning (drag to angle / move / resize / slices)
  wireSeriesViewer(plane, box);   // acquired-series viewing (scroll, window/level, DnD)
}

// ---- Apply & acquire ------------------------------------------------------ //
async function applyAndAcquire() {
  if (!active || isLocalizer(active)) return;
  if (imageExam) { acquireImageExample(); return; }   // pop up the example image
  const pl = active.plan;
  const payload = {
    region, orientation: pl.orientation, fov_planning: true, inplane_fov_pct: pl.fov_pct,
    inplane_off: pl.inplane_off, tilt: pl.tilt, rot: pl.rot, params: active.params,
  };
  if (pl.slice != null) payload.slice_idx = pl.slice;
  $("pp-apply").disabled = true;
  $("pp-readout").textContent = "Acquiring…";
  try {
    const r = await call("render", payload);
    active.image = r.image;
    active.status = "acquired";
    active.metrics = r.metrics || {};
    // the acquired series fills the acquired-plane viewport (drag it to any box;
    // double-click to bring the scout back; scroll to page through its slices)
    slotState[pl.orientation] = {
      kind: "series", itemId: active.id, png: r.image,
      label: `${active.label} (acquired)`, payload,
      slice: r.slice_idx, maxSlice: r.max_slice, wl: { b: 1, c: 1 },
    };
    lastSeriesPlane = pl.orientation;            // arrow keys page it right away
    renderSlot(pl.orientation);
    const m = active.metrics;
    // SNR metrics are brain-tissue-keyed; body exams (Knee, Abdomen) have none,
    // so only show an SNR term when one is available rather than a bare "SNR 0".
    const snr = Math.round(m.snr_wm || m.snr || m.snr_gm || m.snr_eff || 0);
    const snrTxt = snr > 0 ? ` · SNR ${snr}` : "";
    $("pp-readout").textContent =
      `Acquired ✓ · ${fmtTime(m.scan_time)}${snrTxt} — scroll / ↑↓ to page slices, `
      + `right-drag to window/level, drag to any viewport. ↻ Re-prescribe to adjust & re-acquire.`;
    $("pp-replan").hidden = false;               // re-open the scouts to change the prescription
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
  if (!active.plan || !active.params) return;
  const pl = active.plan, p = active.params;
  const sl = pl.slice == null ? "mid" : pl.slice;
  $("pp-readout").textContent =
    `slice ${sl} · ${p.n_slices ?? 1}×${p.slice_thickness ?? 5} mm · tilt ${pl.tilt}° · rot ${pl.rot}° · FOV ${pl.fov_pct}%`;
}
