/* MRISim render worker — runs Pyodide + the Qt-free engine off the main thread,
 * so renders never freeze the UI. The page posts {id, type, payload} requests and
 * gets {id, result|error} back; boot progress arrives as {type:"progress"} and
 * {type:"ready"}. */
"use strict";

importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.2/full/pyodide.js");

let pyodide = null;
let renderFn = null, scoutFn = null, measureFn = null, reconstructFn = null, reconstructCineFn = null;
let scoutPanelsFn = null, protocolsFn = null;   // protocol-planning page
const post = (m) => self.postMessage(m);

// Per-deploy cache-buster: build_web.py writes build_id.js with the commit/build
// id, so a new deploy's engine + anatomy are always fetched fresh (no stale atlas
// served from the browser cache, which once made a fixed atlas still look wrong).
let BUILD_ID = "dev";
try { importScripts("build_id.js"); } catch (e) { /* unstamped — local dev */ }
const bust = (url) => url + (url.includes("?") ? "&" : "?") + "v=" + BUILD_ID;

async function boot() {
  post({ type: "progress", pct: 8, msg: "Loading Pyodide…" });
  pyodide = await loadPyodide();
  post({ type: "progress", pct: 30, msg: "Loading numpy / scipy / matplotlib…" });
  await pyodide.loadPackage(["numpy", "scipy", "matplotlib"]);

  post({ type: "progress", pct: 62, msg: "Loading MRISim engine…" });
  const zip = await (await fetch(bust("mrisim_src.zip"))).arrayBuffer();
  await pyodide.unpackArchive(zip, "zip", { extractDir: "/src" });

  post({ type: "progress", pct: 74, msg: "Loading brain phantom…" });
  pyodide.FS.mkdirTree("/data");
  const npy = new Uint8Array(await (await fetch(bust("data/brainweb_sub04_anat.npy"))).arrayBuffer());
  pyodide.FS.writeFile("/data/brainweb_sub04_anat.npy", npy);
  // Precomputed vessel-tree indices (~50 KB) so SWI / MR-angiography don't stall
  // ~1 min building them in-browser. Best-effort: the engine falls back to
  // building them if the file is missing.
  try {
    const v = new Uint8Array(await (await fetch(bust("data/brain_vessels_idx.npy"))).arrayBuffer());
    pyodide.FS.writeFile("/data/brain_vessels_idx.npy", v);
  } catch (e) { /* engine will build vessels on demand */ }

  post({ type: "progress", pct: 86, msg: "Starting engine…" });
  pyodide.runPython("import sys; sys.path.insert(0, '/src')");
  const info = JSON.parse(pyodide.runPython(
    "import json, web_adapter; json.dumps(web_adapter.init())"));
  renderFn = pyodide.runPython("web_adapter.render_json");
  scoutFn = pyodide.runPython("web_adapter.render_scout_json");
  measureFn = pyodide.runPython("web_adapter.measure_json");
  reconstructFn = pyodide.runPython("web_adapter.reconstruct_json");
  reconstructCineFn = pyodide.runPython("web_adapter.reconstruct_cine_json");
  scoutPanelsFn = pyodide.runPython("web_adapter.render_scout_panels_json");
  protocolsFn = pyodide.runPython("web_adapter.protocols_json");
  post({ type: "ready", info });
}

// Regions backed by a real segmented atlas that's lazy-fetched on first use.
const REAL_REGIONS = new Set(["Abdomen", "Spine", "Pelvis", "Torso", "Knee"]);
const fetchedRegions = new Set();

async function ensureRegionData(name) {
  if (!REAL_REGIONS.has(name) || fetchedRegions.has(name)) return;
  pyodide.FS.mkdirTree("/data/regions");
  for (const kind of ["atlas", "texture", "mixel"]) {
    const r = await fetch(bust(`data/regions/${name}_${kind}.npy`));
    if (!r.ok) continue;                       // texture optional / region absent
    pyodide.FS.writeFile(`/data/regions/${name}_${kind}.npy`,
      new Uint8Array(await r.arrayBuffer()));
  }
  fetchedRegions.add(name);
}

// Pyodide is synchronous, but the worker thread keeps the page responsive.
// setRegion may first fetch the region's real atlas, so the handler is async.
self.onmessage = async (e) => {
  const { id, type, payload } = e.data;
  try {
    // Direct render/scout/scoutPanels calls embed the region in the payload (the quiz and
    // the protocol scouts issue no separate setRegion) — lazy-load that region's real atlas
    // too, so e.g. Knee/Spine use the real anatomy instead of the synthetic-phantom fallback.
    if (payload && payload.region) await ensureRegionData(payload.region);
    let result;
    if (type === "render") result = JSON.parse(renderFn(JSON.stringify(payload)));
    else if (type === "scout") result = JSON.parse(scoutFn(JSON.stringify(payload)));
    else if (type === "measure") result = JSON.parse(measureFn(JSON.stringify(payload)));
    else if (type === "reconstruct") result = JSON.parse(reconstructFn(JSON.stringify(payload)));
    else if (type === "reconstructCine") result = JSON.parse(reconstructCineFn(JSON.stringify(payload)));
    else if (type === "scoutPanels") result = JSON.parse(scoutPanelsFn(JSON.stringify(payload)));
    else if (type === "protocols") result = JSON.parse(protocolsFn(JSON.stringify(payload)));
    else if (type === "setRegion") {
      await ensureRegionData(payload);         // lazy-load the real atlas if needed
      result = JSON.parse(pyodide.runPython(
        `import json; json.dumps(web_adapter.set_region(${JSON.stringify(payload)}))`));
    } else if (type === "preset")
      result = JSON.parse(pyodide.runPython(
        `import json; json.dumps(web_adapter.apply_preset(${JSON.stringify(payload)}))`));
    else throw new Error("unknown request type: " + type);
    post({ id, result });
  } catch (err) {
    post({ id, error: String(err && err.message ? err.message : err) });
  }
};

boot().catch((e) => post({ type: "error", msg: String(e && e.message ? e.message : e) }));
