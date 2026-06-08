/* Headless-browser smoke test for the MRISim web build.
 *
 * Boots the page in headless Chromium (Playwright), waits for Pyodide to load the
 * engine + brain and produce the first render, then asserts the image and metrics
 * actually populated. This is the real "does the browser build work" check that
 * the Python tests can't make. Run by .github/workflows/web-smoke.yml against a
 * locally served `web/`.  Usage: node web/smoke.mjs [url]
 */
import { chromium } from "playwright";

const url = process.argv[2] || "http://localhost:8765/";
const BOOT_TIMEOUT = 180_000;   // first load pulls ~30–50 MB of wheels from the CDN

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

function fail(msg) {
  console.error("SMOKE FAIL:", msg);
  if (errors.length) console.error("page errors:\n" + errors.join("\n"));
  process.exit(1);
}

try {
  await page.goto(url, { waitUntil: "domcontentloaded" });

  // The control panel unhides once Pyodide has booted and the first render lands.
  await page.waitForSelector("#app:not([hidden])", { timeout: BOOT_TIMEOUT });

  // The main image must carry a real PNG data URL.
  await page.waitForFunction(
    () => {
      const s = document.getElementById("mainImage")?.src || "";
      return s.startsWith("data:image/png") && s.length > 2000;
    },
    { timeout: 30_000 },
  );

  // First-run intro must appear, then dismiss it (it overlays the controls).
  await page.waitForSelector("#intro:not([hidden])", { timeout: 10_000 });
  await page.click("#intro-ok");
  await page.waitForSelector("#intro", { state: "hidden", timeout: 5_000 });

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

  // Changing the sequence must re-render without throwing.
  await page.selectOption("#sequence", "Gradient Echo");
  await page.waitForTimeout(1500);
  const src2 = await page.getAttribute("#mainImage", "src");
  if (!src2 || !src2.startsWith("data:image/png")) fail("re-render after sequence change failed");

  // Applying a preset must repopulate controls and re-render.
  const presets = await page.$$eval("#preset option", (os) => os.map((o) => o.value).filter(Boolean));
  if (presets.length === 0) fail("no presets listed");
  const before = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#preset", presets[0]);
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    before, { timeout: 30_000 });

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
  await page.click("#exitAB");
  await page.waitForSelector("#wrapB", { state: "hidden", timeout: 5_000 });

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

  // "Label the anatomy" must re-render the image (named structures drawn on it).
  {
    const before = await page.getAttribute("#mainImage", "src");
    await page.check("#labelanat");
    await page.waitForFunction(
      (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
      before, { timeout: 15_000 });
    await page.uncheck("#labelanat");
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
  const sliceBefore = await page.inputValue("#slice");
  const sb = await page.$eval("#scoutImage", (el) => { const r = el.getBoundingClientRect(); return { w: r.width, h: r.height }; });
  // Element-relative click so events target the scout image regardless of layout.
  // Middle (coronal) panel, low → a row-mapped cross panel in axial acquisition.
  await page.click("#scoutImage", { position: { x: sb.w * 0.5, y: sb.h * 0.82 } });
  await page.waitForTimeout(800);
  const sliceAfter = await page.inputValue("#slice");
  if (sliceAfter === sliceBefore) fail("scout click did not move the slice (before=" + sliceBefore + ")");

  // Dragging the slice band on a cross panel must angle the plane (oblique). The
  // band now sits at y≈0.82 of the coronal panel (the slice we just moved to);
  // grab it and drag up — the oblique readout must report a non-zero angle.
  const sr = await page.$eval("#scoutImage", (el) => {
    const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  await page.mouse.move(sr.x + sr.w * 0.5, sr.y + sr.h * 0.82);
  await page.mouse.down();
  await page.mouse.move(sr.x + sr.w * 0.6, sr.y + sr.h * 0.55, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(900);
  const readout = await page.textContent("#oblique-readout");
  if (/Oblique\s+0°\s*\/\s*0°/.test(readout || "")) fail("oblique drag did not angle the plane (" + readout + ")");

  await page.uncheck("#fovplan");

  // Contrast map (TR×TE): toggling on must render the landscape panel.
  await page.check("#cmap");
  await page.waitForSelector("#cmapwrap:not([hidden])", { timeout: 5_000 });
  await page.waitForFunction(
    () => { const s = document.getElementById("cmapImage")?.src || ""; return s.startsWith("data:image/png") && s.length > 2000; },
    { timeout: 20_000 });
  await page.uncheck("#cmap");

  // Keyboard slice navigation (blur any focused control first — the handler
  // intentionally ignores keys while an input/select is focused).
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  const kBefore = await page.inputValue("#slice");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(600);
  if (await page.inputValue("#slice") === kBefore) fail("keyboard did not change the slice");

  // A new acquisition control (NEX) must re-render and the URL must stay shareable.
  const beforeNex = await page.getAttribute("#mainImage", "src");
  await page.evaluate(() => { const e = document.getElementById("nex"); e.value = 3; e.dispatchEvent(new Event("input")); });
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s !== prev; },
    beforeNex, { timeout: 15_000 });
  if (!(await page.evaluate(() => location.hash.length > 1))) fail("URL hash was not updated for sharing");

  // Download must produce a .png.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.click("#download"),
  ]);
  if (!download.suggestedFilename().endsWith(".png")) fail("download is not a .png: " + download.suggestedFilename());

  // Guided lessons: open the picker, start a lesson, advance a step.
  await page.click("#lessons-btn");
  await page.waitForSelector("#lesson-picker:not([hidden])", { timeout: 5_000 });
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

  // Real body atlas: switching to Abdomen lazy-fetches its segmented atlas and
  // renders real anatomy.
  const beforeRegion = await page.getAttribute("#mainImage", "src");
  await page.selectOption("#region", "Abdomen");
  await page.waitForFunction(
    (prev) => { const s = document.getElementById("mainImage").src; return s && s.startsWith("data:image/png") && s !== prev; },
    beforeRegion, { timeout: 45_000 });        // includes the one-time atlas fetch

  if (errors.length) fail("console/page errors during smoke");
  console.log("SMOKE OK — render, metrics, intro, sequence/preset, compare, window-level, scout, keyboard, controls, share-URL, download, lessons, and real body atlas all work.");
  await browser.close();
  process.exit(0);
} catch (e) {
  fail(e.message);
}
