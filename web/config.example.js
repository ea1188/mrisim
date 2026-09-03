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
