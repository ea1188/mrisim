/* Headless smoke for the Protocol Planning page: boots Pyodide, loads the Brain
 * protocol queue, opens a sequence, tweaks a parameter, and Applies — asserting the
 * acquired image lands in a viewport. Run: node web/protocol_smoke.mjs <base-url> */
import { chromium } from "playwright";

const base = (process.argv[2] || "http://localhost:8765/").replace(/\/?$/, "/");
const url = base + "protocol.html";
const BOOT = 180_000;

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
const fail = (m) => { console.error("FAIL:", m); process.exitCode = 1; };

try {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#pp-root:not([hidden])", { timeout: BOOT });
  console.log("booted");

  const n = await page.$$eval("#pp-list li", (li) => li.length);
  if (n < 6) fail(`queue did not load (${n} items)`); else console.log("queue items:", n);

  // localizer opens by default → all three viewports show scout images
  await page.waitForFunction(
    () => ["sagittal", "coronal", "axial"].every((p) => {
      const im = document.querySelector(`#vp-${p} img`); return im && im.src.startsWith("data:image");
    }), { timeout: 40_000 });
  console.log("localizer scouts rendered");

  // open the T1 sequence (2nd item) → parameter panel appears
  await page.click("#pp-list li:nth-child(2)");
  await page.waitForFunction(() => !document.querySelector("#pp-controls").hidden, { timeout: 15_000 });
  console.log("opened a sequence, TR =", await page.inputValue("#pp-tr"));

  // tweak the in-plane FOV → scouts refresh without error
  await page.fill("#pp-fov", "70");
  await page.dispatchEvent("#pp-fov", "input");
  await page.waitForTimeout(1500);

  // Apply → acquire → the acquired series fills the axial viewport, item marked done
  await page.click("#pp-apply");
  await page.waitForFunction(
    () => document.querySelector("#pp-readout").textContent.includes("Acquired"),
    { timeout: 40_000 });
  const tag = await page.textContent("#vp-axial .vp-tag");
  if (!/acquired/i.test(tag)) fail("acquired image not placed in a viewport");
  const done = await page.$$eval("#pp-list li.acquired", (li) => li.length);
  if (done < 1) fail("queue item not marked acquired");
  console.log("acquired ✓  (axial tag:", JSON.stringify(tag) + ", done:", done + ")");

  // scroll the acquired series → its slice counter (n/max) appears in the tag
  await page.evaluate(() => document.querySelector("#vp-axial").dispatchEvent(
    new WheelEvent("wheel", { deltaY: -1, bubbles: true, cancelable: true })));
  await page.waitForFunction(
    () => /\d+\s*\/\s*\d+/.test(document.querySelector("#vp-axial .vp-tag").textContent),
    { timeout: 8_000 });
  console.log("scroll acquired slices ✓");

  // drag the acquired series from the axial viewport to the coronal viewport; the
  // coronal box shows it and the axial box reverts to its scout. (Native HTML5 drag
  // can't be driven by Playwright's mouse, so dispatch the DnD events with a shared
  // DataTransfer — this exercises the page's real dragstart/drop handlers.)
  await page.evaluate(() => {
    const dt = new DataTransfer();
    const src = document.querySelector("#vp-axial img");
    const dst = document.querySelector("#vp-coronal");
    src.dispatchEvent(new DragEvent("dragstart", { bubbles: true, dataTransfer: dt }));
    dst.dispatchEvent(new DragEvent("dragover", { bubbles: true, dataTransfer: dt }));
    dst.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }));
  });
  await page.waitForFunction(
    () => /acquired/i.test(document.querySelector("#vp-coronal .vp-tag").textContent)
       && !/acquired/i.test(document.querySelector("#vp-axial .vp-tag").textContent),
    { timeout: 8_000 });
  console.log("drag between viewports ✓");

  // double-click the series viewport → its scout returns
  await page.dblclick("#vp-coronal");
  await page.waitForFunction(
    () => !/acquired/i.test(document.querySelector("#vp-coronal .vp-tag").textContent),
    { timeout: 8_000 });
  console.log("double-click revert ✓");

  // append / re-run: the acquired queue item gets a ＋ that clones it to the queue
  const nBefore = await page.$$eval("#pp-list li", (li) => li.length);
  await page.click("#pp-list li.acquired .q-append");
  await page.waitForFunction((n) => document.querySelectorAll("#pp-list li").length === n + 1,
    nBefore, { timeout: 8_000 });
  console.log("append / re-run ✓  (queue", nBefore, "→", nBefore + 1 + ")");
} catch (e) {
  fail(e.message);
}

if (errors.length) { console.error("console errors:\n" + errors.join("\n")); process.exitCode = 1; }
await browser.close();
console.log(process.exitCode ? "PROTOCOL SMOKE FAILED" : "PROTOCOL SMOKE PASSED");
