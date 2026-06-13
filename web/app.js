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
  if (info.version) document.querySelector(".tag").textContent = "browser edition · v" + info.version;
  setSplash(100, "Ready");
  $("splash").style.display = "none";
  $("app").hidden = false;
  booted = true;
  await applyHashState();        // restore a shared prescription, if the URL has one
  render();
  updateSeqHelp();
  maybeShowIntro();
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
  const sv = (key) => { if (st[key] !== undefined && st[key] !== null) { $(key).value = st[key]; const o = $(key + "-val"); if (o) o.value = $(key).value; updateSliderAria(key); } };
  ["slice", "tr", "te", "ti", "fa", "matrix", "bw", "nex", "thick", "bval", "etl", "np",
   "nslices", "sgap", "ipfov", "accel", "pv"].forEach(sv);
  ["fatsat", "gd", "flow", "acq3d", "kzpf", "fovplan", "cmap", "kspaceshow", "psdshow",
   "b0mapshow", "gfactorshow", "mathshow", "labelanat",
   "motion", "chemshift", "suscept"].forEach((k) => { if (st[k] !== undefined) $(k).checked = !!st[k]; });
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
  for (const [k, v] of p) st[k] = ["fatsat", "gd", "flow", "acq3d", "kzpf"].includes(k) ? v === "1" : v;
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
function showIntro() { openDialog("intro", "intro-ok"); }
function hideIntro() { closeDialog("intro"); localStorage.setItem("mrisim_seen", "1"); }
function maybeShowIntro() {
  $("intro-ok").addEventListener("click", hideIntro);
  $("intro-x").addEventListener("click", hideIntro);
  $("help").addEventListener("click", showIntro);
  try { if (!localStorage.getItem("mrisim_seen")) showIntro(); } catch (e) { /* private mode */ }
}

