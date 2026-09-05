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
    ["DBS", "D B S"], ["B1+rms", "B one plus R M S"],
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
    // Roman numerals in the contexts the course uses them (safety zones,
    // gadolinium agent groups): the voice reads bare "IV" as letters, which is
    // right for intravenous but wrong for "Zone IV". Ranges/pairs first.
    var ROMAN = { I: "1", II: "2", III: "3", IV: "4" };
    out = out.replace(/\b(Zones?|Groups?)\s+(I{1,3}|IV)\s+(or|and|to|through)\s+(I{1,3}|IV)\b/g,
      function (_m, w, a, conj, b) { return w + " " + ROMAN[a] + " " + conj + " " + ROMAN[b]; });
    out = out.replace(/\b(Zones?|Groups?)\s+(I{1,3}|IV)\b/g,
      function (_m, w, n) { return w + " " + ROMAN[n]; });
    // Zone lists that drop the word "Zone" ("four zones, I public through IV
    // magnet room"): a numeral directly before a zone descriptor is a zone.
    out = out.replace(/\b(I{1,3}|IV)\b(?=\s+(public|screening|controlled|magnet))/g,
      function (_m, n) { return ROMAN[n]; });
    // Abbreviations the voice expands like honorifics or words.
    out = out.replace(/\bMR\b/g, "M R");          // else it reads "mister"
    out = out.replace(/\bMS\b/g, "M S");          // else it reads "Ms"
    out = out.replace(/\bIV\b/g, "I V");          // intravenous, letter by letter
    out = out.replace(/\bGd\b/g, "gadolinium");
    out = out.replace(/\b([BP])I-?RADS\b/g, "$1 I rads");   // clinical reading
    out = out.replace(/\s*(?:→|->)\s*/g, " to ");
    // Compound units before single symbols: W/kg would otherwise read "W per kg".
    out = out.replace(/\bW\/kg\b/g, "watts per kilogram");
    out = out.replace(/\bmT\/m\b/g, "millitesla per meter");
    out = out.replace(/\bT\/s\b/g, "tesla per second");
    out = out.replace(/\bHz\/(px|pixel)\b/g, "hertz per pixel");
    out = out.replace(/\bkHz\b/g, "kilohertz").replace(/\bMHz\b/g, "megahertz");
    out = out.replace(/\b[µu]T\b/g, "microtesla");
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
  var allSpoken = [];
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
    queue = []; allSpoken = []; active = false;
    if (synth) synth.cancel();
    if (onDone) { var f = onDone; onDone = null; f(); }
  }

  function speaking() { return active; }

  var currentChunk = null, chunkIndex = -1, onChunk = null;
  function _next() {
    if (!queue.length) { active = false; currentChunk = null; if (onDone) { var f = onDone; onDone = null; f(); } return; }
    var p = prefs();
    currentChunk = queue.shift();
    chunkIndex++;
    if (onChunk) { try { onChunk(chunkIndex); } catch (e) { /* highlight is best-effort */ } }
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
    chunkIndex--;                       // the requeued chunk keeps its index
    synth.cancel();   // fires the cancelled utterance's end handler -> _next()
  }

  // Jump TTS playback to sentence i (the audio bar's drag-to-seek).
  function seekChunk(i) {
    if (!synth || !active || !allSpoken.length) return;
    i = Math.max(0, Math.min(allSpoken.length - 1, Math.round(i)));
    queue = allSpoken.slice(i);
    chunkIndex = i - 1;                 // _next() advances to i and reports it
    currentChunk = null;
    synth.cancel();                     // end handler pulls the new queue head
  }
  function position() { return { index: chunkIndex, total: allSpoken.length }; }

  function speak(text, onend, onchunk) {
    if (!synth) { if (onend) onend(); return false; }
    stop();
    onDone = onend || null;
    onChunk = onchunk || null;
    chunkIndex = -1;
    allSpoken = chunks(text).map(speakable);   // chunk DISPLAY text first: indices align with sentencePlan
    queue = allSpoken.slice();
    active = queue.length > 0;
    if (active) _next(); else stop();
    return active;
  }

  // Chunk counts per card part, mirroring the spoken construction
  // (title, then each body block, then each "Key point: ..." item). The
  // wrapper assigns each part the index range [start, start+count).
  function sentencePlan(title, blockTexts, keypoints, workedBlocks, hooks, traps) {
    var idx = 0;
    function take(text) {
      var n = chunks(text).length;
      var r = { start: idx, count: n };
      idx += n;
      return r;
    }
    var plan = {
      title: take(title + "."),
      blocks: (blockTexts || []).map(function (t) { return take(t); }),
      keypoints: (keypoints || []).map(function (k) { return take("Key point: " + k + "."); }),
    };
    if (workedBlocks && workedBlocks.length) {
      plan.workedHeader = take("Worked example.");
      plan.workedBlocks = workedBlocks.map(function (t) { return take(t); });
    } else {
      plan.workedHeader = null; plan.workedBlocks = [];
    }
    plan.hooks = (hooks || []).map(function (k) { return take("Memory hook: " + k + "."); });
    plan.traps = (traps || []).map(function (k) { return take("Exam trap: " + k + "."); });
    plan.total = idx;
    return plan;
  }

  return { speakable: speakable, describeScan: describeScan, chunks: chunks,
           sentencePlan: sentencePlan,
           pickVoice: pickVoice, voices: voices, prefs: prefs, setPrefs: setPrefs,
           speak: speak, stop: stop, speaking: speaking, refresh: refresh,
           seekChunk: seekChunk, position: position };
});
