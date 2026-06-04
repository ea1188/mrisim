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

  // Metrics must have populated (not the "—" placeholder).
  const scan = await page.textContent("#x-scan");
  const snr = await page.textContent("#x-snr");
  if (!scan || scan.includes("—")) fail("scan-time metric did not populate: " + scan);
  if (!snr || snr.includes("—")) fail("SNR metric did not populate: " + snr);

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
  await page.waitForSelector("#wrapB[hidden]", { timeout: 5_000 });

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

  if (errors.length) fail("console/page errors during smoke");
  console.log("SMOKE OK — render, metrics, sequence/preset, A/B compare, and window-level all work.");
  await browser.close();
  process.exit(0);
} catch (e) {
  fail(e.message);
}
