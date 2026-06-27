// ESLint flat config for the browser build (web/). Static analysis the
// headless-browser smoke test can't give us: undefined variables, typos,
// duplicate keys, unreachable code, etc. — caught fast on every PR.
import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["node_modules/**"] },

  // Main thread: classic script in the browser. `Tour` is the shared tour engine
  // (web/tour.js, loaded before app.js).
  {
    files: ["web/app.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, Tour: "readonly" },
    },
    rules: {
      ...js.configs.recommended.rules,
      // Allow intentionally-unused error bindings (catch (e) { /* ignore */ }).
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
    },
  },

  // Shared tour engine: classic script that defines window.Tour for both pages.
  {
    files: ["web/tour.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
    },
  },

  // Service worker: offline cache, runs in the ServiceWorker global scope.
  {
    files: ["web/sw.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.serviceworker },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
    },
  },

  // Pyodide worker: runs in a Web Worker, pulls in pyodide.js via importScripts.
  {
    files: ["web/worker.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.worker, loadPyodide: "readonly" },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
    },
  },

  // Playwright smoke test: an ES module run under Node. It also contains
  // page.evaluate() callbacks that run in the *browser*, so it legitimately
  // references both Node and browser globals; no-op callbacks (() => {}) are fine.
  {
    files: ["web/*.mjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
];
