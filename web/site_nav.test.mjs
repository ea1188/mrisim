// Shared-header guard: every page carries the SAME site header (brand, primary
// links in the same order, menu button, sign-in) so navigation never drifts
// page to page again. Page-specific controls live inside the header's
// <div class="site-slot"> and are the only part allowed to differ.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Pages that are deliberately not part of the site chrome: the standalone
// feature walkthrough and the anonymous feedback survey.
const PAGES = [
  "index", "simulator", "protocol", "course", "reference", "quiz",
  "account", "about", "contact", "credits", "privacy", "terms",
];

const PRIMARY = [
  ["simulator", "Simulator"], ["protocol", "Planner"], ["course", "Course"],
  ["reference", "Reference"], ["quiz", "Quiz"],
];

function html(page) {
  return readFileSync(new URL(`./${page}.html`, import.meta.url), "utf8");
}

function header(page) {
  const m = /<header class="site-nav"[^>]*>([\s\S]*?)<\/header>/.exec(html(page));
  assert.ok(m, `${page}.html has one <header class="site-nav">`);
  return m[1];
}

// Strip the page slot (free-form) so the rest can be compared verbatim.
function chrome(page) {
  const h = header(page)
    .replace(/<div class="site-slot">[\s\S]*?<\/div>\s*<!-- \/site-slot -->/, "")
    .replace(/ aria-current="page"/g, "");
  return h.replace(/\s+/g, " ").trim();
}

for (const page of PAGES) {
  test(`${page}.html: exactly one shared header, no legacy header`, () => {
    const src = html(page);
    assert.equal((src.match(/<header class="site-nav"/g) || []).length, 1);
    for (const legacy of ['<nav class="nav">', 'id="topbar"', 'id="pp-head"', 'id="qz-head"', '<div class="top" role="banner">', '<div class="top">\n']) {
      assert.ok(!src.includes(legacy), `${page}.html still has legacy header ${legacy}`);
    }
    assert.ok(src.includes('<script src="site_nav.js"></script>'), `${page}.html loads site_nav.js`);
    assert.ok(src.includes('<link rel="stylesheet" href="site_nav.css" />'), `${page}.html loads site_nav.css`);
  });

  test(`${page}.html: brand, primary links in order, menu button, sign-in`, () => {
    const h = header(page);
    assert.ok(/<a class="site-brand" href="index\.html">\s*<img class="site-mark" src="logo-nav\.png" alt=""[^>]*\/>\s*MRISim\s*<\/a>/.test(h), "brand");
    assert.ok(/<button class="site-menu" type="button" aria-expanded="false" aria-controls="site-links" aria-label="Menu">/.test(h), "menu button");
    const links = [...h.matchAll(/<nav class="site-links" id="site-links"[^>]*>([\s\S]*?)<\/nav>/g)];
    assert.equal(links.length, 1, "one primary nav");
    const found = [...links[0][1].matchAll(/<a href="([a-z]+)\.html"( aria-current="page")?>([^<]+)<\/a>/g)]
      .map((m) => [m[1], m[3]]);
    assert.deepEqual(found, PRIMARY, "primary links and order");
    assert.ok(h.includes('<div class="site-slot">'), "page slot present");
    assert.ok(/<a class="site-signin accounts-only" href="account\.html" hidden>Sign in<\/a>/.test(h), "sign-in link");
  });

  test(`${page}.html: aria-current marks its own primary link`, () => {
    const h = header(page);
    const own = PRIMARY.find(([p]) => p === page);
    const current = [...h.matchAll(/href="([a-z]+)\.html" aria-current="page"/g)].map((m) => m[1]);
    assert.deepEqual(current, own ? [own[0]] : [], "aria-current only on this page's own link");
  });
}

test("the header chrome is byte-identical across pages (slot aside)", () => {
  const ref = chrome("index");
  for (const page of PAGES) assert.equal(chrome(page), ref, `${page}.html header differs from index.html`);
});
