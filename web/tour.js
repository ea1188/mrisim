// Shared guided-tour engine: a spotlight (#tour-spot) + tooltip (#tour-pop) over the real
// controls. The main app and the Protocol Planning page use the same #tour DOM and drive
// it from a page-specific steps array via window.Tour — see app.js / protocol.js for the
// per-page TOUR arrays and how they start it.
"use strict";
(function (global) {
  const $ = (id) => document.getElementById(id);
  let STEPS = [], idx = 0, storeKey = "mrisim_tour";

  function start(steps, opts) {
    STEPS = steps || [];
    storeKey = (opts && opts.storageKey) || "mrisim_tour";
    idx = 0;
    $("tour").hidden = false;
    showStep();
    global.addEventListener("resize", reposition);
    global.addEventListener("keydown", onKey);
  }
  function end() {
    $("tour").hidden = true;
    global.removeEventListener("resize", reposition);
    global.removeEventListener("keydown", onKey);
    try { localStorage.setItem(storeKey, "1"); } catch (e) { /* private mode */ }
  }
  function onKey(e) {
    if (e.key === "Escape") end();
    else if (e.key === "ArrowRight") next();
    else if (e.key === "ArrowLeft") prev();
  }
  function next() { if (idx >= STEPS.length - 1) { end(); return; } idx++; showStep(); }
  function prev() { if (idx > 0) { idx--; showStep(); } }

  function showStep() {
    const step = STEPS[idx];
    const el = document.querySelector(step.el);
    if (!el) { next(); return; }                      // skip a control that isn't present
    const sec = el.closest("details.group");
    if (sec && !sec.open) sec.open = true;            // open a collapsed section (main app)
    // skip a target with no layout box (e.g. the curve panel when the curve is hidden)
    if (!el.offsetParent && el.getClientRects().length === 0) { next(); return; }
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    $("tour-title").textContent = step.title;
    $("tour-text").innerHTML = step.text;
    $("tour-progress").textContent = `${idx + 1} / ${STEPS.length}`;
    $("tour-prev").disabled = idx === 0;
    $("tour-next").textContent = idx === STEPS.length - 1 ? "Done" : "Next ›";
    setTimeout(reposition, 220);                      // after the scroll/layout settles
  }
  function reposition() {
    if ($("tour").hidden) return;
    const el = document.querySelector(STEPS[idx].el);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const pad = 6, spot = $("tour-spot");
    spot.style.left = (r.left - pad) + "px"; spot.style.top = (r.top - pad) + "px";
    spot.style.width = (r.width + 2 * pad) + "px"; spot.style.height = (r.height + 2 * pad) + "px";
    // place the tooltip beside the target, clamped to the viewport
    const pop = $("tour-pop");
    pop.style.visibility = "hidden"; pop.style.left = "0px"; pop.style.top = "0px";
    const pw = pop.offsetWidth, ph = pop.offsetHeight, m = 12;
    let left = r.right + m;
    if (left + pw > global.innerWidth - 8) left = r.left - pw - m;     // flip to the left
    if (left < 8) left = Math.min(Math.max(8, r.left), global.innerWidth - pw - 8);
    const top = Math.max(8, Math.min(r.top + r.height / 2 - ph / 2, global.innerHeight - ph - 8));
    pop.style.left = left + "px"; pop.style.top = top + "px"; pop.style.visibility = "visible";
  }
  function wire() {                                   // hook up the tooltip's Next / Back / Skip
    $("tour-next").addEventListener("click", next);
    $("tour-prev").addEventListener("click", prev);
    $("tour-skip").addEventListener("click", end);
  }

  global.Tour = { start, end, next, prev, wire };
})(window);
