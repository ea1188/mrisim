-- Widen the activity.kind check so premium-course formative events sync to the
-- class owner. Before this, kind was limited to lesson_complete + quiz_attempt,
-- and course.js never emitted anything, so module mastery checks and mock exams
-- were invisible to instructors. course.js now logs 'mastery_check' (ref = module
-- title, score = percent, total = 100) and 'mock_exam' (ref = 'mock', score =
-- correct, total = questions); this constraint must accept them or the inserts
-- fail (and logActivity swallows the error, so it would fail silently).
alter table activity drop constraint if exists activity_kind_check;
alter table activity add constraint activity_kind_check
  check (kind in ('lesson_complete', 'quiz_attempt', 'mastery_check', 'mock_exam'));
