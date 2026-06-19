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
page.on("console", (m) => {
  if (m.type() !== "error") return;
  // image-library exams reference per-part image files that may not exist yet and
  // fall back to a placeholder — those 404s are expected, not a failure.
  const loc = (m.location() && m.location().url) || "";
  if (/img\/exams\//.test(loc) || /img\/exams\//.test(m.text())) return;
  errors.push(m.text());
});
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

  // the interactive planning layer is a client-side SVG overlay: cross panels carry the
  // band + angle handles (rects), the acquired plane carries the FOV box + handles.
  await page.waitForFunction(
    () => document.querySelectorAll("#vp-sagittal svg.pp-ov rect, #vp-sagittal svg.pp-ov circle").length > 0
       && document.querySelectorAll("#vp-axial svg.pp-ov rect").length >= 4,
    { timeout: 10_000 });
  console.log("client SVG overlay handles render ✓");

  // angling follows the drag: grab the right end of the band on the sagittal scout and
  // drag it UP → tilt goes positive (right end up), not the opposite way. The band moves
  // client-side on pointermove (no server round-trip) — tilt updates before pointerup.
  const tiltDuringDrag = await page.evaluate(() => {
    const img = document.querySelector("#vp-sagittal img"); const r = img.getBoundingClientRect();
    const x = r.left + r.width * 0.82, y0 = r.top + r.height * 0.5, y1 = r.top + r.height * 0.25;
    img.dispatchEvent(new PointerEvent("pointerdown", { button: 0, clientX: x, clientY: y0, bubbles: true }));
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: x, clientY: y1, bubbles: true }));
    const t = parseFloat(document.querySelector("#pp-tilt").value);   // set synchronously, no server
    window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
    return t;
  });
  if (!(tiltDuringDrag > 0)) fail("angle drag did not update tilt client-side during the drag");
  console.log("angle follows the drag, client-side ✓ (tilt =", tiltDuringDrag + ")");
  await page.dblclick("#vp-sagittal");                // reset the prescription
  await page.waitForFunction(() => document.querySelector("#pp-tilt").value === "0", { timeout: 6_000 });

  // grabbing the CENTRE of the band moves the slice package (not the angle): drag the
  // centre handle perpendicular → tilt stays 0 and the slice position changes.
  const centreDrag = await page.evaluate(() => {
    const img = document.querySelector("#vp-sagittal img"); const r = img.getBoundingClientRect();
    const x = r.left + r.width * 0.5, y0 = r.top + r.height * 0.5, y1 = r.top + r.height * 0.3;
    img.dispatchEvent(new PointerEvent("pointerdown", { button: 0, clientX: x, clientY: y0, bubbles: true }));
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: x, clientY: y1, bubbles: true }));
    const out = { tilt: parseFloat(document.querySelector("#pp-tilt").value),
                  readout: document.querySelector("#pp-readout").textContent };
    window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
    return out;
  });
  if (centreDrag.tilt !== 0) fail("grabbing the band centre angled the plane instead of moving it");
  if (!/slice\s+\d/.test(centreDrag.readout)) fail("grabbing the band centre did not move the slice position");
  console.log("band centre moves the slice package (not angle) ✓");
  await page.dblclick("#vp-sagittal");                // reset again
  await page.waitForFunction(() => document.querySelector("#pp-tilt").value === "0", { timeout: 6_000 });

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

  // scan time + SNR readout, and the protocol total time in the queue header
  const rd = await page.textContent("#pp-readout");
  if (!/\d:\d{2}.*SNR/.test(rd)) fail("scan time / SNR not shown after acquire");
  const totalTxt = await page.textContent("#pp-total");
  if (!/\d:\d{2}/.test(totalTxt)) fail("protocol total time not shown");
  console.log("scan time + SNR ✓  (total:", JSON.stringify(totalTxt) + ")");

  // window/level via right-drag changes the image's CSS filter
  await page.evaluate(() => {
    const box = document.querySelector("#vp-axial");
    box.dispatchEvent(new PointerEvent("pointerdown", { button: 2, clientX: 100, clientY: 100, bubbles: true }));
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 170, clientY: 50, bubbles: true }));
    window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
  });
  await page.waitForFunction(
    () => { const im = document.querySelector("#vp-axial img"); return im && /brightness|contrast/.test(im.style.filter); },
    { timeout: 6_000 });
  console.log("window/level ✓");

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

  // double-click a scout resets the prescription (angle it, then undo)
  await page.fill("#pp-tilt", "20");
  await page.dispatchEvent("#pp-tilt", "input");
  await page.dblclick("#vp-coronal");
  await page.waitForFunction(() => document.querySelector("#pp-tilt").value === "0", { timeout: 6_000 });
  console.log("double-click reset ✓");

  // sequence-relevant params: FLAIR (IR) shows TI; MPRAGE (3-D) labels the count "Partitions"
  await page.click("#pp-list li:nth-child(4)");                      // FLAIR
  await page.waitForFunction(() => !document.querySelector("#pp-ti-row").hidden, { timeout: 12_000 });
  await page.click("#pp-list li:nth-child(8)");                      // MPRAGE (3-D)
  await page.waitForFunction(
    () => document.querySelector("#pp-nsl-label").textContent === "Partitions", { timeout: 12_000 });
  console.log("sequence params (TI) + 3-D partitions ✓");

  // the acquisition honours the prescription: acquiring at tilt 0 vs 30 must differ
  const acquireTilt = async (deg) => {
    await page.click("#pp-list li:nth-child(2)");                    // re-open T1 (resets scouts)
    await page.waitForFunction(() => !document.querySelector("#pp-controls").hidden, { timeout: 12_000 });
    await page.fill("#pp-tilt", String(deg)); await page.dispatchEvent("#pp-tilt", "input");
    await page.waitForTimeout(700);
    await page.click("#pp-apply");
    await page.waitForFunction(() => /Acquired/.test(document.querySelector("#pp-readout").textContent), { timeout: 30_000 });
    return page.getAttribute("#vp-axial img", "src");
  };
  const a0 = await acquireTilt(0), a30 = await acquireTilt(30);
  if (a0 === a30) fail("the acquired image ignored the prescribed tilt");
  console.log("acquisition honours the prescription (tilt) ✓");

  // switch the exam to Spine → the queue reloads with the spine protocol (lazy-loads
  // the spine atlas the first time, so give it room).
  await page.selectOption("#pp-exam", "Spine");
  await page.waitForFunction(
    () => [...document.querySelectorAll("#pp-list li .q-label")].some((e) => /sag/i.test(e.textContent)),
    { timeout: 90_000 });
  console.log("exam switch → Spine protocol ✓");

  // and to Abdomen → the liver/abdomen queue loads (lazy-loads the abdomen atlas;
  // wait for an abdomen-unique label, e.g. the VIBE post-Gd series).
  await page.selectOption("#pp-exam", "Abdomen");
  await page.waitForFunction(
    () => [...document.querySelectorAll("#pp-list li .q-label")].some((e) => /VIBE|phase/i.test(e.textContent)),
    { timeout: 90_000 });
  console.log("exam switch → Abdomen protocol ✓");

  // the exam picker exposes all the protocol exams (data-driven from protocols.py);
  // assert Pelvis is offered without paying for another atlas load.
  const exams = await page.$$eval("#pp-exam option", (os) => os.map((o) => o.value));
  for (const want of ["Brain", "Spine", "Knee", "Abdomen", "Pelvis"]) {
    if (!exams.includes(want)) fail(`exam picker missing "${want}" (has ${exams.join(", ")})`);
  }
  console.log("exam picker offers Brain/Spine/Knee/Abdomen/Pelvis ✓");

  // image-library exams (no engine): static scout images you can angle on (cosmetic),
  // and an example image (placeholder until real ones are dropped in) on Acquire.
  for (const want of ["Ankle", "Wrist", "Shoulder", "Foot"]) {
    if (!exams.includes(want)) fail(`image-library exam "${want}" not offered`);
  }
  await page.selectOption("#pp-exam", "Ankle");
  await page.waitForFunction(
    () => [...document.querySelectorAll("#pp-list li .q-label")].some((e) => /T1 Sagittal/.test(e.textContent)),
    { timeout: 10_000 });
  await page.waitForFunction(() => {                      // static placeholder scout loads
    const im = document.querySelector("#vp-axial img");
    return im && im.src.startsWith("data:image/svg");
  }, { timeout: 8_000 });
  await page.click("#pp-list li:nth-child(2)");           // T1 Sagittal
  await page.waitForFunction(() => !document.querySelector("#pp-actions").hidden, { timeout: 8_000 });
  await page.click("#pp-apply");                          // acquire → example image pops up
  await page.waitForFunction(
    () => /example/i.test(document.querySelector("#pp-readout").textContent), { timeout: 8_000 });
  console.log("image-library exam (Ankle): static scouts + example acquire ✓");
} catch (e) {
  fail(e.message);
}

if (errors.length) { console.error("console errors:\n" + errors.join("\n")); process.exitCode = 1; }
await browser.close();
console.log(process.exitCode ? "PROTOCOL SMOKE FAILED" : "PROTOCOL SMOKE PASSED");
