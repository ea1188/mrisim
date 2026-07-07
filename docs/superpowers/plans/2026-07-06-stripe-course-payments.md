# Stripe Course Payments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a signed-in learner buy one-time $49 lifetime access to the `mri-core` course with a card and be automatically entitled on payment.

**Architecture:** A Stripe-hosted Payment Link (carrying the Supabase `user_id` as `client_reference_id` and the course in `metadata.course`) takes the payment. A single Supabase Edge Function `stripe-webhook` verifies the Stripe signature on `checkout.session.completed` and does a `service_role` upsert into the existing `entitlements` table — the only privileged writer, exactly as that table's RLS was designed for. The frontend Buy button lives in `course.js` and stays dormant until a public Payment Link URL is configured.

**Tech Stack:** Supabase (Postgres + Deno/TypeScript Edge Functions), Stripe (Payment Links + webhooks, `npm:stripe`), vanilla ES5-style JS in `web/`.

## Global Constraints

- **No em dashes or AI-tell punctuation in any user-facing copy** — natural prose only (button labels, paywall text, error messages). Verbatim from project memory `feedback_no_ai_tells_content`.
- **UI aesthetic:** professional/clinical — no emoji, no pills, no gradients; reuse the existing `.btn` class. From `feedback_ui_aesthetic`.
- **No `Co-Authored-By: Claude` trailers on commits.** From `feedback_no_claude_commit_attribution`.
- **Secrets never in the repo:** the Stripe secret key and webhook signing secret exist only as Supabase Edge Function secrets. Only the Payment Link (a public URL) may be committed.
- **Course allowlist:** the only valid course string is `mri-core`.
- **Fail-closed:** the course must never unlock from a URL param or client state alone — only from `Accounts.isEntitled("mri-core")` reading the database.

---

## File Structure

- `supabase/migrations/0004_entitlement_audit.sql` — **Create.** Adds `granted_via` + `stripe_ref` audit columns to `entitlements`.
- `supabase/functions/stripe-webhook/validate.ts` — **Create.** Pure, dependency-free function that turns a verified checkout session into a grant (or `null`). The unit-testable heart.
- `supabase/functions/stripe-webhook/validate_test.ts` — **Create.** `deno test` for `validate.ts`.
- `supabase/functions/stripe-webhook/index.ts` — **Create.** The HTTP handler: signature verify → parse → `service_role` upsert.
- `supabase/functions/stripe-webhook/deno.json` — **Create.** Pins the function's import map.
- `web/config.example.js` — **Modify.** Document the new public `MRISIM_STRIPE` block.
- `web/config.js` — **Modify.** Add the `MRISIM_STRIPE` block (blank Payment Link = dormant).
- `web/course.js` — **Modify.** Buy button in `paywallView`, `?checkout=success` return handler with polling, `loadCourse()` extraction.

---

## Task 1: Migration — entitlement audit columns

**Files:**
- Create: `supabase/migrations/0004_entitlement_audit.sql`

**Interfaces:**
- Consumes: the `entitlements` table from `0002_course_entitlements.sql`.
- Produces: two new columns readable by the webhook upsert in Task 4 — `granted_via text not null default 'manual'`, `stripe_ref text`.

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/0004_entitlement_audit.sql`:

```sql
-- Audit provenance on entitlements: how a grant was made and (for Stripe) which
-- checkout session produced it. Nullable/defaulted so it is backward compatible —
-- every existing manual grant reads as granted_via = 'manual'. Not read by any RLS
-- policy or gate; purely for audit and support. Apply after 0003.
alter table entitlements
  add column granted_via text not null default 'manual',
  add column stripe_ref  text;
