/* Pure, DOM-free helpers for the Supabase auth callback URL and email-code flow.
 * No window, no DOM, no network — just parsing/decisions over plain strings, so it
 * is unit-testable under node (web/auth_url.test.mjs) and shared by account.js.
 * UMD: attaches window.AuthUrl in the browser, module.exports under node.
 *
 * Why this exists: corporate mail scanners (Microsoft Safe Links, prefetchers) open
 * the one-time magic-link before the human clicks, so Supabase hands the browser back
 * an error (#error=access_denied&error_code=otp_expired&...) instead of a session. The
 * account page must (a) read that error rather than silently showing the form again,
 * and (b) offer the scanner-proof path: a 6-digit code the user types (verifyOtp). */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AuthUrl = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Parse a URL fragment ("#a=1&b=2" or "?a=1&b=2", with or without the leading
  // #/?) into a plain object. Values are URL-decoded and "+" is treated as space
  // (Supabase encodes error_description with "+").
  function _params(fragment) {
    var out = {};
    if (!fragment) return out;
    var s = String(fragment).replace(/^[#?]/, "");
    s.split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("=");
      var k = i < 0 ? kv : kv.slice(0, i);
      var v = i < 0 ? "" : kv.slice(i + 1);
      if (!k) return;
      try { k = decodeURIComponent(k); } catch (e) { /* keep raw */ }
      try { v = decodeURIComponent(v.replace(/\+/g, " ")); } catch (e) { v = v.replace(/\+/g, " "); }
      out[k] = v;
    });
    return out;
  }

  // Read a Supabase auth error handed back in the callback URL. Checks both the
  // hash (implicit flow) and the query string (PKCE). Returns { code, message } or
  // null when no error is present.
  function parseAuthError(hash, search) {
    var p = _params(hash);
    var q = _params(search);
    var code = p.error_code || q.error_code || p.error || q.error;
    if (!code) return null;
    var message = p.error_description || q.error_description || p.error || q.error || "Sign-in failed.";
    return { code: code, message: message };
  }

  // Is this string a plausible 6-digit email OTP code? (Supabase email codes are 6
  // digits.) Used to enable the "Verify code" button only for well-formed input.
  function looksLikeCode(s) {
    return /^[0-9]{6}$/.test(String(s == null ? "" : s).trim());
  }

  // Turn a raw Supabase auth error into a message that tells the user what to do.
  // The consumed/expired-link case (the Safe-Links prefetch race) is the whole
  // makes it actionable. Sign-in is Google-only, so callbacks that fail come back as
  // an OAuth error (a cancelled/denied consent, or a stale link); tell the user to try again.
  function friendlyAuthError(code, message) {
    var c = String(code || "").toLowerCase();
    var m = String(message || "");
    if (c === "access_denied") {
      return "Sign-in was cancelled or not permitted. Please try Continue with Google again.";
    }
    if (c === "otp_expired" || /invalid or has expired/i.test(m)) {
      return "That sign-in link has expired or was already used. Please sign in again.";
    }
    return m || "Sign-in failed. Please try again.";
  }

  return {
    parseAuthError: parseAuthError,
    looksLikeCode: looksLikeCode,
    friendlyAuthError: friendlyAuthError,
  };
});
