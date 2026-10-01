// Shared site header behaviour: the narrow-screen menu button toggles the primary
// links. Markup is static in every page (see site_nav.test.mjs); this only wires
// the toggle, closes on Escape / outside click, and keeps aria-expanded honest.
(function () {
  "use strict";
  var nav = document.querySelector(".site-nav");
  var btn = nav && nav.querySelector(".site-menu");
  if (!nav || !btn) return;

  function setOpen(open) {
    nav.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  btn.addEventListener("click", function () { setOpen(!nav.classList.contains("open")); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && nav.classList.contains("open")) { setOpen(false); btn.focus(); }
  });
  document.addEventListener("click", function (e) {
    if (nav.classList.contains("open") && !nav.contains(e.target)) setOpen(false);
  });
  // Leaving the narrow layout: drop the open state so the desktop row is never stuck "open".
  var mq = window.matchMedia("(min-width: 761px)");
  (mq.addEventListener || mq.addListener).call(mq, "change", function (ev) { if (ev.matches) setOpen(false); });
})();
