# Roster & Class Management (Sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a class owner rename a class, rotate its join code, remove a member, and share a
one-click `?join=CODE` link.

**Architecture:** Almost entirely client-side — the existing RLS (`classes_owner_all`,
`enroll_instructor_delete`) already permits owner rename/remove; only join-code rotation needs a
small owner-checked `SECURITY DEFINER` RPC. Three thin `accounts.js` methods, UI in `account.js`'s
`classCard`, a boot-time join-link handler, and one pure node-tested URL helper (`web/join_link.js`).

**Tech Stack:** Supabase (Postgres RLS + RPC), vanilla browser JS (classic scripts), node --test.

## Global Constraints

- `web/*.js` account files are **classic browser scripts** (ES5 style: `var`, `function () {}`,
  no arrow functions/`let`/`const`). Match the surrounding code exactly.
- Do NOT edit `eslint.config.mjs` (a hook blocks it). New browser globals are referenced via a local
  alias `var X = window.X;` (as `account.js` already does for `AuthUrl`). Pure UMD modules
  (`join_link.js`) are not in an eslint files-block, like `course_logic.js`/`auth_url.js`, so they
  lint clean without config changes; their `*.test.mjs` is covered by the `web/*.mjs` block.
- Copy: no em dashes, no AI-tell punctuation; plain clinical prose.
- UI: reuse existing `.ghost` buttons, `.classhead`, `.code`, `.msg`, table styles. No emoji, no
  gradients, no pills.
- Migration number is `0006` (existing: 0001–0005).
- Remove-member is **un-enroll only** (delete the `enrollments` row; never touch `activity`).
- Join-code validation charset is `[A-Z0-9]{6}` (uppercased).
- `accounts.js` stays config-gated (methods run through `client()`, which rejects when not configured).
- Subagents run on Fable; the final whole-branch review runs on Opus.

---

### Task 1: `rotate_join_code` RPC (migration 0006)

**Files:**
- Create: `supabase/migrations/0006_rotate_join_code.sql`

**Interfaces:**
- Produces: Postgres function `rotate_join_code(p_class uuid) returns text` — owner-checked, returns
  the new join code; `accounts.js` Task 3 calls it via `rpc("rotate_join_code", { p_class })`.

- [ ] **Step 1: Write the migration file** `supabase/migrations/0006_rotate_join_code.sql`:

```sql
-- Owner-only rotation of a class join code. The JS client cannot call gen_join_code()
-- inside an UPDATE value, so this SECURITY DEFINER RPC does it server-side, guarded by
-- is_class_owner(), reusing the collision-safe generator from 0001.
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

- [ ] **Step 2: Apply the migration** via Supabase MCP `apply_migration` (project
  `idgyjmamxxyddjuaamit`, name `rotate_join_code`, the SQL above).

- [ ] **Step 3: Verify the function exists and the owner guard fires.** Run via MCP `execute_sql`:

```sql
select proname from pg_proc where proname = 'rotate_join_code';
-- owner guard: MCP runs as admin with auth.uid() = null, so is_class_owner() is false
-- and the call must raise 'not the class owner'.
do $$ begin
  perform rotate_join_code('00000000-0000-0000-0000-000000000000');
  raise exception 'guard did not fire';
exception when insufficient_privilege then
  raise notice 'owner guard ok';
end $$;
```
Expected: one row `rotate_join_code`; the `do` block emits `NOTICE: owner guard ok`.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0006_rotate_join_code.sql
git commit -m "feat(db): owner-only rotate_join_code RPC (migration 0006)"
```

---

### Task 2: `parseJoinCode` URL helper (pure, node-tested)

**Files:**
- Create: `web/join_link.js`
- Create: `web/join_link.test.mjs`
- Modify: `package.json` (add the test file to `test:web`)

**Interfaces:**
- Produces: `window.JoinLink` / CommonJS export with `parseJoinCode(search) -> string|null`
  (uppercased 6-char `[A-Z0-9]` code, else null). Consumed by `account.js` Task 4.

