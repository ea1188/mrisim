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
  // suppress the first-visit auto-tour so it doesn't overlay the planning-flow steps
  await page.addInitScript(() => { try { localStorage.setItem("mrisim_pp_tour", "1"); } catch (e) { /* private mode */ } });
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

  // re-grab the now-TILTED band and angle again — it must keep changing, not lock at the
  // first angle. (The bug: the hit-test used the straight band position, so once the plane
  // was oblique the tilted band fell outside it and every later grab read as a slice move.)
  await page.waitForFunction(() => {
    const g = (window.vpGeom || {}).sagittal;
    return g && g.band && Math.abs(g.band[0][1] - g.band[1][1]) > 0.05;   // band is now oblique
  }, { timeout: 8_000 });
  const reangle = await page.evaluate(() => {
    const img = document.querySelector("#vp-sagittal img"), r = img.getBoundingClientRect();
    const g = (window.vpGeom || {}).sagittal; if (!g || !g.band) return null;
    const nAR = img.naturalWidth / img.naturalHeight, eAR = r.width / r.height;
    let cw, ch, ox, oy;
    if (eAR > nAR) { ch = r.height; cw = ch * nAR; ox = (r.width - cw) / 2; oy = 0; }
    else { cw = r.width; ch = cw / nAR; ox = 0; oy = (r.height - ch) / 2; }
    const cc = g.center || [0.5, 0.5], b = g.band;
    const gx = b[0][0] + (b[1][0] - b[0][0]) * 0.85, gy = b[0][1] + (b[1][1] - b[0][1]) * 0.85;  // on the band, near an end
    const rx = gx - cc[0], ry = gy - cc[1], rl = Math.hypot(rx, ry) || 1;
    const tx = -ry / rl, ty = rx / rl;             // unit tangent (perp to the radius) → changes the angle
    const cx = r.left + ox + gx * cw, cy = r.top + oy + gy * ch;
    const before = parseFloat(document.querySelector("#pp-tilt").value);
    img.dispatchEvent(new PointerEvent("pointerdown", { button: 0, clientX: cx, clientY: cy, bubbles: true }));
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: cx + tx * cw * 0.22, clientY: cy + ty * ch * 0.22, bubbles: true }));
    const after = parseFloat(document.querySelector("#pp-tilt").value);
    window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
    return { before, after };
  });
  if (!reangle || reangle.after === reangle.before) {
    fail("re-grabbing the tilted band did not change the angle (locked): " + JSON.stringify(reangle));
  } else console.log("re-grab the tilted band keeps angling ✓ (tilt " + reangle.before + " → " + reangle.after + ")");

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

  // double-click a scout resets the prescription (angle it, then undo). The append above
  // re-rendered the queue/params, so wait for the tilt control to settle before driving it
  // — filling it mid-re-render intermittently hit a detached input (30 s timeout flake).
  await page.waitForFunction(() => {
    const e = document.querySelector("#pp-tilt");
    return e && !e.disabled && e.offsetParent !== null;
  }, { timeout: 12_000 });
  await page.fill("#pp-tilt", "20");
  await page.dispatchEvent("#pp-tilt", "input");
  await page.dblclick("#vp-coronal");
  await page.waitForFunction(() => document.querySelector("#pp-tilt").value === "0", { timeout: 6_000 });
  console.log("double-click reset ✓");

  // sequence-relevant params: FLAIR (IR) shows TI; MPRAGE (3-D) labels the count "Partitions".
  // Select by label text (robust to protocol queue reordering / added sequences).
  await page.click("#pp-list li:has-text('FLAIR')");                 // FLAIR
  await page.waitForFunction(() => !document.querySelector("#pp-ti-row").hidden, { timeout: 12_000 });
  await page.click("#pp-list li:has-text('MPRAGE')");                // MPRAGE (3-D)
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
  // and an example image on Acquire (a real drop-in image, or a placeholder until one is added).
  for (const want of ["Ankle", "Wrist", "Shoulder", "Foot"]) {
    if (!exams.includes(want)) fail(`image-library exam "${want}" not offered`);
  }
  await page.selectOption("#pp-exam", "Ankle");
  await page.waitForFunction(
    () => [...document.querySelectorAll("#pp-list li .q-label")].some((e) => /PD FS/.test(e.textContent)),
    { timeout: 10_000 });
  await page.waitForFunction(() => {                      // scout loads (real image or placeholder)
    const im = document.querySelector("#vp-axial img");
    return im && im.complete && im.naturalWidth > 0;
  }, { timeout: 8_000 });
  await page.click("#pp-list li:nth-child(2)");           // first sequence after the localizer (PD Axial → axial)
  await page.waitForFunction(() => !document.querySelector("#pp-actions").hidden, { timeout: 8_000 });
  await page.waitForFunction(                             // in-plane FOV box drawn on the matching (axial) scout
    () => !!document.querySelector("#vp-axial svg.pp-ov rect[stroke='#7fb8ff']"), { timeout: 8_000 });
  // a cross scout shows an angle band; dragging near its centre MOVES the slice
  await page.waitForFunction(
    () => !!document.querySelector("#vp-sagittal svg.pp-ov line[stroke='#ffdd44']"), { timeout: 5_000 });
  const bandY0 = await page.$eval("#vp-sagittal svg.pp-ov line[stroke='#ffdd44']", (l) => +l.getAttribute("y1"));
  const vbb = await (await page.$("#vp-sagittal")).boundingBox();
  const mx = vbb.x + vbb.width / 2, my = vbb.y + vbb.height / 2;
  await page.mouse.move(mx, my); await page.mouse.down();
  await page.mouse.move(mx, my + Math.round(vbb.height * 0.12), { steps: 4 });
  await page.mouse.up();
  await page.waitForFunction((prev) => {                  // the band moved with the cursor
    const l = document.querySelector("#vp-sagittal svg.pp-ov line[stroke='#ffdd44']");
    return l && Math.abs(+l.getAttribute("y1") - prev) > 1;
  }, bandY0, { timeout: 5_000 });
  console.log("image-exam: in-plane FOV box + slice move on cross scout ✓");

  // angle drag: grab the band's actual on-screen end on a cross scout and rotate → it tilts
  const covRect = await (await page.$("#vp-coronal svg.pp-ov")).boundingBox();
  const band = await page.$eval("#vp-coronal svg.pp-ov line[stroke='#ffdd44']",
    (l) => ["x1", "y1", "x2", "y2"].map((a) => +l.getAttribute(a)));
  const dy0 = Math.abs(band[3] - band[1]);
  const end = band[2] >= band[0] ? [band[2], band[3]] : [band[0], band[1]];   // the right-hand end
  const sx = covRect.x + end[0], sy = covRect.y + end[1];
  await page.mouse.move(sx, sy); await page.mouse.down();
  await page.mouse.move(sx, sy + covRect.height * 0.25, { steps: 5 });
  await page.mouse.up();
  await page.waitForFunction((prev) => {                  // the band gained a vertical tilt
    const l = document.querySelector("#vp-coronal svg.pp-ov line[stroke='#ffdd44']");
    return l && Math.abs(+l.getAttribute("y2") - +l.getAttribute("y1")) > prev + 5;
  }, dy0, { timeout: 5_000 });
  console.log("image-exam: angle drag tilts the band ✓");

  // The angle drag above captured the pointer on the viewport and kicked off a debounced
  // overlay/scout update. Clicking a queue item immediately after intermittently hung on
  // Playwright's actionability check (the recurring 30 s timeout in this smoke): move the
  // pointer off the viewport to drop the capture context, then let it settle first.
  await page.mouse.move(4, 4);
  await page.waitForTimeout(600);

  // presets orient the slice to the acquired plane: a sagittal sequence's cross band is vertical
  await page.click("#pp-list li:nth-child(3)");           // PD Sagittal → sagittal plane
  await page.waitForFunction(() => {
    const l = document.querySelector("#vp-coronal svg.pp-ov line[stroke='#ffdd44']");
    if (!l) return false;
    const dx = Math.abs(+l.getAttribute("x2") - +l.getAttribute("x1"));
    const dy = Math.abs(+l.getAttribute("y2") - +l.getAttribute("y1"));
    return dy > dx * 1.5;                                  // vertical band for a sagittal acquisition
  }, { timeout: 5_000 });
  console.log("image-exam: preset band orients to the acquired plane ✓");
  await page.click("#pp-list li:nth-child(2)");           // back to PD Axial to acquire
  await page.waitForFunction(() => !document.querySelector("#pp-actions").hidden, { timeout: 8_000 });
  await page.click("#pp-apply");                          // acquire → example image pops up
  await page.waitForFunction(
    () => /example/i.test(document.querySelector("#pp-readout").textContent), { timeout: 8_000 });
  const credit = await page.$eval("#pp-credit", (e) => (e.hidden ? "" : e.textContent));
  if (!/Radiopaedia/.test(credit)) fail(`image exam credit not shown (got "${credit}")`);
  console.log("image-library exam (Ankle): static scouts + in-plane FOV box + example acquire + credit ✓");

  // after acquiring, "↻ Re-prescribe" restores the planning view so you can set it up again
  await page.waitForFunction(() => !document.querySelector("#pp-replan").hidden, { timeout: 5_000 });
  await page.click("#pp-replan");
  await page.waitForFunction(            // the acquired (axial) plane is a plannable scout again (FOV box back)
    () => document.querySelector("#pp-replan").hidden
      && !!document.querySelector("#vp-axial svg.pp-ov rect[stroke='#7fb8ff']"), { timeout: 5_000 });
  console.log("image-exam: re-prescribe restores the planning view ✓");

  // guided tour: opens from the button, steps through, and closes
  await page.click("#pp-tour-btn");
  await page.waitForFunction(() => !document.querySelector("#tour").hidden, { timeout: 5_000 });
  const total = await page.$eval("#tour-progress", (e) => +e.textContent.split("/")[1]);
  if (!(total >= 3)) fail(`tour has too few steps (${total})`);
  for (let i = 0; i < total; i++) await page.click("#tour-next");   // last click = Done → closes
  await page.waitForFunction(() => document.querySelector("#tour").hidden, { timeout: 5_000 });
  console.log(`guided tour: ${total} steps, opens and closes ✓`);

  // mobile layout: a phone-width viewport stacks the views into a single column
  const desktopCols = await page.$eval("#pp-views", (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(
    () => getComputedStyle(document.querySelector("#pp-views")).gridTemplateColumns.split(" ").length === 1,
    { timeout: 5_000 });
  await page.setViewportSize({ width: 1280, height: 720 });
  if (desktopCols !== 3) fail(`desktop views should be 3 columns, got ${desktopCols}`);
  console.log("mobile: views collapse to one column at phone width ✓");
} catch (e) {
  fail(e.message);
}

if (errors.length) { console.error("console errors:\n" + errors.join("\n")); process.exitCode = 1; }
await browser.close();
console.log(process.exitCode ? "PROTOCOL SMOKE FAILED" : "PROTOCOL SMOKE PASSED");
