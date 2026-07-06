-- Supabase database-linter (advisor) hardening, applied after 0003.
-- Note: the linter also warns that is_entitled / is_class_owner / is_enrolled /
-- shares_class_with_me / join_class are EXECUTE-able by authenticated (and anon).
-- Those grants are REQUIRED and safe: RLS evaluates a policy's function as the
-- querying role, so the role must hold EXECUTE, and each function is strictly
-- caller-scoped (keys off auth.uid(), returns only booleans/ids about the caller).
-- Only the two genuinely-actionable items are fixed here.

-- Pin search_path on the last mutable function (defence-in-depth).
alter function gen_join_code() set search_path = public;

-- handle_new_user is a trigger function; it should not be callable as a REST RPC.
-- Triggers execute regardless of the invoker's EXECUTE grant, so this is safe.
revoke all on function handle_new_user() from public;