- [ ] **Step 1: Write the failing test** `web/join_link.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import JoinLink from "./join_link.js";

const { parseJoinCode } = JoinLink;

test("parseJoinCode returns the code from ?join=, uppercased", () => {
  assert.equal(parseJoinCode("?join=A1B2C3"), "A1B2C3");
  assert.equal(parseJoinCode("?join=a1b2c3"), "A1B2C3");
  assert.equal(parseJoinCode("?join=%20a1b2c3%20"), "A1B2C3");
});

test("parseJoinCode ignores other params", () => {
  assert.equal(parseJoinCode("?foo=1&join=A1B2C3&bar=2"), "A1B2C3");
});

test("parseJoinCode returns null for missing or malformed codes", () => {
  assert.equal(parseJoinCode(""), null);
  assert.equal(parseJoinCode("?x=1"), null);
  assert.equal(parseJoinCode("?join="), null);
  assert.equal(parseJoinCode("?join=ABC12"), null);   // 5 chars
  assert.equal(parseJoinCode("?join=ABC1234"), null);  // 7 chars
  assert.equal(parseJoinCode("?join=ABC-12"), null);   // bad charset
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test web/join_link.test.mjs`
Expected: FAIL — cannot find module `./join_link.js`.

- [ ] **Step 3: Implement** `web/join_link.js`:

```js
/* Pure, DOM-free helper: read a class join code from a ?join=CODE query string.
 * UMD like course_logic.js / auth_url.js (window.JoinLink in the browser, module.exports
 * under node). Used by the account page's one-click invite link. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.JoinLink = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Return the uppercased 6-char [A-Z0-9] join code from a query string, or null.
  function parseJoinCode(search) {
    if (!search) return null;
    var s = String(search).replace(/^\?/, "");
    var code = null;
    s.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i < 0) return;
      var k = kv.slice(0, i);
      if (k !== "join") return;
      var v = kv.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) { /* keep raw */ }
      code = v;
    });
    if (code == null) return null;
    code = code.trim().toUpperCase();
    return /^[A-Z0-9]{6}$/.test(code) ? code : null;
  }

  return { parseJoinCode: parseJoinCode };
});
```

- [ ] **Step 4: Add the test to `test:web`.** In `package.json`, change the `test:web` script to:

```json
    "test:web": "node --test web/course_logic.test.mjs web/auth_url.test.mjs web/join_link.test.mjs"
```

- [ ] **Step 5: Run to verify it passes**

Run: `npm run test:web`
Expected: PASS — all node tests green.

- [ ] **Step 6: Commit**

```bash
git add web/join_link.js web/join_link.test.mjs package.json
git commit -m "feat(accounts): parseJoinCode URL helper (join-link)"
```

---

### Task 3: `accounts.js` owner methods

**Files:**
- Modify: `web/accounts.js` (add three functions near `createClass`; extend the `window.Accounts`
  export at lines 268–278)

**Interfaces:**
- Consumes: the `rotate_join_code` RPC (Task 1).
- Produces on `window.Accounts`: `renameClass(id, name)`, `rotateJoinCode(id)`,
  `removeMember(classId, studentId)` — each returns a Supabase promise (`{ data, error }` shape).
  Consumed by `account.js` Tasks 4 and 5. (`joinClass` already exists.)

- [ ] **Step 1: Add the three methods** in `web/accounts.js`, immediately after the existing
  `function createClass(name) { ... }` block:

```js
  // Rename a class you own. RLS (classes_owner_all) scopes this to the owner.
  function renameClass(id, name) {
    return client().then(function (c) {
      return c.from("classes").update({ name: name }).eq("id", id);
    });
  }
  // Rotate the join code of a class you own (server-side, owner-checked RPC). Resolves
  // to { data: <new code>, error }.
  function rotateJoinCode(id) {
    return client().then(function (c) { return c.rpc("rotate_join_code", { p_class: id }); });
  }
  // Remove a member from a class you own (un-enroll only; their activity is untouched).
  // RLS (enroll_instructor_delete) scopes this to the owning instructor.
  function removeMember(classId, studentId) {
    return client().then(function (c) {
      return c.from("enrollments").delete().eq("class_id", classId).eq("student_id", studentId);
    });
  }
```

- [ ] **Step 2: Export them.** In the `window.Accounts = { ... }` object, change the class-methods
  line so it reads:

