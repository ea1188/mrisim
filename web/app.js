/* MRISim browser edition — control shell. Pyodide + the engine run in a web
   worker (worker.js); this file wires the HTML controls and talks to the worker
   over a small request/response protocol so renders never freeze the UI. */
"use strict";

const $ = (id) => document.getElementById(id);
let booted = false;

// Offline support + CDN resilience: register the (network-first) service worker
// after load so it never competes with the first paint. Best-effort — the app
// works fine without it, and the SW never serves stale shell code to online users.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch((e) => console.warn("SW registration failed:", e));
  });
}

let compareMode = false;
let protocolA = null;       // snapshot payload for the "A" side of a comparison
let applyingPreset = false; // suppress the custom-reset while a preset populates
let winW = 1.0, winL = 0.5; // window/level (normalised), driven by image drag
let scoutPanels = [];       // per-panel click→slice geometry from the last scout
let measureMode = "off";    // "off" | "ruler" | "roi"
let measureDrag = null;     // {p0,p1} fractions while dragging a measurement
let measureShape = null;    // last completed {kind,p0,p1} (kept drawn until cleared)
let planOff = 0, planTilt = 0, planRot = 0;  // in-plane FOV offset + oblique angles (drag-set)
let probe = null;           // {bytes, w, h, tissues} aligned label map for the cursor readout

const SEQ_FA = new Set(["Gradient Echo", "Balanced SSFP", "MR Angiography", "Susceptibility (SWI)"]);
const SEQ_TI = new Set(["Inversion Recovery"]);
// Sequences needing the ~1-minute vessel-tree build the first time (see web_adapter).
const SEQ_SLOW_FIRST = new Set(["MR Angiography", "Susceptibility (SWI)"]);
const ACQ3D_SEQ = new Set(["Spin Echo", "Gradient Echo", "Inversion Recovery", "Balanced SSFP"]);

// Plain-language "what this is clinically for" blurb under the sequence picker.
// Fixed-role sequences key off the name; SE/FSE/GRE key off the computed weighting.
const SEQ_HELP = {
  "Diffusion (DWI)": "Restricted diffusion lights up — acute stroke, abscess, dense tumour. Always read with the ADC map to rule out T2 shine-through.",
  "Perfusion (ASL)": "Magnetically-labelled arterial blood as a tracer (no contrast) — the label-control difference is the perfusion-weighted image (~1% signal, grey matter brightest); the CBF map quantifies flow in mL/100g/min.",
  "Perfusion (Dynamic)": "Gadolinium-bolus perfusion. DSC (T2*) bolus-tracking → CBV / CBF / MTT maps — stroke core shows low CBV + prolonged MTT. DCE (T1) uptake → Ktrans permeability — ~0 behind an intact blood-brain barrier, high in leaky tumour / active lesions.",
  "MR Angiography": "Flowing blood is bright (time-of-flight) — maps vessels with no contrast injection.",
  "Susceptibility (SWI)": "Blood products, iron and calcium go dark — microbleeds, veins, mineralisation.",
  "fMRI (BOLD)": "T2*-sensitive to the blood-oxygenation change with neural activity — functional mapping.",
  "Echo Planar (EPI)": "Single-shot T2* readout (the engine behind DWI/fMRI): very fast, but prone to distortion and ghosting.",
  "Balanced SSFP": "Bright fluid and blood (T2/T1 contrast), fast — cardiac cine, MRCP-type and fetal imaging.",
  "Inversion Recovery": "A 180° pulse then a delay (TI) nulls one tissue: FLAIR (TI≈2500 ms) blacks out CSF so lesions pop; STIR (TI≈250 ms) blacks out fat to reveal oedema.",
  "Quantitative (qMRI)": "Fits the actual T1/T2/PD value at every pixel instead of a single weighted picture.",
};
const WEIGHT_HELP = {
  "T1": "T1-weighted: fat and white matter bright, fluid (CSF) dark. Anatomy and post-contrast enhancement.",
  "T2": "T2-weighted: fluid and most pathology bright, white matter darker. The workhorse for lesions, oedema and tumours.",
  "PD": "Proton-density: little T1/T2 weighting, so contrast tracks tissue water. Good for cartilage and subtle lesions.",
  "Mixed": "Mixed weighting — push TR/TE toward T1 (both short) or T2 (both long) for cleaner contrast.",
};
function updateSeqHelp() {
  const seq = $("sequence").value;
  $("seq-help").textContent =
    SEQ_HELP[seq] || WEIGHT_HELP[weighting(seq, +$("tr").value, +$("te").value)] || "";
}
// Canonical default plane per region — the spine/knee are acquired/best seen
// sagittal, so opening them axial would show a coarse reformat.
const REGION_PLANE = { Spine: "sagittal", Knee: "sagittal" };

// --- Worker plumbing -------------------------------------------------------- //
const worker = new Worker("worker.js");
let reqId = 0;
let workerDead = false;              // set if the engine worker crashes (vs. a per-call error)
const pending = new Map();           // id -> {resolve, reject}

function call(type, payload) {
  if (workerDead) return Promise.reject(new Error("the engine has stopped — please reload the page"));
  return new Promise((resolve, reject) => {
    const id = ++reqId;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, payload });
  });
}

// If the worker itself crashes (e.g. out of memory) it fires an `error` event
// rather than posting a result — without this, in-flight calls would hang forever
// and the UI would silently freeze. Fail them loudly and tell the user to reload.
function onWorkerCrash(ev) {
  if (workerDead) return;
  workerDead = true;
  const msg = (ev && ev.message) || "the engine worker stopped unexpectedly";
  for (const [, p] of pending) p.reject(new Error(msg));
  pending.clear();
  document.body.classList.remove("busy");
  const hint = document.getElementById("hint");
  if (hint) hint.textContent = "Engine error — please reload the page to continue.";
  const splashStatus = document.getElementById("splash-status");
  if (splashStatus && !document.getElementById("splash").hidden) {
    splashStatus.textContent = "The engine failed to start — please reload.";
  }
  console.warn("worker crashed:", msg);
}
worker.onerror = onWorkerCrash;
worker.onmessageerror = onWorkerCrash;

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
  await loadLessons();           // populate the guided-lesson picker (shared data)
  if (info.version) document.querySelector(".tag").textContent = "browser edition · v" + info.version;
  setSplash(100, "Ready");
  $("splash").style.display = "none";
  $("app").hidden = false;
  booted = true;
  await applyHashState();        // restore a shared prescription, if the URL has one
  render();
  updateSeqHelp();
  if (!maybeStartDeepLinkLesson()) maybeShowIntro();
}

// Deep-link: simulator.html?lesson=<exact title> opens that guided lesson on load,
// so the course page can launch an interactive lesson directly (skips the intro).
function maybeStartDeepLinkLesson() {
  try {
    const t = new URLSearchParams(location.search).get("lesson");
    if (t && LESSON_INDEX.has(t)) { curriculumPos = -1; deepLinkLesson = true; startLesson(LESSON_INDEX.get(t)); return true; }
  } catch (e) { /* ignore */ }
  return false;
}

// --- Shareable URL state + export ------------------------------------------- //
// Schema version for shareable links. Bump when a key's *meaning* changes (units,
// encoding) so migrateState() can fix up old links instead of misapplying them.
// Adding/removing keys doesn't need a bump — missing keys are simply ignored.
const STATE_SCHEMA = 1;
const HASH_KEYS = {
  v: () => STATE_SCHEMA,
  region: () => curRegion(), seq: () => $("sequence").value, orient: () => curOrient(),
  slice: () => $("slice").value, field: () => $("field").value,
  tr: () => $("tr").value, te: () => $("te").value, ti: () => $("ti").value, fa: () => $("fa").value,
  matrix: () => $("matrix").value, bw: () => $("bw").value, nex: () => $("nex").value,
  bval: () => $("bval").value, etl: () => $("etl").value, thick: () => $("thick").value,
  fatsat: () => ($("fatsat").checked ? 1 : 0), gd: () => ($("gd").checked ? 1 : 0),
  flow: () => ($("flow").checked ? 1 : 0), acq3d: () => ($("acq3d").checked ? 1 : 0),
  np: () => $("np").value, kzpf: () => ($("kzpf").checked ? 1 : 0),
  curvemode: () => $("curvemode").value, curveshow: () => ($("curveshow").checked ? 1 : 0),
  receivecoil: () => $("receivecoil").value,
};

function stateToHash() {
  const q = Object.entries(HASH_KEYS).map(([k, f]) => `${k}=${encodeURIComponent(f())}`).join("&");
  history.replaceState(null, "", "#" + q);
}

// Apply a plain state object (short keys, same as the URL hash) to the controls.
// Only keys present are set, so callers can override a subset (presets, lessons,
// shared links). Booleans for the checkbox keys.
async function applyState(st) {
  st = st || {};                    // a reading/concept lesson step carries no state
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
  const sv = (key) => { if (st[key] !== undefined && st[key] !== null) { $(key).value = st[key]; const o = $(key + "-val"); if (o) o.value = $(key).value; updateSliderAria(key); } };
  ["slice", "tr", "te", "ti", "fa", "matrix", "bw", "nex", "thick", "bval", "etl", "np",
   "nslices", "sgap", "ipfov", "satpos", "satwidth", "satangle", "satangle2", "accel", "pv"].forEach(sv);
  ["fatsat", "gd", "flow", "acq3d", "kzpf", "fovplan", "cmap", "kspaceshow", "psdshow",
   "b0mapshow", "gfactorshow", "mathshow", "labelanat", "curveshow",
   "motion", "chemshift", "suscept", "nowrap", "peswap", "satband"].forEach((k) => { if (st[k] !== undefined) $(k).checked = !!st[k]; });
  // A lesson/link that enables the 3-D slab without asking for a specific depth
  // gets full anatomy coverage (same as ticking 3D by hand), so reformats are full.
  if (st.acq3d && st.np === undefined) {
    syncSlabMax(); $("np").value = $("np").max; const o = $("np-val"); if (o) o.value = $("np").value;
  }
  if (st.motiontype) $("motiontype").value = st.motiontype;
  if (st.accelmethod) $("accelmethod").value = st.accelmethod;
  if (st.diffdisp) $("diffdisp").value = st.diffdisp;
  if (st.angiotype) $("angiotype").value = st.angiotype;
  if (st.qmridisp) $("qmridisp").value = st.qmridisp;
  if (st.fmridisp) $("fmridisp").value = st.fmridisp;
  if (st.perfdisp) $("perfdisp").value = st.perfdisp;
  if (st.perfdyndisp) $("perfdyndisp").value = st.perfdyndisp;
  if (st.curvemode) $("curvemode").value = st.curvemode;
  if (st.receivecoil) $("receivecoil").value = st.receivecoil;
  // Pathology select (back-compat: the old boolean `lesion` maps to "lesion").
  if (st.pathology !== undefined) $("pathology").value = st.pathology;
  else if (st.lesion !== undefined) $("pathology").value = st.lesion ? "lesion" : "";
  // Reflect the teaching panels a lesson/share-link may have toggled.
  $("scoutwrap").hidden = !$("fovplan").checked;
  $("planctl").hidden = !$("fovplan").checked;
  $("cmapwrap").hidden = !$("cmap").checked;
  $("kspacewrap").hidden = !$("kspaceshow").checked;
  $("psdwrap").hidden = !$("psdshow").checked;
  $("b0mapwrap").hidden = !$("b0mapshow").checked;
  $("gfactorwrap").hidden = !$("gfactorshow").checked;
  $("mathwrap").hidden = !$("mathshow").checked;
  $("curvewrap").hidden = !$("curveshow").checked;
  syncVisibility();
  applyingPreset = false;
}

// Bring an older share-link's state up to the current schema. No-op today (v1);
// add per-version fix-ups here as the schema evolves so old links keep working.
function migrateState(st, fromV) {
  // Example for the future:
  //   if (fromV < 2) { /* rename/convert keys */ }
  return st;
}

