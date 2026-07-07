import { assertEquals } from "jsr:@std/assert@1";
import { parseCheckoutGrant } from "./validate.ts";

const ALLOW = ["mri-core"];
const UID = "3f8c9b2a-1d4e-4a7b-8c2f-0e1a2b3c4d5e";

Deno.test("valid paid session -> grant", () => {
  const g = parseCheckoutGrant(
    { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: { course: "mri-core" } },
    ALLOW,
  );
  assertEquals(g, { userId: UID, course: "mri-core", stripeRef: "cs_1" });
});

Deno.test("unpaid session -> null", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "unpaid", client_reference_id: UID, metadata: { course: "mri-core" } },
      ALLOW,
    ),
    null,
  );
});

Deno.test("non-uuid client_reference_id -> null", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: "not-a-uuid", metadata: { course: "mri-core" } },
      ALLOW,
    ),
    null,
  );
});

Deno.test("course not in allowlist -> null", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: { course: "evil" } },
      ALLOW,
    ),
    null,
  );
});

Deno.test("missing metadata -> null", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: null },
      ALLOW,
    ),
    null,
  );
});

Deno.test("missing session id -> null", () => {
  assertEquals(
    parseCheckoutGrant(
      { payment_status: "paid", client_reference_id: UID, metadata: { course: "mri-core" } },
      ALLOW,
    ),
    null,
  );
});

// defaultCourse: Stripe Payment Links can't set session metadata, so a paid session
// with no metadata.course falls back to the default (still allowlist-checked).
Deno.test("missing metadata + defaultCourse -> grant", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: null },
      ALLOW,
      "mri-core",
    ),
    { userId: UID, course: "mri-core", stripeRef: "cs_1" },
  );
});

Deno.test("empty metadata.course + defaultCourse -> grant", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: { course: "" } },
      ALLOW,
      "mri-core",
    ),
    { userId: UID, course: "mri-core", stripeRef: "cs_1" },
  );
});

Deno.test("metadata.course overrides defaultCourse", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: { course: "mri-core" } },
      ALLOW,
      "something-else",
    ),
    { userId: UID, course: "mri-core", stripeRef: "cs_1" },
  );
});

Deno.test("defaultCourse not in allowlist -> null", () => {
  assertEquals(
    parseCheckoutGrant(
      { id: "cs_1", payment_status: "paid", client_reference_id: UID, metadata: null },
      ALLOW,
      "evil",
    ),
    null,
  );
});
