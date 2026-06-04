/* MRISim render worker — runs Pyodide + the Qt-free engine off the main thread,
 * so renders never freeze the UI. The page posts {id, type, payload} requests and
 * gets {id, result|error} back; boot progress arrives as {type:"progress"} and
 * {type:"ready"}. */
"use strict";

importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.2/full/pyodide.js");

let pyodide = null;
let renderFn = null, scoutFn = null;
const post = (m) => self.postMessage(m);

async function boot() {
  post({ type: "progress", pct: 8, msg: "Loading Pyodide…" });
  pyodide = await loadPyodide();
  post({ type: "progress", pct: 30, msg: "Loading numpy / scipy / matplotlib…" });
  await pyodide.loadPackage(["numpy", "scipy", "matplotlib"]);

  post({ type: "progress", pct: 62, msg: "Loading MRISim engine…" });
  const zip = await (await fetch("mrisim_src.zip")).arrayBuffer();
  await pyodide.unpackArchive(zip, "zip", { extractDir: "/src" });

  post({ type: "progress", pct: 74, msg: "Loading brain phantom…" });
  pyodide.FS.mkdirTree("/data");
  const npy = new Uint8Array(await (await fetch("data/brainweb_sub04_anat.npy")).arrayBuffer());
  pyodide.FS.writeFile("/data/brainweb_sub04_anat.npy", npy);

  post({ type: "progress", pct: 86, msg: "Starting engine…" });
  pyodide.runPython("import sys; sys.path.insert(0, '/src')");
  const info = JSON.parse(pyodide.runPython(
    "import json, web_adapter; json.dumps(web_adapter.init())"));
  renderFn = pyodide.runPython("web_adapter.render_json");
  scoutFn = pyodide.runPython("web_adapter.render_scout_json");
  post({ type: "ready", info });
}

// Regions backed by a real segmented atlas that's lazy-fetched on first use.
const REAL_REGIONS = new Set(["Abdomen", "Spine", "Pelvis", "Torso", "Knee"]);
const fetchedRegions = new Set();

async function ensureRegionData(name) {
  if (!REAL_REGIONS.has(name) || fetchedRegions.has(name)) return;
  pyodide.FS.mkdirTree("/data/regions");
  for (const kind of ["atlas", "texture"]) {
    const r = await fetch(`data/regions/${name}_${kind}.npy`);
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
    let result;
    if (type === "render") result = JSON.parse(renderFn(JSON.stringify(payload)));
    else if (type === "scout") result = JSON.parse(scoutFn(JSON.stringify(payload)));
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
