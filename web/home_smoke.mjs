/* Headless smoke for the home/launcher page: the three mode cards are present, and an
 * old deep link (index.html#<state>) redirects to the simulator, preserving the hash.
 * Run: node web/home_smoke.mjs <base-url> */
import { chromium } from "playwright";

const base = (process.argv[2] || "http://localhost:8765/").replace(/\/?$/, "/");
const browser = await chromium.launch();
const page = await browser.newPage();
const fail = (m) => { console.error("FAIL:", m); process.exitCode = 1; };

try {
  // Old shareable deep links (index.html#<state>) must redirect to the simulator,
  // carrying the hash so existing links keep working. This must be a FRESH load — a
  // real user arrives at index.html#hash directly, so the head-script redirect runs on
  // parse. (Do it first: navigating index.html → index.html#test is a same-document
  // fragment nav that wouldn't re-run the script.) Poll page.url() rather than
  // waitForURL, which races with the cancel-and-replace navigation.
  await page.goto(base + "index.html#test", { waitUntil: "commit" }).catch(() => {});
  let target = page.url();
  for (let i = 0; i < 60 && !/simulator\.html#test$/.test(target); i++) {
    await page.waitForTimeout(200);
    target = page.url();
  }
  if (!/simulator\.html#test$/.test(target)) fail(`deep link did not redirect (final url: ${target})`);
  else console.log("deep-link redirect index.html#… → simulator.html ✓");

  // The launcher (no hash) shows cards linking to the three modes.
  await page.goto(base + "index.html", { waitUntil: "domcontentloaded" });
  const hrefs = await page.$$eval("#home .card", (a) => a.map((x) => x.getAttribute("href")));
  for (const h of ["simulator.html", "protocol.html", "quiz.html"]) {
    if (!hrefs.includes(h)) fail(`launcher is missing a card linking to ${h} (got ${JSON.stringify(hrefs)})`);
  }
  if (!process.exitCode) console.log(`launcher shows ${hrefs.length} mode cards ✓  (${hrefs.join(", ")})`);

  if (process.exitCode) console.error("HOME SMOKE FAILED"); else console.log("HOME SMOKE PASSED");
} catch (e) {
  fail(e.message); console.error("HOME SMOKE FAILED");
} finally {
  await browser.close();
}
