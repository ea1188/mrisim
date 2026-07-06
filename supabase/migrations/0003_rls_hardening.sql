-- RLS hardening from the migration security review (two independent reviewers).
-- The access model was found sound; these close low/medium gaps. Apply after 0002.

-- 1. is_entitled() is called by the course_content policy for the `public` role
--    (incl. anon), but was execute-granted only to `authenticated`. So a signed-out
--    SELECT on course_content errored ("permission denied for function") instead of
--    cleanly returning zero rows. Still fail-closed, but grant anon execute for a
--    clean empty result.
grant execute on function is_entitled(text) to anon;

-- 2. activity: a student could stamp a fabricated quiz/lesson row to ANY class UUID
--    they knew (e.g. a since-revoked enrollment), surfacing spurious activity in that
--    instructor's dashboard. Tie the write to a real, current enrollment.
drop policy activity_self_all on activity;
create policy activity_self_all on activity for all
  using (student_id = auth.uid())
  with check (student_id = auth.uid() and (class_id is null or is_enrolled(class_id)));

-- 3. Consistency / defense-in-depth: restrict 0001's SECURITY DEFINER helpers the same
--    way 0001's join_class and 0002's is_entitled are (execute to authenticated only).
revoke all on function is_class_owner(uuid) from public;
revoke all on function is_enrolled(uuid) from public;
revoke all on function shares_class_with_me(uuid) from public;
grant execute on function is_class_owner(uuid) to authenticated;
grant execute on function is_enrolled(uuid) to authenticated;
grant execute on function shares_class_with_me(uuid) to authenticated;
