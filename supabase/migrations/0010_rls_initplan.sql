-- 0010: RLS init-plan optimization (Supabase linter 0003_auth_rls_initplan).
--
-- Wrap `auth.uid()` as `(select auth.uid())` in the self-scoped policies so Postgres
-- evaluates it ONCE per query (an InitPlan) instead of re-running it for every row.
-- Pure performance — the value is identical, so access semantics are unchanged. Only
-- the policies that reference auth.uid() directly are touched; policies that call the
-- SECURITY DEFINER helpers (is_enrolled / is_class_owner / shares_class_with_me) are
-- left as-is.

alter policy activity_self_all on public.activity
  using (student_id = (select auth.uid()))
  with check ((student_id = (select auth.uid())) and ((class_id is null) or is_enrolled(class_id)));

alter policy classes_owner_all on public.classes
  using (instructor_id = (select auth.uid()))
  with check (instructor_id = (select auth.uid()));

alter policy course_content_entitled_read on public.course_content
  using ((select auth.uid()) is not null);

alter policy course_progress_self_all on public.course_progress
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter policy enroll_self_delete on public.enrollments
  using (student_id = (select auth.uid()));

alter policy enroll_self_read on public.enrollments
  using (student_id = (select auth.uid()));

alter policy entitlements_self_read on public.entitlements
  using (user_id = (select auth.uid()));

alter policy profiles_self_insert on public.profiles
  with check (id = (select auth.uid()));

alter policy profiles_self_select on public.profiles
  using (id = (select auth.uid()));

alter policy profiles_self_update on public.profiles
  using (id = (select auth.uid()));
