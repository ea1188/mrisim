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
  // TEMPORARY: Stripe TEST-mode link for a live end-to-end verification. Revert to
  // "" (or the live link) after testing — a test link takes no real payments.
  paymentLink: "https://buy.stripe.com/test_14A4gA8Yk2hk5cLehre3e00",
};
