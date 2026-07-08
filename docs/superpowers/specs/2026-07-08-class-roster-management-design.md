# Roster & Class Management (Owner abilities, Sub-project A) — Design

**Goal:** Give a class owner the day-to-day controls to actually run a class: rename it, rotate its
join code if it leaks, remove a member, and hand out a one-click join link.

**Status:** Approved 2026-07-08. First of three sub-projects expanding owner abilities
(A: roster/management → B: deeper student insight → C: assign/direct work). Remove-member is
**un-enroll only** (keep the student's activity). No true email invites in A (the `?join=` link
covers onboarding without email infrastructure).

## Context

The instructor layer already exists (`supabase/migrations/0001_instructor_formative.sql`):
`classes(instructor_id, name, join_code unique, archived)`, `enrollments(class_id, student_id)`,
`activity(student_id, class_id, kind, ref, score, total, detail)`. `web/accounts.js` exposes the
owner API (`createClass`, `instructorClasses`, `archiveClass`, `deleteClass`, `roster`,
`classActivity`, `joinClass`); `web/account.js` renders the owner UI (`classCard`, `signedInView`).
Sign-in is Google-only (`signInWithGoogle`, OAuth redirect that drops the query string).

Crucially, the RLS already permits everything A needs:
- `classes_owner_all` — `for all using (instructor_id = auth.uid())` → the owner may UPDATE any
  column of their own class (covers **rename** and **rotate code**).
- `enroll_instructor_delete` — `for delete using (is_class_owner(class_id))` → the owner may DELETE
  enrollments in their own class (covers **remove member**).
- `join_class(p_code)` — existing `SECURITY DEFINER` RPC that enrolls the caller by code.
- `gen_join_code()` — existing collision-safe 6-char code generator.

So A is almost entirely client-side. The one backend addition is a small RPC for code rotation,
because the Supabase JS client cannot call `gen_join_code()` inside an UPDATE value.

## Architecture

One tiny migration (a `SECURITY DEFINER` RPC), three thin `accounts.js` methods, owner-UI additions
in `account.js`'s `classCard`, a boot-time join-link handler, and one pure node-tested URL helper.
No new tables, no changes to existing RLS.

## Backend (migration `0006_rotate_join_code.sql`)

```sql
-- Owner-only: assign a fresh unique join code to a class you own. Reuses the
-- collision-safe gen_join_code(). Returns the new code (or raises if not owner).
create function rotate_join_code(p_class uuid) returns text
  language plpgsql security definer set search_path = public as $$
declare v_code text;
begin
  if not is_class_owner(p_class) then
    raise exception 'not the class owner' using errcode = 'insufficient_privilege';
  end if;
  v_code := gen_join_code();
  update classes set join_code = v_code where id = p_class;
  return v_code;
end;
$$;
revoke all on function rotate_join_code(uuid) from public;
grant execute on function rotate_join_code(uuid) to authenticated;
```

Applied via Supabase MCP `apply_migration` and committed to `supabase/migrations/`.

## `accounts.js` (three methods, added to `window.Accounts`)

```js
function renameClass(id, name) {                     // RLS: classes_owner_all
  return client().then(function (c) {
    return c.from("classes").update({ name: name }).eq("id", id);
  });
}
function rotateJoinCode(id) {                          // RPC returns the new code
  return client().then(function (c) { return c.rpc("rotate_join_code", { p_class: id }); });
}
function removeMember(classId, studentId) {           // RLS: enroll_instructor_delete
  return client().then(function (c) {
    return c.from("enrollments").delete().eq("class_id", classId).eq("student_id", studentId);
  });
}
```

Each is best-effort/awaited by the caller; errors surface in the UI. RLS guarantees a non-owner call
affects zero rows / is rejected, so no extra authorization logic is needed client-side.

## `account.js` owner UI (in `classCard`)

