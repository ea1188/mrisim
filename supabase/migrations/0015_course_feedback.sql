-- Anonymous end-of-course feedback (see docs/superpowers/specs/2026-08-06-course-feedback-survey-design.md).
-- Deliberately has NO user_id and no PII: the survey page (web/feedback.html)
-- requires sign-in only so that random anonymous traffic can't submit, but the
-- stored row is not linked to the submitter. The owner reads responses with the
-- service_role in the Supabase dashboard; no client may SELECT.
create table course_feedback (
  id               uuid        primary key default gen_random_uuid(),
  cohort           text        not null default '2026-08',   -- separates future classes
  recommend        smallint    check (recommend between 0 and 10),
  prepared         smallint    check (prepared between 1 and 5),
  pace             text        check (pace in ('too_slow', 'about_right', 'too_fast')),
  workload         text        check (workload in ('too_light', 'about_right', 'too_heavy')),
  useful_simulator smallint    check (useful_simulator between 1 and 5),
  useful_planner   smallint    check (useful_planner between 1 and 5),
  useful_quiz      smallint    check (useful_quiz between 1 and 5),
  useful_lessons   smallint    check (useful_lessons between 1 and 5),
  useful_reference smallint    check (useful_reference between 1 and 5),
  hardest_module   text        check (hardest_module in ('m1','m2','m3','m4','m5','m6','m7','m8','m9','m10','none')),
  helped_most      text        check (char_length(helped_most) <= 2000),
  improve          text        check (char_length(improve) <= 2000),
  other            text        check (char_length(other) <= 2000),
  created_at       timestamptz not null default now()
);

alter table course_feedback enable row level security;

-- Signed-in users may INSERT. No SELECT/UPDATE/DELETE policy exists, so RLS denies
-- all reads through the anon/authenticated clients — the response stays anonymous
-- and is only reachable via the service_role (dashboard).
create policy course_feedback_insert on course_feedback
  for insert to authenticated with check (true);
