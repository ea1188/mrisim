import Stripe from "stripe";
import { createClient } from "@supabase/supabase-js";

// Self-serve refund: an authenticated buyer can refund their own course purchase
// within the window and have access revoked. Enforced server-side; the browser
// only asks. verify_jwt is ON, so only signed-in users reach this.
const COURSE_ALLOWLIST = ["mri-core"];
const REFUND_WINDOW_DAYS = 7;

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!, {
  httpClient: Stripe.createFetchHttpClient(),
});
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { ...CORS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  // Identify the caller from their Supabase JWT.
  const authHeader = req.headers.get("Authorization") || "";
  const userClient = createClient(SUPABASE_URL, ANON_KEY, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });
  const { data: { user } } = await userClient.auth.getUser();
  if (!user) return json({ error: "You need to be signed in." }, 401);

  let course = "mri-core";
  try {
    const b = await req.json();
    if (b && b.course) course = String(b.course);
  } catch { /* default course */ }
  if (!COURSE_ALLOWLIST.includes(course)) return json({ error: "Unknown course." }, 400);

  // service_role bypasses RLS for the entitlement read + delete.
  const admin = createClient(SUPABASE_URL, SERVICE_KEY, { auth: { persistSession: false } });
  const { data: ent } = await admin.from("entitlements")
    .select("granted_via, stripe_ref, granted_at")
    .eq("user_id", user.id).eq("course", course).maybeSingle();

  if (!ent) return json({ error: "You don't have this course, or it was already refunded." });
  if (ent.granted_via !== "stripe" || !ent.stripe_ref) {
    return json({ error: "This access wasn't a Stripe purchase, so it can't be refunded here. Please email support." });
  }
  const ageDays = (Date.now() - new Date(ent.granted_at).getTime()) / 86_400_000;
  if (ageDays > REFUND_WINDOW_DAYS) {
    return json({ error: `The ${REFUND_WINDOW_DAYS}-day refund window has passed. Email support if you think this is a mistake.` });
  }

  // Refund the payment behind the checkout session, then revoke access.
  try {
    const session = await stripe.checkout.sessions.retrieve(ent.stripe_ref);
    const pi = typeof session.payment_intent === "string"
      ? session.payment_intent
      : session.payment_intent?.id;
    if (!pi) return json({ error: "Could not find the payment to refund. Please email support." });
    await stripe.refunds.create({ payment_intent: pi });
  } catch (err) {
    console.error("refund failed:", (err as Error).message);
    return json({ error: "The refund could not be processed. Please email support." }, 500);
  }

  const { error: delErr } = await admin.from("entitlements")
    .delete().eq("user_id", user.id).eq("course", course);
  if (delErr) console.error("entitlement delete after refund failed:", delErr.message);

  return json({ ok: true });
});
