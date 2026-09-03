-- Widen the activity.kind check to accept OSCE attempts (graded protocol-planning
-- scenarios in the planner, feat/osce Phase C). Same pattern as 0014: the CHECK
-- rejects unknown kinds SILENTLY on the client (inserts fail without surfacing),
-- so every new activity kind needs this bump BEFORE the client ships logging.
alter table activity drop constraint if exists activity_kind_check;
alter table activity add constraint activity_kind_check
  check (kind in ('lesson_complete', 'quiz_attempt', 'mastery_check', 'mock_exam', 'osce'));
