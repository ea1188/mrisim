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
  var JoinLink = window.JoinLink;   // pure ?join=CODE parser (join_link.js), loaded before this
  var ClassInsight = window.ClassInsight;   // pure class-activity aggregation (class_insight.js), loaded before this
  var Assignments = window.Assignments;   // pure assignment catalog + completion (assignments.js)

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
  // preErrMsg: an optional message to show on entry (e.g. an OAuth callback error
  // read from the URL by the boot handler; see auth_url.js).
  function signInView(preErrMsg, invited) {
    var msg = h("div", { class: "msg" });
    if (preErrMsg) { msg.className = "msg err"; msg.textContent = preErrMsg; }

    var gbtn = h("button", { class: "primary", text: "Continue with Google", onclick: function () {
      gbtn.disabled = true; msg.className = "msg"; msg.textContent = "Redirecting to Google…";
      Accounts.signInWithGoogle().then(function (r) {
        if (r && r.error) { gbtn.disabled = false; msg.className = "msg err"; msg.textContent = r.error.message; }
      }).catch(function (e) { gbtn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });

    // Tell users up front which address Google's consent screen will show (our
    // Supabase auth host), so the supabase.co URL doesn't read as a scam.
    var supaHost = ((window.MRISIM_SUPABASE && window.MRISIM_SUPABASE.url) || "").replace(/^https?:\/\//, "").replace(/\/+$/, "");
    var authNote = supaHost ? h("p", { style: "margin-top:12px;font-size:12.5px;color:var(--muted);line-height:1.5", text: "When you continue, Google will ask you to sign in to " + supaHost + ", our secure authentication provider. This is expected." }) : null;
    show(card([
      h("h2", { text: "Sign in" }),
      invited ? h("p", { class: "sub", text: "You've been invited to join a class. Sign in with Google to join it." }) : h("p", { class: "sub", text: "Sign in with your Google account to create classes, join them, and keep your course progress synced across your devices." }),
      gbtn, authNote, msg,
    ].filter(Boolean)));
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

  // Curriculum totals ({ lessons, topics }) for the practice-coverage denominator:
  // the same lessons.json the learner app loads and the quiz.json category list.
  // Fetched once per page (cached promise), best-effort — on any failure it resolves
  // with whatever loaded (0 for the rest) so the insight table still renders.
  var totalsPromise = null;
  function curriculumTotals() {
    if (!totalsPromise) {
      var lessons = fetch("lessons.json").then(function (r) { return r.json(); })
        .then(function (d) { return (d.lessons || []).length; }).catch(function () { return 0; });
      var topics = fetch("quiz.json").then(function (r) { return r.json(); })
        .then(function (d) { return (d.categories || []).length; }).catch(function () { return 0; });
      totalsPromise = Promise.all([lessons, topics]).then(function (v) {
        return { lessons: v[0], topics: v[1] };
      });
    }
    return totalsPromise;
  }

  // The assignable catalog ({ modules, lessons, quizzes }) from the same lessons.json
  // and quiz.json the learner loads. Fetched once per page (cached), best-effort — an
  // empty catalog just yields empty pickers.
  var catalogPromise = null;
  function assignableCatalog() {
    if (!catalogPromise) {
      var lessons = fetch("lessons.json").then(function (r) { return r.json(); }).catch(function () { return {}; });
      var quiz = fetch("quiz.json").then(function (r) { return r.json(); }).catch(function () { return {}; });
      catalogPromise = Promise.all([lessons, quiz]).then(function (v) { return Assignments.catalog(v[0], v[1]); });
    }
    return catalogPromise;
  }

  // Drill-down body for one member: per-topic best/latest/attempts + lessons done.
  function drillDown(row) {
    var box = h("div");
    var keys = Object.keys(row.topics);
    if (!keys.length) box.appendChild(h("p", { class: "muted", text: "No quiz practice yet." }));
    keys.forEach(function (k) {
      var t = row.topics[k];
      box.appendChild(h("p", { class: "muted", text:
        k + " — best " + (t.best == null ? "—" : Math.round(t.best) + "%") +
        " · latest " + (t.latest == null ? "—" : Math.round(t.latest) + "%") +
        " · " + t.attempts + " attempt" + (t.attempts === 1 ? "" : "s") }));
    });
    box.appendChild(h("p", { class: "muted", text: row.lessonsDone + " lesson" + (row.lessonsDone === 1 ? "" : "s") + " completed." }));
    box.appendChild(h("p", { class: "muted", text:
      row.modulesMastered + " module" + (row.modulesMastered === 1 ? "" : "s") + " mastered · best mock exam "
      + (row.bestMockPct == null ? "—" : Math.round(row.bestMockPct) + "%") }));
    return box;
  }

  var KIND_LABEL = { lesson: "Lesson", quiz: "Quiz topic", module: "Module" };

  // Owner: the "Assignments" block for one class — an add form + a list with X/N done.
  function assignmentsSection(cl, roster, acts, cat, assignments, reload) {
    var box = h("div", { class: "assign" }, [h("h3", { text: "Assignments" })]);

    var kindSel = h("select", {}, [
      h("option", { value: "lesson" }, ["Lesson"]),
      h("option", { value: "quiz" }, ["Quiz topic"]),
      h("option", { value: "module" }, ["Module"]),
    ]);
    var itemSel = h("select");
    function fillItems() {
      clear(itemSel);
      var list = kindSel.value === "module" ? cat.modules : kindSel.value === "quiz" ? cat.quizzes : cat.lessons;
      (list || []).forEach(function (it) { itemSel.appendChild(h("option", { value: it.ref }, [it.label])); });
    }
    kindSel.addEventListener("change", fillItems);
    fillItems();
    var dueIn = h("input", { type: "date" });
    var amsg = h("div", { class: "msg" });
    var add = h("button", { class: "ghost", text: "Assign", onclick: function () {
      if (!itemSel.value) return;
      add.disabled = true; amsg.className = "msg"; amsg.textContent = "";
      var dueAt = dueIn.value ? new Date(dueIn.value + "T23:59:59").toISOString() : null;
      Accounts.createAssignment(cl.id, kindSel.value, itemSel.value, dueAt).then(function (res) {
        add.disabled = false;
        if (res && res.error) { amsg.className = "msg err"; amsg.textContent = res.error.message; return; }
        reload();
      }).catch(function () { add.disabled = false; });
    } });
    box.appendChild(h("div", { class: "assign-form" }, [kindSel, itemSel, dueIn, add]));
    box.appendChild(amsg);

    var comp = Assignments.classCompletion(assignments, roster, acts, cat);
    if (!comp.length) { box.appendChild(h("p", { class: "muted", text: "No assignments yet." })); return box; }
    var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
      th("Assigned"), th("Type"), th("Due"), th("Done"), th(""),
    ])])]);
    var tb = h("tbody");
    comp.forEach(function (a) {
      var due = Assignments.dueLabel(a.dueAt);
      var dueCell = h("td", {}, [document.createTextNode(due ? due.text : "—")]);
      if (due && due.overdue) dueCell.appendChild(h("span", { class: "chip", text: "overdue" }));
      var rm = h("button", { class: "ghost", text: "Remove", onclick: function () {
        rm.disabled = true;
        Accounts.deleteAssignment(a.id).then(function (res) {
          if (res && res.error) { rm.disabled = false; return; }
          reload();
        }).catch(function () { rm.disabled = false; });
      } });
      tb.appendChild(h("tr", {}, [
        td(a.label), td(KIND_LABEL[a.kind] || a.kind), dueCell,
        tdNum(a.doneCount + "/" + a.total), h("td", {}, [rm]),
      ]));
    });
    tbl.appendChild(tb);
    box.appendChild(tbl);
    return box;
  }

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
    var c = card([head, body]);
    body.appendChild(h("p", { class: "muted", text: "Loading roster…" }));
    Promise.all([Accounts.roster(cl.id), Accounts.classActivity(cl.id), curriculumTotals(),
      Accounts.classAssignments(cl.id), assignableCatalog()]).then(function (res) {
      clear(body);
      var roster = res[0], acts = res[1], totals = res[2];
      var assignments = res[3], cat = res[4];
      if (!roster.length) {
        body.appendChild(h("p", { class: "muted", text: "No members yet. Share the join code above." }));
        body.appendChild(assignmentsSection(cl, roster, acts, cat, assignments, reload));
        return;
      }
      var rows = ClassInsight.perStudent(roster, acts);
      var byId = {};
      rows.forEach(function (r) { byId[r.studentId] = r; });
      var covTh = th("Coverage");
      covTh.title = "practice coverage — formative, not graded completion";
      var masteredTh = th("Mastered");
      masteredTh.title = "premium modules with a passing mastery check";
      var mockTh = th("Best mock");
      mockTh.title = "best full-length mock-exam score";
      var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
        th("Member"), covTh, th("Best"), masteredTh, mockTh, th("Weakest topic"), th("Last active"), th(""),
      ])])]);
      var tb = h("tbody");
      roster.forEach(function (r) {
        var row = byId[r.student_id];
        var rm = h("button", { class: "ghost", text: "Remove", onclick: function (ev) {
          ev.stopPropagation();   // don't also toggle the drill-down
          if (!window.confirm("Remove " + row.name + " from \"" + cl.name + "\"? They keep their own progress and can rejoin with the code.")) return;
          rm.disabled = true;
          Accounts.removeMember(cl.id, r.student_id).then(function (res) {
            if (res && res.error) { rm.disabled = false; return; }
            reload();
          }).catch(function () { rm.disabled = false; });
        } });
        var nameCell = h("td", {}, [document.createTextNode(row.name)]);
        if (row.struggling) nameCell.appendChild(h("span", { class: "chip", text: "struggling" }));
        var detail = null;   // the inline drill-down <tr>, present while expanded
        var tr = h("tr", { style: "cursor:pointer", onclick: function () {
          if (detail) { tb.removeChild(detail); detail = null; return; }
          detail = h("tr", {}, [h("td", { colspan: "8" }, [drillDown(row)])]);
          tb.insertBefore(detail, tr.nextSibling);
        } }, [
          nameCell,
          tdNum(ClassInsight.coverage(row, totals) + "%"),
          tdNum(row.bestPct == null ? "—" : Math.round(row.bestPct) + "%"),
          tdNum(row.modulesMastered || 0),
          tdNum(row.bestMockPct == null ? "—" : Math.round(row.bestMockPct) + "%"),
          td(row.weakestTopic || "—"),
          tdNum(row.lastActive ? when(row.lastActive) : "—"),
          h("td", {}, [rm]),
        ]);
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      body.appendChild(tbl);
      var st = ClassInsight.classStats(rows, totals);
      var weak = st.weakestTopics.map(function (w) { return w.topic; }).join(", ");
      body.appendChild(h("p", { class: "muted", text:
        st.members + " member" + (st.members === 1 ? "" : "s") +
        " · class avg best " + (st.avgBestPct == null ? "—" : st.avgBestPct + "%") +
        " · avg mock " + (st.avgMockPct == null ? "—" : st.avgMockPct + "%") +
        " · avg coverage " + st.avgCoverage + "%" +
        (weak ? " · weakest topics: " + weak : "") }));
      body.appendChild(h("p", { class: "muted", text: "Practice scores are formative, not graded exams." }));
      body.appendChild(h("button", { class: "ghost", text: "Download CSV", onclick: function () {
        var csv = ClassInsight.toCSV(rows, totals);
        var url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
        var a = h("a", { href: url, download: cl.name + "-insight.csv" });
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } }));
      body.appendChild(assignmentsSection(cl, roster, acts, cat, assignments, reload));
    });
    return c;
  }

  // A small "Your name" card: the display name instructors see, prefilled from the Google
  // profile on first visit (captured via the self-update RLS) and editable by the user.
  function profileCard() {
    var nameIn = h("input", { type: "text", placeholder: "Your name", autocomplete: "name" });
    var msg = h("div", { class: "msg" });
    var save = h("button", { class: "ghost", text: "Save name", onclick: function () {
      var v = nameIn.value.trim();
      if (!v) { msg.className = "msg err"; msg.textContent = "Enter a name."; return; }
      Accounts.updateProfile({ display_name: v }).then(function (res) {
        msg.className = res && res.error ? "msg err" : "msg ok";
        msg.textContent = res && res.error ? "Could not save. Try again." : "Saved.";
      });
    } });
    Promise.all([Accounts.profile(), Accounts.getUser()]).then(function (r) {
      var prof = r[0] || {}, meta = (r[1] && r[1].user_metadata) || {};
      var googleName = meta.full_name || meta.name || "";
      if (prof.display_name) {
        nameIn.value = prof.display_name;
      } else if (googleName) {
        nameIn.value = googleName;
        Accounts.updateProfile({ display_name: googleName });   // capture the Google name once
      }
    });
    return card([
      h("h2", { text: "Your name" }),
      h("p", { class: "sub", text: "The name your instructors see for your work." }),
      nameIn, save, msg,
    ]);
  }

  // ---- unified signed-in view (everyone can teach and join) ------------- //
  function signedInView(uid, note) {
    var wrap = h("div");
    if (note) wrap.appendChild(h("p", { class: note.ok ? "msg ok" : "msg err", text: note.text }));
    wrap.appendChild(profileCard());
    var teachList = h("div"), joinedList = h("div"), assigned = h("div"), recent = h("div");

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

    // -- work assigned to you (across the classes you've joined) --
    function loadAssigned() {
      clear(assigned); assigned.appendChild(h("p", { class: "muted", text: "Loading…" }));
      Promise.all([Accounts.myAssignments(), Accounts.myActivityRefs(), assignableCatalog()]).then(function (res) {
        clear(assigned);
        var rows = Assignments.studentStatus(res[0], res[1], res[2]);
        assigned.appendChild(h("h2", { text: "Assigned to you" }));
        if (!rows.length) {
          assigned.appendChild(h("p", { class: "muted", text: "No assignments yet. When a class you've joined assigns work, it shows up here." }));
          return;
        }
        var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
          th("Done"), th("Assigned"), th("Type"), th("Due"), th(""),
        ])])]);
        var tb = h("tbody");
        rows.forEach(function (a) {
          var due = Assignments.dueLabel(a.dueAt);
          var dueCell = h("td", {}, [document.createTextNode(due ? due.text : "—")]);
          if (due && due.overdue && !a.done) dueCell.appendChild(h("span", { class: "chip", text: "overdue" }));
          var link = a.kind === "quiz" ? "quiz.html?topic=" + encodeURIComponent(a.ref)
            : a.kind === "lesson" ? "course.html?lesson=" + encodeURIComponent(a.ref)
              : "course.html?module=" + encodeURIComponent(a.ref);
          var doneCell = h("td", {}, [a.done ? h("span", { class: "chip", text: "done" }) : document.createTextNode("—")]);
          tb.appendChild(h("tr", {}, [
            doneCell, td(a.label), td(KIND_LABEL[a.kind] || a.kind), dueCell,
            h("td", {}, [h("a", { class: "linkout", href: link, text: "open" })]),
          ]));
        });
        tbl.appendChild(tb); assigned.appendChild(tbl);
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
    wrap.appendChild(card([assigned]));
    wrap.appendChild(card([recent]));
    show(wrap);
    loadTeach(); loadJoined(); loadAssigned(); loadRecent();
  }

  var PENDING_JOIN_KEY = "mrisim_pending_join";
  function loadPendingJoin() { try { return localStorage.getItem(PENDING_JOIN_KEY) || null; } catch (e) { return null; } }
  function savePendingJoin(code) { try { localStorage.setItem(PENDING_JOIN_KEY, code); } catch (e) { /* storage off */ } }
  function clearPendingJoin() { try { localStorage.removeItem(PENDING_JOIN_KEY); } catch (e) { /* storage off */ } }

  // ---- boot ------------------------------------------------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  // A mail scanner (Microsoft Safe Links, prefetchers) can open the one-time magic
  // link before the user, so Supabase hands us back an error in the URL instead of a
  // session. Read it and explain, rather than silently re-showing the form. Only strip
  // the params in the error case — a valid callback carries an access_token we must keep.
  var urlErr = AuthUrl ? AuthUrl.parseAuthError(location.hash, location.search) : null;
  var errMsg = urlErr ? AuthUrl.friendlyAuthError(urlErr.code, urlErr.message) : null;
  // Read the invite code before the urlErr strip below can clear location.search.
  var joinCode = JoinLink ? JoinLink.parseJoinCode(location.search) : null;
  if (urlErr) { try { history.replaceState(null, "", location.pathname); } catch (e) { /* best-effort */ } }
  // Invite link: stash ?join=CODE so it survives the Google OAuth round-trip (which drops the
  // query string) and a refresh, then strip it from the URL (keep any hash for the auth callback).
  if (joinCode) {
    savePendingJoin(joinCode);
    try { history.replaceState(null, "", location.pathname + location.hash); } catch (e) { /* best-effort */ }
  }
  // Creating the client (inside getSession) processes a magic-link redirect.
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
        proceed(res && res.error
          ? { text: "That invite code did not work. Ask for a new one.", ok: false }
          : { text: "You've joined the class. It is listed below.", ok: true });
      }).catch(function () {
        clearPendingJoin();
        proceed({ text: "Could not join the class. Please try the code again.", ok: false });
      });
    } else {
      proceed(null);
    }
  }).catch(function (e) {
    signInView(errMsg || ("Something went wrong: " + String(e.message || e)));
  });
})();
