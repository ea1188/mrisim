/* MRISim accounts — the optional instructor/student layer over the free simulator.
 *
 * Config-gated: with no web/config.js (or blank values) every method is inert and
 * the accounts UI stays hidden, so the open, no-account experience is unchanged.
 * Talks to Supabase directly with the public anon key; Row-Level Security is the
 * whole authorization model (see supabase/migrations + docs/INSTRUCTOR_BACKEND.md).
 *
 * supabase-js is lazy-loaded (only when a method actually runs), so a signed-out
 * visitor never pays for it on page load. Defines window.Accounts. */
(function () {
  "use strict";
  var CFG = window.MRISIM_SUPABASE || {};
  var ENABLED = !!(CFG.url && CFG.anonKey);
  var SUPABASE_ESM = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";
  var _client = null;      // cached client
  var _clientP = null;     // in-flight client load

  function enabled() { return ENABLED; }

  // Lazy-load supabase-js and build the client exactly once. detectSessionInUrl
  // lets the magic-link redirect (…/account.html#access_token=…) log the user in.
  function client() {
    if (_client) return Promise.resolve(_client);
    if (!ENABLED) return Promise.reject(new Error("accounts not configured"));
    if (!_clientP) {
      _clientP = import(SUPABASE_ESM).then(function (m) {
        _client = m.createClient(CFG.url, CFG.anonKey, {
          auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
        });
        return _client;
      });
    }
    return _clientP;
  }

  // Cheap, synchronous best-effort read of the persisted session (supabase-js
  // stores it under sb-<ref>-auth-token). Used only to gate best-effort activity
  // sync without loading the library; the account page uses the async authority.
  function _ref() { try { return CFG.url.split("//")[1].split(".")[0]; } catch (e) { return ""; } }
  function cachedSession() {
    try {
      var raw = localStorage.getItem("sb-" + _ref() + "-auth-token");
      if (!raw) return null;
      var s = JSON.parse(raw);
      var sess = s && s.currentSession ? s.currentSession : s;
      if (!sess || !sess.access_token) return null;
      if (sess.expires_at && sess.expires_at * 1000 < Date.now()) return null;
      return sess;
    } catch (e) { return null; }
  }
  function signedIn() { return !!cachedSession(); }

  // --- auth ---------------------------------------------------------------- //
  function signIn(email, opts) {
    opts = opts || {};
    return client().then(function (c) {
      return c.auth.signInWithOtp({
        email: email,
        options: {
          emailRedirectTo: opts.redirectTo || (location.origin + location.pathname),
          data: opts.meta || undefined,   // role/name — applied on first sign-in only
        },
      });
    });
  }
  // Verify a 6-digit code the user typed from the sign-in email (verifyOtp). This is
  // the scanner-proof path: corporate mail systems (Microsoft Safe Links, prefetchers)
  // open the one-time magic-link before the human, spending the token; a typed code
  // can't be consumed that way. type "email" covers new and returning users alike.
  function verifyCode(email, code) {
    return client().then(function (c) {
      return c.auth.verifyOtp({
        email: email,
        token: String(code == null ? "" : code).trim(),
        type: "email",
      });
    });
  }
  function signOut() { return client().then(function (c) { return c.auth.signOut(); }); }
  // OAuth (Google): redirect to Google, then back to `redirectTo`; the client's
  // detectSessionInUrl completes the sign-in on return. One click, no email.
  function signInWithGoogle(opts) {
    opts = opts || {};
    return client().then(function (c) {
      return c.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: opts.redirectTo || (location.origin + location.pathname) },
      });
    });
  }
  function getSession() {
    return client().then(function (c) { return c.auth.getSession(); })
      .then(function (r) { return r.data.session; });
  }
  function getUser() {
    return client().then(function (c) { return c.auth.getUser(); })
      .then(function (r) { return r.data.user; });
  }
  function profile() {
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return null;
        return c.from("profiles").select("id,role,display_name,institution")
          .eq("id", u.id).maybeSingle().then(function (p) { return p.data; });
      });
    });
  }
  function onChange(cb) {
    return client().then(function (c) {
      return c.auth.onAuthStateChange(function (_e, s) { cb(s); });
    });
  }

  // --- learner: formative activity sync ------------------------------------ //
  // Best-effort: never block or error the learner. No-op when off or signed out.
  function logActivity(kind, ref, score, total, detail) {
    if (!ENABLED || !signedIn()) return Promise.resolve();
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return null;
        // Stamp to the learner's class if enrolled (RLS returns only theirs).
        return c.from("enrollments").select("class_id").limit(1).then(function (e) {
          var classId = e.data && e.data[0] ? e.data[0].class_id : null;
          return c.from("activity").insert({
            student_id: u.id, class_id: classId, kind: kind, ref: String(ref),
            score: score == null ? null : score | 0,
            total: total == null ? null : total | 0,
            detail: detail || {},
          });
        });
      });
    }).catch(function () { /* formative sync is best-effort */ });
  }

  // --- learner: cross-device course progress sync -------------------------- //
  // Best-effort mirror of the course's localStorage state. Never block or error the learner.
  function loadProgress() {
    if (!ENABLED || !signedIn()) return Promise.resolve(null);
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return null;
        return c.from("course_progress").select("state").eq("user_id", u.id).maybeSingle()
          .then(function (p) { return p.data ? p.data.state : null; });
      });
    }).catch(function () { return null; });
  }
  function saveProgress(state) {
    if (!ENABLED || !signedIn()) return Promise.resolve();
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return null;
        return c.from("course_progress").upsert(
          { user_id: u.id, state: state, updated_at: new Date().toISOString() },
          { onConflict: "user_id" });
      });
    }).catch(function () { /* progress sync is best-effort */ });
  }

  // --- student ------------------------------------------------------------- //
  function joinClass(code) {
    return client().then(function (c) {
      return c.rpc("join_class", { p_code: String(code || "").trim() });
    });
  }
  function myClasses() {
    return client().then(function (c) {
      return c.from("classes").select("id,name,join_code,instructor_id");
    }).then(function (r) { return r.data || []; });
  }
  function myActivity() {
    return client().then(function (c) {
      return c.from("activity").select("kind,ref,score,total,created_at")
        .order("created_at", { ascending: false }).limit(50);
    }).then(function (r) { return r.data || []; });
  }

  // --- instructor ---------------------------------------------------------- //
  function createClass(name) {
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        return c.from("classes").insert({ instructor_id: r.data.user.id, name: name })
          .select().single();
      });
    });
  }
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
  // Classes this user OWNS (teaches). Filtered by instructor_id, because RLS also
  // grants read on classes the user is merely enrolled in — without this filter the
  // account page would list a class under both "teach" and "joined".
  function instructorClasses() {
    return client().then(function (c) {
      return c.auth.getUser().then(function (u) {
        return c.from("classes").select("id,name,join_code,archived,created_at")
          .eq("instructor_id", u.data.user.id)
          .order("created_at", { ascending: false });
      });
    }).then(function (r) { return r.data || []; });
  }
  function archiveClass(classId, archived) {
    return client().then(function (c) {
      return c.from("classes").update({ archived: !!archived }).eq("id", classId);
    });
  }
  function deleteClass(classId) {
    return client().then(function (c) {
      return c.from("classes").delete().eq("id", classId);   // cascades enrollments + activity
    });
  }
  function roster(classId) {
    return client().then(function (c) {
      return c.from("enrollments")
        .select("student_id,joined_at,profiles(display_name,institution)")
        .eq("class_id", classId);
    }).then(function (r) { return r.data || []; });
  }
  function classActivity(classId) {
    return client().then(function (c) {
      return c.from("activity").select("student_id,kind,ref,score,total,created_at")
        .eq("class_id", classId).order("created_at", { ascending: false }).limit(1000);
    }).then(function (r) { return r.data || []; });
  }

  // --- paid course: entitlement + exclusive premium content ---------------- //
  // isEntitled: does the signed-in user hold this course? (RLS returns only own rows.)
  function isEntitled(course) {
    if (!ENABLED) return Promise.resolve(false);
    return client().then(function (c) {
      return c.from("entitlements").select("course").eq("course", course).maybeSingle();
    }).then(function (r) { return !!(r && r.data); }).catch(function () { return false; });
  }
  // requestRefund: ask the refund-course edge function to refund the purchase + revoke
  // this course (the server enforces the window + that it's the caller's own purchase).
  function requestRefund(course) {
    return client().then(function (c) {
      return c.functions.invoke("refund-course", { body: { course: course || "mri-core" } });
    });
  }
  // premiumContent: the exclusive course material — RLS serves rows only to an entitled
  // user, so a signed-out or non-entitled caller gets [].
  function premiumContent(course) {
    return client().then(function (c) {
      return c.from("course_content").select("topic,kind,ord,body")
        .eq("course", course).order("ord", { ascending: true });
    }).then(function (r) { return r.data || []; }).catch(function () { return []; });
  }

  // Reveal any element tagged .accounts-only when the layer is configured
  // (e.g. the "Sign in" link in a page footer), so it stays hidden otherwise.
  // When the visitor is already signed in, relabel a "Sign in" entry point to
  // "Account" so the nav reflects state (best-effort from the cached session, so
  // it paints on first render without waiting on the network).
  function _revealLinks() {
    if (!ENABLED) return;
    var signed = signedIn();
    var els = document.querySelectorAll(".accounts-only");
    for (var i = 0; i < els.length; i++) {
      els[i].hidden = false;
      if (signed && /sign\s*in/i.test(els[i].textContent)) els[i].textContent = "Account";
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _revealLinks);
  } else { _revealLinks(); }

  window.Accounts = {
    enabled: enabled, signedIn: signedIn, cachedSession: cachedSession, client: client,
    signIn: signIn, verifyCode: verifyCode, signInWithGoogle: signInWithGoogle, signOut: signOut, getSession: getSession, getUser: getUser,
    profile: profile, onChange: onChange, logActivity: logActivity,
    joinClass: joinClass, myClasses: myClasses, myActivity: myActivity,
    createClass: createClass, instructorClasses: instructorClasses,
    renameClass: renameClass, rotateJoinCode: rotateJoinCode, removeMember: removeMember,
    archiveClass: archiveClass, deleteClass: deleteClass,
    roster: roster, classActivity: classActivity,
    isEntitled: isEntitled, premiumContent: premiumContent, requestRefund: requestRefund,
    loadProgress: loadProgress, saveProgress: saveProgress,
  };
})();
