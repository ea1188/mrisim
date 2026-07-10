-- 0009 definer hardening: remove REST/RPC callability from SECURITY DEFINER functions
-- that are NOT needed for RLS policy evaluation. Applied after 0008.
--
-- Deliberately NOT touched: is_entitled, is_enrolled, is_class_owner,
-- shares_class_with_me, join_class. RLS evaluates a policy's function AS the querying
-- role, so anon/authenticated MUST keep EXECUTE on them, otherwise policy checks error
-- ("permission denied for function") instead of cleanly returning zero rows. Each is
-- strictly caller-scoped (keys off auth.uid(), returns only booleans/ids about the
-- caller), so their exposure is safe. (Supersedes the stale PR #353, whose fix #3 would
-- have revoked exactly these and reintroduced the signed-out error it also tried to fix.)

-- Supabase grants EXECUTE explicitly to the anon and authenticated roles on public
-- functions (not only via PUBLIC), so these revokes name the roles directly. service_role
-- is backend-only (never exposed through the browser anon key) and is left untouched.

-- handle_new_user is the auth signup trigger function. It has no business being a
-- callable REST RPC. Triggers fire as the table owner regardless of the invoker's
-- EXECUTE grant, so removing these grants does not affect signups.
revoke execute on function handle_new_user() from anon, authenticated;

-- rotate_join_code is an owner-only action invoked by signed-in class owners; anon has
-- no reason to call it. Keep authenticated execute (ownership is enforced inside the
-- function via auth.uid()).
revoke execute on function rotate_join_code(uuid) from anon;
