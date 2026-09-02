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
    return out;
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
  var current = null;

  function stop() {
    if (synth) synth.cancel();
    if (current) { current.onend = null; current = null; }
  }

  function speaking() { return !!(synth && synth.speaking); }

  function speak(text, onend) {
    if (!synth) { if (onend) onend(); return false; }
    stop();
    var u = new SpeechSynthesisUtterance(speakable(text));
    u.onend = function () { current = null; if (onend) onend(); };
    current = u;
    synth.speak(u);
    return true;
  }

  return { speakable: speakable, describeScan: describeScan,
           speak: speak, stop: stop, speaking: speaking };
});
