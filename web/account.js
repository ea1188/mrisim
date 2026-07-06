/* MRISim account page controller. Uses window.Accounts (accounts.js). Renders the
 * sign-in form when signed out, and a role-adaptive view when signed in: an
 * instructor dashboard (classes, join codes, per-student practice) or a student
 * view (join a class, my classes, recent activity). */
(function () {
  "use strict";
  var root = document.getElementById("root");
  var whoami = document.getElementById("whoami");

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
  function signInView() {
    var email = h("input", { type: "email", id: "email", placeholder: "you@school.edu", autocomplete: "email" });
    var name = h("input", { type: "text", id: "name", placeholder: "Your name (optional)" });
    var inst = h("input", { type: "text", id: "inst", placeholder: "Institution (optional)" });
    var msg = h("div", { class: "msg" });
    var rStudent = h("input", { type: "radio", name: "role", value: "student", checked: true });
    var rInstr = h("input", { type: "radio", name: "role", value: "instructor" });

    var btn = h("button", { class: "primary", text: "Email me a sign-in link", onclick: function () {
      var addr = email.value.trim();
      if (!addr) { msg.className = "msg err"; msg.textContent = "Enter your email."; return; }
      var role = rInstr.checked ? "instructor" : "student";
      btn.disabled = true; msg.className = "msg"; msg.textContent = "Sending…";
      Accounts.signIn(addr, { meta: { role: role, display_name: name.value.trim(), institution: inst.value.trim() } })
        .then(function (r) {
          btn.disabled = false;
          if (r && r.error) { msg.className = "msg err"; msg.textContent = r.error.message; return; }
          msg.className = "msg ok";
          msg.textContent = "Check " + addr + " for a sign-in link. (First time as an instructor? Your account is set up when you click it.)";
        })
        .catch(function (e) { btn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });

    show(card([
      h("h2", { text: "Sign in to run a class" }),
      h("p", { class: "sub", text: "Passwordless — we email you a one-time sign-in link. Instructors create classes and see student practice; students join a class with a code." }),
      h("label", { text: "Email" }), email,
      h("label", { text: "I am a…" }),
      h("div", { class: "roles" }, [
        h("label", {}, [rStudent, "Student"]),
        h("label", {}, [rInstr, "Instructor"]),
      ]),
      h("label", { text: "Name" }), name,
      h("label", { text: "Institution" }), inst,
      btn, msg,
    ]));
  }

  // ---- signed in -------------------------------------------------------- //
  function signedInChrome(prof, email) {
    whoami.hidden = false;
    clear(whoami);
    whoami.appendChild(document.createTextNode((prof && prof.display_name ? prof.display_name + " · " : "") + (email || "") + " · " + (prof && prof.role === "instructor" ? "Instructor" : "Student") + " "));
    whoami.appendChild(h("button", { text: "Sign out", onclick: function () {
      Accounts.signOut().then(function () { location.reload(); });
    } }));
  }

  function pct(s, t) { return t ? Math.round((100 * s) / t) + "%" : "—"; }
  function when(iso) { try { return new Date(iso).toLocaleDateString(); } catch (e) { return ""; } }

  // ---- instructor dashboard --------------------------------------------- //
  function instructorView() {
    var wrap = h("div");
    var nameIn = h("input", { type: "text", placeholder: "e.g. MRI Physics — Fall 2026" });
    var msg = h("div", { class: "msg" });
    var create = h("button", { class: "primary", text: "Create class", onclick: function () {
      var nm = nameIn.value.trim();
      if (!nm) { msg.className = "msg err"; msg.textContent = "Name the class."; return; }
      create.disabled = true;
      Accounts.createClass(nm).then(function (r) {
        create.disabled = false;
        if (r && r.error) { msg.className = "msg err"; msg.textContent = r.error.message; return; }
        nameIn.value = ""; msg.textContent = ""; load();
      }).catch(function (e) { create.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });

    var list = h("div");
    function load() {
      clear(list);
      list.appendChild(h("p", { class: "muted", text: "Loading classes…" }));
      Accounts.instructorClasses().then(function (classes) {
        clear(list);
        if (!classes.length) { list.appendChild(h("p", { class: "muted", text: "No classes yet — create one above, then share its join code." })); return; }
        classes.forEach(function (cl) { list.appendChild(classCard(cl)); });
      });
    }

    function classCard(cl) {
      var body = h("div");
      var archiveBtn = h("button", { class: "ghost", text: cl.archived ? "Unarchive" : "Archive", onclick: function () {
        archiveBtn.disabled = true;
        Accounts.archiveClass(cl.id, !cl.archived).then(function () { load(); })
          .catch(function () { archiveBtn.disabled = false; });
      } });
      var delBtn = h("button", { class: "ghost", text: "Delete", onclick: function () {
        if (!window.confirm("Delete \"" + cl.name + "\"? This removes its roster and all its activity. This cannot be undone.")) return;
        delBtn.disabled = true;
        Accounts.deleteClass(cl.id).then(function () { load(); })
          .catch(function () { delBtn.disabled = false; });
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
        if (!roster.length) { body.appendChild(h("p", { class: "muted", text: "No students yet. Give them the join code above." })); return; }
        // Aggregate per student.
        var by = {};
        acts.forEach(function (a) {
          var s = by[a.student_id] || (by[a.student_id] = { quizzes: 0, lessons: 0, bestPct: null, last: null });
          if (a.kind === "quiz_attempt") { s.quizzes++; if (a.total) { var p = (100 * a.score) / a.total; if (s.bestPct == null || p > s.bestPct) s.bestPct = p; } }
          if (a.kind === "lesson_complete") s.lessons++;
          if (!s.last || a.created_at > s.last) s.last = a.created_at;
        });
        var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
          th("Student"), th("Quiz runs"), th("Best score"), th("Lessons"), th("Last active"),
        ])])]);
        var tb = h("tbody");
        roster.forEach(function (r) {
          var p = (r.profiles && r.profiles.display_name) || "(unnamed)";
          var s = by[r.student_id] || { quizzes: 0, lessons: 0, bestPct: null, last: null };
          tb.appendChild(h("tr", {}, [
            td(p), tdNum(s.quizzes), tdNum(s.bestPct == null ? "—" : Math.round(s.bestPct) + "%"),
            tdNum(s.lessons), tdNum(s.last ? when(s.last) : "—"),
          ]));
        });
        tbl.appendChild(tb);
        body.appendChild(tbl);
        body.appendChild(h("p", { class: "muted", text: roster.length + " student" + (roster.length === 1 ? "" : "s") + " · practice scores are formative, not graded exams." }));
      });
      return c;
    }
    function th(t) { return h("th", { text: t }); }
    function td(t) { return h("td", { text: t }); }
    function tdNum(t) { return h("td", { class: "num", text: String(t) }); }

    wrap.appendChild(card([
      h("h2", { text: "Create a class" }),
      h("p", { class: "sub", text: "Students join with the code it generates. You'll see their practice as they go." }),
      nameIn, create, msg,
    ]));
    wrap.appendChild(list);
    show(wrap);
    load();
  }

  // ---- student view ----------------------------------------------------- //
  function studentView() {
    var wrap = h("div");
    var codeIn = h("input", { type: "text", placeholder: "e.g. A1B2C3", maxlength: "12" });
    var msg = h("div", { class: "msg" });
    var join = h("button", { class: "primary", text: "Join class", onclick: function () {
      var code = codeIn.value.trim();
      if (!code) { msg.className = "msg err"; msg.textContent = "Enter the code your instructor gave you."; return; }
      join.disabled = true; msg.className = "msg"; msg.textContent = "Joining…";
      Accounts.joinClass(code).then(function (r) {
        join.disabled = false;
        if (r && r.error) { msg.className = "msg err"; msg.textContent = r.error.message || "That code didn't work."; return; }
        codeIn.value = ""; msg.className = "msg ok"; msg.textContent = "Joined."; load();
      }).catch(function (e) { join.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });

    var classes = h("div"), recent = h("div");
    function load() {
      clear(classes); classes.appendChild(h("p", { class: "muted", text: "Loading…" }));
      Accounts.myClasses().then(function (cs) {
        clear(classes);
        classes.appendChild(h("h2", { text: "My classes" }));
        if (!cs.length) { classes.appendChild(h("p", { class: "muted", text: "You haven't joined a class yet." })); return; }
        cs.forEach(function (c) { classes.appendChild(h("p", {}, [document.createTextNode(c.name), document.createTextNode("  "), h("span", { class: "muted", text: "(" + c.join_code + ")" })])); });
      });
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
      h("h2", { text: "Join a class" }),
      h("p", { class: "sub", text: "Enter the code your instructor shared. Once you're in, your quiz and lesson practice shows up for them." }),
      codeIn, join, msg,
    ]));
    wrap.appendChild(card([classes]));
    wrap.appendChild(card([recent]));
    show(wrap);
    load();
  }

  // ---- boot ------------------------------------------------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  // Creating the client (inside getSession) processes a magic-link redirect.
  Accounts.getSession().then(function (session) {
    if (!session) { signInView(); return; }
    var email = session.user && session.user.email;
    Accounts.profile().then(function (prof) {
      signedInChrome(prof, email);
      if (prof && prof.role === "instructor") instructorView(); else studentView();
    });
  }).catch(function (e) {
    show(card([h("h2", { text: "Something went wrong" }), h("p", { class: "sub", text: String(e.message || e) })]));
  });
})();
