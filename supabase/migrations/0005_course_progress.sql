-- Cross-device course progress: one jsonb state blob per user, self-scoped by RLS.
-- The client merges monotonically, so this is a best-effort mirror of localStorage.
create table course_progress (
  user_id uuid primary key references auth.users on delete cascade,
  state jsonb not null default '{}',
  updated_at timestamptz not null default now()
);

alter table course_progress enable row level security;

create policy course_progress_self_all on course_progress
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