1. **Rename.** The class-name heading becomes clickable ("Rename"); clicking swaps it for an input
   pre-filled with the current name plus Save/Cancel. Save validates non-empty (1–120 chars, matching
   the DB check) → `Accounts.renameClass(id, name)` → on success re-render the owning list (`reload`).
2. **Regenerate code.** A "Regenerate" ghost button next to the join code. `window.confirm`:
   "Generate a new join code? The current code stops working immediately. Members already in the
   class stay enrolled." → `Accounts.rotateJoinCode(id)` → show the new code (re-render).
3. **Remove member.** Each roster row gets a "Remove" ghost button. `window.confirm`:
   "Remove <name> from <class>? They keep their own progress and can rejoin with the code." →
   `Accounts.removeMember(classId, studentId)` → re-render. (Un-enroll only; their `activity` rows
   remain, invisible in the roster-driven table, and reappear if they rejoin.)

Styling reuses the existing `.ghost` buttons, `.classhead`, `.code`, and table styles; no or minimal
new CSS.

## Join link (`account.html?join=CODE`)

A pure helper in a small UMD module `web/join_link.js` (same pattern as `auth_url.js`):
`parseJoinCode(search)` → an uppercased 6-char `[A-Z0-9]{6}` code or `null`.

Boot flow in `account.js` (after the existing auth-error handling):
- Read `code = JoinLink.parseJoinCode(location.search)`. If present, stash it in `localStorage`
  (`mrisim_pending_join`) and strip it from the URL (`history.replaceState`) so it survives the
  Google OAuth round-trip (which drops the query string) and a refresh.
- After `getSession()` resolves **with** a session, if a pending code exists: call
  `Accounts.joinClass(code)`, clear the pending key, and show a confirmation ("Joined." / the error)
  before/above the signed-in view.
- If **no** session and a pending code exists: the sign-in view shows a line "You've been invited to
  join a class. Sign in with Google to join." Sign-in proceeds as normal; the pending code is applied
  on the next boot once signed in.

The class name is not shown pre-join (a non-member cannot read the class row under RLS); the joined
class simply appears in "Classes you've joined" afterward. `join_class` already handles an invalid or
archived code with a clear error.

## Error handling / edge cases

- **Rename empty / too long:** client validation mirrors the DB `check (length between 1 and 120)`.
- **Rotate while offline / not owner:** RPC error surfaces in the card; the old code stays.
- **Remove the last member / remove yourself:** an owner is not enrolled in their own class, so they
  cannot remove themselves via the roster; removing the last member just empties the roster.
- **Join code already used / archived class:** `join_class` raises; the message is shown and the
  pending key cleared so it does not retry forever.
- **Storage disabled:** the pending-join stash is in try/catch; without it the `?join=` link only
  works when already signed in (no cross-OAuth persistence), which is an acceptable degradation.

## Testing

- **Node unit test** (`web/join_link.test.mjs`, added to `npm run test:web`): `parseJoinCode` —
  valid code uppercased, lowercase accepted, wrong length/charset → null, missing param → null,
  extra params ignored.
- **Lint/render:** `npm run lint` clean; manual signed-in check that rename, regenerate, and remove
  work and re-render, and that a `?join=CODE` link enrolls after Google sign-in.
- **Security check (post-build, via MCP):** confirm a signed-in non-owner calling
  `update classes` / `delete enrollments` / `rotate_join_code` for a class they do not own affects
  zero rows or is rejected — i.e. the existing RLS + the new RPC's `is_class_owner` guard hold.
- No engine/physics change; the Python suite is unaffected.

## Out of scope (later sub-projects or deferred)

- Per-student drill-down, class-level stats, CSV export, retake/attempt history (Sub-project B).
- Assignments, due dates, required-work completion (Sub-project C).
- True email invitations (needs an email-sending edge function; deferred — `?join=` covers onboarding).
- Enrollment caps / sections / co-instructors (YAGNI for now).