async function applyHashState() {
  const h = location.hash.slice(1);
  if (!h) return false;
  const p = new URLSearchParams(h);
  let st = {};
  for (const [k, v] of p) st[k] = ["fatsat", "gd", "flow", "acq3d", "kzpf", "curveshow"].includes(k) ? v === "1" : v;
  // Schema handling: pre-versioned links have no `v` (treat as v0). Newer-than-known
  // links still apply best-effort (forward-compatible: unknown keys are ignored).
  const linkV = st.v === undefined ? 0 : parseInt(st.v, 10) || 0;
  delete st.v;
  if (linkV < STATE_SCHEMA) st = migrateState(st, linkV);
  else if (linkV > STATE_SCHEMA) {
    console.warn(`Share-link schema v${linkV} is newer than this build (v${STATE_SCHEMA}); applying what it can.`);
  }
  await applyState(st);
  return true;
}

// The page-load state — every console control at its authored default. Reset
// re-applies it through applyState (the same path a share-link uses), then puts
// the view back to Brain / axial / mid-slice with a clean window/level.
const DEFAULT_STATE = {
  region: "Brain", seq: "Spin Echo", orient: "axial", field: "3T",
  tr: 500, te: 15, ti: 800, fa: 90,
  matrix: 256, bw: 125, nex: 1, thick: 5, bval: 1000, etl: 16,
  ipfov: 100, satpos: 50, satwidth: 15, satangle: 0, satangle2: 0,
  nslices: 1, sgap: 0, np: 400, accel: 1, pv: 10,
  fatsat: false, gd: false, flow: false, acq3d: false, kzpf: false, fovplan: false,
  cmap: false, kspaceshow: false, psdshow: false, b0mapshow: false, gfactorshow: false,
  mathshow: false, labelanat: false, curveshow: false,
  motion: false, chemshift: false, suscept: false, nowrap: false, peswap: false, satband: false,
  motiontype: "periodic", accelmethod: "SENSE", receivecoil: "uniform", curvemode: "TE decay",
  diffdisp: "DWI", angiotype: "TOF", qmridisp: "T1 Map (VFA)", fmridisp: "EPI Image",
  perfdisp: "Perfusion-weighted", perfdyndisp: "CBV (DSC)", pathology: "",
};

async function resetToDefaults() {
  if (compareMode) setCompare(false);                       // leave A/B compare
  await applyState(DEFAULT_STATE);                          // applies every control + syncVisibility
  // Authoritative slice range from a fresh Brain load (applyState skips the reload
  // when already on Brain, leaving slice.max stale), then land on the middle slice.
  const d = await loadRegion("Brain");
  $("slice").max = d.max_slice;
  setSlice(Math.floor(d.max_slice / 2));
  const offBtn = $("measuremode").querySelector('button[data-m="off"]');
  if (offBtn && measureMode !== "off") offBtn.click();      // measure tool → off
  winW = 1.0; winL = 0.5;                                   // clean window/level
  const pop = $("overlay-pop");                             // send the inspector back to its corner + default size
  if (pop) { pop.style.left = pop.style.top = pop.style.right = pop.style.bottom = ""; pop.style.width = pop.style.height = ""; }
  $("preset").value = ""; syncPresetRail();                 // Custom
  render();
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
let lastDialogFocus = null;   // element to restore focus to when a dialog closes
function openDialog(id, focusId) {
  lastDialogFocus = document.activeElement;
  $(id).hidden = false;
  const f = $(focusId); if (f) f.focus();
}
function closeDialog(id) {
  $(id).hidden = true;
  if (lastDialogFocus && typeof lastDialogFocus.focus === "function") lastDialogFocus.focus();
}
function showIntro() { openDialog("intro", "intro-tour"); }
function hideIntro() { closeDialog("intro"); localStorage.setItem("mrisim_seen", "1"); }
function maybeShowIntro() {
  $("intro-ok").addEventListener("click", hideIntro);
  $("intro-x").addEventListener("click", hideIntro);
  $("intro-tour").addEventListener("click", () => { hideIntro(); Tour.start(TOUR, { storageKey: "mrisim_tour" }); });
  $("help").addEventListener("click", showIntro);
  Tour.wire();
  try { if (!localStorage.getItem("mrisim_seen")) showIntro(); } catch (e) { /* private mode */ }
}

// --- Guided feature tour (spotlight coachmarks over the real controls) ------- //
const TOUR = [
  { el: "#sequence", title: "Pick a sequence", reveal: () => showTab("setup"),
    text: "Choose the pulse sequence — Spin Echo, FLAIR, diffusion, angiography… The plain-language note just below says what each one is for." },
  { el: "#tr", title: "Set the timing", reveal: () => showTab("contrast"),
    text: "Sweep <b>TR / TE / flip</b> to change the contrast — drag the slider, or type an exact value in the box (or arrow-key it)." },
  { el: "#mainImage", title: "The image",
    text: "The reconstructed slice. <b>Scroll</b> (or ↑/↓) to change slice, <b>drag</b> to window/level, and <b>hover</b> any pixel to read its tissue and T1 / T2 / PD." },
  { el: "#protocol-link", title: "Protocol planning",
    text: "Plan a whole exam like a <b>scanner console</b>: pick a protocol, then for each sequence <b>prescribe it on the scout images</b> — angle the plane, place the FOV, set the slices — and <b>Apply to acquire</b> (with scan time + SNR). Drag the acquired images between viewports, window/level, and re-run sequences. Opens in a new workspace." },
  { el: "#curveshow", title: "The signal curve", reveal: () => showTab("learn"),
    text: "Tick <b>Signal curve</b> (or any overlay here) and it pops up over the image — showing how signal depends on your settings." },
  { el: "#preset-list", title: "Clinical presets",
    text: "Apply a real-world protocol in one click — every setting is filled in for you." },
  { el: "#compare", title: "Compare A / B",
    text: "Snapshot the current setup as <b>A</b>, change something, then <b>Compare</b> to see the two side by side." },
  { el: "#acq3d", title: "3D & reconstruction", reveal: () => showTab("quality"),
    text: "Acquire a whole <b>3D slab</b> once and reformat any plane. Reconstruction opens a PACS-style 2×2 view (three planes + a 3D MIP)." },
  { el: "#measuremode", title: "Measure", reveal: () => showTab("learn"),
    text: "<b>Ruler</b> and <b>ROI</b> tools — drag on the image (or a reformat) to read a distance in mm, or an ROI's mean / SD / SNR." },
  { el: "#ctrl-find", title: "Find anything",
    text: "Lost a control? Type here — matching controls from every tab appear together as you type." },
  { el: "#lessons-btn", title: "Learn from scratch",
    text: "New to MRI? Open <b>Lessons</b> for short guided walkthroughs, or <b>Curriculum</b> for a beginner path. You can re-open this tour anytime from <b>?</b>." },
];
// The tour engine lives in web/tour.js (shared with the Protocol Planning page);
// app.js just supplies the steps above and drives it via window.Tour.

// --- Guided lessons --------------------------------------------------------- //
// Guided-lesson data lives in lessons.json (single source shared with the
// desktop app); loadLessons() fetches and populates these at startup.
let LESSONS = [];

// --- Guided curriculum: an ordered beginner path through the lessons --------- //
// Each module groups existing lessons into a sequence that builds from "what is
// an MRI image?" up to advanced contrast, reconstruction and artifacts.
let CURRICULUM = [];   // loaded from lessons.json (single source shared with desktop)
let LESSON_INDEX = new Map();
// Flat ordered path of lesson indices (skip any title that doesn't resolve).
let CURRICULUM_PATH = [];
let curriculumPos = -1;     // position in CURRICULUM_PATH while following the path; -1 = free lesson
let deepLinkLesson = false; // true when the current lesson was opened via ?lesson= (course-page embed)

function curriculumDone() {
  try { return new Set(JSON.parse(localStorage.getItem("mrisim_curriculum") || "[]")); }
  catch (e) { return new Set(); }
}
function curriculumMarkDone(title) {
  try { const s = curriculumDone(); s.add(title); localStorage.setItem("mrisim_curriculum", JSON.stringify([...s])); }
  catch (e) { /* private mode: progress just won't persist */ }
}
function curriculumModuleOf(pos) {       // which module a path position belongs to
  let n = 0;
  for (let m = 0; m < CURRICULUM.length; m++) { n += CURRICULUM[m].lessons.length; if (pos < n) return m; }
  return CURRICULUM.length - 1;
}

let lessonIdx = -1, stepIdx = 0;

// Fetch the shared lesson data (single source, also read by the desktop app) and
// populate the derived indices + picker list. Tolerant of a failed fetch so the
// rest of the app still works; the picker just stays empty.
async function loadLessons() {
  try {
    const data = await (await fetch("lessons.json")).json();
    LESSONS = data.lessons || [];
    CURRICULUM = data.curriculum || [];
    LESSON_INDEX = new Map(LESSONS.map((L, i) => [L.title, i]));
    CURRICULUM_PATH = CURRICULUM.flatMap((m) => m.lessons.map((t) => LESSON_INDEX.get(t)).filter((i) => i !== undefined));
    buildLessonList();
  } catch (e) {
    console.warn("lessons.json failed to load:", e);
  }
}

function buildLessonList() {
  const list = $("lesson-list");
  list.innerHTML = "";
  let firstBeginner = true, firstAdvanced = true;
  LESSONS.forEach((L, i) => {
    // Section dividers: the beginner "Start here" track, then the rest.
    if (L.beginner && firstBeginner) {
      firstBeginner = false;
      const h = document.createElement("p"); h.className = "lesson-section";
      h.textContent = "New to MRI? Start here";
      list.appendChild(h);
    } else if (!L.beginner && firstAdvanced) {
      firstAdvanced = false;
      const h = document.createElement("p"); h.className = "lesson-section";
      h.textContent = "Go deeper — the physics";
      list.appendChild(h);
    }
    const b = document.createElement("button");
    b.className = "lesson-item" + (L.beginner ? " beginner" : "");
    b.innerHTML = `<b>${L.title}</b><span>${L.blurb}</span>`;
    b.addEventListener("click", () => { $("lesson-picker").hidden = true; curriculumPos = -1; startLesson(i); });
    list.appendChild(b);
  });
}

function wireLessons() {
  $("lessons-btn").addEventListener("click", () => openDialog("lesson-picker", "lesson-picker-close"));
  $("lesson-picker-close").addEventListener("click", () => closeDialog("lesson-picker"));
  $("lesson-picker-x").addEventListener("click", () => closeDialog("lesson-picker"));
  $("lesson-exit").addEventListener("click", exitLesson);
  $("lesson-prev").addEventListener("click", () => { if (stepIdx > 0) { stepIdx--; applyStep(); } });
  $("lesson-next").addEventListener("click", () => {
    if (stepIdx < LESSONS[lessonIdx].steps.length - 1) { stepIdx++; applyStep(); } else finishLesson();
  });
  wireCurriculum();
}

// Finishing a lesson: in the curriculum, mark it done and advance to the next
// lesson in the path (or close when the path is complete); otherwise just exit.
function finishLesson() {
  // Sync completion to the instructor backend when signed in (no-op otherwise).
  if (lessonIdx >= 0 && window.Accounts) Accounts.logActivity("lesson_complete", LESSONS[lessonIdx].title);
  if (curriculumPos >= 0 && lessonIdx >= 0) {
    curriculumMarkDone(LESSONS[lessonIdx].title);
    curriculumPos++;
    if (curriculumPos < CURRICULUM_PATH.length) { startLesson(CURRICULUM_PATH[curriculumPos]); return; }
    curriculumPos = -1;        // whole curriculum complete
    exitLesson();
    openCurriculum();          // show the (now fully ticked) overview
    return;
  }
  // Opened straight from the course page (deep-link): still record completion so the
  // course's progress ticks — the two share localStorage across the iframe boundary.
  if (deepLinkLesson && lessonIdx >= 0) curriculumMarkDone(LESSONS[lessonIdx].title);
  exitLesson();
}

function startLesson(i) {
  lessonIdx = i; stepIdx = 0;
  if (compareMode) setCompare(false);
  ["gd", "flow", "fatsat", "acq3d", "kzpf"].forEach((id) => { $(id).checked = false; });  // clean baseline
  $("lesson-panel").hidden = false;
  applyStep();
}
function exitLesson() {
  lessonIdx = -1; curriculumPos = -1; deepLinkLesson = false; $("lesson-panel").hidden = true;
  if (compareMode) setCompare(false);   // a lesson may have ended in a comparison
}

function startCurriculumAt(pos) {
  curriculumPos = pos;
  closeDialog("curriculum");
  startLesson(CURRICULUM_PATH[pos]);
}

// Build the curriculum overview: a progress bar, the modules with their lessons
// (ticked when done), and a Start/Continue button that resumes the first lesson
// you haven't finished.
function openCurriculum() {
  const done = curriculumDone();
  const list = $("curriculum-list");
  list.innerHTML = "";
  let pos = 0, firstUndone = -1, completed = 0;
  CURRICULUM.forEach((mod) => {
    const modEl = document.createElement("div"); modEl.className = "cur-module";
    const head = document.createElement("div"); head.className = "cur-module-h";
    let modDone = 0;
    mod.lessons.forEach((t) => { if (done.has(t)) modDone++; });
    head.innerHTML = `<span>${mod.title}</span><span class="cur-count">${modDone}/${mod.lessons.length}</span>`;
    modEl.appendChild(head);
    mod.lessons.forEach((title) => {
      const idx = LESSON_INDEX.get(title);
      if (idx === undefined) return;
      const thisPos = pos++;                 // path position for this lesson
      const isDone = done.has(title);
      if (isDone) completed++;
      if (!isDone && firstUndone < 0) firstUndone = thisPos;
      const b = document.createElement("button");
      b.className = "cur-lesson" + (isDone ? " done" : "");
      b.innerHTML = `<span class="tick">${isDone ? "✓" : ""}</span><span>${title}</span>`;
      b.addEventListener("click", () => startCurriculumAt(thisPos));
      modEl.appendChild(b);
    });
    list.appendChild(modEl);
  });
  const total = CURRICULUM_PATH.length;
  $("cur-bar").style.width = `${Math.round(100 * completed / total)}%`;
  $("cur-progress-text").textContent =
    completed === 0 ? `${total} lessons across ${CURRICULUM.length} modules — start from the top.`
    : completed >= total ? `All ${total} lessons complete — revisit any module any time.`
    : `${completed} of ${total} lessons done — pick up where you left off.`;
  const resume = firstUndone < 0 ? 0 : firstUndone;
  const startBtn = $("curriculum-start");
  startBtn.textContent = completed === 0 ? "Start" : (completed >= total ? "Review from start" : "Continue");
  startBtn.onclick = () => startCurriculumAt(resume);
  openDialog("curriculum", "curriculum-start");
}

function wireCurriculum() {
  $("curriculum-btn").addEventListener("click", openCurriculum);
  $("curriculum-close").addEventListener("click", () => closeDialog("curriculum"));
  $("curriculum-x").addEventListener("click", () => closeDialog("curriculum"));
  $("curriculum-reset").addEventListener("click", () => {
    try { localStorage.removeItem("mrisim_curriculum"); } catch (e) { /* ignore */ }
    openCurriculum();          // re-render with cleared ticks
  });
}

async function applyStep() {
  const L = LESSONS[lessonIdx], s = L.steps[stepIdx];
  $("lesson-title").textContent = L.title;
  // A step with no simulator state is a reading/concept step (e.g. MR safety):
  // mark the panel so it reads as a reading card, and leave the viewport as-is.
  $("lesson-panel").classList.toggle("reading", !s.state && !s.compareWith);
  $("lesson-step").innerHTML = s.text;
  $("lesson-progress").textContent = `Step ${stepIdx + 1} / ${L.steps.length}`;
  $("lesson-prev").disabled = stepIdx === 0;
  // In the curriculum, show where you are and offer "Next lesson" rather than "Finish".
  const inCur = curriculumPos >= 0;
  const cur = $("lesson-cur");
  cur.hidden = !inCur;
  if (inCur) {
    const m = curriculumModuleOf(curriculumPos);
    cur.textContent = `Curriculum · ${CURRICULUM[m].title}  —  lesson ${curriculumPos + 1} of ${CURRICULUM_PATH.length}`;
  }
  const last = stepIdx === L.steps.length - 1;
  $("lesson-next").textContent = !last ? "Next ›"
    : (inCur && curriculumPos < CURRICULUM_PATH.length - 1 ? "Next lesson ›" : "Finish");
  await applyState(s.state);
  // A step may stage a side-by-side comparison: `state` becomes panel A and
  // `compareWith` (a second state) becomes panel B, in compare mode.
  if (s.compareWith) {
    protocolA = collectPayload();
    $("setA").classList.add("on");
    await applyState(s.compareWith);
    setCompare(true);                  // renders A (snapshot) vs B (current)
  } else {
    if (compareMode) setCompare(false);
    render();
  }
}

// --- Keyboard + wheel slice navigation -------------------------------------- //
function setSlice(v) {
  const sl = $("slice");
  v = Math.max(0, Math.min(+sl.max, v));
  if (v === +sl.value) return;
  sl.value = v; $("slice-val").value = v; updateSliderAria("slice"); reflectSlice(); schedule();
}

// Keep the vertical slice rail (#slice-v, next to the image) in step with #slice.
function reflectSlice() {
  const sl = $("slice"), rail = $("slice-v");
  if (!rail) return;
  rail.min = sl.min; rail.max = sl.max; rail.value = sl.value;
  rail.setAttribute("aria-valuetext", `slice ${sl.value} of ${sl.max}`);
}

// Size the (absolutely-positioned) slice rail to the image area so a drag covers
// the whole stack. The rail is out of flow, so setting its height can't grow the
// row or shift the image — unlike an in-flow height, which caused a feedback loop.
function sizeSliceRail() {
  const rail = $("slice-v"), images = document.querySelector(".image-row .images");
  if (!rail || !images) return;
  const h = images.clientHeight - 16;
  if (h > 60) rail.style.height = h + "px";
}

function wireKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!$("intro").hidden) { hideIntro(); return; }
      if (!$("lesson-picker").hidden) { closeDialog("lesson-picker"); return; }
      if (!$("lesson-panel").hidden) { exitLesson(); return; }
    }
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
    "Balanced SSFP", "Diffusion (DWI)", "Perfusion (ASL)", "Perfusion (Dynamic)", "MR Angiography", "Susceptibility (SWI)",
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
    const on = $("fovplan").checked;
    $("scoutwrap").hidden = !on;
    $("planctl").hidden = !on;
    render();   // re-render so the main image picks up / drops the FOV crop
  });
  $("ipfov").addEventListener("input", () => { if (document.activeElement !== $("ipfov-val")) $("ipfov-val").value = $("ipfov").value; updateSliderAria("ipfov"); schedule(); });
  $("nowrap").addEventListener("change", render);   // toggle phase wraparound on the main image
  $("peswap").addEventListener("change", render);   // swap the phase-encode (wrap) direction
  $("satband").addEventListener("change", render);  // toggle the saturation band
  ["satpos", "satwidth", "satangle", "satangle2"].forEach((id) =>
    $(id).addEventListener("input", () => { if (document.activeElement !== $(id + "-val")) $(id + "-val").value = $(id).value; updateSliderAria(id); schedule(); }));
  // Signal curve: hide/show the panel, and switch what the curve plots (the engine
  // already supports several modes; re-render to redraw it).
  $("curveshow").addEventListener("change", () => { $("curvewrap").hidden = !$("curveshow").checked; });
  $("curvemode").addEventListener("change", render);
  $("cmap").addEventListener("change", () => { $("cmapwrap").hidden = !$("cmap").checked; render(); });
  $("kspaceshow").addEventListener("change", () => { $("kspacewrap").hidden = !$("kspaceshow").checked; render(); });
  $("psdshow").addEventListener("change", () => { $("psdwrap").hidden = !$("psdshow").checked; render(); });
  $("b0mapshow").addEventListener("change", () => { $("b0mapwrap").hidden = !$("b0mapshow").checked; render(); });
  $("gfactorshow").addEventListener("change", () => { $("gfactorwrap").hidden = !$("gfactorshow").checked; render(); });
  $("accelmethod").addEventListener("change", schedule);
  $("accel").addEventListener("input", () => { $("accelmethod-row").hidden = +$("accel").value <= 1; });
  $("mathshow").addEventListener("change", () => { $("mathwrap").hidden = !$("mathshow").checked; });
  $("labelanat").addEventListener("change", render);   // re-render with/without the anatomy labels
  $("pathology").addEventListener("change", render);   // re-render with/without the demo pathology
  $("slice-v").addEventListener("input", () => setSlice(+$("slice-v").value));  // rail beside the image
  wireWindowLevel();
  wireScout();
  wireRecon();
  wireProbe();
  wireMeasure();
  wireReconMeasure();
  wireKeyboard();
  wireLessons();

  setupSliderA11y();
  setupTabs();
  buildPresetRail();
  setupOverlayPop();
  setupSearch();
  ["tr", "te", "ti", "fa", "np", "slabsharp", "slice", "matrix", "bw", "nex", "thick", "bval", "etl", "nslices", "sgap", "accel", "pv"].forEach((id) => {
    $(id).addEventListener("input", () => {
      // Don't clobber the number field while the user is typing into it.
      const out = $(id + "-val"); if (out && document.activeElement !== out) out.value = $(id).value;
      updateSliderAria(id);
      schedule();
    });
  });
  wireNumbers();
  $("copylink").addEventListener("click", copyLink);
  $("download").addEventListener("click", downloadPNG);
  $("reset-defaults").addEventListener("click", resetToDefaults);
  [reg, seq, $("field")].forEach((el) => el.addEventListener("change", onSequenceOrRegion));
  ["fatsat", "gd", "flow", "acq3d", "kzpf"].forEach((id) =>
    $(id).addEventListener("change", () => {
      if (id === "acq3d") {
        // Cover the whole anatomy from the first click: a freshly-enabled slab
        // spans the full slice axis (the user can thin it down afterwards).
        if ($("acq3d").checked) { syncSlabMax(); $("np").value = $("np").max; const o = $("np-val"); if (o) o.value = $("np").value; }
        syncVisibility();
      }
      schedule();
    }));
  ["motion", "chemshift", "suscept"].forEach((id) =>
    $(id).addEventListener("change", () => { syncVisibility(); schedule(); }));
  $("motiontype").addEventListener("change", schedule);
  ["diffdisp", "perfdisp", "perfdyndisp", "angiotype", "qmridisp", "fmridisp"].forEach((id) => $(id).addEventListener("change", schedule));
  $("receivecoil").addEventListener("change", render);   // re-render with the coil's shading
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
    setOrient(REGION_PLANE[curRegion()] || "axial");   // open on the region's canonical plane
  }
  syncVisibility();
  schedule();
}

