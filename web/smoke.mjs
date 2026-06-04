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

  if (errors.length) fail("console/page errors during smoke");
  console.log("SMOKE OK — image rendered, metrics populated, re-render works.");
  await browser.close();
  process.exit(0);
} catch (e) {
  fail(e.message);
}
