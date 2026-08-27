-- 0016: co-instructors. A class owner shares a separate *instructor* invite code;
-- a colleague who redeems it becomes a teach-level co-instructor: they see the
-- roster, per-student insight and the activity feed, and they manage assignments.
-- Class administration — rename/archive/delete, rotating either code, removing
-- students, removing instructors — stays with the owner (classes.instructor_id).
--
-- The instructor code deliberately lives in its OWN owner-readable table, not as a
-- column on classes: enrolled students can select their class row (the student
-- join_code is visible to them by design), and the instructor code must never be —
-- otherwise any student could promote themselves to co-instructor.
--
-- Idempotent: guarded creates; policies dropped-if-exists before recreation.

-- ── membership ────────────────────────────────────────────────────────────────
create table if not exists public.class_instructors (
  class_id      uuid        not null references public.classes(id) on delete cascade,
  instructor_id uuid        not null references public.profiles(id) on delete cascade,
  added_at      timestamptz not null default now(),
  primary key (class_id, instructor_id)
);
create index if not exists class_instructors_instructor_idx
  on public.class_instructors (instructor_id);

-- ── instructor invite codes (owner-readable only) ─────────────────────────────
create table if not exists public.class_instructor_codes (
  class_id uuid primary key references public.classes(id) on delete cascade,
  code     text not null unique
);

-- Same shape as gen_join_code(), colliding against BOTH code namespaces so a
-- student code and an instructor code can never be the same string.
create or replace function private.gen_instructor_code() returns text
  language plpgsql set search_path = public as $$
declare v_code text;
begin
  loop
    v_code := upper(substr(md5(random()::text), 1, 6));
    exit when not exists (select 1 from class_instructor_codes where code = v_code)
      and not exists (select 1 from classes where join_code = v_code);
  end loop;
  return v_code;
end;
$$;
revoke all on function private.gen_instructor_code() from public, anon, authenticated;