```js
    createClass: createClass, instructorClasses: instructorClasses,
    renameClass: renameClass, rotateJoinCode: rotateJoinCode, removeMember: removeMember,
    archiveClass: archiveClass, deleteClass: deleteClass,
```

- [ ] **Step 3: Lint**

Run: `npm run lint`
Expected: clean (no output).

- [ ] **Step 4: Commit**

```bash
git add web/accounts.js
git commit -m "feat(accounts): renameClass, rotateJoinCode, removeMember"
```

---

### Task 4: `account.js` owner UI (rename, regenerate, remove member)

**Files:**
- Modify: `web/account.js` — `classCard` (lines 77–125): the `head` block and the roster table.

**Interfaces:**
- Consumes: `Accounts.renameClass`, `Accounts.rotateJoinCode`, `Accounts.removeMember` (Task 3);
  existing `reload`, `clear`, `h`, `td`, `tdNum`, `th`, `when`.

- [ ] **Step 1: Replace the `head` construction** in `classCard`. The current block is:

```js
    var head = h("div", { class: "classhead" }, [
      h("h2", { class: "grow", text: cl.name + (cl.archived ? " (archived)" : "") }),
      h("span", { class: "muted", text: "Join code:" }),
      h("span", { class: "code", text: cl.join_code }),
      archiveBtn, delBtn,
    ]);
```

Replace it with (defines `title`, a `rename` button that edits in place, and a `regen` button):

```js
    var title = h("h2", { class: "grow", text: cl.name + (cl.archived ? " (archived)" : "") });
    var rename = h("button", { class: "ghost", text: "Rename", onclick: function () {
      var input = h("input", { type: "text", value: cl.name });
      var save = h("button", { class: "ghost", text: "Save", onclick: function () {
        var nm = input.value.trim();
        if (nm.length < 1 || nm.length > 120) { input.focus(); return; }
        save.disabled = true;
        Accounts.renameClass(cl.id, nm).then(function (res) {
          if (res && res.error) { save.disabled = false; return; }
          reload();
        }).catch(function () { save.disabled = false; });
      } });
      var cancel = h("button", { class: "ghost", text: "Cancel", onclick: reload });
      clear(head);
      [input, save, cancel].forEach(function (n) { head.appendChild(n); });
      input.focus();
    } });
    var regen = h("button", { class: "ghost", text: "Regenerate", onclick: function () {
      if (!window.confirm("Generate a new join code for \"" + cl.name + "\"? The current code stops working immediately. Members already in the class stay enrolled.")) return;
      regen.disabled = true;
      Accounts.rotateJoinCode(cl.id).then(function (res) {
        regen.disabled = false;
        if (res && res.error) return;
        reload();
      }).catch(function () { regen.disabled = false; });
    } });
    var head = h("div", { class: "classhead" }, [
      title,
      h("span", { class: "muted", text: "Join code:" }),
      h("span", { class: "code", text: cl.join_code }),
      regen, rename, archiveBtn, delBtn,
    ]);
```

- [ ] **Step 2: Add the remove-member column.** In the same `classCard`, change the table header
  row from:

```js
      var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
        th("Member"), th("Quiz runs"), th("Best score"), th("Lessons"), th("Last active"),
      ])])]);
```
to add a trailing empty header cell:
```js
      var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
        th("Member"), th("Quiz runs"), th("Best score"), th("Lessons"), th("Last active"), th(""),
      ])])]);
```

- [ ] **Step 3: Add the Remove button per roster row.** Change the `roster.forEach` body from:

```js
      roster.forEach(function (r) {
        var p = (r.profiles && r.profiles.display_name) || "(unnamed)";
        var s = by[r.student_id] || { quizzes: 0, lessons: {}, bestPct: null, last: null };
        tb.appendChild(h("tr", {}, [
          td(p), tdNum(s.quizzes), tdNum(s.bestPct == null ? "—" : Math.round(s.bestPct) + "%"),
          tdNum(Object.keys(s.lessons).length), tdNum(s.last ? when(s.last) : "—"),
        ]));
      });
```
to:
```js
      roster.forEach(function (r) {
        var p = (r.profiles && r.profiles.display_name) || "(unnamed)";
        var s = by[r.student_id] || { quizzes: 0, lessons: {}, bestPct: null, last: null };
        var rm = h("button", { class: "ghost", text: "Remove", onclick: function () {
          if (!window.confirm("Remove " + p + " from \"" + cl.name + "\"? They keep their own progress and can rejoin with the code.")) return;
          rm.disabled = true;
          Accounts.removeMember(cl.id, r.student_id).then(function (res) {
            if (res && res.error) { rm.disabled = false; return; }
            reload();
          }).catch(function () { rm.disabled = false; });
        } });
        tb.appendChild(h("tr", {}, [
          td(p), tdNum(s.quizzes), tdNum(s.bestPct == null ? "—" : Math.round(s.bestPct) + "%"),
          tdNum(Object.keys(s.lessons).length), tdNum(s.last ? when(s.last) : "—"),
          h("td", {}, [rm]),
        ]));
      });
```

- [ ] **Step 4: Lint**

Run: `npm run lint`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add web/account.js
git commit -m "feat(account): rename, regenerate code, and remove-member UI"
```

---

### Task 5: Join-link boot flow

**Files:**
- Modify: `web/account.html` (load `join_link.js`)
- Modify: `web/account.js` (alias `JoinLink`; pending-join helpers; boot flow; `signInView` and
  `signedInView` optional notes)

**Interfaces:**
- Consumes: `JoinLink.parseJoinCode` (Task 2); existing `Accounts.joinClass`, `Accounts.getSession`,
  `signInView`, `signedInView`.

- [ ] **Step 1: Load the module.** In `web/account.html`, add the script before `accounts.js`:

```html
  <script src="config.js"></script>
  <script src="auth_url.js"></script>
  <script src="join_link.js"></script>
  <script src="accounts.js"></script>
  <script src="account.js"></script>
```

- [ ] **Step 2: Alias the global** in `web/account.js`, next to the existing `AuthUrl` alias
  (`var AuthUrl = window.AuthUrl;`):

```js
  var JoinLink = window.JoinLink;   // pure ?join=CODE parser (join_link.js), loaded before this
```

- [ ] **Step 3: Add pending-join storage helpers** (place them near the other module helpers, e.g.
  just above the `// ---- boot` section):

```js
  var PENDING_JOIN_KEY = "mrisim_pending_join";
  function loadPendingJoin() { try { return localStorage.getItem(PENDING_JOIN_KEY) || null; } catch (e) { return null; } }
  function savePendingJoin(code) { try { localStorage.setItem(PENDING_JOIN_KEY, code); } catch (e) { /* storage off */ } }
  function clearPendingJoin() { try { localStorage.removeItem(PENDING_JOIN_KEY); } catch (e) { /* storage off */ } }
```

- [ ] **Step 4: Capture the invite in boot.** Immediately after the existing
  `if (urlErr) { try { history.replaceState(...) } ... }` line, add:

```js
  // Invite link: stash ?join=CODE so it survives the Google OAuth round-trip (which drops the
  // query string) and a refresh, then strip it from the URL (keep any hash for the auth callback).
  var joinCode = JoinLink ? JoinLink.parseJoinCode(location.search) : null;
  if (joinCode) {
    savePendingJoin(joinCode);
    try { history.replaceState(null, "", location.pathname + location.hash); } catch (e) { /* best-effort */ }
  }
```

- [ ] **Step 5: Apply the pending join after sign-in.** Replace the existing
  `Accounts.getSession().then(...)` success body so a pending code is joined before rendering:

```js
  Accounts.getSession().then(function (session) {
    if (!session) { signInView(errMsg, !!loadPendingJoin()); return; }
    var user = session.user, email = user && user.email;
    var proceed = function (note) {
      Accounts.profile().then(function (prof) {
        signedInChrome(prof, email);
        signedInView(user.id, note);
      });
    };
    var pending = loadPendingJoin();
    if (pending) {
      Accounts.joinClass(pending).then(function (res) {
        clearPendingJoin();
        proceed(res && res.error ? null : "You've joined the class. It is listed below.");
      }).catch(function () { clearPendingJoin(); proceed(null); });
    } else {
      proceed(null);
    }
  }).catch(function (e) {
    signInView(errMsg || ("Something went wrong: " + String(e.message || e)));
  });
```

