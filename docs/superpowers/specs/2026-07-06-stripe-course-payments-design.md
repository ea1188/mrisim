# Stripe course payments — design spec

**Date:** 2026-07-06
**Status:** approved for planning
**Course:** `mri-core` (the single paid guided course)

## Goal

Let a signed-in learner **buy lifetime access to the paid course with a card** and
be **automatically entitled** on payment — replacing today's manual `entitlements`
grant (a mailto "Request access" paywall). One-time **$49**, never revoked.

## Decisions (fixed)

- **Pricing:** one-time payment, **$49**, lifetime access. No subscriptions, no
  auto-revoke. (Subscriptions explicitly out of scope; see "Out of scope".)
- **Approach A — Stripe Payment Link + one webhook Edge Function.** The buy button
  redirects to a Stripe-hosted Payment Link; a single Supabase Edge Function
  (`stripe-webhook`) grants the entitlement. No `create-checkout` function.
- **Support email** in the webhook-lag fallback: `erolakkoc8@gmail.com`.
- **Migration `0004`** adds two nullable audit columns to `entitlements`.
- Build against Stripe **test mode** first; user swaps in live keys later.

## Why this fits the existing system

The `entitlements` table (migration 0002) was built for exactly this: users have
**read-only RLS and no INSERT policy**, so only the `service_role` can grant. The
webhook is the one privileged writer — no new RLS policy, no self-grant hole. The
`is_entitled(course)` SECURITY DEFINER helper and the `course_content` RLS gate are
unchanged; entitlement rows just start arriving from Stripe instead of by hand.

## Components

### 1. Stripe dashboard (owner-configured, not code)
- **Product** "MRISim Course" → one-time **Price $49 USD**.
- **Payment Link** for that price with:
  - `client_reference_id` **passthrough enabled** (carries the Supabase `user_id`),
  - **metadata** `course = "mri-core"` (so the webhook knows which course; keeps the
    design multi-course-ready without code changes),
  - **after-payment redirect** to `https://mrisimlab.com/course.html?checkout=success`.
- Webhook endpoint (added after the function is deployed) pointing at the Edge
  Function URL, subscribed to **`checkout.session.completed`** only.

### 2. Frontend — `web/course.js`
- Replace `paywallView()` (currently a mailto) with a **"Get lifetime access — $49"**
  button. On click it builds the Payment Link URL with:
  - `client_reference_id=<supabase user_id>` (from `Accounts.getUser()`),
  - `prefilled_email=<email>`,
  and redirects (`location.assign`).
- **Return handler:** when the page loads with `?checkout=success`, render a
  "Payment received — unlocking your course…" state and **poll**
  `Accounts.isEntitled("mri-core")` every ~2 s for up to ~30 s. On `true`, strip the
  query param and render the course. On timeout, show a "taking longer than expected —
  refresh in a minute, or email erolakkoc8@gmail.com" message. The unlock is **never**
  trusted from the browser/URL alone — only from `isEntitled()` reading the DB.
- Gate order is unchanged and fail-closed: not configured → signed out → **not
  entitled (now shows Buy) → entitled**.

### 3. Config — `web/config.js` (tracked; public values only)
Add a new public block (Payment Link is a public URL, safe to commit):
```js
window.MRISIM_STRIPE = {
  paymentLink: "",  // e.g. https://buy.stripe.com/test_xxx  (blank = Buy button hidden)
};
```
- Mirror it in `web/config.example.js` with a comment: public URL only, never a key.
- When `paymentLink` is blank/absent, the paywall falls back to the current
  mailto "Request access" so nothing breaks in deployments without Stripe.

### 4. Backend — Supabase Edge Function `stripe-webhook`
- Path: `supabase/functions/stripe-webhook/index.ts` (Deno/TS).
- **Deployed with JWT verification OFF** (`--no-verify-jwt`) — Stripe calls it with a
  Stripe signature, not a Supabase JWT.
