// WCAG AA guard for the shared palette: every text token must hold 4.5:1 on
// every surface it can sit on, in BOTH palette copies (theme.css and the
// simulator's styles.css aliases — they must stay in sync, and this fails if
// either copy regresses).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

function tokens(file) {
  const css = readFileSync(new URL(file, import.meta.url), "utf8");
  const root = /:root\s*{([^}]*)}/.exec(css)[1];
  const out = {};
  for (const m of root.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) out[m[1]] = m[2];
  return out;
}

function luminance(hex) {
  const c = (i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * c(1) + 0.7152 * c(3) + 0.0722 * c(5);
}

function ratio(a, b) {
  const la = luminance(a), lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const CASES = [
  { file: "./theme.css", text: ["text", "muted", "dim"], grounds: ["bg", "bg-2", "panel", "panel-2"] },
  { file: "./styles.css", text: ["text", "text-dim", "text-faint"], grounds: ["bg", "canvas", "raised", "header"] },
];

for (const { file, text, grounds } of CASES) {
  test(`${file} text tokens hold AA on all surfaces`, () => {
    const t = tokens(file);
    for (const fg of text) {
      for (const g of grounds) {
        if (!t[fg] || !t[g]) continue;
        const r = ratio(t[fg], t[g]);
        assert.ok(r >= 4.5, `--${fg} (${t[fg]}) on --${g} (${t[g]}) is ${r.toFixed(2)}:1, needs 4.5:1`);
      }
    }
  });
}

test("the two palette copies agree on shared values", () => {
  const a = tokens("./theme.css"), b = tokens("./styles.css");
  assert.equal(a.dim, b["text-faint"], "--dim (theme.css) must match --text-faint (styles.css)");
  assert.equal(a.muted, b["text-dim"], "--muted must match --text-dim");
  assert.equal(a.text, b.text);
});
