-- MRISim paid course — add a third premium content kind: 'reference'.
--
-- The reference library (reference.html) is a deep, browsable, searchable set of short
-- Q&A-style entries. Each entry reuses the education body shape ({title, html,
-- keypoints[]}) but is surfaced as a library rather than as inline course material,
-- so it is stored under kind='reference' to keep it cleanly separate from the per-topic
-- kind='education' pieces the course page shows.
--
-- No new policy is needed: course_content_entitled_read (0002) already gates EVERY row
-- of course_content by entitlement regardless of kind, so reference entries are premium
-- and exclusive automatically. This migration only widens the kind CHECK. Apply after 0002.

alter table course_content drop constraint course_content_kind_check;
alter table course_content add constraint course_content_kind_check
  check (kind in ('education', 'quiz', 'reference'));
