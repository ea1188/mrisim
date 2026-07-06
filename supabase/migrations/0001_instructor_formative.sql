-- MRISim instructor backend — formative MVP (Phase 1: schema + access policies).
--
-- All learner compute stays in the browser (Pyodide); this backend stores only
-- identity, class rosters, and *formative* activity (practice-quiz scores, lesson
-- completion). Scores here are practice signal, NOT trusted grades: the quiz
-- answers ship to the client in quiz.json, so a graded-exam path (a server-held
-- question bank) is a later phase and deliberately not modelled here.
--
-- Target: Postgres / Supabase. Access is enforced entirely by Row-Level Security
-- so the browser can talk to the database directly with the anon key — there is
-- no app server. Apply with `supabase db push` or paste into the SQL editor.

-- ---------------------------------------------------------------------------
-- Schema
-- ---------------------------------------------------------------------------
create type user_role as enum ('instructor', 'student');

-- One row per authenticated user, created automatically on sign-up (trigger below).
create table profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  role         user_role   not null default 'student',
  display_name text        not null default '',
  institution  text        not null default '',
  created_at   timestamptz not null default now()
);

-- A short, human-typeable, collision-free class code (e.g. "A1B2C3").
create function gen_join_code() returns text language plpgsql as $$
declare code text;
begin
  loop
    code := upper(substr(md5(random()::text), 1, 6));
    exit when not exists (select 1 from classes where join_code = code);
  end loop;
  return code;
end;
$$;

create table classes (
  id            uuid primary key default gen_random_uuid(),
  instructor_id uuid        not null references profiles(id) on delete cascade,
  name          text        not null check (length(name) between 1 and 120),
  join_code     text        not null unique default gen_join_code(),
  archived      boolean     not null default false,
  created_at    timestamptz not null default now()
);
create index classes_instructor_idx on classes (instructor_id);

create table enrollments (
  class_id   uuid        not null references classes(id) on delete cascade,
  student_id uuid        not null references profiles(id) on delete cascade,
  joined_at  timestamptz not null default now(),
  primary key (class_id, student_id)
);
create index enrollments_student_idx on enrollments (student_id);

-- Append-only formative activity. `class_id` is nullable so activity from a
-- learner not (yet) in a class is still captured; it's stamped when they enroll.
create table activity (
  id         bigint generated always as identity primary key,
  student_id uuid        not null references profiles(id) on delete cascade,
  class_id   uuid        references classes(id) on delete set null,
  kind       text        not null check (kind in ('lesson_complete', 'quiz_attempt')),
  ref        text        not null,                    -- topic id / lesson title
  score      int         check (score >= 0),          -- practice score (null for lessons)
  total      int         check (total >= 0),
  detail     jsonb       not null default '{}',
  created_at timestamptz not null default now()
);
create index activity_student_idx on activity (student_id, created_at desc);
create index activity_class_idx   on activity (class_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Sign-up: auto-create a profile. Role comes from sign-up metadata (defaulting
-- to student); a bad/absent value falls back to student rather than erroring.
-- ---------------------------------------------------------------------------
create function handle_new_user() returns trigger
  language plpgsql security definer set search_path = public as $$
begin
  insert into profiles (id, role, display_name, institution)
  values (
    new.id,
    case when new.raw_user_meta_data ->> 'role' = 'instructor'
         then 'instructor'::user_role else 'student'::user_role end,
    coalesce(new.raw_user_meta_data ->> 'display_name', ''),
    coalesce(new.raw_user_meta_data ->> 'institution', '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ---------------------------------------------------------------------------
-- Enrolment by code. A SECURITY DEFINER function so we never expose a
-- "select any class by its code" policy (which would let anyone enumerate
-- classes); the student only ever learns about the one code they were given.
-- ---------------------------------------------------------------------------
create function join_class(p_code text) returns uuid
  language plpgsql security definer set search_path = public as $$
declare v_class uuid;
begin
  select id into v_class
    from classes
   where join_code = upper(trim(p_code)) and not archived;
  if v_class is null then
    raise exception 'invalid or archived join code' using errcode = 'no_data_found';
  end if;
  insert into enrollments (class_id, student_id)
  values (v_class, auth.uid())
  on conflict do nothing;
  return v_class;
end;
$$;
revoke all on function join_class(text) from public;
grant execute on function join_class(text) to authenticated;

-- ---------------------------------------------------------------------------
-- Access helpers. The cross-table membership checks live in SECURITY DEFINER
-- functions (which run with RLS bypassed) so that a policy on `classes` can ask
-- about `enrollments` and vice-versa *without* the two tables' policies
-- referencing each other and tripping Postgres' "infinite recursion detected in
-- policy" — the standard Supabase pattern. Created after the tables because
-- `language sql` bodies are validated at creation time.
-- ---------------------------------------------------------------------------
create function is_class_owner(p_class uuid) returns boolean
  language sql security definer stable set search_path = public as $$
  select exists (select 1 from classes
                  where id = p_class and instructor_id = auth.uid());
$$;

create function is_enrolled(p_class uuid) returns boolean
  language sql security definer stable set search_path = public as $$
  select exists (select 1 from enrollments
                  where class_id = p_class and student_id = auth.uid());
$$;

create function shares_class_with_me(p_student uuid) returns boolean
  language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from enrollments e join classes c on c.id = e.class_id
     where e.student_id = p_student and c.instructor_id = auth.uid());
$$;

-- ---------------------------------------------------------------------------
-- Row-Level Security. Multiple permissive policies on a table are OR-combined.
-- ---------------------------------------------------------------------------
alter table profiles    enable row level security;
alter table classes     enable row level security;
alter table enrollments enable row level security;
alter table activity    enable row level security;

-- profiles: read/update your own row; instructors may read the profiles of
-- students enrolled in a class they own (for the roster/dashboard).
create policy profiles_self_select on profiles for select using (id = auth.uid());
create policy profiles_self_insert on profiles for insert with check (id = auth.uid());
create policy profiles_self_update on profiles for update using (id = auth.uid());
create policy profiles_instructor_read on profiles for select
  using (shares_class_with_me(id));

-- classes: instructors own their classes; students read classes they're in.
create policy classes_owner_all on classes for all
  using (instructor_id = auth.uid()) with check (instructor_id = auth.uid());
create policy classes_enrolled_read on classes for select using (is_enrolled(id));

-- enrollments: student reads/leaves own; instructor reads/removes for own classes.
-- (Inserts go through join_class(), not a direct policy.)
create policy enroll_self_read on enrollments for select using (student_id = auth.uid());
create policy enroll_self_delete on enrollments for delete using (student_id = auth.uid());
create policy enroll_instructor_read on enrollments for select
  using (is_class_owner(class_id));
create policy enroll_instructor_delete on enrollments for delete
  using (is_class_owner(class_id));

-- activity: a student writes/reads their own; an instructor reads activity
-- stamped to a class they own.
create policy activity_self_all on activity for all
  using (student_id = auth.uid()) with check (student_id = auth.uid());
create policy activity_instructor_read on activity for select
  using (class_id is not null and is_class_owner(class_id));