- **Secrets** (Supabase function secrets, never in repo):
  - `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (set via `supabase secrets set`).
  - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are **auto-injected** by the
    Supabase runtime — no need to set them.
- Logic:
  1. Read raw body + `Stripe-Signature` header; verify with
     `stripe.webhooks.constructEventAsync(body, sig, STRIPE_WEBHOOK_SECRET)`
     (async variant, required on Deno). Bad/missing signature → **400**.
  2. If `event.type !== "checkout.session.completed"` → **200** ignore.
  3. From the session: require `payment_status === "paid"`; read
     `client_reference_id` (uid) and `metadata.course`. Validate uid is a UUID and
     course is in an **allowlist** (`["mri-core"]`). If invalid → **200 + log**
     (retry won't fix malformed data), no write.
  4. **`service_role` upsert** into `entitlements`:
     `{ user_id: uid, course, granted_via: "stripe", stripe_ref: session.id }`,
     `onConflict: "user_id,course", ignoreDuplicates: true` → idempotent (a Stripe
     retry or duplicate event yields exactly one row).
  5. On success → **200**. On transient DB error → **500** so Stripe retries with
     backoff.

### 5. Migration `0004_entitlement_audit.sql`
```sql
alter table entitlements
  add column granted_via text not null default 'manual',
  add column stripe_ref  text;
```
Nullable/defaulted → backward compatible; existing manual grants read as
`granted_via = 'manual'`. Purely for audit; not read by any gate.

## Data flow

```
signed-in, non-entitled user
   │ clicks "Get lifetime access — $49"
   ▼
Stripe Payment Link  (client_reference_id=uid, metadata.course=mri-core)
   │ pays with card (test: 4242 4242 4242 4242)
   ├──────────────► redirect: course.html?checkout=success
   │                          └─ frontend polls isEntitled() ──┐
   └──────────────► POST checkout.session.completed            │
                          │ verify signature                   │
                          │ service_role upsert entitlements ──┘ (row now exists)
                          ▼
                    isEntitled()==true → course unlocks
```

## Security

- **Signature verification is the trust boundary.** Every downstream fact (who to
  grant, which course) rides on data Stripe signed. Unverified → 400, no action.
- `service_role` key lives only in the function env; never shipped to the browser.
- Only `checkout.session.completed` with `payment_status="paid"` grants.
- UID/course validated against a UUID check + allowlist before any write.
- Idempotent upsert on the `(user_id, course)` PK — safe under Stripe's at-least-once
  delivery and manual event replays.
- No user-facing write path to `entitlements` is added; RLS is untouched.

## Error handling summary

| Situation | Response | Rationale |
|---|---|---|
| Missing/invalid Stripe signature | 400 | Don't act on unsigned data |
| Event type != checkout.session.completed | 200 | Ignore, no retry needed |
| Not paid / bad uid / unknown course | 200 + log | Malformed; retry won't help |
| Transient DB failure on upsert | 500 | Let Stripe retry with backoff |
| Webhook lags the redirect | (frontend) poll ~30 s | Async gap is UX, not data |
| Still not entitled after poll window | (frontend) "refresh / email support" | Never browser-trust the unlock |

## Testing

- **Unit/local:** `stripe listen --forward-to <fn-url>` + `stripe trigger
  checkout.session.completed` (test mode) → assert an `entitlements` row appears with
  `granted_via='stripe'`.
- **Signature rejection:** tampered body → 400.
- **Idempotency:** replay the same event → exactly one row.
- **End-to-end (manual):** signed-in test user → Buy → test card `4242…` → redirect →
  poll → course unlocks.
- **No-config fallback:** blank `paymentLink` → paywall shows the mailto, no Buy button.
- Existing CI (lint/smoke/test) is unaffected (Deno/TS function isn't in the Python or
  web-smoke path). Optional: a small `deno test` for the uid/course validation helper.

## Rollout

1. Land migration `0004`, the `stripe-webhook` function, and the `course.js` +
   `config.example.js` changes (Buy button dormant while `paymentLink` is blank).
2. Owner: create Stripe **test** Product/Price/Payment Link; deploy the function
   (`supabase functions deploy stripe-webhook --no-verify-jwt`); set `STRIPE_SECRET_KEY`
   + `STRIPE_WEBHOOK_SECRET`; add the Stripe webhook endpoint; paste the test Payment
   Link into `web/config.js`.
3. Verify end-to-end in test mode with `4242…`.
4. Flip to **live** mode: swap to live keys/secret, live Payment Link, live webhook
   endpoint. No code change.

## Out of scope (YAGNI)

- Subscriptions / recurring billing / auto-revoke on cancel.
- Coupons, dynamic pricing, multiple price tiers (Payment Link is a flat price).
- Refund → auto-revoke (handle refunds manually via a `service_role` delete for now).
- A `create-checkout` Edge Function (Approach B) — can be added later without rework;
  the webhook is unchanged by it.
- Multi-course purchase UI — the webhook already keys off `metadata.course`, so adding
  a second course later is a new Payment Link + allowlist entry, not a redesign.