```

- [ ] **Step 2: Apply the migration**

Apply to the Supabase project using the Supabase MCP `apply_migration` tool (name `0004_entitlement_audit`, the SQL above), or paste it into the Supabase dashboard SQL editor, or run `supabase db push` if the CLI is linked.

- [ ] **Step 3: Verify the columns exist**

Run this query (Supabase MCP `execute_sql` or the dashboard SQL editor):

```sql
select column_name, data_type, column_default, is_nullable
from information_schema.columns
where table_name = 'entitlements' and column_name in ('granted_via','stripe_ref')
order by column_name;
```

Expected: two rows — `granted_via` (text, default `'manual'::text`, NOT nullable) and `stripe_ref` (text, nullable).

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0004_entitlement_audit.sql
git commit -m "feat(db): entitlement audit columns (granted_via, stripe_ref)"
```

---

## Task 2: Webhook grant-parsing helper (TDD)

**Files:**
- Create: `supabase/functions/stripe-webhook/validate.ts`
- Create: `supabase/functions/stripe-webhook/validate_test.ts`

**Interfaces:**
- Consumes: nothing (pure function; no imports beyond the `Grant` type it defines).
- Produces: `parseCheckoutGrant(session, allowlist): Grant | null` and `interface Grant { userId: string; course: string; stripeRef: string }`, consumed by `index.ts` in Task 4.

- [ ] **Step 1: Write the failing test**

Create `supabase/functions/stripe-webhook/validate_test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `deno test supabase/functions/stripe-webhook/validate_test.ts`
Expected: FAIL — `Module not found` / `parseCheckoutGrant` cannot be imported (validate.ts does not exist yet).

- [ ] **Step 3: Write the minimal implementation**

Create `supabase/functions/stripe-webhook/validate.ts`:

```ts
// Pure parsing of a *verified* Stripe checkout.session.completed session into an
// entitlement grant. Returns null for anything that is not a clean, paid grant we
// recognise, so the caller never writes on malformed or ineligible data.

export interface Grant {
  userId: string;
  course: string;
  stripeRef: string;
}

interface SessionLike {
  id?: string | null;
  payment_status?: string | null;
  client_reference_id?: string | null;
  metadata?: { course?: string | null } | null;
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseCheckoutGrant(
  session: SessionLike,
  allowlist: readonly string[],
): Grant | null {
  if (!session || session.payment_status !== "paid") return null;
  const userId = session.client_reference_id ?? "";
  const course = session.metadata?.course ?? "";
  const stripeRef = session.id ?? "";
  if (!UUID_RE.test(userId)) return null;
  if (!allowlist.includes(course)) return null;
  if (!stripeRef) return null;
  return { userId, course, stripeRef };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `deno test supabase/functions/stripe-webhook/validate_test.ts`
Expected: PASS — 6 passed; 0 failed.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/stripe-webhook/validate.ts supabase/functions/stripe-webhook/validate_test.ts
git commit -m "feat(webhook): grant-parsing helper for stripe checkout sessions"
```

---

## Task 3: Webhook function config

**Files:**
- Create: `supabase/functions/stripe-webhook/deno.json`

**Interfaces:**
- Consumes: nothing.
- Produces: an import map so `index.ts` (Task 4) resolves `stripe` and `@supabase/supabase-js` and the function deploys cleanly.

- [ ] **Step 1: Write the Deno config**

Create `supabase/functions/stripe-webhook/deno.json`:

```json
{
  "imports": {
    "stripe": "npm:stripe@^17",
    "@supabase/supabase-js": "jsr:@supabase/supabase-js@2"
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add supabase/functions/stripe-webhook/deno.json
git commit -m "chore(webhook): deno import map for stripe-webhook function"
```

---

## Task 4: Webhook HTTP handler

**Files:**
- Create: `supabase/functions/stripe-webhook/index.ts`

**Interfaces:**
- Consumes: `parseCheckoutGrant` + `Grant` from Task 2; the import map from Task 3; the `entitlements` columns from Task 1.
- Produces: an HTTP endpoint that returns 400 (bad signature), 200 (ignored / no grant / success), or 500 (transient DB error), and on a valid grant upserts `{ user_id, course, granted_via: "stripe", stripe_ref }`.

- [ ] **Step 1: Write the handler**

Create `supabase/functions/stripe-webhook/index.ts`:

```ts
import Stripe from "stripe";
import { createClient } from "@supabase/supabase-js";
import { parseCheckoutGrant } from "./validate.ts";

// The only course a Stripe payment may grant. Add a new Payment Link + a string
// here to sell another course later — no other change needed.
const COURSE_ALLOWLIST = ["mri-core"];

// Fetch-based HTTP client is required on Deno (no Node http).
const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!, {
  httpClient: Stripe.createFetchHttpClient(),
});
const WEBHOOK_SECRET = Deno.env.get("STRIPE_WEBHOOK_SECRET")!;

// SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are auto-injected by the Supabase
// Edge runtime. The service_role client bypasses RLS — this is the one privileged
// writer the entitlements table was designed around.
const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false, autoRefreshToken: false } },
);

