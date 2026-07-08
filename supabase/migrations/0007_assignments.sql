-- Owner-assigned work for a class: a lesson, a quiz topic, or a whole curriculum
-- module, with an optional due date. Completion is NOT stored here; it is derived
-- client-side from the existing `activity` table (see docs/superpowers/specs/2026-07-08-assignments-design.md).
create table assignments (
  id         uuid        primary key default gen_random_uuid(),
  class_id   uuid        not null references classes(id) on delete cascade,
  kind       text        not null check (kind in ('lesson', 'quiz', 'module')),
  ref        text        not null,          -- lesson title / quiz topic id / module title
  due_at     timestamptz,                   -- nullable = no due date
  created_at timestamptz not null default now()
);
create index assignments_class_idx on assignments (class_id);
-- one assignment per (class, kind, ref); a re-assign updates the due date via upsert.
create unique index assignments_class_kind_ref_idx on assignments (class_id, kind, ref);

alter table assignments enable row level security;

-- Owner of the class does full CRUD; enrolled students may read their classes' rows.
create policy assignments_owner_all on assignments for all
  using (is_class_owner(class_id)) with check (is_class_owner(class_id));
create policy assignments_enrolled_read on assignments for select
  using (is_enrolled(class_id));
