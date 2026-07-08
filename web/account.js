/* MRISim account page controller. Uses window.Accounts (accounts.js). Renders the
 * sign-in form when signed out, and one unified self-serve view when signed in:
 * every account can create classes (and share join codes) AND join classes with a
 * code. "Instructor" is a per-class relationship — you own the classes you create —
 * not an account type, so there is no role fork. */
(function () {
  "use strict";
  var root = document.getElementById("root");
  var whoami = document.getElementById("whoami");
  var AuthUrl = window.AuthUrl;   // pure URL/code helpers (auth_url.js), loaded before this

  // Tiny DOM builder. Children may be nodes or strings (set as textContent-safe).
  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === "class") e.className = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] === true) e.setAttribute(k, "");
      else if (attrs[k] != null && attrs[k] !== false) e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) {
      e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return e;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function show(nodes) { clear(root); (Array.isArray(nodes) ? nodes : [nodes]).forEach(function (n) { root.appendChild(n); }); }
  function card(kids) { return h("div", { class: "card" }, kids); }

  function notConfigured() {
    show(card([h("h2", { text: "Accounts are not set up" }),
      h("p", { class: "sub", text: "This MRISim deployment has no backend configured, so there is nothing to sign in to. The simulator, planner and quiz all work without an account." })]));
  }

  // ---- sign-in (signed out) --------------------------------------------- //
  // preErrMsg: an optional message to show on entry (e.g. a magic link that a mail
  // scanner already consumed — see the boot handler and auth_url.js).
  function signInView(preErrMsg) {
    var email = h("input", { type: "email", id: "email", placeholder: "you@school.edu", autocomplete: "email" });
    var name = h("input", { type: "text", id: "name", placeholder: "Your name (optional)" });
    var inst = h("input", { type: "text", id: "inst", placeholder: "Institution (optional)" });
    var msg = h("div", { class: "msg" });
    if (preErrMsg) { msg.className = "msg err"; msg.textContent = preErrMsg; }
    var sentAddr = "";

    // Code entry: the reliable path when a mail system opens the link before the user.
    // Hidden until an email is sent, then revealed so they can paste the 6-digit code.
    var code = h("input", { type: "text", id: "code", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "6", placeholder: "123456" });
    var verify = h("button", { class: "primary", text: "Verify code", onclick: function () {
      var c = code.value.trim();
      if (!AuthUrl || !AuthUrl.looksLikeCode(c)) { msg.className = "msg err"; msg.textContent = "Enter the 6-digit code from the email."; return; }
      verify.disabled = true; msg.className = "msg"; msg.textContent = "Verifying…";
      Accounts.verifyCode(sentAddr || email.value.trim(), c).then(function (r) {
        if (r && r.error) { verify.disabled = false; msg.className = "msg err"; msg.textContent = r.error.message; return; }
        location.reload();   // boot re-runs, finds the fresh session, renders the signed-in view
      }).catch(function (e) { verify.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });
    var codeRow = h("div", { hidden: true, style: "margin-top:14px" }, [
      h("label", { text: "6-digit code from the email" }), code, verify,
    ]);

    var btn = h("button", { class: "primary", text: "Email me a sign-in link", onclick: function () {
      var addr = email.value.trim();
      if (!addr) { msg.className = "msg err"; msg.textContent = "Enter your email."; return; }
      btn.disabled = true; msg.className = "msg"; msg.textContent = "Sending…";
      Accounts.signIn(addr, { meta: { display_name: name.value.trim(), institution: inst.value.trim() } })
        .then(function (r) {
          btn.disabled = false;
          if (r && r.error) { msg.className = "msg err"; msg.textContent = r.error.message; return; }
          sentAddr = addr;
          codeRow.hidden = false;
          msg.className = "msg ok";
          msg.textContent = "Check " + addr + " for the sign-in email. Click its link, or if that does not work, paste the 6-digit code below.";
          try { code.focus(); } catch (e) { /* focus is best-effort */ }
        })
        .catch(function (e) { btn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });

    var gbtn = h("button", { class: "primary", text: "Continue with Google", onclick: function () {
      gbtn.disabled = true; msg.className = "msg"; msg.textContent = "Redirecting to Google…";
      Accounts.signInWithGoogle().then(function (r) {
        if (r && r.error) { gbtn.disabled = false; msg.className = "msg err"; msg.textContent = r.error.message; }
      }).catch(function (e) { gbtn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });

    show(card([
      h("h2", { text: "Sign in" }),
      h("p", { class: "sub", text: "One click with Google, or use email below. It's the same account either way — once you're in you can create classes and join them." }),
      gbtn,
      h("p", { class: "sub", style: "margin:16px 0 2px", text: "or sign in with email" }),
      h("label", { text: "Email" }), email,
      h("label", { text: "Name" }), name,
      h("label", { text: "Institution" }), inst,
      btn, codeRow, msg,
    ]));
  }

  // ---- signed in -------------------------------------------------------- //
  function signedInChrome(prof, email) {
    whoami.hidden = false;
    clear(whoami);
    whoami.appendChild(document.createTextNode((prof && prof.display_name ? prof.display_name + " · " : "") + (email || "") + " "));
    whoami.appendChild(h("button", { text: "Sign out", onclick: function () {
      Accounts.signOut().then(function () { location.reload(); });
    } }));
  }

  function pct(s, t) { return t ? Math.round((100 * s) / t) + "%" : "—"; }
  function when(iso) { try { return new Date(iso).toLocaleDateString(); } catch (e) { return ""; } }
  function th(t) { return h("th", { text: t }); }
  function td(t) { return h("td", { text: t }); }
  function tdNum(t) { return h("td", { class: "num", text: String(t) }); }

  // A class you own: join code, roster and each member's formative practice.
  // `reload` re-fetches the owning list after archive/delete.
  function classCard(cl, reload) {
    var body = h("div");
    var archiveBtn = h("button", { class: "ghost", text: cl.archived ? "Unarchive" : "Archive", onclick: function () {
      archiveBtn.disabled = true;
      Accounts.archiveClass(cl.id, !cl.archived).then(reload).catch(function () { archiveBtn.disabled = false; });
    } });
    var delBtn = h("button", { class: "ghost", text: "Delete", onclick: function () {
      if (!window.confirm("Delete \"" + cl.name + "\"? This removes its roster and all its activity. This cannot be undone.")) return;
      delBtn.disabled = true;
      Accounts.deleteClass(cl.id).then(reload).catch(function () { delBtn.disabled = false; });
    } });
    var head = h("div", { class: "classhead" }, [
      h("h2", { class: "grow", text: cl.name + (cl.archived ? " (archived)" : "") }),
      h("span", { class: "muted", text: "Join code:" }),
      h("span", { class: "code", text: cl.join_code }),
      archiveBtn, delBtn,
    ]);
    var c = card([head, body]);
    body.appendChild(h("p", { class: "muted", text: "Loading roster…" }));
    Promise.all([Accounts.roster(cl.id), Accounts.classActivity(cl.id)]).then(function (res) {
      clear(body);
      var roster = res[0], acts = res[1];
      if (!roster.length) { body.appendChild(h("p", { class: "muted", text: "No members yet. Share the join code above." })); return; }
      // Aggregate per student.
      var by = {};
      acts.forEach(function (a) {
        var s = by[a.student_id] || (by[a.student_id] = { quizzes: 0, lessons: {}, bestPct: null, last: null });
        if (a.kind === "quiz_attempt") { s.quizzes++; if (a.total) { var p = (100 * a.score) / a.total; if (s.bestPct == null || p > s.bestPct) s.bestPct = p; } }
        if (a.kind === "lesson_complete") s.lessons[a.ref] = true;   // distinct lessons, not repeats
        if (!s.last || a.created_at > s.last) s.last = a.created_at;
      });
      var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
        th("Member"), th("Quiz runs"), th("Best score"), th("Lessons"), th("Last active"),
      ])])]);
      var tb = h("tbody");
      roster.forEach(function (r) {
        var p = (r.profiles && r.profiles.display_name) || "(unnamed)";
        var s = by[r.student_id] || { quizzes: 0, lessons: {}, bestPct: null, last: null };
        tb.appendChild(h("tr", {}, [
          td(p), tdNum(s.quizzes), tdNum(s.bestPct == null ? "—" : Math.round(s.bestPct) + "%"),
          tdNum(Object.keys(s.lessons).length), tdNum(s.last ? when(s.last) : "—"),
        ]));
      });
      tbl.appendChild(tb);
      body.appendChild(tbl);
      body.appendChild(h("p", { class: "muted", text: roster.length + " member" + (roster.length === 1 ? "" : "s") + " · practice scores are formative, not graded exams." }));
    });
    return c;
  }

  // ---- unified signed-in view (everyone can teach and join) ------------- //
  function signedInView(uid) {
    var wrap = h("div");
    var teachList = h("div"), joinedList = h("div"), recent = h("div");

    // -- teach: create a class + the classes you own --
    var nameIn = h("input", { type: "text", placeholder: "e.g. MRI Physics — Fall 2026" });
    var cmsg = h("div", { class: "msg" });
    var create = h("button", { class: "primary", text: "Create class", onclick: function () {
      var nm = nameIn.value.trim();
      if (!nm) { cmsg.className = "msg err"; cmsg.textContent = "Name the class."; return; }
      create.disabled = true;
      Accounts.createClass(nm).then(function (r) {
        create.disabled = false;
        if (r && r.error) { cmsg.className = "msg err"; cmsg.textContent = r.error.message; return; }
        nameIn.value = ""; cmsg.textContent = ""; loadTeach();
      }).catch(function (e) { create.disabled = false; cmsg.className = "msg err"; cmsg.textContent = String(e.message || e); });
    } });
    function loadTeach() {
      clear(teachList);
      teachList.appendChild(h("p", { class: "muted", text: "Loading…" }));
      Accounts.instructorClasses().then(function (classes) {
        clear(teachList);
        if (!classes.length) { teachList.appendChild(h("p", { class: "muted", text: "No classes yet — create one above, then share its join code." })); return; }
        classes.forEach(function (cl) { teachList.appendChild(classCard(cl, loadTeach)); });
      });
    }

    // -- join: enter a code + the classes you've joined (owned ones excluded) --
    var codeIn = h("input", { type: "text", placeholder: "e.g. A1B2C3", maxlength: "12" });
    var jmsg = h("div", { class: "msg" });
    var join = h("button", { class: "primary", text: "Join class", onclick: function () {
      var code = codeIn.value.trim();
      if (!code) { jmsg.className = "msg err"; jmsg.textContent = "Enter the code you were given."; return; }
      join.disabled = true; jmsg.className = "msg"; jmsg.textContent = "Joining…";
      Accounts.joinClass(code).then(function (r) {
        join.disabled = false;
        if (r && r.error) { jmsg.className = "msg err"; jmsg.textContent = r.error.message || "That code didn't work."; return; }
        codeIn.value = ""; jmsg.className = "msg ok"; jmsg.textContent = "Joined."; loadJoined();
      }).catch(function (e) { join.disabled = false; jmsg.className = "msg err"; jmsg.textContent = String(e.message || e); });
    } });
    function loadJoined() {
      clear(joinedList);
      joinedList.appendChild(h("p", { class: "muted", text: "Loading…" }));
      Accounts.myClasses().then(function (cs) {
        clear(joinedList);
        var joined = cs.filter(function (c) { return c.instructor_id !== uid; });  // not the ones you own
        if (!joined.length) { joinedList.appendChild(h("p", { class: "muted", text: "You haven't joined a class yet." })); return; }
        joined.forEach(function (c) {
          joinedList.appendChild(h("p", {}, [document.createTextNode(c.name), document.createTextNode("  "),
            h("span", { class: "muted", text: "(" + c.join_code + ")" })]));
        });
      });
    }

    // -- your recent practice --
    function loadRecent() {
      clear(recent); recent.appendChild(h("p", { class: "muted", text: "Loading…" }));
      Accounts.myActivity().then(function (as) {
        clear(recent);
        recent.appendChild(h("h2", { text: "Your recent practice" }));
        if (!as.length) { recent.appendChild(h("p", { class: "muted", text: "Nothing yet — try the quiz or a lesson; your progress syncs here when you're signed in." })); return; }
        var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
          h("th", { text: "Activity" }), h("th", { text: "Topic" }), h("th", { text: "Score" }), h("th", { text: "When" }),
        ])])]);
        var tb = h("tbody");
        as.slice(0, 25).forEach(function (a) {
          tb.appendChild(h("tr", {}, [
            h("td", { text: a.kind === "quiz_attempt" ? "Quiz" : "Lesson" }),
            h("td", { text: a.ref }),
            h("td", { class: "num", text: a.kind === "quiz_attempt" ? (a.score + "/" + a.total + " (" + pct(a.score, a.total) + ")") : "—" }),
            h("td", { class: "num", text: when(a.created_at) }),
          ]));
        });
        tbl.appendChild(tb); recent.appendChild(tbl);
      });
    }

    wrap.appendChild(card([
      h("h2", { text: "Classes you teach" }),
      h("p", { class: "sub", text: "Create a class and share its join code. You'll see each member's quiz and lesson practice as they go." }),
      nameIn, create, cmsg,
      teachList,
    ]));
    wrap.appendChild(card([
      h("h2", { text: "Classes you've joined" }),
      h("p", { class: "sub", text: "Enter a join code to follow a class. Your practice then shows up for whoever runs it." }),
      codeIn, join, jmsg,
      joinedList,
    ]));
    wrap.appendChild(card([recent]));
    show(wrap);
    loadTeach(); loadJoined(); loadRecent();
  }

  // ---- boot ------------------------------------------------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  // A mail scanner (Microsoft Safe Links, prefetchers) can open the one-time magic
  // link before the user, so Supabase hands us back an error in the URL instead of a
  // session. Read it and explain, rather than silently re-showing the form. Only strip
  // the params in the error case — a valid callback carries an access_token we must keep.
  var urlErr = AuthUrl ? AuthUrl.parseAuthError(location.hash, location.search) : null;
  var errMsg = urlErr ? AuthUrl.friendlyAuthError(urlErr.code, urlErr.message) : null;
  if (urlErr) { try { history.replaceState(null, "", location.pathname); } catch (e) { /* best-effort */ } }
  // Creating the client (inside getSession) processes a magic-link redirect.
  Accounts.getSession().then(function (session) {
    if (!session) { signInView(errMsg); return; }
    var user = session.user, email = user && user.email;
    Accounts.profile().then(function (prof) {
      signedInChrome(prof, email);
      signedInView(user.id);
    });
  }).catch(function (e) {
    signInView(errMsg || ("Something went wrong: " + String(e.message || e)));
  });
})();
