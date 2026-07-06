-- MRISim paid course — entitlements + exclusive premium content (Phase 1).
--
-- The free simulator/quiz/lessons stay public. This adds a PAID guided course whose
-- premium material (extra education + ARRT-registry questions) is genuinely exclusive:
-- it lives here in Postgres, not in the public static site, and Row-Level Security
-- serves it only to users who hold an entitlement.
--
-- Access is granted manually for the pilot (insert an `entitlements` row with the
-- service_role). Users can READ their own entitlement and, if entitled, the course
-- content — but can never WRITE either (no user-facing INSERT/UPDATE/DELETE policy),
-- so a client cannot self-grant. Apply after 0001. Target: Postgres / Supabase.

-- ---------------------------------------------------------------------------
-- Entitlements: who may access which course.
-- ---------------------------------------------------------------------------
create table entitlements (
  user_id    uuid        not null references auth.users(id) on delete cascade,
  course     text        not null,
  granted_at timestamptz not null default now(),
  granted_by uuid        references auth.users(id) on delete set null,
  primary key (user_id, course)
);

-- ---------------------------------------------------------------------------
-- Premium course content: exclusive education + quiz items, keyed by course/topic.
-- `body` is the item payload (education: {title, html, keypoints[]}; quiz: the same
-- shape as web/quiz.json questions, plus a topic). `ord` orders items within a topic.
-- ---------------------------------------------------------------------------
create table course_content (
  id         bigint generated always as identity primary key,
  course     text        not null,
  topic      text        not null,
  kind       text        not null check (kind in ('education', 'quiz')),
  ord        int         not null default 0,
  body       jsonb       not null,
  created_at timestamptz not null default now()
);
create index course_content_lookup on course_content (course, topic, ord);

-- ---------------------------------------------------------------------------
-- Entitlement check as a SECURITY DEFINER helper (bypasses RLS internally, so the
-- course_content policy can ask about entitlements without a cross-table RLS loop).
-- ---------------------------------------------------------------------------
create function is_entitled(p_course text) returns boolean
  language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from entitlements
     where user_id = auth.uid() and course = p_course);
$$;
revoke all on function is_entitled(text) from public;
grant execute on function is_entitled(text) to authenticated;

-- ---------------------------------------------------------------------------
-- Row-Level Security. Read-only for users; all writes require the service_role
-- (which bypasses RLS) — there are deliberately no user INSERT/UPDATE/DELETE policies.
-- ---------------------------------------------------------------------------
alter table entitlements    enable row level security;
alter table course_content  enable row level security;

-- A user may see only their own entitlements.
create policy entitlements_self_read on entitlements for select
  using (user_id = auth.uid());

-- Premium content is readable only by a user entitled to that course — this is what
-- keeps it exclusive (a non-entitled or signed-out caller gets zero rows).
create policy course_content_entitled_read on course_content for select
  using (is_entitled(course));
