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
  const sv = (key) => { if (st[key] !== undefined && st[key] !== null) { $(key).value = st[key]; const o = $(key + "-val"); if (o) o.value = $(key).value; updateSliderAria(key); } };
  ["slice", "tr", "te", "ti", "fa", "matrix", "bw", "nex", "thick", "bval", "etl", "np",
   "nslices", "sgap", "ipfov"].forEach(sv);
  ["fatsat", "gd", "flow", "acq3d", "kzpf", "fovplan", "cmap", "mathshow", "labelanat",
   "motion", "chemshift", "suscept"].forEach((k) => { if (st[k] !== undefined) $(k).checked = !!st[k]; });
  if (st.motiontype) $("motiontype").value = st.motiontype;
  // Pathology select (back-compat: the old boolean `lesion` maps to "lesion").
  if (st.pathology !== undefined) $("pathology").value = st.pathology;
  else if (st.lesion !== undefined) $("pathology").value = st.lesion ? "lesion" : "";
  // Reflect the teaching panels a lesson/share-link may have toggled.
  $("scoutwrap").hidden = !$("fovplan").checked;
  $("planctl").hidden = !$("fovplan").checked;
  $("cmapwrap").hidden = !$("cmap").checked;
  $("mathwrap").hidden = !$("mathshow").checked;
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
      { text: "And <b>sagittal</b>, still from the one acquisition. 3D gives thin contiguous partitions and a √Nz SNR advantage over single 2D slices.",
        state: { orient: "sagittal", slice: 90 } },
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
];

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
    b.addEventListener("click", () => { $("lesson-picker").hidden = true; startLesson(i); });
    list.appendChild(b);
  });
  $("lessons-btn").addEventListener("click", () => openDialog("lesson-picker", "lesson-picker-close"));
  $("lesson-picker-close").addEventListener("click", () => closeDialog("lesson-picker"));
  $("lesson-picker-x").addEventListener("click", () => closeDialog("lesson-picker"));
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
function exitLesson() {
  lessonIdx = -1; $("lesson-panel").hidden = true;
  if (compareMode) setCompare(false);   // a lesson may have ended in a comparison
}

