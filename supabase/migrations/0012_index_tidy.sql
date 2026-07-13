-- 0012: Index tidy-up (Supabase linter 0001_unindexed_foreign_keys + 0005_unused_index).
--
-- Two safe, reasoned changes — NOT a blanket "apply every advisor row":
--
-- 1. entitlements.granted_by is a foreign key (-> auth.users) with no covering index.
--    Add one. Without it, deleting an auth.users row seq-scans entitlements to enforce
--    the FK, and lookups of "grants made by X" have no index.
--
-- 2. assignments_class_idx on (class_id) is redundant: the UNIQUE index
--    (class_id, kind, ref) already serves any class_id-leading lookup (btree prefix
--    rule) and continues to cover the class_id FK. Drop the standalone index to save
--    write/storage overhead. No query path is lost.
--
-- Deliberately NOT dropped: enrollments_student_idx on (student_id). The linter marks
-- it "unused", but the PK is (class_id, student_id) so student_id is not a usable index
-- prefix — this is the only index supporting the student-scoped reads (student_id =
-- auth.uid()) that every student query and dashboard runs. It reads as unused only
-- because the instructor/student feature is pre-launch; it becomes load-bearing under
-- real traffic. Keep it.

create index if not exists entitlements_granted_by_idx
  on public.entitlements (granted_by);

drop index if exists public.assignments_class_idx;