// Keep the slab-depth slider's range tied to the current slice-axis extent, so
// "max" means the whole anatomy (the engine clamps anyway). Caps at the slider's
// hard max so very large volumes stay bounded.
function syncSlabMax() {
  const full = Math.min(400, (+$("slice").max || 0) + 1);
  if (full < 4) return;
  $("np").max = full;
  if (+$("np").value > full) $("np").value = full;
  const o = $("np-val"); if (o) o.value = $("np").value;
}

function syncVisibility() {
  const s = $("sequence").value;
  $("fa-row").hidden = !SEQ_FA.has(s);
  $("ti-row").hidden = !SEQ_TI.has(s);
  $("bval-row").hidden = s !== "Diffusion (DWI)";
  $("diffdisp-row").hidden = s !== "Diffusion (DWI)";
  $("perfdisp-row").hidden = s !== "Perfusion (ASL)";
  $("perfdyndisp-row").hidden = s !== "Perfusion (Dynamic)";
  $("angiotype-row").hidden = s !== "MR Angiography";
  $("qmridisp-row").hidden = s !== "Quantitative (qMRI)";
  $("fmridisp-row").hidden = s !== "fMRI (BOLD)";
  $("etl-row").hidden = s !== "FSE / TSE";
  $("accelmethod-row").hidden = +$("accel").value <= 1;
  const is3d = ACQ3D_SEQ.has(s);
  $("acq3d").disabled = !is3d;
  if (!is3d) $("acq3d").checked = false;
  const on3d = is3d && $("acq3d").checked;
  syncSlabMax();
  $("np-row").hidden = !on3d;
  $("slabsharp-row").hidden = !on3d;
  $("kzpf-row").hidden = !on3d;
  $("slab-readout").hidden = !on3d;
  // Reconstruction needs an acquired 3-D slab; gate the toggle on it.
  $("reconshow").disabled = !on3d;
  $("recon-need").hidden = on3d;
  if (!on3d && $("reconshow").checked) {
    $("reconshow").checked = false; $("reconctl").hidden = true; $("reconwrap").hidden = true;
  }
  // The demo pathologies are painted into brain white matter — only offer on Brain.
  const brain = curRegion() === "Brain";
  $("pathology-row").hidden = !brain;
  if (!brain) $("pathology").value = "";
  // Motion type only matters when motion is on; show a fix-it hint per artifact.
  $("motiontype-row").hidden = !$("motion").checked;
  const tips = [];
  if ($("motion").checked) tips.push("Motion: ghosts repeat along phase-encode — averaging (NEX) or breath-hold reduces them.");
  if ($("chemshift").checked) tips.push("Chemical shift: fat shifts along readout — raise the bandwidth (or fat-sat) to shrink it.");
  if ($("suscept").checked) tips.push("Susceptibility: dropout near air/bone — shorten TE or use spin echo instead of gradient echo.");
  $("artifact-help").textContent = tips.join("  ");
}

