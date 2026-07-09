-- Free mode: open the guided course to any signed-in user at no charge (for now).
--
-- Background: 0002 restricted course_content SELECT to entitled users via
-- `course_content_entitled_read USING is_entitled(course)`. While the course is
-- free, we serve premium content to ANY authenticated user instead. The client
-- side is gated by MRISIM_COURSE.free in web/config.js; this policy is the
-- server-side half so the content actually loads for non-entitled users.
--
-- To return to PAID:
--   1) set MRISIM_COURSE.free = false in web/config.js, and
--   2) restore the entitled-only policy:
--        drop policy course_content_entitled_read on course_content;
--        create policy course_content_entitled_read on course_content for select
--          using (is_entitled(course));
--
-- The entitlements table, is_entitled(), Stripe checkout, and the refund edge
-- function are all left intact, so reverting is a two-line change.

drop policy if exists course_content_entitled_read on course_content;

create policy course_content_entitled_read on course_content for select
  using (auth.uid() is not null);
