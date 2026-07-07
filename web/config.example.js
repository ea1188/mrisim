/* Copy to web/config.js and fill in your Supabase project's PUBLIC values to turn
   on the optional instructor/student accounts layer. With no config.js (or blank
   values) MRISim runs exactly as before — no accounts, no network calls, progress
   in localStorage only.

   The anon key is DESIGNED to be public: it ships to every browser and is safe to
   commit. Row-Level Security is what protects the data. NEVER put the service_role
   (secret) key here — it bypasses RLS. */
window.MRISIM_SUPABASE = {
  url: "",       // e.g. https://YOURREF.supabase.co
  anonKey: "",   // the anon / public key
};

/* Optional: Stripe course payments. The Payment Link is a PUBLIC URL and is safe
   to commit. Leave it blank to hide the Buy button and keep the mailto paywall.
   NEVER put a Stripe secret key or webhook signing secret here — those live only
   as Supabase Edge Function secrets. */
window.MRISIM_STRIPE = {
  paymentLink: "",   // e.g. https://buy.stripe.com/test_xxx
};