const curRegion = () => $("region").value;
function setOrient(v) {
  $("orientation").querySelectorAll("button").forEach((b) => {
    const on = b.dataset.v === v;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on);
  });
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
    n_slices: +$("nslices").value, slice_gap: +$("sgap").value,
    accel_factor: +$("accel").value, accel_method: $("accelmethod").value,
    pv_sigma: +$("pv").value,
    fatsat_enabled: $("fatsat").checked,
    contrast_enabled: $("gd").checked, contrast_dose: $("gd").checked ? 5 : 0,
    flow_enabled: $("flow").checked,
    // Teaching artifacts (the engine already models these; here we just expose them).
    motion_enabled: $("motion").checked, motion_type: $("motiontype").value,
    chemical_shift_enabled: $("chemshift").checked,
    susceptibility_enabled: $("suscept").checked,
  };
  if (s === "Diffusion (DWI)") { params.b_value = +$("bval").value; params.diff_display = $("diffdisp").value; }
  if (s === "Perfusion (ASL)") params.perf_display = $("perfdisp").value;
  if (s === "Perfusion (Dynamic)") params.perf_dyn_display = $("perfdyndisp").value;
  if (s === "FSE / TSE") params.etl = +$("etl").value;
  if (s === "MR Angiography") params.angio_type = $("angiotype").value;
  if (s === "Quantitative (qMRI)") params.qmri_display = $("qmridisp").value;
  if (s === "fMRI (BOLD)") params.fmri_display = $("fmridisp").value;
  if (ACQ3D_SEQ.has(s) && $("acq3d").checked) {
    params.acq3d = true;
    params.n_partitions = +$("np").value;
    params.slab_sharpness = +$("slabsharp").value;
    params.kz_pf = $("kzpf").checked ? 0.75 : null;
  }
  const out = {
    region: curRegion(), orientation: curOrient(),
    slice_idx: +$("slice").value, curve_mode: $("curvemode").value,
    receive_coil: $("receivecoil").value,
    window_width: winW, window_level: winL, params,
    contrast_map: $("cmap").checked,
    show_kspace: $("kspaceshow").checked,
    show_psd: $("psdshow").checked,
    show_b0map: $("b0mapshow").checked,
    show_gfactor: $("gfactorshow").checked,
    label_anatomy: $("labelanat").checked,
    pathology: $("pathology").value,
  };
  if ($("fovplan").checked) {                 // graphic FOV box + oblique prescription
    out.fov_planning = true;
    out.inplane_fov_pct = +$("ipfov").value;
    out.inplane_off = planOff;
    out.no_phase_wrap = $("nowrap").checked;
    out.pe_swap = $("peswap").checked;
    out.satband_enabled = $("satband").checked;
    out.satband_pos = +$("satpos").value;
    out.satband_width = +$("satwidth").value;
    out.satband_angle = +$("satangle").value;
    out.satband_angle2 = +$("satangle2").value;
    out.tilt = planTilt; out.rot = planRot;
  }
  return out;
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
  if (p.diff_display) $("diffdisp").value = p.diff_display;
  if (p.perf_display) $("perfdisp").value = p.perf_display;
  if (p.perf_dyn_display) $("perfdyndisp").value = p.perf_dyn_display;
  if (p.angio_type) $("angiotype").value = p.angio_type;
  if (p.qmri_display) $("qmridisp").value = p.qmri_display;
  if (p.fmri_display) $("fmridisp").value = p.fmri_display;
  if (p.field_strength) $("field").value = p.field_strength;
  $("fatsat").checked = !!p.fatsat_enabled;
  $("gd").checked = !!p.contrast_enabled;
  $("flow").checked = !!p.flow_enabled;
  $("acq3d").checked = !!p.acq3d;
  if (p.acq3d) {                         // a 3-D acquisition covers the whole anatomy
    syncSlabMax();                       // (isotropic volume → full reformats, not a
    set("np", $("np").max);              //  thin 32-partition slab)
  } else if (p.n_partitions) {
    set("np", p.n_partitions);
  }
  syncVisibility();
  applyingPreset = false;
  $("preset").value = name;           // keep the chosen preset shown
  syncPresetRail();
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
  $("compare").hidden = on;    // in compare mode only "Exit compare" shows (avoid a toggle that reads as "compare")
  $("exitAB").hidden = !on;
  $("wrapB").hidden = !on;
  $("tagA").hidden = !on;
  if (!on) {
    $("abdelta").textContent = ""; $("setA").classList.remove("on");
    $("capA").hidden = true; $("capB").hidden = true;
  }
  render();
}

const PATHOLOGY_LABEL = { lesion: "WM lesion", ms: "MS plaques", stroke: "Stroke",
  hemorrhage: "Microhaemorrhage", tumor: "Tumour", abscess: "Abscess" };

// Accessible name + spoken unit for each slider, so a screen reader announces
// "Repetition time TR, 500 milliseconds" rather than a bare "500".
const SLIDER_A11Y = {
  tr: ["Repetition time TR", "milliseconds"], te: ["Echo time TE", "milliseconds"],
  ti: ["Inversion time TI", "milliseconds"], fa: ["Flip angle", "degrees"],
  matrix: ["Matrix size", ""], bw: ["Receiver bandwidth", "kilohertz"],
  nex: ["Averages NEX", ""], thick: ["Slice thickness", "millimeters"],
  bval: ["b-value", "seconds per square millimetre"], etl: ["Echo train length", "echoes"],
  np: ["Partitions", ""], slice: ["Slice", ""], nslices: ["Number of slices", "slices"],
  sgap: ["Slice gap", "millimeters"], ipfov: ["In-plane field of view", "percent"],
};
function updateSliderAria(id) {
  const el = $(id), spec = SLIDER_A11Y[id];
  if (!el || !spec) return;
  el.setAttribute("aria-valuetext", `${el.value} ${spec[1]}`.trim());
}
function setupSliderA11y() {
  for (const id of Object.keys(SLIDER_A11Y)) {
    const el = $(id); if (!el) continue;
    el.setAttribute("aria-label", SLIDER_A11Y[id][0]);
    updateSliderAria(id);
  }
}