// --- Guided lessons --------------------------------------------------------- //
const LESSONS = [
  {
    title: "Start here — what is an MRI image?",
    blurb: "New to MRI? Read this first. What the greys actually mean.",
    beginner: true,
    steps: [
      { text: "This is a single <b>slice</b> through the head — a thin slab of tissue, seen from above. Every pixel is a <b>brightness</b>: how much signal that bit of tissue gave back. <b>Bright = lots of signal, dark = little.</b> MRI doesn't measure 'density' like a CT — it measures how the tissue's water responds to the scan. Nothing to do yet; just look.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 12, fovplan: false, cmap: false, mathshow: false, labelanat: false } },
      { text: "Don't know what you're looking at? Tick <b>Label the anatomy</b> (I just did) and the main structures get named on the image. The big paired blobs deep in the middle are the <b>ventricles</b> — fluid spaces. The outer ribbon is <b>grey matter</b>; the bright bulk inside is <b>white matter</b>.",
        state: { labelanat: true } },
      { text: "Now <b>hover your mouse over any pixel.</b> A readout shows which <b>tissue</b> it is and its three key numbers — <b>T1, T2 and PD</b>. Those three properties (plus your scan settings) are <i>all</i> that decide how bright a pixel is. The next lessons show how. Untick the labels whenever you want a clean image.",
        state: { labelanat: true } },
    ],
  },
  {
    title: "Start here — dark or bright? T1 vs T2",
    blurb: "The one rule that tells the two commonest scans apart.",
    beginner: true,
    steps: [
      { text: "Look at the <b>fluid in the ventricles</b> (centre). Right now it's <b>dark</b>. This is a <b>T1-weighted</b> scan — fat and white matter are bright, water/fluid is dark. Memory hook: on <b>T1, fluid is dark</b>. (T1 scans look 'anatomical' — close to how you'd picture the tissue.)",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 12, labelanat: false } },
      { text: "I changed two settings (TR and TE — more on those later). Watch the <b>ventricles flip to bright.</b> This is a <b>T2-weighted</b> scan: now <b>fluid is bright</b>. T2 is how you spot disease — most problems (swelling, fluid, inflammation) light up bright. Memory hook: <b>T2, fluid is bright.</b>",
        state: { tr: 4000, te: 100 } },
      { text: "That's the whole trick for reading a scan at a glance: <b>find the fluid (the ventricles, or the eyeballs).</b> Dark fluid → T1. Bright fluid → T2. Flip back and forth with <b>Back</b> / <b>Next</b> until it sticks — it's the single most useful habit in MRI.",
        state: { tr: 500, te: 12 } },
    ],
  },
  {
    title: "Start here — why so many sequences?",
    blurb: "What 'sequence' means, and why there are dozens of them.",
    beginner: true,
    steps: [
      { text: "A <b>sequence</b> is the recipe of radio pulses and timings the scanner plays. Different recipes make different tissues bright or dark — so radiologists run several per study, each tuned to show something. Read the <b>plain-language note under the Sequence menu</b>: it says what each one is for. This is <b>Spin Echo</b>, the reliable all-rounder.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 4000, te: 100, labelanat: false } },
      { text: "Switch to <b>FLAIR</b> (an inversion-recovery trick). It's a T2 scan but with the <b>bright fluid switched off</b> — the ventricles go black. Why? So a bright spot sitting <i>next to</i> fluid isn't hidden by it. FLAIR is the workhorse for finding brain lesions. Notice the note under the menu changed too.",
        state: { seq: "Inversion Recovery", tr: 9000, ti: 2548, te: 100 } },
      { text: "Last one: <b>Gradient Echo</b> — a fast recipe used for 3-D scans and angiography. The point isn't to memorise them: it's that each sequence is just a different recipe that makes a chosen tissue stand out. When you're ready, the lessons below open up TR, TE, nulling, SNR and FOV planning one at a time.",
        state: { seq: "Gradient Echo", tr: 400, te: 8 } },
    ],
  },
  {
    title: "Start here — spot the lesion (why it matters)",
    blurb: "The payoff: find a hidden lesion, and see why FLAIR exists.",
    beginner: true,
    steps: [
      { text: "I've added a small <b>lesion</b> to the white matter (choose one any time under <b>Pathology</b>). This is a <b>T1-weighted</b> scan — and the lesion is <b>nearly invisible</b>: its T1 is close to normal white matter, so it barely stands out. Stare at the white matter; you might just make out a faint patch. This is why T1 alone can miss disease.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 12, pathology: "lesion", labelanat: false, fovplan: false, cmap: false, mathshow: false } },
      { text: "Now <b>T2-weighted</b> (long TR, long TE). The lesion holds extra water → long T2 → it lights up <b>bright</b>. Suddenly obvious. This is the find-the-fluid rule from the last lesson working <i>for</i> you: pathology usually means extra water, and water is bright on T2.",
        state: { tr: 4000, te: 100 } },
      { text: "One problem: bright lesions next to the <b>bright CSF</b> of the ventricles can hide. <b>FLAIR</b> fixes it — it's a T2 scan with the CSF signal switched off, so fluid goes black while the lesion stays bright. That contrast is exactly why FLAIR is run on nearly every brain MRI. Tick <b>Label the anatomy</b> to confirm which bright spot is the lesion.",
        state: { seq: "Inversion Recovery", tr: 9000, ti: 2548, te: 100, labelanat: true } },
    ],
  },
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
    title: "Measuring the image — ruler, ROI & SNR",
    blurb: "Use the on-image tools to read distance, signal and noise.",
    steps: [
      { text: "Open the <b>Measure</b> panel on the left and pick <b>Ruler</b>, then drag a line across the image — say the width of the ventricles. The readout shows the <b>distance in mm</b>, calibrated to the field of view shown in the corner.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 4000, te: 100, nex: 1 } },
      { text: "Now pick <b>ROI</b> and drag a small ellipse over <b>white matter</b> — it reports the <b>mean signal</b> and the <b>noise (SD)</b>. Drag another ROI over a <b>dark background corner</b>: its mean is ~0 and its SD <i>is</i> the image noise. SNR ≈ tissue mean ÷ background SD.",
        state: {} },
      { text: "Raise <b>NEX</b> to 4 and watch your tissue ROI: the <b>mean holds</b> but the background SD <b>drops</b>, so SNR climbs by √4 = 2× (at 4× the scan time). The on-image ROI turns the SNR–time tradeoff into something you can measure yourself.",
        state: { nex: 4 } },
    ],
  },
  {
    title: "When images go wrong — artifacts",
    blurb: "Motion, chemical shift and dropout — and the setting that fixes each.",
    steps: [
      { text: "<b>Motion.</b> The patient moved during the scan, so the image <b>repeats as ghosts</b> along the phase-encode direction. Watch the faint copies marching across the brain. The fix: averaging (raise <b>NEX</b>), faster sequences, or a breath-hold. (Tick <b>Motion</b> under Artifacts to do this yourself.)",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 15, motion: true, motiontype: "periodic", chemshift: false, suscept: false } },
      { text: "<b>Chemical shift.</b> Fat and water resonate at slightly different frequencies, so <b>fat is mis-mapped along the readout</b> — see the bright/dark edge where the fatty scalp meets brain. It worsens at <b>low bandwidth</b> and high field. The fix: raise the receiver <b>bandwidth</b> (try the slider) or use fat-sat.",
        state: { motion: false, chemshift: true, bw: 32 } },
      { text: "<b>Susceptibility.</b> Near air/bone (sinuses, ear canals) the field distorts and signal <b>drops out and blooms</b> — worst on <b>gradient echo</b> and at long TE. The fix: shorten TE, or use a spin echo (its 180° refocuses the dephasing). Flip the sequence to Spin Echo and watch the dropout shrink.",
        state: { chemshift: false, suscept: true, seq: "Gradient Echo", te: 40 } },
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
      { text: "And <b>sagittal</b>, still from the one acquisition. Read the <b>slab readout</b> under the 3D controls: thin <b>isotropic</b> partitions, the total slab coverage, and a <b>√Nz SNR</b> gain over a single 2D slice — that's what phase-encoding the slice direction buys.",
        state: { orient: "sagittal", slice: 90 } },
      { text: "More partitions ⇒ more √Nz signal but a longer scan. Drop to <b>16 partitions</b> and watch the SNR-gain figure fall (√16 = 4× vs √32 ≈ 5.7×) while the scan time shortens.",
        state: { np: 16 } },
      { text: "Turn on <b>kz partial Fourier</b>: skip part of the slice-encode k-space to cut the scan further, trading a little SNR (√PF). The slab still reformats to any plane — the headline of 3D imaging.",
        state: { np: 32, kzpf: true } },
    ],
  },
  {
    title: "Where contrast comes from",
    blurb: "Read the whole TR×TE landscape, not just one curve.",
    steps: [
      { text: "Turn on the <b>Contrast map (TR×TE)</b> below the curve. It shades how strongly two tissues differ across every TR/TE — <b>bright = high contrast</b>, and the circle is your current protocol. Start T1-weighted: short TR, short TE.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 12, cmap: true } },
      { text: "Slide to <b>T2-weighted</b> (long TR, long TE). The marker climbs into the bright lobe where gray/white matter — and especially CSF — separate most. The picture's contrast follows the map.",
        state: { tr: 4000, te: 100 } },
      { text: "Now <b>proton-density</b> (long TR, short TE): GM/WM contrast comes purely from water content. Notice the dark <b>low-contrast band</b> a protocol must avoid — that's where the two tissues' signals cross and the image goes flat.",
        state: { tr: 4000, te: 15 } },
    ],
  },
  {
    title: "Multi-slice cross-talk & the gap",
    blurb: "Why packing slices tight costs SNR — and the gap that fixes it.",
    steps: [
      { text: "Open <b>FOV planning</b> and watch the <b>SNR</b> readout. One slice, baseline — the localizer shows a single band of the slice thickness.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 2000, te: 15, fovplan: true, nslices: 1, sgap: 0 } },
      { text: "Prescribe a <b>contiguous stack</b> — 16 slices, no gap. The bands fill the slab on the cross panels, but SNR <b>drops</b>: each slice-select pulse saturates the edges of its neighbours (cross-talk).",
        state: { nslices: 16, sgap: 0 } },
      { text: "Add a <b>slice gap</b> (5 mm). The bands separate and the SNR <b>recovers</b> — the classic reason for an inter-slice gap. The trade is coverage vs. signal.",
        state: { nslices: 16, sgap: 5 } },
    ],
  },
  {
    title: "Pathology → the right sequence",
    blurb: "Why we run DWI, SWI and post-contrast: each catches a different lesion.",
    steps: [
      { text: "Under <b>Pathology</b> I've added an <b>acute stroke</b>. It restricts water diffusion, so on <b>DWI</b> (high b-value) it lights up <b>bright</b> while normal brain darkens — the earliest, most sensitive sign of infarction, often positive within minutes. On routine T1/T2 it can be subtle; DWI makes it obvious.",
        state: { region: "Brain", seq: "Diffusion (DWI)", orient: "axial", slice: 90, bval: 1000, pathology: "stroke", labelanat: false, gd: false } },
      { text: "Now a <b>microhaemorrhage</b> on <b>SWI</b>. It's packed with paramagnetic blood-breakdown products that distort the local field, so it <b>blooms dark</b> — appearing far larger than its true size — while staying nearly invisible on conventional sequences. SWI is the sequence for old blood, calcium and small vessels. (First SWI render builds the venous map — give it a moment.)",
        state: { seq: "Susceptibility (SWI)", te: 40, pathology: "hemorrhage" } },
      { text: "Next an <b>enhancing tumour</b>. It breaks the blood–brain barrier, so it takes up contrast. Compare T1 <b>before</b> and <b>after</b> gadolinium (toggle <b>Gadolinium</b>): the tumour <b>brightens</b> — 'enhancement', the hallmark of an aggressive or breakdown lesion.",
        state: { seq: "Spin Echo", tr: 600, te: 12, pathology: "tumor", gd: true } },
      { text: "Finally a <b>brain abscess</b> — the case that needs <i>two</i> sequences. On <b>DWI</b> its pus core restricts diffusion and lights up <b>bright</b> (this is how an abscess is told apart from a necrotic tumour, whose core does <i>not</i> restrict).",
        state: { seq: "Diffusion (DWI)", bval: 1000, pathology: "abscess", gd: false, labelanat: false } },
      { text: "Now switch to <b>T1 with gadolinium</b> (Spin Echo + Gadolinium): the abscess shows a <b>thin enhancing rim</b> around the non-enhancing core — the classic 'ring enhancement'. (On <b>T2</b> the same capsule is a <b>dark ring</b> around the bright pus.) Bright core on DWI <i>and</i> a smooth enhancing rim = abscess. Four lesions, four sequences — that's why an MRI study is never just one scan.",
        state: { seq: "Spin Echo", tr: 600, te: 12, pathology: "abscess", gd: true, labelanat: true } },
    ],
  },
  {
    title: "Abscess vs. tumour — the DWI test",
    blurb: "Two lesions that look identical on contrast — and the one sequence that splits them.",
    steps: [
      { text: "Here's a <b>ring-enhancing</b> mass on T1 + gadolinium. The problem: a <b>brain abscess</b> and a <b>necrotic tumour</b> can look <i>identical</i> like this — both are a bright rim around a dark centre. Yet the treatment is opposite (drain the pus vs. resect/biopsy the tumour), so you have to tell them apart.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 600, te: 12, pathology: "abscess", gd: true, labelanat: false } },
      { text: "<b>DWI splits them.</b> Same lesion on the left and right, now on diffusion. <b>Left — abscess:</b> the pus restricts diffusion, so the <b>core is bright</b>. <b>Right — necrotic tumour:</b> the core diffuses freely, so it stays <b>dark</b>. That one difference — a bright DWI core — is what calls it an abscess. (Each panel is labelled with what it is.)",
        state: { seq: "Diffusion (DWI)", bval: 1000, pathology: "abscess", gd: false },
        compareWith: { seq: "Diffusion (DWI)", bval: 1000, pathology: "tumor", gd: false } },
    ],
  },
  {
    title: "A tour of the real anatomy",
    blurb: "The same physics on real brain, knee and body atlases.",
    steps: [
      { text: "Real <b>brain</b> (BrainWeb), T1-weighted. <b>Hover the image</b> to read each tissue's T1/T2/PD under the cursor — white matter bright, CSF dark.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 500, te: 12, fovplan: false, cmap: false } },
      { text: "Switch to the real <b>knee</b> (a 3-D T2 dataset). A fat-suppressed STIR lights up joint fluid and marrow oedema against nulled fat — the workhorse MSK contrast.",
        state: { region: "Knee", seq: "Inversion Recovery", orient: "sagittal", slice: 100, tr: 4000, ti: 265, te: 60 } },
      { text: "And the real <b>abdomen</b> (TotalSegmentator), T2 FSE: fluid-filled structures bright, solid organs mid-grey. Same equations, real segmented anatomy — hover to confirm the tissue.",
        state: { region: "Abdomen", seq: "FSE / TSE", orient: "axial", slice: 55, tr: 4000, te: 90, etl: 32 } },
    ],
  },
  {
    title: "The Ernst angle — flip for max signal",
    blurb: "On a gradient echo there's an optimal flip, and it isn't 90°.",
    steps: [
      { text: "On a <b>gradient echo</b> at short TR, a small flip leaves most of the magnetization unused. Start at <b>10°</b> and note the WM <b>SNR</b> on the right.",
        state: { region: "Brain", seq: "Gradient Echo", orient: "axial", slice: 90, tr: 150, te: 5, fa: 10 } },
      { text: "Raise the flip to <b>~35°</b> — the signal climbs to a peak. This is the <b>Ernst angle</b>: cos α = e<sup>−TR/T1</sup>, the flip that maximises steady-state signal for a given TR and T1.",
        state: { fa: 35 } },
      { text: "Push to <b>90°</b> and the signal <b>drops</b>. A big flip tips more magnetization but saturates it — at short TR there's no time to recover — so steady-state signal falls. The sweet spot is the Ernst angle, not 90°.",
        state: { fa: 90 } },
    ],
  },
  {
    title: "Resolution vs SNR — the matrix trade-off",
    blurb: "Finer voxels are sharper, but noisier and slower.",
    steps: [
      { text: "Baseline: a <b>256</b> matrix. Note the <b>resolution</b>, <b>SNR</b> and <b>scan time</b> readouts on the right.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 600, te: 15, matrix: 256 } },
      { text: "Drop to <b>96</b>: bigger voxels collect more signal each (<b>higher SNR</b>) over fewer phase-encode lines (<b>faster</b>) — but the image is visibly <b>blurrier</b>.",
        state: { matrix: 96 } },
      { text: "Go to <b>320</b>: crisp fine detail — but each small voxel holds less signal (<b>lower SNR</b>, grainier) and there are more lines to encode (<b>longer scan</b>). Resolution, SNR and time all pull against each other.",
        state: { matrix: 320 } },
    ],
  },
  {
    title: "Fat suppression — STIR vs spectral",
    blurb: "Two ways to darken fat, and why you'd pick each.",
    steps: [
      { text: "Real <b>knee</b>, T1 spin echo — <b>fat is bright</b> (subcutaneous fat, marrow). Bright fat can mask oedema and enhancement.",
        state: { region: "Knee", seq: "Spin Echo", orient: "sagittal", slice: 100, tr: 600, te: 12, fatsat: false } },
      { text: "<b>STIR</b> nulls fat by its <b>short T1</b> — inversion recovery at TI ≈ 250 ms. Robust on an uneven field, but it suppresses <i>anything</i> with fat's T1 (not fat-specific) and costs SNR.",
        state: { seq: "Inversion Recovery", tr: 4000, ti: 250, te: 40 } },
      { text: "<b>Spectral (CHESS)</b> fat-sat instead targets fat's <b>resonant frequency</b> — tick <b>Fat saturation</b> on a T2. Fat-specific and keeps other short-T1 tissue, but it needs a uniform B0 and fails where the field is distorted.",
        state: { seq: "Spin Echo", tr: 3500, te: 80, fatsat: true } },
    ],
  },
  {
    title: "In- vs opposed-phase (Dixon)",
    blurb: "Fat and water beating in and out of phase — the India-ink sign.",
    steps: [
      { text: "Real <b>abdomen</b> at 1.5 T, gradient echo. At an <b>in-phase</b> TE (4 ms) fat and water in the same voxel <b>add</b> — watch the <b>Fat–water phase</b> readout report <i>In-phase</i>.",
        state: { region: "Abdomen", seq: "Gradient Echo", orient: "axial", slice: 55, field: "1.5T", tr: 150, te: 4, fa: 70 } },
      { text: "Now an <b>opposed-phase</b> TE (2 ms): fat and water point opposite ways and <b>cancel</b>. Voxels with both lose signal — a dark <b>India-ink</b> outline appears at fat–water boundaries (organ edges).",
        state: { te: 2 } },
      { text: "This is the basis of <b>Dixon</b> fat–water imaging and of spotting <b>microscopic fat</b> (adrenal adenoma, fatty liver): tissue that drops signal on opposed- vs in-phase contains intravoxel fat.",
        state: { te: 2 } },
    ],
  },
  {
    title: "Angiography — bright blood (TOF)",
    blurb: "Flowing blood lights up with no contrast.",
    steps: [
      { text: "Switch to <b>MR Angiography</b> (time-of-flight). Stationary brain is saturated by rapid RF and stays dark, while <b>fresh blood flowing in</b> is unsaturated and bright — vessels light up with no injection.",
        state: { region: "Brain", seq: "MR Angiography", orient: "axial", slice: 90, flow: true } },
      { text: "Scroll through slices: the bright vessels are inflowing arteries (the circle of Willis). Clinically these are combined into a <b>maximum-intensity projection</b> to show the whole vascular tree at once.",
        state: { slice: 100 } },
    ],
  },
  {
    title: "DWI vs ADC — is the restriction real?",
    blurb: "The ADC map tells true restriction from T2 shine-through.",
    steps: [
      { text: "An <b>acute stroke</b> on <b>DWI</b> (high b-value): the infarct restricts water diffusion and lights up <b>bright</b> — the earliest sign of infarction.",
        state: { region: "Brain", seq: "Diffusion (DWI)", orient: "axial", slice: 90, bval: 1000, pathology: "stroke", diffdisp: "DWI" } },
      { text: "But bright on DWI isn't always real restriction — long-T2 tissue can be bright by <b>T2 shine-through</b>. Switch the <b>Diffusion display</b> to the <b>ADC map</b>.",
        state: { diffdisp: "ADC Map" } },
      { text: "On the <b>ADC map</b>, genuine restriction is <b>dark</b> (low ADC) — the stroke confirms. T2 shine-through would stay bright on ADC. Always read DWI <i>and</i> ADC together.",
        state: { diffdisp: "ADC Map" } },
    ],
  },
  {
    title: "qMRI — measuring tissue, not a picture",
    blurb: "Quantitative maps read the actual T1 / T2 in milliseconds.",
    steps: [
      { text: "Switch to <b>Quantitative (qMRI)</b> with the <b>T1 map</b>. Instead of a weighted picture, each pixel is the tissue's <b>actual T1 in ms</b> — hover to read it. CSF is long-T1 (bright), white matter short-T1 (dark).",
        state: { region: "Brain", seq: "Quantitative (qMRI)", orient: "axial", slice: 90, qmridisp: "T1 Map (VFA)" } },
      { text: "Now the <b>T2 map</b>: each pixel is the actual <b>T2 in ms</b>. These absolute numbers are reproducible across scanners — the basis of quantitative MRI (e.g. cartilage T2, myocardial T1 mapping) where a <i>value</i>, not just contrast, matters.",
        state: { qmridisp: "T2 Map (multi-echo)" } },
    ],
  },
  {
    title: "Reading k-space",
    blurb: "The raw data the image is the Fourier transform of.",
    steps: [
      { text: "Tick <b>Show k-space</b>. The image isn't acquired pixel-by-pixel — the scanner fills <b>k-space</b> (the spatial-frequency domain), and the image is its 2-D Fourier transform. The bright <b>centre</b> holds low frequencies (contrast and bulk signal).",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 600, te: 15, kspaceshow: true } },
      { text: "The <b>edges</b> of k-space hold high spatial frequencies — fine detail and sharp edges. Drop the <b>matrix</b> to 96: you sample less of k-space's periphery, so the image blurs (and the readouts show higher SNR, shorter scan).",
        state: { matrix: 96 } },
      { text: "Back to a full matrix. Add a <b>pulse-sequence diagram</b> too (<b>Show pulse-sequence diagram</b>) to connect the timing — RF, gradients and the echo — to the data each TR writes into k-space.",
        state: { matrix: 256, psdshow: true } },
    ],
  },
  {
    title: "Parallel imaging & the g-factor",
    blurb: "Skip k-space lines to go faster — at an SNR cost that isn't uniform.",
    steps: [
      { text: "<b>Parallel imaging</b> skips phase-encode lines and unfolds the aliasing using the coil array. Set <b>Acceleration R = 2</b> and watch the <b>scan time</b> drop — but SNR falls by √R plus a spatially-varying penalty.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 90, tr: 600, te: 15, accel: 2, accelmethod: "SENSE" } },
      { text: "Tick <b>Show g-factor map</b>. The <b>g-factor</b> is that extra, <i>local</i> noise amplification from the unfolding — worst toward the centre where the coil geometry is least able to separate aliased pixels. At R=2 it's mild.",
        state: { gfactorshow: true } },
      { text: "Push to <b>R = 4</b>: the g-factor map <b>blows up</b> in the centre — noise amplification grows sharply with R. That's why clinical SENSE rarely exceeds R≈2–3: past that the g-factor penalty outweighs the time saved.",
        state: { accel: 4 } },
    ],
  },
  {
    title: "B0 inhomogeneity & EPI distortion",
    blurb: "Off-resonance near air–tissue interfaces warps fast sequences.",
    steps: [
      { text: "Tick <b>Show B0 field map</b>. Even after shimming, susceptibility differences (air sinuses, bone) leave the field <b>off-resonance</b> — the map shows the local frequency error in Hz, largest near the skull base and sinuses.",
        state: { region: "Brain", seq: "Spin Echo", orient: "axial", slice: 60, tr: 600, te: 15, b0mapshow: true } },
      { text: "Off-resonance shifts signal along the phase-encode direction in proportion to its size. On a slow spin echo it's negligible, but on <b>EPI</b> (the readout behind DWI/fMRI) the low effective bandwidth makes those same Hz warp and pile up the image — geometric distortion worst where the field map is most extreme.",
        state: { seq: "Echo Planar (EPI)", te: 60 } },
    ],
  },
  {
    title: "Reconstructing the 3D slab (MPR & MIP)",
    blurb: "One acquisition, reformatted and projected any way you like.",
    steps: [
      { text: "First acquire a volume: <b>3D slab</b> on a gradient echo with plenty of partitions. Now tick <b>Reconstruction view</b> (under the 3D controls) — it lights up once a slab exists.",
        state: { region: "Brain", seq: "Gradient Echo", orient: "axial", slice: 90, acq3d: true } },
      { text: "In <b>MPR</b> mode you get the three orthogonal reformats from the <i>one</i> acquisition at once. Drag the <b>crosshair</b> sliders (Z / A–P / L–R) to move through the volume in every plane simultaneously — exactly how a workstation navigates a 3D dataset.",
        state: {} },
      { text: "Switch the recon <b>Mode</b> to <b>Thick-slab MIP</b>: it keeps the brightest voxel along each ray through an adjustable slab — raise the thickness to pull bright structures (like vessels) onto a single image. <b>Rotating MIP</b> spins that projection to any angle, and <b>Oblique MPR</b> tilts the reformat plane off the orthogonals.",
        state: {} },
    ],
  },
  {
    title: "MIP, MinIP & AIP — projecting a slab",
    blurb: "Three ways to flatten a slab, and what each is good for.",
    steps: [
      { text: "Acquire a <b>3D slab</b> (gradient echo, plenty of partitions) and open the <b>Reconstruction view</b>, then choose <b>Thick-slab MIP</b>. A projection collapses a slab of partitions onto one image — three ways, set by the <b>Projection</b> picker.",
        state: { region: "Brain", seq: "Gradient Echo", orient: "axial", slice: 90, acq3d: true } },
      { text: "<b>MIP</b> (maximum) keeps the <b>brightest</b> voxel along each ray — it pulls bright structures onto one image. That's the angiogram trick: bright flowing blood (TOF) stands out, and a thick MIP shows a whole vessel in a single picture.",
        state: {} },
      { text: "<b>MinIP</b> (minimum) keeps the <b>darkest</b> voxel — used where the finding is dark: veins and microbleeds on SWI, or air. <b>AIP</b> (average) is the slab <b>mean</b>, the CT-style look that smooths noise. Same slab, three readings — pick the one that makes your finding pop.",
        state: {} },
    ],
  },
  {
    title: "TOF vs phase-contrast angiography",
    blurb: "Two ways to make blood bright — inflow vs velocity.",
    steps: [
      { text: "<b>Time-of-flight (TOF)</b> MRA: stationary tissue is saturated by rapid RF and dark, while <b>fresh blood flowing in</b> is unsaturated and bright. No contrast, no velocity info — just inflow.",
        state: { region: "Brain", seq: "MR Angiography", orient: "axial", slice: 90, angiotype: "TOF" } },
      { text: "<b>Phase contrast (PC)</b> instead encodes <b>velocity</b> directly: moving spins pick up a phase proportional to their speed (set by the velocity-encoding, venc), so PC measures flow magnitude <i>and</i> direction — useful for quantifying flow, not just showing vessels.",
        state: { angiotype: "Phase Contrast" } },
      { text: "Rule of thumb: <b>TOF</b> for a quick, high-resolution roadmap of where the vessels are (combine slices into a MIP); <b>PC</b> when you need the <i>velocity</i> — shunts, stenoses, CSF flow — at the cost of a longer, venc-dependent scan.",
        state: {} },
    ],
  },
  {
    title: "Choosing the protocol (capstone)",
    blurb: "Put it together: question → sequence, plane and options.",
    steps: [
      { text: "Everything so far feeds one decision: <b>what answers the clinical question?</b> Work it as sequence → plane → options. Example — <b>?acute stroke</b>: diffusion restricts early, so <b>DWI</b> (with the ADC map) is the answer. Try it.",
        state: { region: "Brain", seq: "Diffusion (DWI)", orient: "axial", slice: 90, bval: 1000, pathology: "stroke", diffdisp: "DWI" } },
      { text: "<b>?MS lesion load</b>: small periventricular lesions hide in bright CSF, so null the CSF — <b>FLAIR</b>, read in the plane that shows the most lesions. Long TR, long TE, TI≈2550 ms at 3 T.",
        state: { seq: "Inversion Recovery", tr: 9000, ti: 2548, te: 100, pathology: "lesion" } },
      { text: "<b>?Vascular anatomy</b>: flowing blood, no contrast — <b>TOF MRA</b>, then a thick-slab <b>MIP</b> to show the whole tree. The pattern is always the same: name the contrast that makes the finding obvious, pick the plane that shows it, then add the options (fat-sat, Gd, 3D, projection) that sharpen it.",
        state: { seq: "MR Angiography", angiotype: "TOF", pathology: "", flow: true } },
    ],
  },
];

// --- Guided curriculum: an ordered beginner path through the lessons --------- //
// Each module groups existing lessons into a sequence that builds from "what is
// an MRI image?" up to advanced contrast, reconstruction and artifacts.
const CURRICULUM = [
  { title: "1 · What an MRI image is",
    lessons: ["Start here — what is an MRI image?", "Start here — dark or bright? T1 vs T2"] },
  { title: "2 · Where contrast comes from",
    lessons: ["Start here — why so many sequences?", "T1, T2 & PD contrast", "Where contrast comes from"] },
  { title: "3 · Making a tissue disappear",
    lessons: ["Nulling a tissue: FLAIR & STIR", "Fat suppression — STIR vs spectral", "In- vs opposed-phase (Dixon)"] },
  { title: "4 · Reading pathology",
    lessons: ["Start here — spot the lesion (why it matters)", "Pathology → the right sequence",
              "Abscess vs. tumour — the DWI test", "DWI vs ADC — is the restriction real?"] },
  { title: "5 · Image quality & speed",
    lessons: ["SNR vs. scan time", "Resolution vs SNR — the matrix trade-off",
              "The Ernst angle — flip for max signal", "Parallel imaging & the g-factor"] },
  { title: "6 · How the image is built",
    lessons: ["Reading k-space", "Multi-slice cross-talk & the gap", "Measuring the image — ruler, ROI & SNR"] },
  { title: "7 · 3D imaging & reconstruction",
    lessons: ["3D slab acquisition & reformat", "Reconstructing the 3D slab (MPR & MIP)",
              "MIP, MinIP & AIP — projecting a slab"] },
  { title: "8 · Flow, function & artifacts",
    lessons: ["Angiography — bright blood (TOF)", "TOF vs phase-contrast angiography",
              "qMRI — measuring tissue, not a picture",
              "When images go wrong — artifacts", "B0 inhomogeneity & EPI distortion",
              "A tour of the real anatomy"] },
  { title: "9 · Putting it together",
    lessons: ["Choosing the protocol (capstone)"] },
];
const LESSON_INDEX = new Map(LESSONS.map((L, i) => [L.title, i]));
// Flat ordered path of lesson indices (skip any title that doesn't resolve).
const CURRICULUM_PATH = CURRICULUM.flatMap((m) => m.lessons.map((t) => LESSON_INDEX.get(t)).filter((i) => i !== undefined));
let curriculumPos = -1;     // position in CURRICULUM_PATH while following the path; -1 = free lesson

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

function wireLessons() {
  const list = $("lesson-list");
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
  if (curriculumPos >= 0 && lessonIdx >= 0) {
    curriculumMarkDone(LESSONS[lessonIdx].title);
    curriculumPos++;
    if (curriculumPos < CURRICULUM_PATH.length) { startLesson(CURRICULUM_PATH[curriculumPos]); return; }
    curriculumPos = -1;        // whole curriculum complete
    exitLesson();
    openCurriculum();          // show the (now fully ticked) overview
    return;
  }
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
  lessonIdx = -1; curriculumPos = -1; $("lesson-panel").hidden = true;
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
    const on = $("fovplan").checked;
    $("scoutwrap").hidden = !on;
    $("planctl").hidden = !on;
    render();   // re-render so the main image picks up / drops the FOV crop
  });
  $("ipfov").addEventListener("input", () => { if (document.activeElement !== $("ipfov-val")) $("ipfov-val").value = $("ipfov").value; updateSliderAria("ipfov"); schedule(); });
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
  setupCollapsibles();
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
  ["diffdisp", "angiotype", "qmridisp", "fmridisp"].forEach((id) => $(id).addEventListener("change", schedule));
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
  if (p.angio_type) $("angiotype").value = p.angio_type;
  if (p.qmri_display) $("qmridisp").value = p.qmri_display;
  if (p.fmri_display) $("fmridisp").value = p.fmri_display;
  if (p.field_strength) $("field").value = p.field_strength;
  $("fatsat").checked = !!p.fatsat_enabled;
  $("gd").checked = !!p.contrast_enabled;
  $("flow").checked = !!p.flow_enabled;
  $("acq3d").checked = !!p.acq3d;
  if (p.n_partitions) set("np", p.n_partitions);
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
  if (!on) {
    $("abdelta").textContent = ""; $("setA").classList.remove("on");
    $("capA").hidden = true; $("capB").hidden = true;
  }
  render();
}

const PATHOLOGY_LABEL = { lesion: "WM lesion", stroke: "Stroke",
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

// Collapsible control groups (<details data-sec>): remember each section's open/closed
// state per-device so the panel opens the way the user left it.
const SECTION_LS = "mrisim_sections";
function loadSectionState() {
  try { return JSON.parse(localStorage.getItem(SECTION_LS) || "{}"); } catch (e) { return {}; }
}
function setupCollapsibles() {
  const saved = loadSectionState();
  document.querySelectorAll("details.group[data-sec]").forEach((d) => {
    const key = d.dataset.sec;
    if (key in saved) d.open = !!saved[key];   // restore; else keep the HTML default
    d.addEventListener("toggle", () => {
      if (document.body.classList.contains("filtering")) return;  // don't persist filter-forced state
      const s = loadSectionState(); s[key] = d.open;
      try { localStorage.setItem(SECTION_LS, JSON.stringify(s)); } catch (e) { /* private mode */ }
    });
  });
}
// Re-apply the user's saved (or default) open state — used when a filter clears.
function restoreSectionState() {
  const saved = loadSectionState();
  document.querySelectorAll("details.group[data-sec]").forEach((d) => {
    const key = d.dataset.sec;
    d.open = key in saved ? !!saved[key] : d.hasAttribute("data-open-default");
  });
}

// Control search/filter: type to show only matching labels (and the groups holding
// them, force-opened); empty restores the normal collapsed layout.
function setupSearch() {
  const box = $("ctrl-find"), clear = $("ctrl-find-x"), empty = $("ctrl-find-empty");
  if (!box) return;
  // Record each section's HTML default open state so we can restore it after filtering.
  document.querySelectorAll("details.group[data-sec]").forEach((d) => {
    if (d.open) d.setAttribute("data-open-default", "");
  });
  const run = () => {
    const term = box.value.trim().toLowerCase();
    clear.hidden = term === "";
    if (!term) {
      document.querySelectorAll("details.group[data-sec]").forEach((d) => {
        d.hidden = false;
        d.querySelectorAll(":scope > label, :scope > .btnrow, :scope > p, :scope > div").forEach((r) => { r.style.display = ""; });
      });
      restoreSectionState();                       // fires toggles — still guarded by .filtering
      document.body.classList.remove("filtering"); // …so they aren't persisted
      empty.hidden = true;
      return;
    }
    document.body.classList.add("filtering");
    let anyHit = false;
    document.querySelectorAll("details.group[data-sec]").forEach((d) => {
      const heading = (d.querySelector("summary")?.textContent || "").toLowerCase();
      const headingHit = heading.includes(term);
      let groupHit = headingHit;
      // Show/hide each direct control row by its text.
      d.querySelectorAll(":scope > label, :scope > .btnrow, :scope > p, :scope > div").forEach((r) => {
        const hit = headingHit || r.textContent.toLowerCase().includes(term);
        r.style.display = hit ? "" : "none";
        if (hit) groupHit = true;
      });
      d.hidden = !groupHit;
      if (groupHit) { d.open = true; anyHit = true; }
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

// Interactive localizer: drag the FOV box to resize, the box interior (or click
// elsewhere on the acquired panel) to recenter the in-plane FOV, the slice band
// on a cross panel to angle the plane (oblique), or elsewhere to move the slice.
function wireScout() {
  const img = $("scoutImage");
  img.style.cursor = "crosshair";
  let drag = null;

  const start = (f) => {
    const p = panelAt(f); if (!p) return null;
    const loc = panelLocal(p, f);
    if (p.role === "acq") {
      const fb = p.fov_box, cx = fb[0] + fb[2] / 2, cy = fb[1] + fb[3] / 2;
      const edge = Math.max(Math.abs(loc.px - cx) / (fb[2] / 2 || 1),
                            Math.abs(loc.py - cy) / (fb[3] / 2 || 1));
      return { mode: edge > 0.72 ? "resize" : "recenter", p };
    }
    const bp = bandLocal(p);
    const near = p.map === "row" ? Math.abs(loc.py - bp) < 0.10
                                 : Math.abs(loc.px - bp) < 0.10;
    if (near) return { mode: "oblique", p, l0: loc, tilt0: planTilt, rot0: planRot };
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
    } else if (drag.mode === "oblique") {            // angle the plane off-axis
      // Drag direction follows the band orientation (a horizontal band angles with
      // a vertical drag); *which* angle it sets is the panel's own DOF (p.angle),
      // so the two cross panels give independent tilt + rot — full double-oblique.
      const d = (p.map === "row" ? (drag.l0.py - loc.py) : (loc.px - drag.l0.px)) * 90;
      if (p.angle === "tilt") planTilt = clampN(drag.tilt0 + d, -45, 45);
      else planRot = clampN(drag.rot0 + d, -45, 45);
    }
    schedule();
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
  window.addEventListener("pointerup", () => { drag = null; });
  window.addEventListener("pointercancel", () => { drag = null; });
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
  if (!applyingPreset) $("preset").value = "";   // manual tweak → "custom"
  updateSeqHelp();                                // keep the clinical blurb current
  clearTimeout(timer);
  timer = setTimeout(render, 90);    // debounce; the worker keeps the UI free
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
      $("mainImage").style.filter = "";        // drop the live drag-preview filter
      $("mainImageB").style.filter = "";
      $("curveImage").src = resB.curve;
      setMetrics(resB);
      syncSlice(resB, reqSlice);
      showDelta(resA.metrics, resB.metrics);
      // Label each side with what it actually shows (e.g. "Abscess · DWI").
      for (const [id, p] of [["capA", A], ["capB", B]]) {
        const t = captionFor(p);
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
      });
      $("scoutImage").src = s.scout;
      scoutPanels = s.panels || [];
      $("oblique-readout").textContent =
        `Oblique tilt ${planTilt.toFixed(0)}° · rot ${planRot.toFixed(0)}°  —  drag either cross-panel's band to angle that plane; FOV box = resize/move; dbl-click = reset`;
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
  $("x-snr").textContent = `${m.snr_wm.toFixed(1)} / ${m.snr_gm.toFixed(1)}`;
  $("x-cnr").textContent = Math.abs(m.snr_wm - m.snr_gm).toFixed(1);
  $("x-sar").textContent = m.sar_head.toFixed(1) + " W/kg" + (m.sar_exceeds ? " ⚠" : "");
  $("m-scan").textContent = fmtTime(m.scan_time);
  $("m-snrwm").textContent = m.snr_wm.toFixed(1);
  $("m-weight").textContent = weighting($("sequence").value, +$("tr").value, +$("te").value);
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