Deno.serve(async (req) => {
  const sig = req.headers.get("Stripe-Signature");
  const body = await req.text();

  // Signature verification is the trust boundary: everything downstream rides on
  // data Stripe signed. constructEventAsync is the Deno-safe (async) variant.
  let event: Stripe.Event;
  try {
    if (!sig) throw new Error("missing Stripe-Signature header");
    event = await stripe.webhooks.constructEventAsync(body, sig, WEBHOOK_SECRET);
  } catch (err) {
    console.error("signature verification failed:", (err as Error).message);
    return new Response("invalid signature", { status: 400 });
  }

  if (event.type !== "checkout.session.completed") {
    return new Response("ignored", { status: 200 });
  }

  const grant = parseCheckoutGrant(
    event.data.object as Stripe.Checkout.Session,
    COURSE_ALLOWLIST,
  );
  if (!grant) {
    // Malformed or ineligible — retrying will not help, so ack with 200.
    console.warn("completed session without a valid grant:", event.id);
    return new Response("no grant", { status: 200 });
  }

  // Idempotent: the (user_id, course) primary key makes a Stripe retry or a
  // replayed event a no-op instead of a duplicate.
  const { error } = await supabase.from("entitlements").upsert(
    {
      user_id: grant.userId,
      course: grant.course,
      granted_via: "stripe",
      stripe_ref: grant.stripeRef,
    },
    { onConflict: "user_id,course", ignoreDuplicates: true },
  );
  if (error) {
    // Transient — 500 so Stripe retries with backoff.
    console.error("entitlement upsert failed:", error.message);
    return new Response("db error", { status: 500 });
  }

  return new Response("ok", { status: 200 });
});
```

- [ ] **Step 2: Deploy the function (JWT verification off)**

Stripe calls this with a Stripe signature, not a Supabase JWT, so JWT verification must be disabled:

```bash
supabase functions deploy stripe-webhook --no-verify-jwt
```

Expected: deploy succeeds and prints the function URL
(`https://<project-ref>.functions.supabase.co/stripe-webhook`).

- [ ] **Step 3: Set the function secrets**

```bash
supabase secrets set STRIPE_SECRET_KEY=sk_test_xxx STRIPE_WEBHOOK_SECRET=whsec_xxx
```

(Use the **test-mode** secret key now; the webhook signing secret comes from Step 5. Re-run this to update either value. Do NOT set `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` — the runtime injects them.)

- [ ] **Step 4: Create the Stripe test-mode Product, Price, and Payment Link**

In the Stripe dashboard (test mode):
1. Products → add **MRISim Course**, one-time price **$49 USD**.
2. Payment Links → new link for that price. Under options, enable **"Pass an existing client reference ID"** (adds `client_reference_id` passthrough), add **metadata** `course = mri-core`, and set **after payment → redirect** to `https://mrisimlab.com/course.html?checkout=success`.
3. Copy the Payment Link URL (`https://buy.stripe.com/test_...`) for Task 7.

- [ ] **Step 5: Register the webhook endpoint**

