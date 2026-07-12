-- 0011: Consolidate overlapping permissive RLS policies (Supabase linter
-- 0006_multiple_permissive_policies).
--
-- Five tables each carried two PERMISSIVE policies that overlapped on the same
-- command+role: a broad "self/owner" policy plus a narrower "instructor/enrolled"
-- read policy. Postgres already OR-combines permissive policies, so evaluating two
-- where one suffices is pure overhead. This migration collapses each overlap into a
-- single policy with the predicates OR'd together — access semantics are unchanged.
--
-- Where the broad side was FOR ALL (activity/assignments/classes), the SELECT command
-- is the only thing that overlapped the read policy, so we decompose FOR ALL into an
-- explicit merged SELECT policy plus per-command write policies (INSERT/UPDATE/DELETE)
-- that reproduce the original USING/WITH CHECK exactly. Writes stay owner/self-only.
--
-- The cheap `id = (select auth.uid())` comparison is placed before the SECURITY DEFINER
-- helper in each OR so Postgres can short-circuit. auth.uid() stays wrapped as
-- `(select auth.uid())` to preserve the 0010 init-plan optimization.
--
-- Idempotent: every target policy (old and new names) is dropped-if-exists first.

-- ── activity ──────────────────────────────────────────────────────────────────
-- Was: activity_self_all (FOR ALL, self) + activity_instructor_read (SELECT, owner).
drop policy if exists activity_self_all on public.activity;
drop policy if exists activity_instructor_read on public.activity;
drop policy if exists activity_read on public.activity;
drop policy if exists activity_self_insert on public.activity;
drop policy if exists activity_self_update on public.activity;
drop policy if exists activity_self_delete on public.activity;

create policy activity_read on public.activity for select
  using (
    (student_id = (select auth.uid()))
    or ((class_id is not null) and is_class_owner(class_id))
  );
create policy activity_self_insert on public.activity for insert
  with check ((student_id = (select auth.uid())) and ((class_id is null) or is_enrolled(class_id)));
create policy activity_self_update on public.activity for update
  using (student_id = (select auth.uid()))
  with check ((student_id = (select auth.uid())) and ((class_id is null) or is_enrolled(class_id)));
create policy activity_self_delete on public.activity for delete
  using (student_id = (select auth.uid()));

-- ── assignments ───────────────────────────────────────────────────────────────
-- Was: assignments_owner_all (FOR ALL, owner) + assignments_enrolled_read (SELECT, enrolled).
drop policy if exists assignments_owner_all on public.assignments;
drop policy if exists assignments_enrolled_read on public.assignments;
drop policy if exists assignments_read on public.assignments;
drop policy if exists assignments_owner_insert on public.assignments;
drop policy if exists assignments_owner_update on public.assignments;
drop policy if exists assignments_owner_delete on public.assignments;

create policy assignments_read on public.assignments for select
  using (is_class_owner(class_id) or is_enrolled(class_id));
create policy assignments_owner_insert on public.assignments for insert
  with check (is_class_owner(class_id));
create policy assignments_owner_update on public.assignments for update
  using (is_class_owner(class_id))
  with check (is_class_owner(class_id));
create policy assignments_owner_delete on public.assignments for delete
  using (is_class_owner(class_id));

-- ── classes ───────────────────────────────────────────────────────────────────
-- Was: classes_owner_all (FOR ALL, instructor) + classes_enrolled_read (SELECT, enrolled).
drop policy if exists classes_owner_all on public.classes;
drop policy if exists classes_enrolled_read on public.classes;
drop policy if exists classes_read on public.classes;
drop policy if exists classes_owner_insert on public.classes;
drop policy if exists classes_owner_update on public.classes;
drop policy if exists classes_owner_delete on public.classes;

create policy classes_read on public.classes for select
  using ((instructor_id = (select auth.uid())) or is_enrolled(id));
create policy classes_owner_insert on public.classes for insert
  with check (instructor_id = (select auth.uid()));
create policy classes_owner_update on public.classes for update
  using (instructor_id = (select auth.uid()))
  with check (instructor_id = (select auth.uid()));
create policy classes_owner_delete on public.classes for delete
  using (instructor_id = (select auth.uid()));

-- ── enrollments ───────────────────────────────────────────────────────────────
-- Overlaps on SELECT and DELETE (no FOR ALL here). Merge each pair. INSERT is handled
-- elsewhere (SECURITY DEFINER join flow), so it is left untouched.
drop policy if exists enroll_self_read on public.enrollments;
drop policy if exists enroll_instructor_read on public.enrollments;
drop policy if exists enroll_self_delete on public.enrollments;
drop policy if exists enroll_instructor_delete on public.enrollments;
drop policy if exists enroll_read on public.enrollments;
drop policy if exists enroll_delete on public.enrollments;

create policy enroll_read on public.enrollments for select
  using ((student_id = (select auth.uid())) or is_class_owner(class_id));
create policy enroll_delete on public.enrollments for delete
  using ((student_id = (select auth.uid())) or is_class_owner(class_id));

-- ── profiles ──────────────────────────────────────────────────────────────────
-- Overlaps on SELECT only. Merge the two read policies; leave self insert/update alone.
drop policy if exists profiles_self_select on public.profiles;
drop policy if exists profiles_instructor_read on public.profiles;
drop policy if exists profiles_read on public.profiles;

create policy profiles_read on public.profiles for select
  using ((id = (select auth.uid())) or shares_class_with_me(id));
