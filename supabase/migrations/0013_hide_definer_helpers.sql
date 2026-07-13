-- 0013: Remove RPC exposure of the RLS-only SECURITY DEFINER helpers
-- (Supabase linters 0028_anon_security_definer_function_executable +
--  0029_authenticated_security_definer_function_executable).
--
-- Four SECURITY DEFINER helpers are only ever called from inside RLS policies, yet
-- being in the `public` schema made them callable directly via /rest/v1/rpc/*. A bare
-- REVOKE EXECUTE cannot fix this: RLS evaluates these functions AS the querying role,
-- so revoking EXECUTE from `authenticated` breaks the policies themselves (verified on
-- prod in a rolled-back probe -> "permission denied for function").
--
-- The correct lever is the schema. PostgREST only exposes `public` (+ graphql_public),
-- so moving the helpers to a non-exposed `private` schema closes the RPC endpoint while
-- keeping them usable in RLS:
--   * Policies bind the functions by OID, so the move does not disturb them.
--   * Each helper keeps search_path=public, so its body still reads the public tables.
--   * EXECUTE grants travel with the function; the querying roles additionally need
--     USAGE on `private` (granted below) to reach them.
-- Verified end-to-end on prod (rolled back): authenticated SELECTs on classes,
-- assignments, enrollments, activity, profiles all succeed post-move.
--
-- is_entitled is currently orphaned (free-mode relaxed course_content RLS in 0008), but
-- it comes back into use if the paywall is restored, so it is moved rather than dropped.
-- A future paywall-restore migration should reference private.is_entitled(...).
--
-- join_class and rotate_join_code stay public RPCs (the client calls them). Their
-- security rests on internal authorization, not on being hidden:
--   * join_class validates the code and inserts enrollments(student_id = auth.uid());
--     anon cannot use it (auth.uid() is null -> NOT NULL PK violation), so its anon
--     EXECUTE grant is dropped.
--   * rotate_join_code checks is_class_owner internally. Because it resolves that call
--     by name at runtime, its search_path is extended to include `private`.
-- These two remain visible to linter 0029 by design (they must be callable).

create schema if not exists private;
grant usage on schema private to anon, authenticated;

alter function public.is_class_owner(uuid)       set schema private;
alter function public.is_enrolled(uuid)          set schema private;
alter function public.shares_class_with_me(uuid) set schema private;
alter function public.is_entitled(text)          set schema private;

-- rotate_join_code stays in public; repoint its unqualified is_class_owner call.
alter function public.rotate_join_code(uuid) set search_path = public, private;

-- join_class is authenticated-only in practice; drop the unusable anon grant.
revoke execute on function public.join_class(text) from anon;
