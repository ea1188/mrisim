import test from "node:test";
import assert from "node:assert/strict";
import AuthUrl from "./auth_url.js";

const { parseAuthError, looksLikeCode, friendlyAuthError } = AuthUrl;

test("parseAuthError returns null when there is no error", () => {
  assert.equal(parseAuthError("", ""), null);
  assert.equal(parseAuthError("#access_token=abc&refresh_token=def", ""), null);
  assert.equal(parseAuthError("", "?code=abc123"), null);
});

test("parseAuthError reads an implicit-flow error from the hash", () => {
  const e = parseAuthError(
    "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired",
    ""
  );
  assert.equal(e.code, "otp_expired");
  assert.equal(e.message, "Email link is invalid or has expired");
});

test("parseAuthError reads an error from the query string too", () => {
  const e = parseAuthError("", "?error=access_denied&error_description=Something%20went%20wrong");
  assert.equal(e.code, "access_denied");
  assert.equal(e.message, "Something went wrong");
});

test("parseAuthError tolerates a leading # or ? being absent", () => {
  const e = parseAuthError("error=access_denied&error_code=otp_expired", "");
  assert.equal(e.code, "otp_expired");
});

test("looksLikeCode accepts a 6-digit code and rejects anything else", () => {
  assert.equal(looksLikeCode("123456"), true);
  assert.equal(looksLikeCode(" 123456 "), true);
  assert.equal(looksLikeCode("12345"), false);
  assert.equal(looksLikeCode("1234567"), false);
  assert.equal(looksLikeCode("12a456"), false);
  assert.equal(looksLikeCode(""), false);
  assert.equal(looksLikeCode(null), false);
});

test("friendlyAuthError explains an expired/consumed link in terms of the code", () => {
  const msg = friendlyAuthError("otp_expired", "Email link is invalid or has expired");
  assert.match(msg, /code/i);
  // The consumed-link case should point the user at the code, not just repeat the raw error.
  assert.notEqual(msg, "Email link is invalid or has expired");
});

test("friendlyAuthError falls back to the raw message for unknown codes", () => {
  assert.equal(friendlyAuthError("weird_code", "A specific message"), "A specific message");
  assert.equal(friendlyAuthError("", ""), "Sign-in failed. Please try again.");
});
