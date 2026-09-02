/*
 * A11y — accessibility helpers: text-to-speech with MRI-aware pronunciation,
 * and alt-text generation from engine render setups. UMD like blueprint.js:
 * window.A11y in the browser, module.exports under Node. The speech calls
 * no-op where speechSynthesis is unavailable (Node, very old browsers).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.A11y = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Spoken forms for MRI jargon a generic voice reads badly. Order matters:
  // longer tokens first so "T2*" wins over "T2". Word-boundary matched.
  var SAY = [
    ["T2*", "T two star"], ["T2", "T two"], ["T1", "T one"],
    ["TR", "T R"], ["TE", "T E"], ["TI", "T I"], ["PD", "proton density"],
    ["FOV", "field of view"], ["SNR", "signal to noise ratio"],
    ["CNR", "contrast to noise ratio"], ["SAR", "specific absorption rate"],
    ["NEX", "number of excitations"], ["ETL", "echo train length"],
    ["FSE", "fast spin echo"], ["TSE", "turbo spin echo"],
    ["GRE", "gradient echo"], ["EPI", "echo planar imaging"],
    ["DWI", "diffusion weighted imaging"], ["ADC", "A D C"],
    ["SWI", "susceptibility weighted imaging"], ["CSF", "cerebrospinal fluid"],
    ["MRCP", "M R C P"], ["CHESS", "chess"], ["Gd", "gadolinium"],
    ["B0", "B zero"], ["B1", "B one"], ["1.5T", "1.5 tesla"],
    ["3T", "3 tesla"], ["7T", "7 tesla"], ["mpMRI", "multiparametric MRI"],
  ];

  function speakable(text) {
    var out = String(text == null ? "" : text);
    SAY.forEach(function (p) {
      var esc = p[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      out = out.replace(new RegExp("(^|[^A-Za-z0-9])" + esc + "(?![A-Za-z0-9*])", "g"),
                        "$1" + p[1]);
    });
    out = out.replace(/(\d)\s*ms\b/g, "$1 milliseconds");
    out = out.replace(/(\d)\s*mm\b/g, "$1 millimeters");
    out = out.replace(/°/g, " degrees").replace(/±/g, "plus or minus").replace(/×/g, " by ");
    // Prosody: parentheticals and dashes become comma-breaths, not swallowed.
    out = out.replace(/\s*\(\s*/g, ", ").replace(/\s*\)\s*/g, ", ");
    out = out.replace(/\s+[–—]\s+/g, ", ");
    out = out.replace(/,\s*([.,!?])/g, "$1").replace(/\s{2,}/g, " ").replace(/,\s*$/, "");
    return out.trim();
  }

  // Sentence-level chunks: pleasant rhythm AND a workaround for Chrome's
  // silent truncation of long utterances. Length-capped so run-on sentences
  // still split at the nearest comma.
  function chunks(text, cap) {
    cap = cap || 200;
    var parts = String(text || "").replace(/([.!?])\s+/g, "$1\u0000").split("\u0000")
      .filter(function (t) { return t.trim(); });
    var out = [];
    parts.forEach(function (p) {
      p = p.trim();
      while (p.length > cap) {
        var cut = p.lastIndexOf(", ", cap);
        if (cut < 40) cut = cap;
        out.push(p.slice(0, cut + 1).trim());
        p = p.slice(cut + 1).trim();
      }
      if (p) out.push(p);
    });
    return out;
  }

  // Prefer known-good voices over the platform default (nearly always the
  // worst installed voice). Pure: pass the voice list; an explicit saved
  // preference (by name) wins when still present.
  var VOICE_PREF = [/google us english/i, /\(enhanced\)/i, /samantha/i, /aria/i,
                    /jenny/i, /ava/i, /natural/i];
  function pickVoice(voices, savedName) {
    voices = voices || [];
    if (savedName) {
      var saved = voices.filter(function (v) { return v.name === savedName; })[0];
      if (saved) return saved;
    }
    var en = voices.filter(function (v) { return /^en(-|_|$)/i.test(v.lang || ""); });
    for (var i = 0; i < VOICE_PREF.length; i++) {
      var hit = en.filter(function (v) { return VOICE_PREF[i].test(v.name || ""); })[0];
      if (hit) return hit;
    }
    return en[0] || voices[0] || null;
  }

  // Alt text for an engine-rendered scan, from its render setup (the same
  // payload prerender_course_quiz.py renders from) — so every generated image
  // describes itself without hand-written alt.
  function describeScan(setup) {
    if (!setup) return "MRI scan image";
    var p = setup.params || {};
    var bits = [];
    if (setup.orientation) bits.push(setup.orientation);
    if (setup.region) bits.push(setup.region.toLowerCase());
    bits.push((p.sequence || "MRI").toLowerCase(), "image");
    if (p.field_strength) bits.push("at " + p.field_strength.replace("T", " tesla"));
    var params = [];
    if (p.TR != null) params.push("TR " + p.TR);
    if (p.TE != null) params.push("TE " + p.TE);
    if (p.TI != null) params.push("TI " + p.TI);
    var s = bits.join(" ");
    if (params.length) s += ", " + params.join(", ") + " milliseconds";
    if (p.fatsat_enabled) s += ", with fat saturation";
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  // --- browser speech (no-op under Node) ------------------------------------ //
  var synth = (typeof window !== "undefined" && window.speechSynthesis) || null;
  var queue = [], active = false, onDone = null;
  var PREF_KEY = "mrisim_tts_v1";

  function prefs() {
    try { return JSON.parse(localStorage.getItem(PREF_KEY) || "{}"); }
    catch (e) { return {}; }
  }
  function setPrefs(p) {
    var cur = prefs();
    Object.keys(p || {}).forEach(function (k) { cur[k] = p[k]; });
    try { localStorage.setItem(PREF_KEY, JSON.stringify(cur)); } catch (e) { /* storage off */ }
  }
  function voices() { return synth ? synth.getVoices() : []; }

  function stop() {
    queue = []; active = false;
    if (synth) synth.cancel();
    if (onDone) { var f = onDone; onDone = null; f(); }
  }

  function speaking() { return active; }

  var currentChunk = null;
  function _next() {
    if (!queue.length) { active = false; currentChunk = null; if (onDone) { var f = onDone; onDone = null; f(); } return; }
    var p = prefs();
    currentChunk = queue.shift();
    var u = new SpeechSynthesisUtterance(currentChunk);
    var v = pickVoice(voices(), p.voice);
    if (v) u.voice = v;
    u.rate = p.rate || 0.95;
    u.onend = _next;
    u.onerror = _next;
    synth.speak(u);
  }

  // Re-speak the current sentence with the latest prefs (voice auditioning:
  // a picker change takes effect immediately instead of at the next chunk).
  function refresh() {
    if (!synth || !active || currentChunk == null) return;
    queue.unshift(currentChunk);
    synth.cancel();   // fires the cancelled utterance's end handler -> _next()
  }

  function speak(text, onend) {
    if (!synth) { if (onend) onend(); return false; }
    stop();
    onDone = onend || null;
    queue = chunks(speakable(text));
    active = queue.length > 0;
    if (active) _next(); else stop();
    return active;
  }

  return { speakable: speakable, describeScan: describeScan, chunks: chunks,
           pickVoice: pickVoice, voices: voices, prefs: prefs, setPrefs: setPrefs,
           speak: speak, stop: stop, speaking: speaking, refresh: refresh };
});