// Editable numeric values: each parameter slider has a paired <input type="number">
// (id + "-val"). Typing or arrow-keying it drives the slider and re-renders, reusing
// the slider's own input handlers (which skip writing back while the field is focused).
function wireNumbers() {
  document.querySelectorAll("input.numval").forEach((num) => {
    const sl = $(num.id.replace(/-val$/, ""));
    if (!sl || sl.type !== "range") return;
    // Live: feed each keystroke through to the slider (the slider clamps to min/max)
    // and fire its input handlers so the image updates as you type.
    num.addEventListener("input", () => {
      if (num.value === "") return;             // mid-edit empty field — wait
      sl.value = num.value;                     // range element clamps to its own bounds
      sl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    // On commit (blur / Enter): snap the field to the slider's clamped, stepped value.
    num.addEventListener("change", () => { num.value = sl.value; updateSliderAria(sl.id); });
    num.addEventListener("keydown", (e) => { if (e.key === "Enter") num.blur(); });
  });
}

// Tabbed control strip: one pane (Setup / Contrast / Quality / Learn) visible at a
// time; the active tab is remembered per-device.
const TAB_LS = "mrisim_tab";
function showTab(sec) {
  document.querySelectorAll(".tabs button[data-tab]").forEach((b) => {
    const on = b.dataset.tab === sec;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".pane[data-sec]").forEach((p) => { p.hidden = p.dataset.sec !== sec; });
  try { localStorage.setItem(TAB_LS, sec); } catch (e) { /* private mode */ }
}
function setupTabs() {
  document.querySelectorAll(".tabs button[data-tab]").forEach((b) =>
    b.addEventListener("click", () => showTab(b.dataset.tab)));
  let sec = "setup";
  try { sec = localStorage.getItem(TAB_LS) || sec; } catch (e) { /* private mode */ }
  if (!document.querySelector(`.pane[data-sec="${sec}"]`)) sec = "setup";
  showTab(sec);
}

// Presets rail: one button per preset, proxying the hidden #preset select — the
// select stays the single source of truth (presets apply through its change event,
// and a manual tweak resetting it to "" reads as Custom here).
// Region a preset belongs to, from its name prefix — mirrors the engine's
// get_preset_region() so the rail groups the way the protocol list is authored.
const PRESET_REGION_PREFIX = [
  ["Abdomen", "Abdomen"], ["Spine", "Spine"], ["Pelvis", "Pelvis"], ["Knee", "Knee"],
  ["Torso", "Torso"], ["Cardiac", "Cardiac"], ["MRCP", "Abdomen"],
  ["Brain", "Brain"], ["DWI", "Brain"], ["ADC", "Brain"], ["DTI", "Brain"],
  ["TOF", "Brain"], ["fMRI", "Brain"],
];
function presetRegion(name) {
  const hit = PRESET_REGION_PREFIX.find(([p]) => name.startsWith(p));
  return hit ? hit[1] : "Other";
}
function addPresetRow(list, value, label) {
  const li = document.createElement("li");
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  b.addEventListener("click", () => {
    $("preset").value = value;
    $("preset").dispatchEvent(new Event("change"));
    syncPresetRail();
  });
  li.dataset.preset = value;
  li.appendChild(b);
  list.appendChild(li);
}
function buildPresetRail() {
  const list = $("preset-list");
  if (!list) return;
  let lastRegion = null;
  [...$("preset").options].forEach((o) => {
    if (!o.value) { addPresetRow(list, "", "Custom"); return; }   // custom state row (no section header)
    const region = presetRegion(o.value);
    if (region !== lastRegion) {                                  // section header before each region's first row
      const h = document.createElement("li");
      h.className = "rail-section";
      h.setAttribute("aria-hidden", "true");
      h.textContent = region;
      list.appendChild(h);
      lastRegion = region;
    }
    addPresetRow(list, o.value, o.value);
  });
  syncPresetRail();
}
function syncPresetRail() {
  const cur = $("preset").value;
  document.querySelectorAll("#preset-list li").forEach((li) =>
    li.classList.toggle("active", li.dataset.preset === cur));
}

// Floating inspector (#overlay-pop): hosts the chart/overlay panels over the image.
// Each wrap's [hidden] is still driven by its own checkbox handler; the popup just
// shows itself while any wrap is visible. Its ✕ switches those overlays off.
const OVERLAY_TOGGLES = {
  curvewrap: "curveshow", cmapwrap: "cmap", kspacewrap: "kspaceshow",
  b0mapwrap: "b0mapshow", gfactorwrap: "gfactorshow", psdwrap: "psdshow", mathwrap: "mathshow",
};
function setupOverlayPop() {
  const pop = $("overlay-pop");
  if (!pop) return;
  const sync = () => { pop.hidden = Object.keys(OVERLAY_TOGGLES).every((id) => $(id).hidden); };
  const obs = new MutationObserver(sync);
  Object.keys(OVERLAY_TOGGLES).forEach((id) => obs.observe($(id), { attributes: true, attributeFilter: ["hidden"] }));
  $("overlay-pop-x").addEventListener("click", () => {
    Object.entries(OVERLAY_TOGGLES).forEach(([wrap, box]) => {
      if (!$(wrap).hidden && $(box).checked) { $(box).checked = false; $(box).dispatchEvent(new Event("change")); }
    });
  });
  makeOverlayDraggable(pop);
  makeOverlayResizable(pop);
  sync();
}

// Resize the inspector by its top-left grip. The popup sits at the image's
// bottom-right, so the room to grow is up/left: we pin the bottom-right corner
// (switching to a right/bottom anchor) and grow width/height toward the cursor.
// Bounds come from CSS (min/max-width/height); MARGIN keeps it off the edges.
function makeOverlayResizable(pop) {
  const grip = pop.querySelector(".op-resize");
  if (!grip) return;
  const MIN_W = 240, MIN_H = 140, MARGIN = 8;
  let sizing = false, fixedR = 0, fixedB = 0;
  const onDown = (e) => {
    const host = pop.offsetParent || document.documentElement;
    const hr = host.getBoundingClientRect(), pr = pop.getBoundingClientRect();
    fixedR = pr.right - hr.left; fixedB = pr.bottom - hr.top;   // pin bottom-right
    pop.style.left = "auto"; pop.style.top = "auto";
    pop.style.right = (hr.width - fixedR) + "px"; pop.style.bottom = (hr.height - fixedB) + "px";
    sizing = true; e.preventDefault(); e.stopPropagation();
    try { grip.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
  };
  const onMove = (e) => {
    if (!sizing) return;
    const host = pop.offsetParent || document.documentElement;
    const hr = host.getBoundingClientRect();
    const cx = e.clientX - hr.left, cy = e.clientY - hr.top;
    pop.style.width = clampN(fixedR - cx, MIN_W, Math.max(MIN_W, fixedR - MARGIN)) + "px";
    pop.style.height = clampN(fixedB - cy, MIN_H, Math.max(MIN_H, fixedB - MARGIN)) + "px";
  };
  const onUp = (e) => { sizing = false; try { grip.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ } };
  grip.addEventListener("pointerdown", onDown);
  grip.addEventListener("pointermove", onMove);
  grip.addEventListener("pointerup", onUp);
  grip.addEventListener("pointercancel", onUp);
}

// Drag the inspector by its header to move it off the image's baked annotations.
// Positioned via left/top (switching off the default right/bottom anchor), clamped
// to the viewport so it can't be dragged out of reach.
function makeOverlayDraggable(pop) {
  const head = pop.querySelector(".op-head");
  if (!head) return;
  let dragging = false, dx = 0, dy = 0;
  const onDown = (e) => {
    if (e.target.closest("button")) return;            // the ✕ isn't a drag handle
    const host = pop.offsetParent || document.documentElement;
    const hr = host.getBoundingClientRect(), pr = pop.getBoundingClientRect();
    dx = e.clientX - pr.left; dy = e.clientY - pr.top;
    pop.style.right = "auto"; pop.style.bottom = "auto";
    pop.style.left = (pr.left - hr.left) + "px"; pop.style.top = (pr.top - hr.top) + "px";
    dragging = true; head.setPointerCapture(e.pointerId); e.preventDefault();
  };
  const onMove = (e) => {
    if (!dragging) return;
    const host = pop.offsetParent || document.documentElement;
    const hr = host.getBoundingClientRect();
    const maxL = hr.width - pop.offsetWidth, maxT = hr.height - pop.offsetHeight;
    pop.style.left = clampN(e.clientX - hr.left - dx, 0, Math.max(0, maxL)) + "px";
    pop.style.top = clampN(e.clientY - hr.top - dy, 0, Math.max(0, maxT)) + "px";
  };
  const onUp = () => { dragging = false; };
  head.addEventListener("pointerdown", onDown);
  head.addEventListener("pointermove", onMove);
  head.addEventListener("pointerup", onUp);
  head.addEventListener("pointercancel", onUp);
}

// Control search/filter: type to show only matching rows — across every tab at
// once (panes and columns without a hit hide); clearing restores the active tab.
function setupSearch() {
  const box = $("ctrl-find"), clear = $("ctrl-find-x"), empty = $("ctrl-find-empty");
  if (!box) return;
  const colRows = (c) => c.querySelectorAll(":scope > label, :scope > p, :scope > div, :scope > button");
  const run = () => {
    const term = box.value.trim().toLowerCase();
    clear.hidden = term === "";
    if (!term) {
      document.querySelectorAll(".pane[data-sec]").forEach((p) => {
        p.querySelectorAll(".col").forEach((c) => {
          c.style.display = "";
          colRows(c).forEach((r) => { r.style.display = ""; });
        });
      });
      document.body.classList.remove("filtering");
      showTab(document.querySelector(".tabs button.on")?.dataset.tab || "setup");
      empty.hidden = true;
      return;
    }
    document.body.classList.add("filtering");
    let anyHit = false;
    document.querySelectorAll(".pane[data-sec]").forEach((p) => {
      let paneHit = false;
      p.querySelectorAll(".col").forEach((c) => {
        const head = (c.querySelector(".subhead")?.textContent || "").toLowerCase();
        const headHit = head.includes(term);
        let colHit = headHit;
        colRows(c).forEach((r) => {
          const hit = headHit || r.textContent.toLowerCase().includes(term);
          r.style.display = hit ? "" : "none";
          if (hit) colHit = true;
        });
        c.style.display = colHit ? "" : "none";
        if (colHit) paneHit = true;
      });
      p.hidden = !paneHit;
      if (paneHit) anyHit = true;
    });
    empty.hidden = anyHit;
  };
  box.addEventListener("input", run);
  clear.addEventListener("click", () => { box.value = ""; run(); box.focus(); });
  box.addEventListener("keydown", (e) => { if (e.key === "Escape" && box.value) { box.value = ""; run(); } });
}

// A short human label for a compare panel: pathology · sequence (· +Gd).
function captionFor(payload) {
  const bits = [];
  if (payload.pathology && PATHOLOGY_LABEL[payload.pathology]) bits.push(PATHOLOGY_LABEL[payload.pathology]);
  if (payload.params?.sequence) bits.push(payload.params.sequence);
  if (payload.params?.contrast_enabled) bits.push("+Gd");
  return bits.join(" · ");
}

// The on-image compare caption shows only what the image doesn't already bake in
// (pathology, +Gd) — the sequence is already annotated top-left on every panel —
// so in the common case it's empty and the overlay hides, avoiding any collision
// with the corner annotations.
function captionExtras(payload) {
  const bits = [];
  if (payload.pathology && PATHOLOGY_LABEL[payload.pathology]) bits.push(PATHOLOGY_LABEL[payload.pathology]);
  if (payload.params?.contrast_enabled) bits.push("+Gd");
  return bits.join(" · ");
}

function showDelta(mA, mB) {
  const arrow = (a, b) => (b > a ? "↑" : b < a ? "↓" : "=");
  const pct = (a, b) => (a ? Math.round(Math.abs(b - a) / a * 100) : 0);
  const cnr = (m) => Math.abs(m.snr_wm - m.snr_gm);
  const snr = (m) => m.snr_wm || m.snr || 0;          // brain WM, else generic tissue SNR
  const cnrPart = (mA.snr_wm || mB.snr_wm)            // CNR is brain-only
    ? `CNR ${arrow(cnr(mA), cnr(mB))} ${pct(cnr(mA), cnr(mB))}% · ` : "";
  $("abdelta").innerHTML =
    `B vs A — SNR ${arrow(snr(mA), snr(mB))} ${pct(snr(mA), snr(mB))}% · ` +
    cnrPart +
    `time ${arrow(mA.scan_time, mB.scan_time)} ${pct(mA.scan_time, mB.scan_time)}%`;
}

// --- Window/level drag on the main image ------------------------------------ //
// Window/level is applied INSTANTLY client-side while dragging: the current
// image is re-windowed with a CSS filter (no server round-trip), then one
// accurate server render lands on release. The transform from the baseline the
// image was rendered at (w0,l0) to the live (winW,winL) is linear, y = a·x + b
// with a = w0/winW, b = ((l0-w0/2)-(winL-winW/2))/winW, realised as
// brightness(bf)·contrast(cf): cf = 1−2b, bf = a/cf.
function wlFilter(w0, l0) {
  const a = w0 / winW;
  const b = ((l0 - w0 / 2) - (winL - winW / 2)) / winW;
  const cf = Math.min(8, Math.max(0.05, 1 - 2 * b));
  const bf = Math.min(8, Math.max(0, a / cf));
  return `brightness(${bf}) contrast(${cf})`;
}

function wireWindowLevel() {
  const imgA = $("mainImage"), imgB = $("mainImageB");
  let dragging = false, lx = 0, ly = 0, w0 = 1, l0 = 0.5;
  const startWL = (e) => {
    if (measureMode !== "off") return;   // measuring owns the drag (disabled in compare)
    dragging = true; lx = e.clientX; ly = e.clientY;
    w0 = winW; l0 = winL;              // baseline the current image was rendered at
    e.preventDefault();
  };
  imgA.addEventListener("pointerdown", startWL);
  imgB.addEventListener("pointerdown", startWL);   // grab either side in compare
  window.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    winW = Math.min(3, Math.max(0.05, winW + (e.clientX - lx) * 0.004));
    winL = Math.min(1, Math.max(0, winL - (e.clientY - ly) * 0.003));
    lx = e.clientX; ly = e.clientY;
    const f = wlFilter(w0, l0);            // instant preview, no server call
    imgA.style.filter = f;
    if (compareMode) imgB.style.filter = f;   // window both sides together
  });
  const endWL = () => {
    if (!dragging) return;
    dragging = false;
    schedule();                            // one accurate render at the final W/L (both sides)
  };
  window.addEventListener("pointerup", endWL);
  window.addEventListener("pointercancel", endWL);
  const reset = () => { winW = 1.0; winL = 0.5; schedule(); };
  imgA.addEventListener("dblclick", reset);
  imgB.addEventListener("dblclick", reset);
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

const clampN = (v, a, b) => Math.max(a, Math.min(b, v));
// Magnet a dragged oblique angle onto a common value (every 15° up to ±90).
const snapAngle = (v) => {
  for (const t of [0, 15, 30, 45, 60, 75, 90, -15, -30, -45, -60, -75, -90]) if (Math.abs(v - t) <= 2.5) return t;
  return v;
};
function panelAt(f) {
  for (const p of scoutPanels) {
    const [l, t, r, b] = p.box;
    if (f.fx >= l && f.fx <= r && f.fy >= t && f.fy <= b) return p;
  }
  return null;
}
function panelLocal(p, f) {            // 0..1 within the panel (y from top)
  const [l, t, r, b] = p.box;
  return { px: (f.fx - l) / (r - l), py: (f.fy - t) / (b - t) };
}
function bandLocal(p) {                // panel-local position of the slice band line
  const s = +$("slice").value;
  if (p.map === "row") return 1 - s / (p.n - 1);          // y (origin at bottom)
  const col = p.flip ? (p.n - 1 - s) : s;
  return col / (p.n - 1);                                  // x
}
// Perpendicular distance from a point to the segment a→b (all in [0,1] fractions).
function segDist(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy || 1e-9;
  let t = ((px - a[0]) * dx + (py - a[1]) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy));
}

// Map a localizer drag mode to a CSS cursor, so hovering shows what's grabbable.
function cursorFor(mode) {
  return {
    satmove: "move", satangle: "grab", satangle2: "grab", recenter: "move",
    resize: "nwse-resize", oblique: "grab", slice: "ns-resize",
  }[mode] || "crosshair";
}

// Hit-test the saturation band on whichever panel it's drawn: near an end handle →
// angle it ('satangle' in-plane on the acquired panel, 'satangle2' cross-plane on the
// cross panel — sb.amode says which); inside the slab body → 'satmove'. loc is
// panel-local (0..1). All geometry is the projected slab, so it tracks any orientation.
function satbandHit(p, loc) {
  const sb = p.satband;
  if (!sb || !sb.e1) return null;
  const dist = (e) => Math.hypot(loc.px - e[0], loc.py - e[1]);
  if (dist(sb.e1) < 0.06 || dist(sb.e2) < 0.06)
    return sb.amode === "angle2" ? "satangle2" : "satangle";
  let dx = sb.e2[0] - sb.c[0], dy = sb.e2[1] - sb.c[1];
  const len = Math.hypot(dx, dy) || 1; dx /= len; dy /= len;
  const vx = loc.px - sb.c[0], vy = loc.py - sb.c[1];
  const along = vx * dx + vy * dy, perp = Math.abs(-vx * dy + vy * dx);
  return (perp <= sb.half_t + 0.02 && Math.abs(along) <= len) ? "satmove" : null;
}

// Interactive localizer: drag the FOV box to resize, the box interior (or click
// elsewhere on the acquired panel) to recenter the in-plane FOV, the slice band
// on a cross panel to angle the plane (oblique), the saturation band to move /
// angle it, or elsewhere to move the slice.
function wireScout() {
  const img = $("scoutImage");
  img.style.cursor = "crosshair";
  let drag = null;

  const start = (f) => {
    const p = panelAt(f); if (!p) return null;
    const loc = panelLocal(p, f);
    const sm = satbandHit(p, loc);            // sat band is grabbable on any panel it's on
    if (sm === "satangle2") {                 // grab a cross-panel end → swing to angle
      const cc = p.satband.cc;
      return { mode: sm, p, prevA: Math.atan2(loc.py - cc[1], loc.px - cc[0]),
               curAngle: +$("satangle2").value };
    }
    if (sm) return { mode: sm, p };
    if (p.role === "acq") {
      const fb = p.fov_box, cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
      const edge = Math.max(Math.abs(loc.px - cx) / (fb[2] / 2 || 1),
                            Math.abs(loc.py - cy) / (fb[3] / 2 || 1));
      return { mode: edge > 0.72 ? "resize" : "recenter", p };
    }
    // Grab the ACTUAL slice band (which may already be oblique) to angle; tap elsewhere
    // to move the slice. The band geometry (p.band) is in y-up / sagittal-flipped panel
    // fractions, so convert the click to match. Using the real band — not the straight
    // bandLocal position — means a tilted band can still be re-grabbed and angled further
    // (the old test missed it once it rotated → "angle once, then stuck").
    if (p.angle && p.band) {
      const gx = p.flip ? 1 - loc.px : loc.px, gy = 1 - loc.py;
      if (segDist(gx, gy, p.band[0], p.band[1]) < 0.12) {
        return { mode: "oblique", p, l0: loc, tilt0: planTilt, rot0: planRot };
      }
    } else if (p.angle) {                       // fallback: straight-band position
      const bp = bandLocal(p);
      const near = p.map === "row" ? Math.abs(loc.py - bp) < 0.16 : Math.abs(loc.px - bp) < 0.16;
      if (near) return { mode: "oblique", p, l0: loc, tilt0: planTilt, rot0: planRot };
    }
    return { mode: "slice", p };
  };

  const apply = (f) => {
    if (!drag) return;
    const p = drag.p, loc = panelLocal(p, f);
    if (drag.mode === "slice") {
      let s = p.map === "row" ? (1 - loc.py) * (p.n - 1)
                              : (p.flip ? (1 - loc.px) : loc.px) * (p.n - 1);
      s = clampN(Math.round(s), 0, p.n - 1);
      $("slice").value = s; $("slice-val").value = s;
    } else if (drag.mode === "recenter") {           // set in-plane FOV centre
      const u = (p.ip_dir === "x" ? loc.px : loc.py) - 0.5;
      planOff = p.ip_sign * u * p.ip_axis_len;
    } else if (drag.mode === "resize") {             // grow/shrink the FOV box
      const fb = p.fov_box, cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
      const half = Math.max(Math.abs(loc.px - cx), Math.abs(loc.py - cy));
      const pct = Math.round(clampN(2 * half, 0.3, 1.0) * 100 / 5) * 5;
      $("ipfov").value = pct; $("ipfov-val").value = pct;
    } else if (drag.mode === "satmove") {            // slide the band along its normal
      const sb = drag.p.satband, a = sb.p0, b = sb.p1;   // p0→p1 = the travel line
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const t = ((loc.px - a[0]) * dx + (loc.py - a[1]) * dy) / ((dx * dx + dy * dy) || 1);
      const pos = clampN(Math.round(t * 100 / 5) * 5, 0, 100);
      $("satpos").value = pos; $("satpos-val").value = pos;
    } else if (drag.mode === "satangle2") {          // swing the cross-panel band end
      const cc = drag.p.satband.cc;
      const a1 = Math.atan2(loc.py - cc[1], loc.px - cc[0]);
      let dd = (a1 - drag.prevA) * 180 / Math.PI;
      if (dd > 180) dd -= 360; else if (dd < -180) dd += 360;
      // Negate so the band turns the way you pull (not the opposite).
      drag.curAngle = clampN(drag.curAngle - dd, -90, 90);
      drag.prevA = a1;
      const v = Math.round(drag.curAngle / 5) * 5;
      $("satangle2").value = v; $("satangle2-val").value = v;
    } else if (drag.mode === "satangle") {           // angle the saturation band
      const sb = drag.p.satband, W = sb.wh[0], H = sb.wh[1];
      // Undo the panel's display aspect to recover the true (data-space) angle.
      let ang = Math.atan2(-(loc.py - sb.c[1]) * H, (loc.px - sb.c[0]) * W) * 180 / Math.PI;
      if (ang > 90) ang -= 180; else if (ang < -90) ang += 180;
      ang = clampN(Math.round(ang / 5) * 5, -90, 90);
      $("satangle").value = ang; $("satangle-val").value = ang;
    } else if (drag.mode === "oblique") {            // angle the plane off-axis
      // Drag direction follows the band orientation (a horizontal band angles with
      // a vertical drag); *which* angle it sets is the panel's own DOF (p.angle),
      // so the two cross panels give independent tilt + rot — full double-oblique.
      // Sign chosen so the plane angles the same way you drag (not the opposite).
      const d = (p.map === "row" ? (loc.py - drag.l0.py) : (drag.l0.px - loc.px)) * 90;
      // Raw (un-snapped) while dragging so the plane tracks the cursor smoothly; the
      // snap-to-15° only fires on release (live snapping made it stick / jump at 0).
      if (p.angle === "tilt") planTilt = clampN(drag.tilt0 + d, -90, 90);
      else planRot = clampN(drag.rot0 + d, -90, 90);
    }
    scheduleScoutDrag();   // throttled: the localizer follows the cursor during the drag
  };

  img.addEventListener("pointerdown", (e) => {
    const f = imgFraction(img, e.clientX, e.clientY);
    if (!f) return;
    drag = start(f); apply(f); e.preventDefault();
  });
  window.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const f = imgFraction(img, e.clientX, e.clientY);
    if (f) apply(f);
  });
  img.addEventListener("pointermove", (e) => {       // hover: show what's grabbable
    if (drag) return;
    const f = imgFraction(img, e.clientX, e.clientY);
    img.style.cursor = cursorFor(f ? (start(f) || {}).mode : null);
  });
  const endScoutDrag = () => {
    if (!drag) return;
    if (drag.mode === "oblique") {     // snap to 0 / ±15 / ±30 / ±45 only on release
      planTilt = snapAngle(planTilt); planRot = snapAngle(planRot);
    }
    drag = null;
    schedule();                        // one accurate render at the settled prescription
  };
  window.addEventListener("pointerup", endScoutDrag);
  window.addEventListener("pointercancel", endScoutDrag);
  img.addEventListener("dblclick", (e) => {          // reset to straight / full FOV
    planOff = 0; planTilt = 0; planRot = 0;
    $("ipfov").value = 100; $("ipfov-val").value = 100;
    schedule(); e.preventDefault();
  });
}