- [ ] **Step 6: Show the invite hint on the sign-in view.** Change `signInView`'s signature and add
  the hint. The current signature is `function signInView(preErrMsg) {`; change to
  `function signInView(preErrMsg, invited) {` and, inside its `show(card([...]))`, replace the
  single intro `<p class="sub">` so it becomes conditional:

```js
    show(card([
      h("h2", { text: "Sign in" }),
      invited ? h("p", { class: "sub", text: "You've been invited to join a class. Sign in with Google to join it." }) : h("p", { class: "sub", text: "Sign in with your Google account to create classes, join them, and keep your course progress synced across your devices." }),
      gbtn, msg,
    ]));
```

- [ ] **Step 7: Show the join confirmation on the signed-in view.** The current signature is
  `function signedInView(uid) {`; change to `function signedInView(uid, note) {` and, right after
  `var wrap = h("div");`, add:

```js
    if (note) wrap.appendChild(h("p", { class: "msg ok", text: note }));
```

- [ ] **Step 8: Lint + web tests**

Run: `npm run lint && npm run test:web`
Expected: lint clean; all node tests pass.

- [ ] **Step 9: Commit**

```bash
git add web/account.html web/account.js
git commit -m "feat(account): one-click ?join=CODE invite link"
```

---

### Task 6: RLS security verification

**Files:** none (verification only).

**Interfaces:** Consumes the deployed RPC (Task 1) and existing RLS.

- [ ] **Step 1: Simulate a non-owner and confirm every mutation is denied.** Run via MCP
  `execute_sql`. This impersonates an authenticated user who owns nothing (RLS applies to the
  `authenticated` role, unlike the default admin connection):

```sql
-- Seed two owners and a class owned by owner A, with owner B enrolled as a "student".
insert into profiles (id) values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa') on conflict do nothing;
insert into profiles (id) values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb') on conflict do nothing;
insert into classes (id, instructor_id, name)
  values ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'RLS test class')
  on conflict do nothing;
insert into enrollments (class_id, student_id)
  values ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')
  on conflict do nothing;

-- Impersonate owner B (a non-owner of the class) and attempt each mutation.
set local role authenticated;
set local request.jwt.claims = '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated"}';

-- rename: RLS must match zero rows (returns no updated row).
update classes set name = 'HACKED' where id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
  returning id;
-- remove member: RLS must match zero rows.
delete from enrollments where class_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
  and student_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' returning class_id;
-- rotate: the RPC's is_class_owner guard must raise insufficient_privilege.
do $$ begin
  perform rotate_join_code('cccccccc-cccc-cccc-cccc-cccccccccccc');
  raise exception 'rotate guard did not fire';
exception when insufficient_privilege then raise notice 'rotate guard ok'; end $$;
```
Expected: the `update` and `delete` return **0 rows**; the `do` block emits `NOTICE: rotate guard ok`.

- [ ] **Step 2: Confirm the class name and enrollment are unchanged, then clean up.** Run via MCP
  `execute_sql` (a fresh call, back on the admin connection — do NOT reuse the impersonation session):

```sql
select name from classes where id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';   -- 'RLS test class'
delete from classes where id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';         -- cascades enrollment
delete from profiles where id in ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
```
Expected: name is still `RLS test class`; cleanup removes the test rows.

- [ ] **Step 3: Full check.** Run `npm run lint && npm run test:web` and confirm both are green.
  No commit (verification only).

## Self-Review

- **Spec coverage:** RPC (T1), join-code parser (T2), accounts methods (T3), rename/regenerate/remove
  UI (T4), `?join=` link (T5), RLS security check (T6). Every spec section maps to a task.
- **Placeholder scan:** none — each step carries full code/SQL/commands.
- **Type consistency:** `renameClass(id,name)`, `rotateJoinCode(id)`, `removeMember(classId,studentId)`,
  `parseJoinCode(search)`, `signInView(preErrMsg, invited)`, `signedInView(uid, note)` are used
  identically across tasks.