-- Every class gets a code row: seeded by trigger on creation, backfilled for
-- existing classes. SECURITY DEFINER so the creating instructor's role doesn't
-- need (and doesn't get) insert rights on the codes table.
create or replace function private.seed_instructor_code() returns trigger
  language plpgsql security definer set search_path = public, private as $$
begin
  insert into class_instructor_codes (class_id, code)
  values (new.id, private.gen_instructor_code())
  on conflict do nothing;
  return new;
end;
$$;
revoke all on function private.seed_instructor_code() from public, anon, authenticated;

drop trigger if exists classes_seed_instructor_code on public.classes;
create trigger classes_seed_instructor_code
  after insert on public.classes
  for each row execute function private.seed_instructor_code();

insert into public.class_instructor_codes (class_id, code)
select id, private.gen_instructor_code() from public.classes
on conflict do nothing;

-- ── helpers ───────────────────────────────────────────────────────────────────
-- "Teaches this class": the owner or a co-instructor. is_class_owner stays
-- owner-only and keeps guarding the administrative surface.
create or replace function private.is_class_instructor(p_class uuid) returns boolean
  language sql security definer stable set search_path = public as $$
  select exists (select 1 from classes
                  where id = p_class and instructor_id = auth.uid())
      or exists (select 1 from class_instructors
                  where class_id = p_class and instructor_id = auth.uid());
$$;

-- Profile visibility now follows teaching, not just ownership: I can read the
-- profile of anyone who studies in — or co-teaches — a class I teach.
create or replace function private.shares_class_with_me(p_student uuid) returns boolean
  language sql security definer stable set search_path = public, private as $$
  select exists (select 1 from enrollments e
                  where e.student_id = p_student
                    and private.is_class_instructor(e.class_id))
      or exists (select 1 from classes c
                  where (c.instructor_id = p_student
                         or exists (select 1 from class_instructors ci
                                     where ci.class_id = c.id
                                       and ci.instructor_id = p_student))
                    and private.is_class_instructor(c.id));
$$;

-- ── RLS: widen reads (and assignment writes) from owner to instructor ─────────
-- Recreated policies keep the 0010 `(select auth.uid())` init-plan form and the
-- 0011 cheap-check-first ordering; helpers are schema-qualified (0013).

drop policy if exists activity_read on public.activity;
create policy activity_read on public.activity for select
  using (
    (student_id = (select auth.uid()))
    or ((class_id is not null) and private.is_class_instructor(class_id))
  );

drop policy if exists assignments_read on public.assignments;
create policy assignments_read on public.assignments for select
  using (private.is_class_instructor(class_id) or private.is_enrolled(class_id));
drop policy if exists assignments_owner_insert on public.assignments;
create policy assignments_owner_insert on public.assignments for insert
  with check (private.is_class_instructor(class_id));
drop policy if exists assignments_owner_update on public.assignments;
create policy assignments_owner_update on public.assignments for update
  using (private.is_class_instructor(class_id))
  with check (private.is_class_instructor(class_id));
drop policy if exists assignments_owner_delete on public.assignments;
create policy assignments_owner_delete on public.assignments for delete
  using (private.is_class_instructor(class_id));

drop policy if exists classes_read on public.classes;
create policy classes_read on public.classes for select
  using (
    (instructor_id = (select auth.uid()))
    or private.is_enrolled(id)
    or private.is_class_instructor(id)
  );

drop policy if exists enroll_read on public.enrollments;
create policy enroll_read on public.enrollments for select
  using ((student_id = (select auth.uid())) or private.is_class_instructor(class_id));
-- enroll_delete is untouched: removing students stays owner-only (plus self-leave).

-- ── RLS on the new tables ─────────────────────────────────────────────────────
alter table public.class_instructors enable row level security;
drop policy if exists class_instructors_read on public.class_instructors;
create policy class_instructors_read on public.class_instructors for select
  using ((instructor_id = (select auth.uid())) or private.is_class_instructor(class_id));
drop policy if exists class_instructors_delete on public.class_instructors;
create policy class_instructors_delete on public.class_instructors for delete
  using ((instructor_id = (select auth.uid())) or private.is_class_owner(class_id));
-- No insert/update policy: membership is created only via join_class_instructor().

alter table public.class_instructor_codes enable row level security;
drop policy if exists class_instructor_codes_owner_read on public.class_instructor_codes;
create policy class_instructor_codes_owner_read on public.class_instructor_codes for select
  using (private.is_class_owner(class_id));
-- No insert/update/delete policy: rows are managed by the trigger and rotate RPC.

-- ── RPCs ──────────────────────────────────────────────────────────────────────
-- Redeem an instructor code. SECURITY DEFINER for the same reason as join_class:
-- no "select any class by its code" policy exists, so codes can't be enumerated.
-- The owner redeeming their own code is a harmless no-op.
create or replace function public.join_class_instructor(p_code text) returns uuid
  language plpgsql security definer set search_path = public as $$
declare v_class uuid; v_owner uuid;
begin
  select c.id, c.instructor_id into v_class, v_owner
    from class_instructor_codes cic
    join classes c on c.id = cic.class_id
   where cic.code = upper(trim(p_code)) and not c.archived;
  if v_class is null then
    raise exception 'invalid or archived instructor code' using errcode = 'no_data_found';
  end if;
  if v_owner <> auth.uid() then
    insert into class_instructors (class_id, instructor_id)
    values (v_class, auth.uid())
    on conflict do nothing;
  end if;
  return v_class;
end;
$$;
revoke all on function public.join_class_instructor(text) from public, anon;
grant execute on function public.join_class_instructor(text) to authenticated;

-- Owner-only rotation, mirroring rotate_join_code (0006/0013).
create or replace function public.rotate_instructor_code(p_class uuid) returns text
  language plpgsql security definer set search_path = public, private as $$
declare v_code text;
begin
  if not private.is_class_owner(p_class) then
    raise exception 'not the class owner' using errcode = 'insufficient_privilege';
  end if;
  v_code := private.gen_instructor_code();
  update class_instructor_codes set code = v_code where class_id = p_class;
  if not found then
    insert into class_instructor_codes (class_id, code) values (p_class, v_code);
  end if;
  return v_code;
end;
$$;
revoke all on function public.rotate_instructor_code(uuid) from public, anon;
grant execute on function public.rotate_instructor_code(uuid) to authenticated;