// --- Render orchestration (async, via the worker) --------------------------- //
let timer = null, pending2 = false, running = false;
function schedule() {
  if (!booted) return;
  if (!applyingPreset) { $("preset").value = ""; syncPresetRail(); }   // manual tweak → "custom"
  updateSeqHelp();                                // keep the clinical blurb current
  clearTimeout(timer);
  timer = setTimeout(render, 90);    // debounce; the worker keeps the UI free
}

// During an interactive scout drag we THROTTLE renders (~9 fps) instead of debouncing.
// The debounce above keeps deferring while the pointer moves, so the (server-baked)
// localizer band/box would freeze mid-drag until you stopped — making angling feel stuck.
// This renders steadily during the drag, plus a final time when motion settles.
let _dragRenderAt = 0;
function scheduleScoutDrag() {
  if (!booted) return;
  if (!applyingPreset) { $("preset").value = ""; syncPresetRail(); }
  const now = Date.now(), gap = now - _dragRenderAt;
  clearTimeout(timer);
  if (gap >= 110) { _dragRenderAt = now; render(); }
  else timer = setTimeout(() => { _dragRenderAt = Date.now(); render(); }, 110 - gap);
}

// --- 3-D reconstruction (MPR / MIP / oblique from the acquired slab) -------- //
let reconDims = null;                  // last block dims, for fraction→voxel centre
const reconActive = () => $("reconshow").checked && $("acq3d").checked;

function reconCenterVoxel() {
  if (!reconDims) return null;
  const f = (id, n) => Math.round((+$(id).value / 100) * (n - 1));
  return [f("rz", reconDims.nz), f("ry", reconDims.ny), f("rx", reconDims.nx)];
}

function syncReconMode() {
  const m = $("reconmode").value;
  $("recon-mpr").hidden = m !== "mpr";
  $("recon-mip").hidden = m !== "mip";
  $("recon-rmip").hidden = m !== "rmip";
  $("recon-oblique").hidden = m !== "oblique";
}

async function runRecon() {
  if (!reconActive()) return;
  clearReconMeasure();   // panels are being rebuilt — drop any stale measure overlay
  const p = collectPayload();
  const mode = $("reconmode").value;
  p.mode = mode;
  const c = reconCenterVoxel();
  if (c) p.center = c;
  if (mode === "mip") { p.mip_plane = $("mipplane").value; p.mip_thickness = +$("mipthick").value; p.mip_mode = $("mipmode").value; p.mip_center_frac = +$("mipcenter").value / 100; }
  else if (mode === "rmip") { p.azimuth = +$("raz").value; p.elevation = +$("rel").value; }
  else if (mode === "oblique") { p.tilt = +$("rtilt").value; p.rot = +$("rrot").value; p.base = "axial"; }
  document.body.classList.add("busy");
  try {
    const r = await call("reconstruct", p);
    if (!r || !r.ok) {
      $("recon-msg").hidden = false;
      $("recon-msg").textContent = (r && r.error) || "reconstruction failed";
      return;
    }
    $("recon-msg").hidden = true;
    reconDims = r.dims;
    if (mode === "mpr") {
      $("recon-tri").hidden = false; $("recon-single").hidden = true;
      $("reconAxial").src = r.panels.axial;
      $("reconCoronal").src = r.panels.coronal;
      $("reconSagittal").src = r.panels.sagittal;
      if (r.panels.overview) $("reconOverview").src = r.panels.overview;
    } else {
      $("recon-tri").hidden = true; $("recon-single").hidden = false;
      $("reconMain").src = r.panels.main;
    }
  } finally { document.body.classList.remove("busy"); }
}

// Download the current reconstruction as PNG — the single panel for MIP/oblique/
// rotating modes, or the three MPR reformats as separate files.
function downloadRecon() {
  const dl = (src, name) => {
    if (!src || !src.startsWith("data:image")) return;
    const a = document.createElement("a"); a.href = src; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  };
  if ($("reconmode").value === "mpr") {
    // All four shown panels: the three reformats + the 3D MIP overview.
    for (const p of ["Axial", "Coronal", "Sagittal", "Overview"]) dl($("recon" + p).src, `mrisim_recon_mpr_${p.toLowerCase()}.png`);
  } else {
    const m = $("reconmode").value;
    const tag = m === "mip" ? `${$("mipmode").value}_${$("mipplane").value}` : m;
    dl($("reconMain").src, `mrisim_recon_${tag}.png`);
  }
}

// Rotating-MIP cine: pre-render a 360° stack of frames once, then cycle them
// client-side for a smooth spin (no per-frame server round-trip).
const reconCine = { timer: null, frames: [], i: 0 };
function stopCine() {
  if (reconCine.timer) { clearInterval(reconCine.timer); reconCine.timer = null; }
  $("recon-spin").textContent = "▶ Spin cine";
}
async function toggleCine() {
  if (reconCine.timer) { stopCine(); return; }
  const p = collectPayload();
  p.n_frames = 12; p.elevation = +$("rel").value;
  $("recon-spin").textContent = "Building cine…";
  const r = await call("reconstructCine", p);
  if (!r || !r.ok || !(r.frames || []).length) { stopCine(); return; }
  reconCine.frames = r.frames; reconCine.i = 0;
  $("recon-single").hidden = false; $("recon-tri").hidden = true;
  $("recon-spin").textContent = "■ Stop";
  reconCine.timer = setInterval(() => {
    $("reconMain").src = reconCine.frames[reconCine.i % reconCine.frames.length];
    reconCine.i++;
  }, 120);
}

