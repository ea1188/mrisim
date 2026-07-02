/* Headless-browser smoke test for the MRISim web build.
 *
 * Boots the page in headless Chromium (Playwright), waits for Pyodide to load the
 * engine + brain and produce the first render, then asserts the image and metrics
 * actually populated. This is the real "does the browser build work" check that
 * the Python tests can't make. Run by .github/workflows/web-smoke.yml against a
 * locally served `web/`.  Usage: node web/smoke.mjs [url]
 */
import { chromium } from "playwright";

// The site root is now the launcher; the simulator lives at simulator.html.
const url = (process.argv[2] || "http://localhost:8765/").replace(/\/?$/, "/") + "simulator.html";
const BOOT_TIMEOUT = 180_000;   // first load pulls ~30–50 MB of wheels from the CDN

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

let _step = "start";
function step(name) { _step = name; console.log("• " + name); }
function fail(msg) {
  console.error("SMOKE FAIL [" + _step + "]:", msg);
  if (errors.length) console.error("page errors:\n" + errors.join("\n"));
  process.exit(1);
}

try {
  await page.goto(url, { waitUntil: "domcontentloaded" });

  // The control panel unhides once Pyodide has booted and the first render lands.
  step("boot (await #app)");
  await page.waitForSelector("#app:not([hidden])", { timeout: BOOT_TIMEOUT });

  step("first image render");
  // The main image must carry a real PNG data URL.
  await page.waitForFunction(
    () => {
      const s = document.getElementById("mainImage")?.src || "";
      return s.startsWith("data:image/png") && s.length > 2000;
    },
    { timeout: 30_000 },
  );

  step("intro");
  // First-run intro must appear, then dismiss it (it overlays the controls).
  await page.waitForSelector("#intro:not([hidden])", { timeout: 10_000 });
  // Accessibility: the intro is a labelled modal dialog.
  if ((await page.getAttribute("#intro", "role")) !== "dialog") fail("intro is not role=dialog");
  if ((await page.getAttribute("#intro", "aria-modal")) !== "true") fail("intro not aria-modal");
  // The card caps its height and the body scrolls (title/footer/✕ stay pinned).
  const introBody = await page.$eval("#intro .intro-body", (el) => getComputedStyle(el).overflowY);
  if (!/auto|scroll/.test(introBody)) fail("intro body not scrollable: " + introBody);
  // The corner ✕ closes the intro too.
  await page.click("#intro-x");
  await page.waitForSelector("#intro", { state: "hidden", timeout: 5_000 });

  step("UI: collapsible groups, numeric entry, search");
  // Advanced groups start collapsed (shorter scroll); core groups stay open.
  if (await page.evaluate(() => document.querySelector('details[data-sec="acquisition"]').open))
    fail("Acquisition group should start collapsed");
  if (!(await page.evaluate(() => document.querySelector('details[data-sec="protocol"]').open)))
    fail("Protocol group should start open");
  // Clicking a section header expands it.
  await page.click('details[data-sec="acquisition"] > summary');
  if (!(await page.evaluate(() => document.querySelector('details[data-sec="acquisition"]').open)))
    fail("clicking the Acquisition header did not expand it");

  // Editable numeric value: typing an exact TR into its number field drives the
  // slider and re-renders the image. (Timing is open by default.)
  const numBefore = await page.getAttribute("#mainImage", "src");
  await page.fill("#tr-val", "2200");
  await page.waitForFunction(() => document.getElementById("tr").value === "2200", { timeout: 5_000 });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    numBefore, { timeout: 15_000 });

  // Control search: filtering by "bandwidth" reveals (and opens) the Acquisition
  // group and hides unrelated groups; clearing restores them.
  await page.fill("#ctrl-find", "bandwidth");
  await page.waitForFunction(() => {
    const acq = document.querySelector('details[data-sec="acquisition"]');
    const tim = document.querySelector('details[data-sec="timing"]');
    return acq && !acq.hidden && acq.open && tim && tim.hidden;
  }, { timeout: 5_000 });
  await page.fill("#ctrl-find", "");
  await page.waitForFunction(
    () => !document.querySelector('details[data-sec="timing"]').hidden, { timeout: 5_000 });

  step("feature tour");
  // The ? button opens the welcome; "Take the feature tour" starts the spotlight
  // tour over the real controls; Next advances, Skip ends it.
  await page.click("#help");
  await page.waitForSelector("#intro:not([hidden])", { timeout: 5_000 });
  await page.click("#intro-tour");
  await page.waitForSelector("#tour:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(() => {
    const s = document.getElementById("tour-spot");
    return s && s.offsetWidth > 0 && (document.getElementById("tour-title").textContent || "").length > 0;
  }, { timeout: 5_000 });
  const tourP0 = await page.textContent("#tour-progress");
  await page.click("#tour-next");
  await page.waitForFunction(
    (prev) => document.getElementById("tour-progress").textContent !== prev, tourP0, { timeout: 5_000 });
  await page.click("#tour-skip");
  await page.waitForSelector("#tour", { state: "hidden", timeout: 5_000 });

  // Expand every group so all controls are actionable in the functional tests below
  // (the collapse/search UX itself is covered above).
  await page.evaluate(() => document.querySelectorAll("details.group").forEach((d) => { d.open = true; }));

  // The topbar shows the running engine version (e.g. "browser edition · v1.6.1").
  const tag = await page.textContent(".tag");
  if (!/v\d+\.\d+/.test(tag || "")) fail("version not shown in topbar: " + tag);

  // Metrics must have populated (not the "—" placeholder).
  const scan = await page.textContent("#x-scan");
  const snr = await page.textContent("#x-snr");
  if (!scan || scan.includes("—")) fail("scan-time metric did not populate: " + scan);
  if (!snr || snr.includes("—")) fail("SNR metric did not populate: " + snr);

  // The plain-language clinical blurb under the sequence picker must populate.
  if (!((await page.textContent("#seq-help")) || "").trim()) fail("sequence help blurb is empty");

  // Accessibility: sliders carry a screen-reader name + a spoken value-with-unit,
  // and the value text updates as the slider moves.
  const trLabel = await page.getAttribute("#tr", "aria-label");
  if (!trLabel || !/TR/.test(trLabel)) fail("TR slider missing aria-label: " + trLabel);
  const vt0 = await page.getAttribute("#tr", "aria-valuetext");
  if (!vt0 || !/milliseconds/.test(vt0)) fail("TR slider missing aria-valuetext: " + vt0);
  await page.evaluate(() => { const t = document.getElementById("tr"); t.value = 2000; t.dispatchEvent(new Event("input")); });
  const vt1 = await page.getAttribute("#tr", "aria-valuetext");
  if (vt1 === vt0) fail("TR aria-valuetext did not update on change: " + vt1);

  step("sequence change");
  // Changing the sequence must re-render without throwing.
  await page.selectOption("#sequence", "Gradient Echo");
  await page.waitForTimeout(1500);
  const src2 = await page.getAttribute("#mainImage", "src");
  if (!src2 || !src2.startsWith("data:image/png")) fail("re-render after sequence change failed");

  step("preset apply");
  // Applying a preset must repopulate controls and re-render.
  const presets = await page.$$eval("#preset option", (os) => os.map((o) => o.value).filter(Boolean));
  if (presets.length === 0) fail("no presets listed");
  const before = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#preset", presets[0]);
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    before, { timeout: 30_000 });

  step("A/B compare");
  // A/B compare: snapshot A, tweak B, expect two images + a delta line.
  await page.click("#setA");
  await page.waitForSelector("#wrapB:not([hidden])", { timeout: 10_000 });
  await page.fill("#tr", "2500").catch(() => {});      // range fill may no-op; fall back
  await page.evaluate(() => { const t = document.getElementById("tr"); t.value = 3000; t.dispatchEvent(new Event("input")); });
  await page.waitForTimeout(2500);
  const imgB = await page.getAttribute("#mainImageB", "src");
  if (!imgB || !imgB.startsWith("data:image/png")) fail("compare B image did not render");
  const delta = await page.textContent("#abdelta");
  if (!delta || !/SNR/.test(delta)) fail("compare delta did not populate: " + delta);
  // Compare-mode controls: only "Exit compare" shows — the "Compare A/B" toggle is
  // hidden while comparing so it can't read as "compare" when you're already there.
  if (!(await page.isHidden("#compare"))) fail("'Compare A/B' should be hidden while comparing");
  if (!(await page.isVisible("#exitAB"))) fail("'Exit compare' should be visible while comparing");
  // The per-side caption carries only what the image doesn't bake in (pathology/+Gd);
  // with none set it stays hidden, clear of the baked corner annotations.
  if (!(await page.isHidden("#capB"))) fail("compare caption B should be hidden when there are no extras");
  // Window/level works in compare and re-windows BOTH sides: dragging on A must
  // change both A and B images (shared window/level for a fair comparison).
  const a0 = await page.getAttribute("#mainImage", "src");
  const b0 = await page.getAttribute("#mainImageB", "src");
  const boxAB = await page.$eval("#mainImage", (el) => { const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await page.mouse.move(boxAB.x, boxAB.y);
  await page.mouse.down();
  await page.mouse.move(boxAB.x + 80, boxAB.y + 40, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(
    (p) => { const a = document.getElementById("mainImage").src, b = document.getElementById("mainImageB").src;
             return a && b && a !== p.a && b !== p.b; },
    { a: a0, b: b0 }, { timeout: 20_000 });
  await page.click("#exitAB");
  await page.waitForSelector("#wrapB", { state: "hidden", timeout: 5_000 });

  // Touch support: the image must opt out of the browser's touch gestures so a
  // finger can drag window/level / measure instead of scrolling the page.
  const touchAction = await page.$eval("#mainImage", (el) => getComputedStyle(el).touchAction);
  if (touchAction !== "none") fail("mainImage touch-action should be none, got: " + touchAction);

  step("window/level");
  // Window/level drag must change the image (single render path).
  const beforeWL = await page.getAttribute("#mainImage", "src");
  const box = await page.$eval("#mainImage", (el) => { const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await page.mouse.move(box.x, box.y);
  await page.mouse.down();
  await page.mouse.move(box.x + 80, box.y + 50, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    beforeWL, { timeout: 15_000 });

  // Touch path: a finger drag (pointerType "touch") must also drive window/level.
  const beforeTouch = await page.getAttribute("#mainImage", "src");
  await page.evaluate(({ x, y }) => {
    const img = document.getElementById("mainImage");
    const pe = (t, cx, cy) => new PointerEvent(t, { pointerType: "touch", pointerId: 1, clientX: cx, clientY: cy, bubbles: true, cancelable: true });
    img.dispatchEvent(pe("pointerdown", x, y));
    window.dispatchEvent(pe("pointermove", x - 70, y - 40));
    window.dispatchEvent(pe("pointermove", x - 90, y - 60));
    window.dispatchEvent(pe("pointerup", x - 90, y - 60));
  }, box);
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    beforeTouch, { timeout: 15_000 });

  // "Label the anatomy" must re-render the image (named structures drawn on it).
  {
    const before = await page.getAttribute("#mainImage", "src");
    await page.check("#labelanat");
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
      before, { timeout: 15_000 });
    await page.uncheck("#labelanat");
  }

  // Demo pathology: selecting one (stroke) must re-render the brain image.
  {
    const before = await page.getAttribute("#mainImage", "src");
    await page.selectOption("#pathology", "stroke");
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
      before, { timeout: 15_000 });
    await page.selectOption("#pathology", "");
  }

  // Teaching artifacts: enabling motion must re-render and reveal the motion-type
  // selector; the engine applies the (already-tested) ghosting.
  {
    const before = await page.getAttribute("#mainImage", "src");
    await page.check("#motion");
    await page.waitForSelector("#motiontype-row:not([hidden])", { timeout: 5_000 });
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
      before, { timeout: 15_000 });
    await page.uncheck("#motion");
  }

  // Measurement tools: pick Ruler, drag a line, and the readout must report mm;
  // then ROI must report a mean/SNR. (Drag over the image element.)
  {
    await page.click('#measuremode button[data-m="ruler"]');
    const ir = await page.$eval("#mainImage", (el) => {
      const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
    await page.mouse.move(ir.x + ir.w * 0.35, ir.y + ir.h * 0.5);
    await page.mouse.down();
    await page.mouse.move(ir.x + ir.w * 0.65, ir.y + ir.h * 0.5, { steps: 6 });
    await page.mouse.up();
    await page.waitForFunction(
      () => /mm/.test(document.getElementById("measure-readout").textContent || ""),
      { timeout: 10_000 });
    await page.click('#measuremode button[data-m="roi"]');
    await page.mouse.move(ir.x + ir.w * 0.45, ir.y + ir.h * 0.45);
    await page.mouse.down();
    await page.mouse.move(ir.x + ir.w * 0.55, ir.y + ir.h * 0.55, { steps: 6 });
    await page.mouse.up();
    await page.waitForFunction(
      () => /SNR/.test(document.getElementById("measure-readout").textContent || ""),
      { timeout: 10_000 });
    await page.click('#measuremode button[data-m="off"]');
  }

  // Cursor tissue probe: hovering the image shows a tissue + T1/T2/PD readout.
  await page.mouse.move(box.x - 4, box.y - 4);
  await page.mouse.move(box.x, box.y);            // ensure a mousemove fires over the image
  await page.waitForFunction(
    () => { const p = document.getElementById("probe"); return p && !p.hidden && /T1\s/.test(p.textContent || ""); },
    { timeout: 5_000 });

  // "Show the math": toggle on, hover, and the equation panel must populate.
  await page.check("#mathshow");
  await page.mouse.move(box.x - 6, box.y - 6);
  await page.mouse.move(box.x, box.y);
  await page.waitForFunction(
    () => { const m = document.getElementById("math"); return m && /S\s*=/.test(m.textContent || "") && /signal/i.test(m.textContent || ""); },
    { timeout: 5_000 });
  await page.uncheck("#mathshow");

  step("FOV scout");
  // FOV-planning scout: toggling on must render the 3-plane localizer.
  await page.check("#fovplan");
  await page.waitForSelector("#scoutwrap:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("scoutImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  // Clicking a cross panel of the localizer must move the slice. Force axial so
  // the middle (coronal) panel is a genuine cross panel, and wait for the scout
  // image to decode (naturalWidth) before mapping a click onto it.
  await page.click('#orientation button[data-v="axial"]');
  await page.waitForTimeout(1500);
  await page.waitForFunction(
    () => { const i = document.getElementById("scoutImage"); return i && i.naturalWidth > 0; },
    { timeout: 15_000 });
  // The whole 3-plane localizer must be visible, not clipped to its top half:
  // the image must fit within its box (no overflow past top/bottom) and keep its
  // aspect ratio (element == displayed image, so the drag math maps exactly).
  const fit = await page.$eval("#scoutImage", (el) => {
    const r = el.getBoundingClientRect(), w = el.parentElement.getBoundingClientRect();
    const nAR = el.naturalWidth / el.naturalHeight, eAR = r.width / r.height;
    return { overflow: Math.max(0, r.bottom - w.bottom, w.top - r.top), arErr: Math.abs(nAR - eAR) / nAR };
  });
  if (fit.overflow > 2) fail("scout localizer is clipped by its box (overflow " + fit.overflow.toFixed(1) + "px)");
  if (fit.arErr > 0.05) fail("scout localizer is distorted (aspect mismatch " + fit.arErr.toFixed(3) + ")");
  const sliceBefore = await page.inputValue("#slice");
  const sb = await page.$eval("#scoutImage", (el) => { const r = el.getBoundingClientRect(); return { w: r.width, h: r.height }; });
  // Element-relative click so events target the scout image regardless of layout.
  // Middle (coronal) panel, low → a row-mapped cross panel in axial acquisition.
  await page.click("#scoutImage", { position: { x: sb.w * 0.5, y: sb.h * 0.82 } });
  await page.waitForTimeout(800);
  const sliceAfter = await page.inputValue("#slice");
  if (sliceAfter === sliceBefore) fail("scout click did not move the slice (before=" + sliceBefore + ")");

  // Dragging the slice band on a cross panel must angle the plane (oblique). Target the
  // band at its ACTUAL rendered position (the engine's panel geometry), then drag it
  // perpendicular — the oblique readout must report a non-zero angle. (Aiming at a fixed
  // spot is unreliable: the band renders at a cropped/scaled position, not py·n.)
  const grab = await page.evaluate(() => {
    const panels = window.scoutPanels || [];
    const p = panels.find((q) => q && q.role !== "acq" && q.angle && q.band);
    if (!p) return null;
    const r = document.getElementById("scoutImage").getBoundingClientRect();
    const mg = [(p.band[0][0] + p.band[1][0]) / 2, (p.band[0][1] + p.band[1][1]) / 2];   // geom midpoint
    const lpx = p.flip ? 1 - mg[0] : mg[0], lpy = 1 - mg[1];      // → panel-local (y-down)
    const [l, t, rr, b] = p.box;
    const cx = r.left + (l + lpx * (rr - l)) * r.width;           // → client px (image fills its box)
    const cy = r.top + (t + lpy * (b - t)) * r.height;
    const d = 0.22;                                               // perpendicular drag length
    return { cx, cy, ex: cx + (p.map === "row" ? r.width * 0.1 : r.width * d),
             ey: cy + (p.map === "row" ? r.height * d : r.height * 0.1) };
  });
  if (!grab) fail("no cross panel with band geometry for the oblique-drag test");
  else {
    await page.mouse.move(grab.cx, grab.cy);
    await page.mouse.down();
    await page.mouse.move(grab.ex, grab.ey, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(900);
    const readout = await page.textContent("#oblique-readout");
    if (/tilt\s*0°\s*·\s*rot\s*0°/.test(readout || "")) fail("oblique drag did not angle the plane (" + readout + ")");
    else console.log("scout oblique drag angled the plane ✓");
  }

  await page.uncheck("#fovplan");

  step("3D slab");
  // 3D slab acquisition: enabling it on a slab-capable sequence must reveal the
  // slab controls and a readout reporting the partition geometry + √Nz SNR gain.
  await page.selectOption("#sequence", "Gradient Echo");
  await page.check("#acq3d");
  await page.waitForSelector("#np-row:not([hidden])", { timeout: 5_000 });
  await page.waitForSelector("#slabsharp-row:not([hidden])", { timeout: 5_000 });
  // Enabling 3D covers the whole anatomy from the first click: the slab depth
  // jumps to (near) the full slice-axis extent, not a thin default.
  if (+(await page.inputValue("#np")) < 64)
    fail("3D slab should default to full coverage, got " + (await page.inputValue("#np")) + " partitions");
  // The reconstruction toggle now lives in the same group (no separate section).
  if (!(await page.$("#reconshow"))) fail("reconstruction toggle missing from the 3D group");
  await page.waitForFunction(
    () => { const t = document.getElementById("slab-readout").textContent || "";
            return /partition/i.test(t) && /SNR/.test(t) && /mm slab/.test(t); },
    { timeout: 20_000 });

  step("reconstruction");
  // With a slab acquired, the Reconstruction toggle enables; MPR shows three
  // reformat panels, and switching to MIP shows the single projection panel.
  if (await page.isDisabled("#reconshow")) fail("reconshow should enable once a 3D slab is on");
  await page.check("#reconshow");
  await page.waitForSelector("#reconwrap:not([hidden])", { timeout: 5_000 });
  // MPR opens as a 2×2 grid: the three reformats + a 3D MIP overview (4th panel).
  await page.waitForFunction(
    () => ["reconAxial", "reconCoronal", "reconSagittal", "reconOverview"].every((id) => {
      const s = document.getElementById(id)?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; }),
    { timeout: 25_000 });
  // Click-to-navigate: clicking a panel moves the crosshair sliders and re-renders.
  const rz0 = await page.inputValue("#rz");
  const axSrc0 = await page.getAttribute("#reconAxial", "src");
  // page.click auto-scrolls the panel into view, then clicks at the given position
  // (near the top of the coronal panel → changes the Z crosshair).
  const ch = await page.$eval("#reconCoronal", (el) => ({ w: el.getBoundingClientRect().width, h: el.getBoundingClientRect().height }));
  await page.click("#reconCoronal", { position: { x: ch.w * 0.5, y: ch.h * 0.2 } });
  await page.waitForFunction((prev) => document.getElementById("rz").value !== prev, rz0, { timeout: 8_000 });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("reconAxial").src; return s && s !== prev; },
    axSrc0, { timeout: 25_000 });

  // Measure on a reconstruction panel: a ruler drag across the axial reformat
  // reports mm; an ROI drag reports SNR. (Measure mode disables click-nav.)
  await page.click('#measuremode button[data-m="ruler"]');
  {
    const r = await page.$eval("#reconAxial", (el) => {
      const b = el.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; });
    await page.mouse.move(r.x + r.w * 0.30, r.y + r.h * 0.5);
    await page.mouse.down();
    await page.mouse.move(r.x + r.w * 0.70, r.y + r.h * 0.5, { steps: 6 });
    await page.mouse.up();
    await page.waitForFunction(
      () => /mm/.test(document.getElementById("measure-readout").textContent || ""),
      { timeout: 10_000 });
    await page.click('#measuremode button[data-m="roi"]');
    await page.mouse.move(r.x + r.w * 0.45, r.y + r.h * 0.45);
    await page.mouse.down();
    await page.mouse.move(r.x + r.w * 0.60, r.y + r.h * 0.60, { steps: 6 });
    await page.mouse.up();
    await page.waitForFunction(
      () => /SNR/.test(document.getElementById("measure-readout").textContent || ""),
      { timeout: 10_000 });
    await page.click('#measuremode button[data-m="off"]');
  }

  await page.selectOption("#reconmode", "mip");
  await page.waitForSelector("#recon-single:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("reconMain")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 25_000 });
  // Switching the projection (MIP → MinIP) must re-render the slab projection.
  const mipSrc = await page.getAttribute("#reconMain", "src");
  await page.selectOption("#mipmode", "minip");
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("reconMain").src; return s && s !== prev && s.length > 2000; },
    mipSrc, { timeout: 25_000 });
  // Moving the slab position must re-render the projection.
  const posSrc = await page.getAttribute("#reconMain", "src");
  await page.evaluate(() => { const s = document.getElementById("mipcenter"); s.value = 15; s.dispatchEvent(new Event("input")); });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("reconMain").src; return s && s !== prev && s.length > 2000; },
    posSrc, { timeout: 25_000 });
  // The reconstruction download button is present and enabled.
  if (await page.isDisabled("#recon-download")) fail("recon download button should be enabled");
  // Rotating-MIP cine: in rmip mode, Spin pre-renders frames and animates them.
  await page.selectOption("#reconmode", "rmip");
  await page.waitForSelector("#recon-spin:visible", { timeout: 5_000 });
  const cineSrc0 = await page.getAttribute("#reconMain", "src");
  await page.click("#recon-spin");
  await page.waitForFunction(() => (document.getElementById("recon-spin").textContent || "").includes("Stop"), { timeout: 30_000 });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("reconMain").src; return s && s !== prev; },
    cineSrc0, { timeout: 10_000 });            // a frame is being shown
  await page.click("#recon-spin");             // stop
  await page.waitForFunction(() => (document.getElementById("recon-spin").textContent || "").includes("Spin"), { timeout: 5_000 });
  await page.uncheck("#reconshow");
  await page.uncheck("#acq3d");

  step("sub-displays");
  // Per-sequence display dropdowns: Diffusion exposes a DWI/ADC/FA picker, and
  // switching it must re-render (the engine returns a different map). 7T must be a
  // selectable field strength.
  await page.selectOption("#sequence", "Diffusion (DWI)");
  await page.waitForSelector("#diffdisp-row:not([hidden])", { timeout: 5_000 });
  const dwiSrc = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#diffdisp", "ADC Map");
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev && s.length > 2000; },
    dwiSrc, { timeout: 20_000 });
  if (!(await page.$$eval("#field option", (os) => os.some((o) => o.value === "7T" || o.textContent === "7T"))))
    fail("7T must be a selectable field strength");
  // a render landed (src differs from `prev` and is a real PNG)
  const rendered = (prev) => page.waitForFunction(
    (p) => { const s = document.getElementById("mainImage").src; return s && s !== p && s.length > 2000; },
    prev, { timeout: 20_000 });

  // ASL perfusion: exposes a Perfusion-weighted / CBF Map picker; selecting it and
  // switching to the CBF map must re-render (the engine renders perfusion via Pyodide).
  let prevSrc = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#sequence", "Perfusion (ASL)");
  await page.waitForSelector("#perfdisp-row:not([hidden])", { timeout: 5_000 });
  await rendered(prevSrc);                                 // wait for the perfusion-weighted render
  prevSrc = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#perfdisp", "CBF Map");
  await rendered(prevSrc);                                 // switching the display re-renders

  // DSC/DCE dynamic perfusion: a CBV/CBF/MTT/Ktrans parameter-map picker; switching the
  // map re-renders (the engine computes the maps via Pyodide).
  prevSrc = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#sequence", "Perfusion (Dynamic)");
  await page.waitForSelector("#perfdyndisp-row:not([hidden])", { timeout: 5_000 });
  await rendered(prevSrc);                                 // CBV map render
  prevSrc = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#perfdyndisp", "Ktrans (DCE)");
  await rendered(prevSrc);                                 // Ktrans map re-renders
  await page.selectOption("#sequence", "Spin Echo");

  step("k-space + PSD");
  // Toggling k-space / pulse-diagram reveals their panels and loads a PNG each.
  await page.check("#kspaceshow");
  await page.waitForSelector("#kspacewrap:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("kspaceImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  await page.check("#psdshow");
  await page.waitForSelector("#psdwrap:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("psdImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  await page.uncheck("#kspaceshow");
  await page.uncheck("#psdshow");

  step("physics maps");
  // Parallel imaging: raising R reveals the method picker; the g-factor map then
  // renders the noise-amplification map. The B0 field map renders independently.
  await page.fill("#accel", "3");
  await page.dispatchEvent("#accel", "input");
  await page.waitForSelector("#accelmethod-row:not([hidden])", { timeout: 5_000 });
  await page.check("#gfactorshow");
  await page.waitForSelector("#gfactorwrap:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("gfactorImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  await page.check("#b0mapshow");
  await page.waitForFunction(
    () => { const s = document.getElementById("b0mapImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  await page.uncheck("#gfactorshow");
  await page.uncheck("#b0mapshow");
  await page.fill("#accel", "1");
  await page.dispatchEvent("#accel", "input");

  // Contrast map (TR×TE): toggling on must render the landscape panel.
  await page.check("#cmap");
  await page.waitForSelector("#cmapwrap:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("cmapImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  await page.uncheck("#cmap");

  // Signal curve: switching the curve type re-renders the curve, and the toggle
  // hides/shows its panel.
  {
    const c0 = await page.getAttribute("#curveImage", "src");
    await page.selectOption("#curvemode", "TR recovery");
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("curveImage").src; return s && s !== prev && s.length > 2000; },
      c0, { timeout: 20_000 });
    // The Ernst-angle (flip) curve renders too.
    const c1 = await page.getAttribute("#curveImage", "src");
    await page.selectOption("#curvemode", "Flip angle");
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("curveImage").src; return s && s !== prev && s.length > 2000; },
      c1, { timeout: 20_000 });
    await page.uncheck("#curveshow");
    await page.waitForSelector("#curvewrap", { state: "hidden", timeout: 5_000 });
    await page.check("#curveshow");
    await page.waitForSelector("#curvewrap:not([hidden])", { timeout: 5_000 });
    await page.selectOption("#curvemode", "TE decay");
  }

  // Receive coil: a surface coil shades the image (re-render), then back to ideal.
  {
    const m0 = await page.getAttribute("#mainImage", "src");
    await page.selectOption("#receivecoil", "surface");
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev && s.length > 2000; },
      m0, { timeout: 20_000 });
    await page.selectOption("#receivecoil", "uniform");
  }

  // Keyboard slice navigation (blur any focused control first — the handler
  // intentionally ignores keys while an input/select is focused).
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  const kBefore = await page.inputValue("#slice");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(600);
  if (await page.inputValue("#slice") === kBefore) fail("keyboard did not change the slice");
  // The keyboard change must also be reflected on the vertical slice rail.
  if (await page.inputValue("#slice-v") !== await page.inputValue("#slice")) fail("slice rail out of sync with #slice");

  // The vertical slice rail beside the image must drive the slice too.
  {
    const before = await page.inputValue("#slice");
    const target = String(Math.max(0, +before - 12));
    await page.evaluate((v) => { const r = document.getElementById("slice-v"); r.value = v; r.dispatchEvent(new Event("input")); }, target);
    await page.waitForTimeout(600);
    if (await page.inputValue("#slice") === before) fail("slice rail did not change the slice");
    // …and it must span most of the image height (so a small drag ≠ many slices).
    const railH = await page.$eval("#slice-v", (el) => el.offsetHeight);
    if (railH < 120) fail("slice rail too short (offsetHeight=" + railH + "px)");
  }

  // A new acquisition control (NEX) must re-render and the URL must stay shareable.
  const beforeNex = await page.getAttribute("#mainImage", "src");
  await page.evaluate(() => { const e = document.getElementById("nex"); e.value = 3; e.dispatchEvent(new Event("input")); });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    beforeNex, { timeout: 15_000 });
  const shareHash = await page.evaluate(() => location.hash);
  if (shareHash.length <= 1) fail("URL hash was not updated for sharing");
  // Share-links carry a schema version (v=) so old links can be migrated, not misapplied.
  if (!/(?:^#|[#&])v=\d+/.test(shareHash)) fail("share-link missing schema version (v=): " + shareHash);
  // Curve state (type + visibility) is part of the shareable link.
  if (!/[#&]curvemode=/.test(shareHash)) fail("share-link missing curve mode: " + shareHash);
  if (!/[#&]curveshow=/.test(shareHash)) fail("share-link missing curve visibility: " + shareHash);
  if (!/[#&]receivecoil=/.test(shareHash)) fail("share-link missing receive coil: " + shareHash);
  // A legacy link with no v= must still apply (back-compat), and a future v must not throw.
  for (const legacy of ["#region=Brain&seq=Spin%20Echo&tr=1800", "#v=999&region=Brain&tr=2600"]) {
    await page.evaluate((h) => { location.hash = h; return window.applyHashState(); }, legacy);
    await page.waitForTimeout(300);
  }

  // Download must produce a .png.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.click("#download"),
  ]);
  if (!download.suggestedFilename().endsWith(".png")) fail("download is not a .png: " + download.suggestedFilename());

  step("lessons");
  // Guided lessons: open the picker, start a lesson, advance a step.
  await page.click("#lessons-btn");
  await page.waitForSelector("#lesson-picker:not([hidden])", { timeout: 5_000 });
  // Accessibility: the picker is a dialog and Escape closes it (then reopen).
  if ((await page.getAttribute("#lesson-picker", "role")) !== "dialog") fail("lesson-picker not role=dialog");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#lesson-picker", { state: "hidden", timeout: 5_000 });
  await page.click("#lessons-btn");
  await page.waitForSelector("#lesson-picker:not([hidden])", { timeout: 5_000 });
  // The corner ✕ closes the picker too (exit without picking a lesson).
  await page.click("#lesson-picker-x");
  await page.waitForSelector("#lesson-picker", { state: "hidden", timeout: 5_000 });
  await page.click("#lessons-btn");
  await page.waitForSelector("#lesson-picker:not([hidden])", { timeout: 5_000 });
  // The long lesson list scrolls inside the card (so the footer stays reachable).
  const listScrolls = await page.$eval("#lesson-list", (el) => getComputedStyle(el).overflowY);
  if (!/auto|scroll/.test(listScrolls)) fail("lesson list is not scrollable: " + listScrolls);
  // The beginner "Start here" track must be present and listed first.
  const sections = await page.$$eval("#lesson-list .lesson-section", (ps) => ps.map((p) => p.textContent));
  if (!sections.some((s) => /start here/i.test(s || ""))) fail("beginner 'Start here' lesson section missing");
  if (!(await page.$("#lesson-list .lesson-item.beginner"))) fail("no beginner lesson rendered");
  await page.click("#lesson-list .lesson-item");
  await page.waitForSelector("#lesson-panel:not([hidden])", { timeout: 5_000 });
  const step1 = await page.textContent("#lesson-step");
  const imgBeforeStep = await page.getAttribute("#mainImage", "src");
  await page.click("#lesson-next");
  await page.waitForFunction(
    (prev) => document.getElementById("lesson-step").textContent !== prev, step1, { timeout: 5_000 });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    imgBeforeStep, { timeout: 15_000 });
  await page.click("#lesson-exit");
  await page.waitForSelector("#lesson-panel", { state: "hidden", timeout: 5_000 });

  step("curriculum");
  // Guided curriculum: the launcher lists modules with a progress bar; Continue
  // starts a lesson in curriculum mode (a path indicator shows), and finishing a
  // lesson advances to the next one in the path.
  await page.evaluate(() => { try { localStorage.removeItem("mrisim_curriculum"); } catch (e) {} });
  // The launcher button is an interactive pill like Lessons (pointer cursor).
  if ((await page.$eval("#curriculum-btn", (el) => getComputedStyle(el).cursor)) !== "pointer")
    fail("curriculum button should have a pointer cursor like the lessons button");
  await page.click("#curriculum-btn");
  await page.waitForSelector("#curriculum:not([hidden])", { timeout: 5_000 });
  if ((await page.getAttribute("#curriculum", "role")) !== "dialog") fail("curriculum not role=dialog");
  const modules = await page.$$eval("#curriculum-list .cur-module", (els) => els.length);
  if (modules < 4) fail("curriculum should list its modules, got " + modules);
  await page.click("#curriculum-start");
  await page.waitForSelector("#lesson-panel:not([hidden])", { timeout: 5_000 });
  await page.waitForSelector("#lesson-cur:not([hidden])", { timeout: 5_000 });
  const curText = await page.textContent("#lesson-cur");
  if (!/curriculum/i.test(curText || "")) fail("curriculum path indicator missing: " + curText);
  // Finish the first lesson; the curriculum must advance to a different lesson.
  const title0 = await page.textContent("#lesson-title");
  let advanced = false;
  for (let i = 0; i < 8 && !advanced; i++) {
    await page.click("#lesson-next");
    await page.waitForTimeout(500);
    advanced = (await page.textContent("#lesson-title")) !== title0;
  }
  if (!advanced) fail("curriculum did not advance to the next lesson on finish");
  await page.click("#lesson-exit");
  await page.waitForSelector("#lesson-panel", { state: "hidden", timeout: 5_000 });

  step("abdomen atlas");
  // Real body atlas: switching to Abdomen lazy-fetches its segmented atlas and
  // renders real anatomy.
  const beforeRegion = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#region", "Abdomen");
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s.startsWith("data:image/png") && s !== prev; },
    beforeRegion, { timeout: 45_000 });        // includes the one-time atlas fetch

  step("service worker (offline)");
  // The network-first service worker must register, take control, and serve a
  // cached shell asset when the network drops (offline-after-first-load). We test
  // the fallback path on a small shell file (not a full Pyodide reboot).
  await page.waitForFunction(
    () => navigator.serviceWorker && navigator.serviceWorker.controller, { timeout: 20_000 });
  await page.evaluate(() => fetch("styles.css").then((r) => r.text()));   // warm the cache
  await page.context().setOffline(true);
  const offlineOk = await page.evaluate(async () => {
    try { const r = await fetch("styles.css"); return r.ok; } catch (e) { return false; }
  });
  await page.context().setOffline(false);
  if (!offlineOk) fail("service worker did not serve a cached shell asset offline");

  step("worker-crash resilience");
  // MUST be last: simulate the engine worker crashing. The UI must surface an error
  // and fail subsequent calls instead of hanging silently. (Permanently kills the
  // worker for this page, hence last; the console breadcrumb is a warn, not error.)
  await page.evaluate(() => window.onWorkerCrash(new ErrorEvent("error", { message: "simulated crash" })));
  await page.waitForFunction(
    () => /Engine error/.test(document.getElementById("hint").textContent || ""), { timeout: 5_000 });
  const callRejected = await page.evaluate(async () => {
    try { await window.call("render", {}); return false; } catch (e) { return true; }
  });
  if (!callRejected) fail("call() did not reject after the worker crashed — UI would hang");

  if (errors.length) fail("console/page errors during smoke");
  console.log("SMOKE OK — render, metrics, intro, sequence/preset, compare, window-level, scout, keyboard, controls, share-URL, download, lessons, real body atlas, offline service worker, and worker-crash resilience all work.");
  await browser.close();
  process.exit(0);
} catch (e) {
  fail(e.message);
}