Stripe dashboard → Developers → Webhooks → add endpoint = the function URL from Step 2, subscribed to **`checkout.session.completed`** only. Copy the endpoint's **Signing secret** (`whsec_...`) and set it via Step 3's command.

- [ ] **Step 6: Integration-test with the Stripe CLI**

```bash
stripe listen --forward-to https://<project-ref>.functions.supabase.co/stripe-webhook
# in another shell, with a real test user's UUID as client_reference_id:
stripe trigger checkout.session.completed \
  --add checkout_session:client_reference_id=<a-real-auth-users-uuid> \
  --add checkout_session:metadata.course=mri-core \
  --add checkout_session:payment_status=paid
```

Then verify the row landed (Supabase MCP `execute_sql` or dashboard):

```sql
select user_id, course, granted_via, stripe_ref
from entitlements where granted_via = 'stripe' order by granted_at desc limit 5;
```

Expected: a row with `granted_via = 'stripe'` and a `stripe_ref` set. Run the same `stripe trigger` twice and confirm still exactly one row for that `(user_id, course)` (idempotency).

- [ ] **Step 7: Commit**

```bash
git add supabase/functions/stripe-webhook/index.ts
git commit -m "feat(webhook): stripe-webhook grants entitlement on checkout.session.completed"
```

---

## Task 5: Public Stripe config block

**Files:**
- Modify: `web/config.example.js`
- Modify: `web/config.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `window.MRISIM_STRIPE = { paymentLink: string }`, read by `course.js` in Task 6. Blank `paymentLink` = Buy button hidden.

- [ ] **Step 1: Document the block in the example config**

Append to `web/config.example.js`:

```js
/* Optional: Stripe course payments. The Payment Link is a PUBLIC URL and is safe
   to commit. Leave it blank to hide the Buy button and keep the mailto paywall.
   NEVER put a Stripe secret key or webhook signing secret here — those live only
   as Supabase Edge Function secrets. */
window.MRISIM_STRIPE = {
  paymentLink: "",   // e.g. https://buy.stripe.com/test_xxx
};
```

- [ ] **Step 2: Add the block to the live config**

Append the same block to `web/config.js`, leaving `paymentLink: ""` for now (it is filled in Task 7 once the Payment Link is verified).

- [ ] **Step 3: Verify the config is valid JS**

Run: `node -e "global.window={}; require('./web/config.js'); console.log(JSON.stringify(window.MRISIM_STRIPE))"`
Expected: prints `{"paymentLink":""}` with no syntax error.

- [ ] **Step 4: Commit**

```bash
git add web/config.example.js web/config.js
git commit -m "feat(course): public MRISIM_STRIPE config block (payment link)"
```

---

## Task 6: Buy button and checkout-return handler in course.js

**Files:**
- Modify: `web/course.js` (constants near line 9–35; `paywallView` at 82–87; boot block at 555–577)

**Interfaces:**
- Consumes: `window.MRISIM_STRIPE.paymentLink` (Task 5); `Accounts.isEntitled`, `Accounts.premiumContent`, `Accounts.getSession` (existing).
- Produces: user-visible Buy flow; no exports (IIFE). Introduces `buildCheckoutUrl(link, uid, email)`, `paywallView(email, uid)`, `loadCourse()`, `waitForEntitlement()`, `pendingView()`.

- [ ] **Step 1: Add the Stripe config read and the URL builder**

In `web/course.js`, after the `EXAM = null;` line (~line 35), add:

```js
  var STRIPE = window.MRISIM_STRIPE || {};

  // Attach the signed-in user's id (and email) to the Payment Link so the webhook
  // can map the payment back to this account.
  function buildCheckoutUrl(link, uid, email) {
    var u = new URL(link);
    u.searchParams.set("client_reference_id", uid);
    if (email) u.searchParams.set("prefilled_email", email);
    return u.toString();
  }