function wireRecon() {
  $("recon-download").addEventListener("click", downloadRecon);
  $("recon-spin").addEventListener("click", toggleCine);
  $("reconshow").addEventListener("change", () => {
    const on = reconActive();
    stopCine();
    $("reconctl").hidden = !on;
    $("reconwrap").hidden = !on;
    if (on) runRecon();
  });
  $("reconmode").addEventListener("change", () => { stopCine(); syncReconMode(); runRecon(); });
  ["rz", "ry", "rx", "mipthick", "mipcenter", "raz", "rel", "rtilt", "rrot"].forEach((id) =>
    $(id).addEventListener("input", () => { stopCine(); const o = $(id + "-val"); if (o) o.value = $(id).value; runRecon(); }));
  $("mipplane").addEventListener("change", runRecon);
  $("mipmode").addEventListener("change", runRecon);
  // Click any MPR panel to move the crosshair (and the other two planes). The
  // panels render edge-to-edge, so the element fraction is the data fraction;
  // origin is bottom-left, and the sagittal panel is L–R flipped (see _recon_png).
  const setPct = (id, v) => { $(id).value = Math.round(Math.max(0, Math.min(100, v))); const o = $(id + "-val"); if (o) o.value = $(id).value; };
  const panelClick = (panel) => (e) => {
    if (measureMode !== "off") return;   // a measure tool is active → measure, don't navigate
    const r = e.currentTarget.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const fx = (e.clientX - r.left) / r.width;
    const fyt = (e.clientY - r.top) / r.height;       // from top
    if (fx < 0 || fx > 1 || fyt < 0 || fyt > 1) return;
    if (panel === "axial") { setPct("rx", fx * 100); setPct("ry", (1 - fyt) * 100); }
    else if (panel === "coronal") { setPct("rx", fx * 100); setPct("rz", (1 - fyt) * 100); }
    else { setPct("ry", (1 - fx) * 100); setPct("rz", (1 - fyt) * 100); }   // sagittal (flipped)
    runRecon();
  };
  $("reconAxial").addEventListener("click", panelClick("axial"));
  $("reconCoronal").addEventListener("click", panelClick("coronal"));
  $("reconSagittal").addEventListener("click", panelClick("sagittal"));
  syncReconMode();
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
      const reqSlice = +$("slice").value;   // guard against stale slice clobber
      const B = collectPayload();
      // Both sides share the live window/level so the contrast comparison is fair
      // and dragging either image re-windows both.
      const A = protocolA ? { ...protocolA, window_width: winW, window_level: winL } : B;
      const resA = await call("render", A);
      const resB = await call("render", B);
      $("mainImage").src = resA.image;
      $("mainImageB").src = resB.image;
      $("mainImage").alt = `Protocol A (simulated): ${captionFor(A) || A.params?.sequence || "MR image"}`;
      $("mainImageB").alt = `Protocol B (simulated): ${captionFor(B) || B.params?.sequence || "MR image"}`;
      $("mainImage").style.filter = "";        // drop the live drag-preview filter
      $("mainImageB").style.filter = "";
      $("curveImage").src = resB.curve;
      setMetrics(resB);
      syncSlice(resB, reqSlice);
      showDelta(resA.metrics, resB.metrics);
      // Label each side with what the baked annotation doesn't cover (e.g. "Abscess").
      for (const [id, p] of [["capA", A], ["capB", B]]) {
        const t = captionExtras(p);
        $(id).textContent = t; $(id).hidden = !t;
      }
    } else {
      const reqSlice = +$("slice").value;   // guard against stale slice clobber
      applyResult(await call("render", collectPayload()), reqSlice);
    }
    if ($("fovplan").checked) {
      const p = collectPayload();
      const s = await call("scout", {
        region: p.region, orientation: p.orientation, slice_idx: p.slice_idx,
        params: p.params, inplane_fov_pct: p.inplane_fov_pct ?? 100,
        inplane_off: planOff, tilt: planTilt, rot: planRot,
        satband_enabled: p.satband_enabled, satband_pos: p.satband_pos,
        satband_width: p.satband_width, satband_angle: p.satband_angle, satband_angle2: p.satband_angle2,
      });
      $("scoutImage").src = s.scout;
      scoutPanels = s.panels || [];
      window.scoutPanels = scoutPanels;   // exposed for the headless smoke's drag targeting
      $("satwidth-mm").textContent =
        (s.satband_mm != null) ? "≈ " + Math.round(s.satband_mm) + " mm" : "";
      // Sat band isn't applied on the oblique path (the slab assumes orthogonal slice
      // geometry) — warn rather than silently dropping it, like the desktop does.
      const satOblique = $("satband").checked &&
        (Math.abs(planTilt) > 0.5 || Math.abs(planRot) > 0.5);
      $("oblique-readout").textContent =
        `Oblique tilt ${planTilt.toFixed(0)}° · rot ${planRot.toFixed(0)}°  —  drag a cross-panel band to angle the plane; FOV box = resize/move; sat band = drag to move, grab an end to angle (on any plane it shows); dbl-click = reset`
        + (satOblique ? "  ·  ⚠ sat band not applied on oblique acquisitions" : "");
    }
    if (reconActive()) await runRecon();   // keep the reconstruction live with the slab
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

function syncSlice(res, reqSlice) {
  $("slice").max = res.max_slice;
  // Don't clobber a slice the user changed (keyboard/wheel/scout) while this
  // async render was in flight — only correct the slider when it still holds the
  // value this render was issued for (e.g. the server clamped it).
  if (reqSlice !== undefined && +$("slice").value !== reqSlice) { reflectSlice(); return; }
  if (+$("slice").value !== res.slice_idx) $("slice").value = res.slice_idx;
  $("slice-val").value = res.slice_idx;
  updateSliderAria("slice");
  reflectSlice();
}

function setMetrics(res) {
  const m = res.metrics;
  $("x-res").textContent = m.resolution.toFixed(2) + " mm";
  $("x-scan").textContent = fmtTime(m.scan_time);
  // SNR: brain shows WM / GM / CNR; body regions (no white/grey matter) show a single
  // representative tissue SNR (CNR is brain-only).
  const brain = m.snr_wm > 0;
  $("x-snr-cap").textContent = brain ? "SNR (WM / GM)" : "SNR";
  $("x-cnr-cap").textContent = brain ? "CNR (WM–GM)" : "CNR";
  $("m-snrwm-cap").textContent = brain ? "SNR (WM)" : "SNR";
  $("x-snr").textContent = brain ? `${m.snr_wm.toFixed(1)} / ${m.snr_gm.toFixed(1)}` : (m.snr || 0).toFixed(1);
  $("x-cnr").textContent = brain ? Math.abs(m.snr_wm - m.snr_gm).toFixed(1) : "—";
  $("x-sar").textContent = m.sar_head.toFixed(1) + " W/kg" + (m.sar_exceeds ? " ⚠" : "");
  // When over the SAR limit, spell out which parameters to change (and to what) to
  // get back under. Computed from the displayed sar_head so it can't drift from it.
  const sg = $("sar-guidance");
  if (m.sar_exceeds && window.SarGuidance) {
    const g = window.SarGuidance.sarGuidance({
      flip_angle: +$("fa").value, TR: +$("tr").value, sequence: $("sequence").value, sar_head: m.sar_head });
    const fixes = [];
    if (g.maxSafeFa != null) fixes.push(`lower flip angle to ≤${g.maxSafeFa}°`);
    if (g.minSafeTr != null) fixes.push(`raise TR to ≥${g.minSafeTr} ms`);
    if (g.lowerSeqOptions.length) fixes.push(`switch to ${g.lowerSeqOptions.join(" or ")}`);
    if (fixes.length) {
      sg.textContent = `SAR ${m.sar_head.toFixed(1)} W/kg is over the ${g.limit} W/kg limit. Any one of these brings it under: ${fixes.join("; ")}.`;
      sg.hidden = false;
    } else { sg.textContent = ""; sg.hidden = true; }
  } else { sg.textContent = ""; sg.hidden = true; }
  $("m-scan").textContent = fmtTime(m.scan_time);
  $("m-snrwm").textContent = (brain ? m.snr_wm : (m.snr || 0)).toFixed(1);
  const weight = weighting($("sequence").value, +$("tr").value, +$("te").value);
  $("m-weight").textContent = weight;
  // Announce the result to assistive tech (the chips update silently otherwise).
  $("a11y-metrics").textContent =
    `${weight}. Scan time ${fmtTime(m.scan_time)}. ${brain ? "SNR white matter" : "SNR"} ${$("m-snrwm").textContent}.`;
  if (!SEQ_SLOW_FIRST.has($("sequence").value)) $("hint").textContent = "";
  // 3D slab readout: what the partition count buys (isotropic resolution, total
  // slab coverage, and the √Nz SNR gain over a single 2D slice).
  if (m.is_3d) {
    $("slab-readout").textContent =
      `Isotropic ${m.partition_mm.toFixed(1)} mm · ${m.n_partitions} contiguous partitions`
      + ` · ${m.slab_mm.toFixed(0)} mm slab · √Nz SNR ≈ ${m.snr_3d_gain.toFixed(1)}× vs one 2D slice`;
  }
}

function applyResult(res, reqSlice) {
  $("mainImage").src = res.image;
  $("mainImage").alt = imageAlt();    // describe the current contrast / plane / slice for AT
  $("mainImage").style.filter = "";   // server image is correctly windowed; drop the live W/L preview filter
  $("curveImage").src = res.curve;
  probe = res.probe || null;          // aligned label map for the hover tissue readout
  if (probe) probe.bytes = Uint8Array.from(atob(probe.labels), (c) => c.charCodeAt(0));
  if (res.cmap) $("cmapImage").src = res.cmap;   // TR×TE contrast landscape
  if (res.kspace) $("kspaceImage").src = res.kspace;   // raw k-space (log magnitude)
  if (res.psd) $("psdImage").src = res.psd;            // pulse-sequence diagram
  if (res.b0map) $("b0mapImage").src = res.b0map;      // B0 off-resonance field
  if (res.gfactor) $("gfactorImage").src = res.gfactor; // parallel-imaging g-factor
  syncSlice(res, reqSlice);
  setMetrics(res);
  refreshMeasure();                   // keep a placed ruler/ROI aligned + live on the new image
  requestAnimationFrame(sizeSliceRail);   // match the rail to the image area (safe: absolute)
}

// After a new image lands, redraw any placed measurement (geometry is FOV-stable)
// and refresh an ROI's statistics against the new slice.
async function refreshMeasure() {
  if (!measureShape) return;
  requestAnimationFrame(() => drawMeasure(measureShape));   // re-place once the <img> has laid out
  if (measureShape.kind !== "roi") return;
  try {
    const res = await call("measure", { kind: "roi",
      points: [[measureShape.p0.fx, measureShape.p0.fy], [measureShape.p1.fx, measureShape.p1.fy]] });
    showMeasureResult(res);
  } catch (_e) { /* ignore races */ }
}

// Hover the main image to read the tissue + T1/T2/PD under the cursor (a
// client-side lookup into the per-render label map — no server round-trip).
function wireProbe() {
  const img = $("mainImage"), box = $("probe");
  img.addEventListener("mousemove", (e) => {
    if (compareMode || !probe || measureMode !== "off") { box.hidden = true; return; }
    const f = imgFraction(img, e.clientX, e.clientY);
    if (!f) { box.hidden = true; return; }
    const col = Math.max(0, Math.min(probe.w - 1, Math.round(f.fx * (probe.w - 1))));
    const row = Math.max(0, Math.min(probe.h - 1, Math.round((1 - f.fy) * (probe.h - 1))));
    const t = probe.tissues[probe.bytes[row * probe.w + col]];
    if (!t) { box.hidden = true; return; }
    box.textContent = `${t.name} · T1 ${Math.round(t.T1)} / T2 ${Math.round(t.T2)} ms · PD ${t.PD.toFixed(2)}`;
    box.hidden = false;
    if ($("mathshow").checked) $("math").innerHTML = mathHTML(t);   // "Show the math"
  });
  img.addEventListener("mouseleave", () => { box.hidden = true; });
}

