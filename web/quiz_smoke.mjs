/* Headless smoke for the Read-the-scan quiz: boots Pyodide, renders the first
 * question via the engine, answers it (the known-correct option) and checks the
 * score, then walks the rest to the end summary.
 * Run: node web/quiz_smoke.mjs <base-url> */
import { chromium } from "playwright";

const base = (process.argv[2] || "http://localhost:8765/").replace(/\/?$/, "/");
const url = base + "quiz.html";
const BOOT = 180_000;

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
const fail = (m) => { console.error("FAIL:", m); process.exitCode = 1; };

// check *computed* visibility (not the inline style string) so a CSS display:none
// that JS fails to override is caught here, not only at the next click.
const shown = (id) => getComputedStyle(document.getElementById(id)).display !== "none";
const rendered = () => page.waitForFunction(
  () => {
    const im = document.getElementById("qz-img");
    if (im && im.src.startsWith("data:image") && getComputedStyle(im).display !== "none") return true;
    const pair = document.getElementById("qz-pair");          // "what changed?" image-pair question
    if (pair && getComputedStyle(pair).display !== "none") {
      const a = document.getElementById("qz-imgA"), b = document.getElementById("qz-imgB");
      return a && b && a.complete && b.complete && a.src.startsWith("data:image") && b.src.startsWith("data:image");
    }
    return false;
  },
  { timeout: 25_000 });
const feedbackShown = () => page.waitForFunction(
  () => getComputedStyle(document.getElementById("qz-feedback")).display !== "none" && getComputedStyle(document.getElementById("qz-next")).display !== "none",
  { timeout: 5_000 });
const summaryShown = () => page.evaluate(shown, "qz-summary").catch(() => false);

try {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#qz-root:not([hidden])", { timeout: BOOT });
  console.log("booted");

  // The topic menu appears; pick "All topics" (first button) to run the full set
  await page.waitForFunction(() => document.querySelectorAll("#qz-topics .qz-topic").length >= 2, { timeout: 10_000 });
  const nTopics = await page.$$eval("#qz-topics .qz-topic", (b) => b.length);
  if (nTopics < 2) fail(`expected several topics, got ${nTopics}`); else console.log(`topic menu offers ${nTopics} topics ✓`);
  await page.click("#qz-topics .qz-topic:first-child");

  // Question 1 renders an engine image and offers 4 options
  await rendered();
  const n = await page.$$eval("#qz-options .qz-opt", (b) => b.length);
  if (n !== 4) fail(`expected 4 options, got ${n}`); else console.log("question 1 rendered with 4 options ✓");

  // Options are shuffled, so click the correct one by its (exposed) shuffled position →
  // grades correct and scores 1/1.
  const correctPos = await page.evaluate(() => window.__qzCorrect);
  if (typeof correctPos !== "number") fail("quiz did not expose the correct option position");
  await page.click(`#qz-options .qz-opt:nth-child(${correctPos + 1})`);
  await feedbackShown();
  const fb = await page.textContent("#qz-feedback");
  if (!/Correct/.test(fb)) fail(`correct answer not graded correct (feedback: "${fb}")`);
  const sc = await page.textContent("#qz-score");
  if (!/\b1 \/ 1\b/.test(sc)) fail(`score not 1/1 after a correct answer (got "${sc}")`);
  console.log("answered correctly → graded + scored ✓  (" + sc + ")");

  // Walk the remaining questions to the end summary. The guard must exceed the question
  // count (the full "All topics" pool), so keep it well above how many questions exist.
  await page.click("#qz-next");
  let guard = 0, sawPair = false;
  while (guard++ < 400 && !(await summaryShown())) {
    await rendered();
    if (!sawPair) sawPair = await page.evaluate(
      () => getComputedStyle(document.getElementById("qz-pair")).display !== "none");
    await page.click("#qz-options .qz-opt:first-child");
    await feedbackShown();
    await page.click("#qz-next");
  }
  if (!sawPair) fail("never encountered an image-pair ('what changed?') question in the walk");
  else console.log("image-pair question rendered two scans ✓");
  await page.waitForFunction(() => document.getElementById("qz-summary").style.display !== "none", { timeout: 5_000 });
  const summary = await page.textContent("#qz-summary-score");
  if (!/\d+ \/ \d+\s*\(\d+%\)/.test(summary)) fail(`end summary score malformed (got "${summary}")`);
  console.log("reached end summary ✓  (" + summary + ")");

  // "Choose another topic" returns to the menu
  await page.click("#qz-topics-back");
  await page.waitForFunction(() => getComputedStyle(document.getElementById("qz-menu")).display !== "none", { timeout: 5_000 });
  console.log("back to topic menu ✓");

  if (errors.length) fail("console errors:\n  " + errors.join("\n  "));
  if (process.exitCode) console.error("QUIZ SMOKE FAILED"); else console.log("QUIZ SMOKE PASSED");
} catch (e) {
  fail(e.message); console.error("QUIZ SMOKE FAILED");
} finally {
  await browser.close();
}
