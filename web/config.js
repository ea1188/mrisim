/* Public Supabase config for the hosted MRISim instructor layer. The anon key is
   public by design (Row-Level Security protects the data), so it is safe to commit
   and serve. See config.example.js and docs/INSTRUCTOR_BACKEND.md. */
window.MRISIM_SUPABASE = {
  url: "https://idgyjmamxxyddjuaamit.supabase.co",
  anonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkZ3lqbWFteHh5ZGRqdWFhbWl0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMyNzg4MDQsImV4cCI6MjA5ODg1NDgwNH0.5lLRy3yb9YZuDdgjsdYbWKo8hlLPHxTpHkBXi9nP74w",
};

/* Optional: Stripe course payments. The Payment Link is a PUBLIC URL and is safe
   to commit. Leave it blank to hide the Buy button and keep the mailto paywall.
   NEVER put a Stripe secret key or webhook signing secret here — those live only
   as Supabase Edge Function secrets. */
window.MRISIM_STRIPE = {
  paymentLink: "https://buy.stripe.com/14A4gA8Yk2hk5cLehre3e00",   // LIVE Payment Link
};

/* Course access mode. free: true opens the guided course to any signed-in user at
   no charge — the paywall and the Buy button are skipped and no refund prompt shows.
   To return to paid: set free: false AND restore the entitled-only RLS policy on
   course_content (see supabase/migrations/0008_course_free_mode.sql). */
window.MRISIM_COURSE = {
  free: true,
};
