import test from "node:test";
import assert from "node:assert/strict";
import JoinLink from "./join_link.js";

const { parseJoinCode } = JoinLink;

test("parseJoinCode returns the code from ?join=, uppercased", () => {
  assert.equal(parseJoinCode("?join=A1B2C3"), "A1B2C3");
  assert.equal(parseJoinCode("?join=a1b2c3"), "A1B2C3");
  assert.equal(parseJoinCode("?join=%20a1b2c3%20"), "A1B2C3");
});

test("parseJoinCode ignores other params", () => {
  assert.equal(parseJoinCode("?foo=1&join=A1B2C3&bar=2"), "A1B2C3");
});

test("parseJoinCode returns null for missing or malformed codes", () => {
  assert.equal(parseJoinCode(""), null);
  assert.equal(parseJoinCode("?x=1"), null);
  assert.equal(parseJoinCode("?join="), null);
  assert.equal(parseJoinCode("?join=ABC12"), null);   // 5 chars
  assert.equal(parseJoinCode("?join=ABC1234"), null);  // 7 chars
  assert.equal(parseJoinCode("?join=ABC-12"), null);   // bad charset
});