// --- On-image measurement: ruler (mm) and ROI (mean / SD / SNR) -------------- //
// Fraction (over the image content) → pixel within #wrapA, accounting for the
// letterbox of object-fit and the image being centred in the wrap.
function fracToWrapPx(fx, fy) {
  const img = $("mainImage"), wr = $("wrapA").getBoundingClientRect();
  const r = img.getBoundingClientRect();
  const nAR = img.naturalWidth / img.naturalHeight, eAR = r.width / r.height;
  let cw, ch, ox, oy;
  if (eAR > nAR) { ch = r.height; cw = ch * nAR; ox = (r.width - cw) / 2; oy = 0; }
  else { cw = r.width; ch = cw / nAR; ox = 0; oy = (r.height - ch) / 2; }
  return { x: (r.left - wr.left) + ox + fx * cw, y: (r.top - wr.top) + oy + fy * ch };
}

function drawMeasure(shape) {
  const svg = $("measure-svg");
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  if (!shape) return;
  const NS = "http://www.w3.org/2000/svg";
  const a = fracToWrapPx(shape.p0.fx, shape.p0.fy), b = fracToWrapPx(shape.p1.fx, shape.p1.fy);
  if (shape.kind === "ruler") {
    const ln = document.createElementNS(NS, "line");
    ln.setAttribute("x1", a.x); ln.setAttribute("y1", a.y);
    ln.setAttribute("x2", b.x); ln.setAttribute("y2", b.y);
    ln.setAttribute("class", "m-line"); svg.appendChild(ln);
    for (const p of [a, b]) {
      const d = document.createElementNS(NS, "circle");
      d.setAttribute("cx", p.x); d.setAttribute("cy", p.y); d.setAttribute("r", 2.6);
      d.setAttribute("class", "m-end"); svg.appendChild(d);
    }
  } else {
    const el = document.createElementNS(NS, "ellipse");
    el.setAttribute("cx", (a.x + b.x) / 2); el.setAttribute("cy", (a.y + b.y) / 2);
    el.setAttribute("rx", Math.abs(b.x - a.x) / 2); el.setAttribute("ry", Math.abs(b.y - a.y) / 2);
    el.setAttribute("class", "m-roi"); svg.appendChild(el);
  }
}

function clearMeasure() {
  measureShape = null; measureDrag = null; drawMeasure(null); clearReconMeasure();
  $("measure-readout").textContent = measureMode === "off"
    ? "Pick Ruler or ROI, then drag on the image."
    : (measureMode === "ruler" ? "Drag a line across the image." : "Drag to place an ROI.");
}

function showMeasureResult(res) {
  const out = $("measure-readout");
  if (!res || !res.ok) { out.textContent = "—"; return; }
  if (res.kind === "ruler") out.innerHTML = `Distance <b>${res.mm.toFixed(1)} mm</b>`;
  else out.innerHTML = `ROI <b>${res.n}</b> px · mean <b>${res.mean.toFixed(3)}</b> · `
    + `SD <b>${res.sd.toFixed(3)}</b> · SNR <b>${res.snr.toFixed(1)}</b> · ${Math.round(res.area_mm2)} mm²`;
}

function wireMeasure() {
  const img = $("mainImage");
  img.addEventListener("pointerdown", (e) => {
    if (measureMode === "off" || compareMode) return;
    const f = imgFraction(img, e.clientX, e.clientY); if (!f) return;
    measureDrag = { p0: f, p1: f };
    e.preventDefault(); e.stopPropagation();
    drawMeasure({ kind: measureMode, ...measureDrag });
  });
  window.addEventListener("pointermove", (e) => {
    if (!measureDrag) return;
    measureDrag.p1 = imgFraction(img, e.clientX, e.clientY) || measureDrag.p1;
    drawMeasure({ kind: measureMode, ...measureDrag });
  });
  const endMeasure = async () => {
    if (!measureDrag) return;
    const shape = { kind: measureMode, ...measureDrag };
    measureShape = shape; measureDrag = null;
    drawMeasure(shape);
    try {
      const res = await call("measure", { kind: shape.kind,
        points: [[shape.p0.fx, shape.p0.fy], [shape.p1.fx, shape.p1.fy]] });
      showMeasureResult(res);
    } catch (_e) { /* a stale render can race; ignore */ }
  };
  window.addEventListener("pointerup", endMeasure);
  window.addEventListener("pointercancel", () => { measureDrag = null; });
  $("measuremode").querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => {
      $("measuremode").querySelectorAll("button").forEach((x) => {
        const on = x === btn;
        x.classList.toggle("on", on);
        x.setAttribute("aria-pressed", on);
      });
      measureMode = btn.dataset.m;
      $("wrapA").classList.toggle("measuring", measureMode !== "off");
      $("reconwrap").classList.toggle("measuring", measureMode !== "off");
      clearMeasure();
    }));
  $("measure-clear").addEventListener("click", clearMeasure);
  window.addEventListener("resize", () => { drawMeasure(measureShape); clearReconMeasure(); sizeSliceRail(); });
}

// --- Measure on the reconstruction panels (ruler / ROI on each reformat) ----- //
let reconMeasureDrag = null;   // { panel, img, p0:{fx,fy}, p1:{fx,fy} }

function drawReconMeasure(shape) {
  const svg = $("recon-measure-svg");
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  if (!shape || !shape.img || !shape.p0 || !shape.p1) return;
  const wrap = $("reconwrap").getBoundingClientRect();
  const pr = shape.img.getBoundingClientRect();
  svg.style.left = (pr.left - wrap.left) + "px";
  svg.style.top = (pr.top - wrap.top) + "px";
  svg.style.width = pr.width + "px";
  svg.style.height = pr.height + "px";
  svg.setAttribute("viewBox", `0 0 ${pr.width} ${pr.height}`);
  const NS = "http://www.w3.org/2000/svg";
  const a = { x: shape.p0.fx * pr.width, y: shape.p0.fy * pr.height };
  const b = { x: shape.p1.fx * pr.width, y: shape.p1.fy * pr.height };
  if (shape.kind === "ruler") {
    const ln = document.createElementNS(NS, "line");
    ln.setAttribute("x1", a.x); ln.setAttribute("y1", a.y);
    ln.setAttribute("x2", b.x); ln.setAttribute("y2", b.y);
    ln.setAttribute("class", "m-line"); svg.appendChild(ln);
    for (const p of [a, b]) {
      const d = document.createElementNS(NS, "circle");
      d.setAttribute("cx", p.x); d.setAttribute("cy", p.y); d.setAttribute("r", 2.6);
      d.setAttribute("class", "m-end"); svg.appendChild(d);
    }
  } else {
    const el = document.createElementNS(NS, "ellipse");
    el.setAttribute("cx", (a.x + b.x) / 2); el.setAttribute("cy", (a.y + b.y) / 2);
    el.setAttribute("rx", Math.abs(b.x - a.x) / 2); el.setAttribute("ry", Math.abs(b.y - a.y) / 2);
    el.setAttribute("class", "m-roi"); svg.appendChild(el);
  }
}

function clearReconMeasure() {
  reconMeasureDrag = null;
  const svg = $("recon-measure-svg");
  if (svg) while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function wireReconMeasure() {
  const PANELS = { reconAxial: "axial", reconCoronal: "coronal", reconSagittal: "sagittal",
                   reconOverview: "overview", reconMain: "main" };
  for (const id of Object.keys(PANELS)) {
    const el = $(id); if (!el) continue;
    el.addEventListener("pointerdown", (e) => {
      if (measureMode === "off") return;
      const f = imgFraction(el, e.clientX, e.clientY); if (!f) return;
      reconMeasureDrag = { panel: PANELS[id], img: el, p0: f, p1: f };
      e.preventDefault(); e.stopPropagation();
      drawReconMeasure({ kind: measureMode, ...reconMeasureDrag });
    });
  }
  window.addEventListener("pointermove", (e) => {
    if (!reconMeasureDrag) return;
    reconMeasureDrag.p1 = imgFraction(reconMeasureDrag.img, e.clientX, e.clientY) || reconMeasureDrag.p1;
    drawReconMeasure({ kind: measureMode, ...reconMeasureDrag });
  });
  window.addEventListener("pointerup", async () => {
    if (!reconMeasureDrag) return;
    const d = reconMeasureDrag;
    try {
      const res = await call("measure", { kind: measureMode, panel: d.panel,
        points: [[d.p0.fx, d.p0.fy], [d.p1.fx, d.p1.fy]] });
      showMeasureResult(res);
    } catch (_e) { /* a stale render can race; ignore */ }
  });
}

// Build the signal-equation HTML for the hovered tissue at the current protocol.
// The final S is the server's value (same equation as the picture); the symbolic
// + substituted lines are formatted client-side from the known TR/TE/TI/FA.
function mathHTML(t) {
  const seq = $("sequence").value;
  const TR = +$("tr").value, TE = +$("te").value, TI = +$("ti").value, FA = +$("fa").value;
  const T1 = Math.round(t.T1), T2 = Math.round(t.T2), T2s = Math.round(t.T2star ?? t.T2);
  const PD = t.PD.toFixed(2), e = (n, d) => `e<sup>−${Math.round(n)}/${d}</sup>`;
  const head = `<div class="m-tissue"><b>${t.name}</b> · T1 ${T1} · T2 ${T2} ms · PD ${PD} · ${seq}</div>`;
  let sym, sub;
  if (seq === "Gradient Echo" || seq === "Echo Planar (EPI)" || seq === "Susceptibility (SWI)") {
    sym = `S = PD·sinα·(1−e<sup>−TR/T1</sup>)⁄(1−cosα·e<sup>−TR/T1</sup>)·e<sup>−TE/T2*</sup>`;
    sub = `= ${PD}·sin${FA}°·(1−${e(TR, T1)})⁄(1−cos${FA}°·${e(TR, T1)})·${e(TE, T2s)}`;
  } else if (seq === "Inversion Recovery") {
    sym = `S = PD·|1−2e<sup>−TI/T1</sup>+e<sup>−TR/T1</sup>|·e<sup>−TE/T2</sup>`;
    sub = `= ${PD}·|1−2·e<sup>−${Math.round(TI)}/${T1}</sup>+${e(TR, T1)}|·${e(TE, T2)}`;
  } else if (seq === "Balanced SSFP") {
    sym = `S ≈ PD·sinα · (T2/T1-weighted balanced steady state)`;
    sub = "";
  } else {   // SE / FSE / qMRI / default
    const E1 = (1 - Math.exp(-TR / t.T1)).toFixed(2), E2 = Math.exp(-TE / t.T2).toFixed(2);
    sym = `S = PD·(1−e<sup>−TR/T1</sup>)·e<sup>−TE/T2</sup>`;
    sub = `= ${PD}·(1−${e(TR, T1)})·${e(TE, T2)} = ${PD}·${E1}·${E2}`;
  }
  return head + `<div class="m-eq">${sym}</div>` + (sub ? `<div class="m-sub">${sub}</div>` : "")
    + `<div class="m-res">signal S = <b>${t.S.toFixed(3)}</b></div>`;
}

// A descriptive alt for the reconstructed image so assistive tech conveys what's
// shown (contrast, plane, slice) instead of the static "reconstructed MR image".
function imageAlt() {
  const seq = $("sequence").value;
  const w = weighting(seq, +$("tr").value, +$("te").value);
  return `${w} ${curOrient()} MR image, slice ${$("slice").value} of ${$("slice").max} — simulated ${seq}`;
}

function weighting(seq, tr, te) {
  const map = {
    "Diffusion (DWI)": "Diffusion", "MR Angiography": "Flow", "fMRI (BOLD)": "T2* (BOLD)",
    "Perfusion (ASL)": "Perfusion", "Perfusion (Dynamic)": "Perfusion",
    "Quantitative (qMRI)": "Quantitative", "Echo Planar (EPI)": "T2* (EPI)",
    "Balanced SSFP": "T2/T1",
  };
  if (map[seq]) return map[seq];
  if (tr < 800 && te < 30) return "T1";
  if (tr > 2000 && te > 60) return "T2";
  if (tr > 2000 && te < 30) return "PD";
  return "Mixed";
}