```

- [ ] **Step 2: Replace `paywallView` with the Buy variant**

Replace the whole `paywallView` function (lines 82–87) with:

```js
  function paywallView(email, uid) {
    var kids = [
      h("h2", { text: "Unlock the full course" }),
      h("p", { text: "Get lifetime access to the guided curriculum: premium lessons, the full ARRT-style question bank, mock exams and the reference library." }),
    ];
    if (STRIPE.paymentLink && uid) {
      kids.push(h("button", { class: "btn", text: "Get lifetime access for $49", onclick: function () {
        location.assign(buildCheckoutUrl(STRIPE.paymentLink, uid, email));
      } }));
    } else {
      kids.push(h("a", { class: "btn", href: "mailto:erolakkoc8@gmail.com?subject=MRISim%20course%20access", text: "Request access" }));
    }
    kids.push(h("p", { class: "quiz-foot", html: "Meanwhile the <a class=\"linkout\" href=\"index.html\">free simulator, quiz and lessons</a> are open to everyone." }));
    gate(kids);
  }
```

- [ ] **Step 3: Add `loadCourse`, `waitForEntitlement`, and `pendingView`**

Immediately before the boot comment (`// --- boot: resolve the gate…`, ~line 555), add:

```js
  // Load the curriculum + premium content and render the course. Extracted so both
  // the entitled path and the post-checkout path use one code path (DRY).
  function loadCourse() {
    return Promise.all([
      fetch("lessons.json").then(function (r) { return r.json(); }),
      Accounts.premiumContent(COURSE),
    ]).then(function (res) {
      var data = res[0], premium = res[1];
      var byTitle = {}; (data.lessons || []).forEach(function (L) { byTitle[L.title] = L; });
      var byTopic = {}; (premium || []).forEach(function (it) {
        (byTopic[it.topic] = byTopic[it.topic] || []).push(it);
      });
      courseView(data.curriculum || [], byTitle, byTopic);
    });
  }

  // After returning from Stripe, the webhook can lag the redirect by a few seconds.
  // Show an unlocking state and poll the DB for the entitlement (never trust the
  // URL). Resolves true once entitled, false after ~30s.
  function waitForEntitlement() {
    gate([h("h2", { text: "Payment received" }),
      h("p", { text: "Unlocking your course. This can take a few seconds." })]);
    var tries = 0;
    return new Promise(function (resolve) {
      (function poll() {
        Accounts.isEntitled(COURSE).then(function (ok) {
          if (ok) return resolve(true);
          if (++tries >= 15) return resolve(false);
          setTimeout(poll, 2000);
        }).catch(function () {
          if (++tries >= 15) return resolve(false);
          setTimeout(poll, 2000);
        });
      })();
    });
  }

  function pendingView() {
    gate([h("h2", { text: "Almost there" }),
      h("p", { text: "Your payment went through, but access is taking longer than usual to activate. Refresh this page in a minute. If it still does not unlock, email erolakkoc8@gmail.com and we will sort it out." }),
      h("button", { class: "btn", text: "Refresh", onclick: function () { location.reload(); } })]);
  }
```

- [ ] **Step 4: Rewrite the boot block to use them**

Replace the boot block (lines 555–577, from the `// --- boot` comment through the `.catch(...)`) with:

```js
  // --- boot: resolve the gate, then load the course --------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  var justPaid = /[?&]checkout=success(?:&|$)/.test(location.search);
  Accounts.getSession().then(function (session) {
    if (!session) { signInView(); return; }
    var email = session.user && session.user.email;
    var uid = session.user && session.user.id;
    chrome(email);
    return Accounts.isEntitled(COURSE).then(function (ok) {
      if (ok) { if (justPaid) history.replaceState(null, "", location.pathname); return loadCourse(); }
      if (justPaid) {
        return waitForEntitlement().then(function (granted) {
          history.replaceState(null, "", location.pathname);
          if (granted) return loadCourse();
          pendingView();
        });
      }
      paywallView(email, uid);
    });
  }).catch(function (e) {
    gate([h("h2", { text: "Something went wrong" }), h("p", { text: String(e.message || e) })]);
  });
```

