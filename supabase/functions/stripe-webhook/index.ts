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