async function applyStep() {
  const L = LESSONS[lessonIdx], s = L.steps[stepIdx];
  $("lesson-title").textContent = L.title;
  $("lesson-step").innerHTML = s.text;
  $("lesson-progress").textContent = `Step ${stepIdx + 1} / ${L.steps.length}`;
  $("lesson-prev").disabled = stepIdx === 0;
  $("lesson-next").textContent = stepIdx === L.steps.length - 1 ? "Finish" : "Next ›";
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
  $("ipfov").addEventListener("input", () => { $("ipfov-val").value = $("ipfov").value; updateSliderAria("ipfov"); schedule(); });
  $("cmap").addEventListener("change", () => { $("cmapwrap").hidden = !$("cmap").checked; render(); });
  $("mathshow").addEventListener("change", () => { $("mathwrap").hidden = !$("mathshow").checked; });
  $("labelanat").addEventListener("change", render);   // re-render with/without the anatomy labels
  $("pathology").addEventListener("change", render);   // re-render with/without the demo pathology
  $("slice-v").addEventListener("input", () => setSlice(+$("slice-v").value));  // rail beside the image
  wireWindowLevel();
  wireScout();
  wireProbe();
  wireMeasure();
  wireKeyboard();
  wireLessons();

  setupSliderA11y();
  ["tr", "te", "ti", "fa", "np", "slice", "matrix", "bw", "nex", "thick", "bval", "etl", "nslices", "sgap"].forEach((id) => {
    $(id).addEventListener("input", () => {
      const out = $(id + "-val"); if (out) out.value = $(id).value;
      updateSliderAria(id);
      schedule();
    });
  });
  $("copylink").addEventListener("click", copyLink);
  $("download").addEventListener("click", downloadPNG);
  [reg, seq, $("field")].forEach((el) => el.addEventListener("change", onSequenceOrRegion));
  ["fatsat", "gd", "flow", "acq3d", "kzpf"].forEach((id) =>
    $(id).addEventListener("change", () => { if (id === "acq3d") syncVisibility(); schedule(); }));
  ["motion", "chemshift", "suscept"].forEach((id) =>
    $(id).addEventListener("change", () => { syncVisibility(); schedule(); }));
  $("motiontype").addEventListener("change", schedule);
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
    fatsat_enabled: $("fatsat").checked,
    contrast_enabled: $("gd").checked, contrast_dose: $("gd").checked ? 5 : 0,
    flow_enabled: $("flow").checked,
    // Teaching artifacts (the engine already models these; here we just expose them).
    motion_enabled: $("motion").checked, motion_type: $("motiontype").value,
    chemical_shift_enabled: $("chemshift").checked,
    susceptibility_enabled: $("suscept").checked,
  };
  if (s === "Diffusion (DWI)") params.b_value = +$("bval").value;
  if (s === "FSE / TSE") params.etl = +$("etl").value;
  if (ACQ3D_SEQ.has(s) && $("acq3d").checked) {
    params.acq3d = true;
    params.n_partitions = +$("np").value;
    params.kz_pf = $("kzpf").checked ? 0.75 : null;
  }
  const out = {
    region: curRegion(), orientation: curOrient(),
    slice_idx: +$("slice").value, curve_mode: "TE decay",
    window_width: winW, window_level: winL, params,
    contrast_map: $("cmap").checked,
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
  const img = $("mainImage");
  let dragging = false, lx = 0, ly = 0, w0 = 1, l0 = 0.5;
  img.addEventListener("pointerdown", (e) => {
    if (compareMode || measureMode !== "off") return;   // measuring owns the drag
    dragging = true; lx = e.clientX; ly = e.clientY;
    w0 = winW; l0 = winL;              // baseline the current image was rendered at
    e.preventDefault();
  });
  window.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    winW = Math.min(3, Math.max(0.05, winW + (e.clientX - lx) * 0.004));
    winL = Math.min(1, Math.max(0, winL - (e.clientY - ly) * 0.003));
    lx = e.clientX; ly = e.clientY;
    img.style.filter = wlFilter(w0, l0);   // instant preview, no server call
  });
  const endWL = () => {
    if (!dragging) return;
    dragging = false;
    schedule();                            // one accurate render at the final W/L
  };
  window.addEventListener("pointerup", endWL);
  window.addEventListener("pointercancel", endWL);
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
      if (p.map === "row") planTilt = clampN(drag.tilt0 + (drag.l0.py - loc.py) * 90, -45, 45);
      else planRot = clampN(drag.rot0 + (loc.px - drag.l0.px) * 90, -45, 45);
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
      const A = protocolA || B;
      const resA = await call("render", A);
      const resB = await call("render", B);
      $("mainImage").src = resA.image;
      $("mainImageB").src = resB.image;
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
        `Oblique ${planTilt.toFixed(0)}° / ${planRot.toFixed(0)}°  ·  drag band = angle, FOV box = resize/move, dbl-click = reset`;
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
}

function applyResult(res, reqSlice) {
  $("mainImage").src = res.image;
  $("mainImage").style.filter = "";   // server image is correctly windowed; drop the live W/L preview filter
  $("curveImage").src = res.curve;
  probe = res.probe || null;          // aligned label map for the hover tissue readout
  if (probe) probe.bytes = Uint8Array.from(atob(probe.labels), (c) => c.charCodeAt(0));
  if (res.cmap) $("cmapImage").src = res.cmap;   // TR×TE contrast landscape
  syncSlice(res, reqSlice);
  setMetrics(res);
  refreshMeasure();                   // keep a placed ruler/ROI aligned + live on the new image
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
  measureShape = null; measureDrag = null; drawMeasure(null);
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
      clearMeasure();
    }));
  $("measure-clear").addEventListener("click", clearMeasure);
  window.addEventListener("resize", () => drawMeasure(measureShape));
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