- [ ] **Step 5: Lint**

Run the lint the way CI does (command is in `.github/workflows/web-lint.yml`; typically `npx eslint web/course.js`).
Expected: no errors.

- [ ] **Step 6: Manual test**

With `paymentLink` still blank in `web/config.js`, serve `web/` locally and open `course.html` signed in as a non-entitled user. Expected: paywall shows the **Request access** mailto (fallback path), no Buy button. Then temporarily set `paymentLink` to the test link, reload: expected a **Get lifetime access for $49** button that navigates to Stripe with `?client_reference_id=<your-uid>` in the URL. Revert `paymentLink` to blank before committing (real value is set in Task 7).

- [ ] **Step 7: Commit**

```bash
git add web/course.js
git commit -m "feat(course): stripe buy button + post-checkout entitlement polling"
```

---

## Task 7: Enable and end-to-end verify

**Files:**
- Modify: `web/config.js` (set the real test Payment Link)

**Interfaces:**
- Consumes: everything above.
- Produces: a working test-mode purchase flow.

- [ ] **Step 1: Set the test Payment Link**

In `web/config.js`, set `paymentLink` to the test link from Task 4 Step 4.

- [ ] **Step 2: Full end-to-end test (test mode)**

Serve `web/`, sign in as a test user with no entitlement, open `course.html`, click **Get lifetime access for $49**, pay on Stripe with card `4242 4242 4242 4242` (any future expiry, any CVC). Expected: redirect to `course.html?checkout=success`, the "Payment received. Unlocking your course." state, then the course renders within a few seconds. Confirm a `granted_via='stripe'` row exists for your user (query from Task 4 Step 6).

- [ ] **Step 3: Commit**

```bash
git add web/config.js
git commit -m "chore(course): enable stripe payment link (test mode)"
```

- [ ] **Step 4: Go live (owner, when ready — no code change)**

Switch the Stripe dashboard to live mode; create the live Product/Price/Payment Link and a live webhook endpoint; run `supabase secrets set STRIPE_SECRET_KEY=sk_live_xxx STRIPE_WEBHOOK_SECRET=whsec_live_xxx`; set `web/config.js` `paymentLink` to the live link; commit. Verify once with a real card (or a real test purchase you refund).

---

## Self-Review

**Spec coverage:**
- Payment Link + `client_reference_id` + `metadata.course` + redirect → Task 4 Step 4.
- Buy button replacing mailto, with blank-config fallback → Task 6 Steps 2, 6.
- `?checkout=success` polling return handler, DB-only unlock → Task 6 Steps 3–4.
- `MRISIM_STRIPE` public config (+ example) → Task 5.
- `stripe-webhook` function: `--no-verify-jwt`, secrets, signature verify, event filter, uid/course validation, service_role idempotent upsert, status codes → Tasks 2–4.
- Migration 0004 audit columns → Task 1.
- Support email in fallback → Task 6 Step 3 (`pendingView`) and paywall mailto.
- Testing (stripe listen/trigger, tampered → 400 via signature verify, idempotency, e2e, no-config fallback) → Tasks 2 (unit), 4 Step 6, 6 Step 6, 7 Step 2.
- Rollout test→live → Task 7.
- Out-of-scope items carry no tasks (correct).

**Placeholder scan:** none — every code step shows complete code; the blank `paymentLink` is an intentional, documented dormant state, not a placeholder.

**Type consistency:** `parseCheckoutGrant(session, allowlist)` and `Grant { userId, course, stripeRef }` are defined in Task 2 and consumed unchanged in Task 4. `paywallView(email, uid)`, `loadCourse()`, `waitForEntitlement()`, `pendingView()`, `buildCheckoutUrl(link, uid, email)` are named consistently between their definitions and call sites in Task 6.
