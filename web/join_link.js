/* Pure, DOM-free helper: read a class join code from a ?join=CODE query string.
 * UMD like course_logic.js / auth_url.js (window.JoinLink in the browser, module.exports
 * under node). Used by the account page's one-click invite link. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.JoinLink = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Return the uppercased 6-char [A-Z0-9] join code from a query string, or null.
  function parseJoinCode(search) {
    if (!search) return null;
    var s = String(search).replace(/^\?/, "");
    var code = null;
    s.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i < 0) return;
      var k = kv.slice(0, i);
      if (k !== "join") return;
      var v = kv.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) { /* keep raw */ }
      code = v;
    });
    if (code == null) return null;
    code = code.trim().toUpperCase();
    return /^[A-Z0-9]{6}$/.test(code) ? code : null;
  }

  return { parseJoinCode: parseJoinCode };
});
