/* MRISim guided course — the PAID, gated curriculum. Uses window.Accounts (accounts.js).
 * Gate order (fail-closed): not configured → signed out → not entitled → entitled.
 * The course packages the free lessons + quiz and adds EXCLUSIVE premium content fetched
 * from Supabase (RLS serves it only to entitled users — the client gate is just UX).
 * Left rail = the 10 curriculum topics; right pane = premium education → free lesson
 * launches → an inline premium quiz. */
(function () {
  "use strict";
  var COURSE = "mri-core";
  var root = document.getElementById("course-root");
  var whoami = document.getElementById("whoami");
  var overlay = document.getElementById("lesson-overlay");
  var lessonState = null;   // { title, steps, i } for the active illustrated lesson
  // Live references so we can re-render progress after an inline lesson closes.
  var CTX = null; // { curriculum, byTitle, byTopic, rail, main, mod }

  // Which free curriculum module maps to which premium topic keys + free quiz categories.
  // Modules absent here just show their free lessons (no premium block / topic quiz yet).
  var TOPIC_CFG = {
    "1 · What an MRI image is":       { premium: ["instrumentation"], quiz: [] },
    "2 · Where contrast comes from":  { premium: ["contrast-weighting"], quiz: ["sequences"] },
    "3 · Making a tissue disappear":  { premium: ["fat-suppression"], quiz: [] },
    "4 · Reading pathology":          { premium: ["pathology", "procedures-anatomy"], quiz: ["pathology"] },
    "5 · Image quality & speed":      { premium: ["image-quality"], quiz: ["image-quality"] },
    "6 · How the image is built":     { premium: ["image-quality", "pulse-sequences", "data-acquisition"], quiz: ["image-quality"] },
    "7 · 3D imaging & reconstruction": { premium: ["three-d-recon"], quiz: [] },
    "8 · Flow, function & artifacts": { premium: ["flow-artifacts", "procedures-vascular"], quiz: ["artifacts", "perfusion"] },
    "9 · Putting it together":        { premium: ["procedures-protocols"], quiz: [] },
    "10 · Safety & patient care":     { premium: ["safety", "patient-care", "contrast-agents"], quiz: ["safety", "patient-care"] },
  };
  var CURRICULUM_DONE_KEY = "mrisim_curriculum";
  var COURSE_QUIZ_KEY = "mrisim_course_quiz_v1";
  var COURSE_READ_KEY = "mrisim_course_read_v1";  // which education/question sections have been read
  var COURSE_EXAM_KEY = "mrisim_course_exam_v1";  // best/last practice-exam score
  var COURSE_MASTERY_KEY = "mrisim_course_mastery_v1"; // per-module mastery-check result
  var COURSE_DIAG_KEY = "mrisim_course_diagnostic_v1"; // placement-test snapshot (separate from progress)
  var DIAG_PER_MODULE = 2;                              // questions sampled per module in the placement test
  var EXAM = null;  // active practice exam: { questions, picks, timer, timed, remaining, elapsed, reviewing }
  var STRIPE = window.MRISIM_STRIPE || {};
  var CourseLogic = window.CourseLogic;
  var PASS_PCT = CourseLogic.PASS_PCT, CHECK_N = CourseLogic.CHECK_N, MIN_POOL = CourseLogic.MIN_POOL;

  // Attach the signed-in user's id (and email) to the Payment Link so the webhook
  // can map the payment back to this account.
  function buildCheckoutUrl(link, uid, email) {
    var u = new URL(link);
    u.searchParams.set("client_reference_id", uid);
    if (email) u.searchParams.set("prefilled_email", email);
    return u.toString();
  }

  // --- tiny DOM builder (textContent-safe; html: only for trusted premium bodies) --- //
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
  function gate(kids) { clear(root); root.appendChild(h("div", { class: "gate" }, [h("div", { class: "card" }, kids)])); }

  // --- gate screens ------------------------------------------------------- //
  function notConfigured() {
    gate([h("h2", { text: "Course unavailable" }),
      h("p", { text: "This deployment has no backend configured, so the paid course can't load. The free simulator, quiz and lessons all work without an account." }),
      h("a", { class: "btn", href: "index.html", text: "Back to the free tools" })]);
  }

  function signInView() {
    var msg = h("div", { class: "msg" });
    // Primary: one-click Google (redirects to Google, returns signed in).
    var gbtn = h("button", { class: "btn", text: "Continue with Google", onclick: function () {
      gbtn.disabled = true; msg.className = "msg"; msg.textContent = "Redirecting to Google…";
      Accounts.signInWithGoogle().then(function (r) {
        if (r && r.error) { gbtn.disabled = false; msg.className = "msg err"; msg.textContent = r.error.message; }
      }).catch(function (e) { gbtn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });
    // Fallback: email sign-in link, revealed on demand so it stays one-click first.
    var email = h("input", { type: "email", placeholder: "you@school.edu", autocomplete: "email" });
    var ebtn = h("button", { class: "btn", style: "margin-top:10px", text: "Email me a sign-in link", onclick: function () {
      var addr = email.value.trim();
      if (!addr) { msg.className = "msg err"; msg.textContent = "Enter your email."; return; }
      ebtn.disabled = true; msg.className = "msg"; msg.textContent = "Sending…";
      Accounts.signIn(addr).then(function (r) {
        ebtn.disabled = false;
        if (r && r.error) { msg.className = "msg err"; msg.textContent = r.error.message; return; }
        msg.className = "msg ok"; msg.textContent = "Check " + addr + " for a sign-in link.";
      }).catch(function (e) { ebtn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });
    var fallback = h("div", { style: "margin-top:14px" }, [h("label", { text: "Email" }), email, ebtn]);
    fallback.hidden = true;
    var toggle = h("button", {
      style: "display:block;margin:12px auto 0;background:none;border:none;color:var(--muted);font:inherit;font-size:13px;cursor:pointer;text-decoration:underline",
      text: "or sign in with email", onclick: function () { fallback.hidden = false; toggle.hidden = true; },
    });
    gate([h("h2", { text: "Sign in to your course" }),
      h("p", { text: "Your guided curriculum, saved progress and premium content — sign in to pick up where you left off." }),
      gbtn, toggle, fallback, msg]);
  }

  function paywallView(email, uid) {
    var kids = [
      h("h2", { text: "Unlock the full course" }),
      h("p", { text: "Get lifetime access to the guided curriculum: premium lessons, the full ARRT-style question bank, mock exams and the reference library." }),
    ];
    if (STRIPE.paymentLink && uid) {
      kids.push(h("button", { class: "btn", text: "Get lifetime access for $45", onclick: function () {
        location.assign(buildCheckoutUrl(STRIPE.paymentLink, uid, email));
      } }));
    } else {
      kids.push(h("a", { class: "btn", href: "mailto:erolakkoc8@gmail.com?subject=MRISim%20course%20access", text: "Request access" }));
    }
    kids.push(h("p", { class: "quiz-foot", html: "Meanwhile the <a class=\"linkout\" href=\"index.html\">free simulator, quiz and lessons</a> are open to everyone." }));
    gate(kids);
  }

  // --- signed-in chrome --------------------------------------------------- //
  function chrome(email) {
    whoami.hidden = false; clear(whoami);
    whoami.appendChild(document.createTextNode((email || "") + " · "));
    whoami.appendChild(h("button", { text: "Sign out", onclick: function () {
      Accounts.signOut().then(function () { location.reload(); });
    } }));
  }

  // --- the course --------------------------------------------------------- //
  function courseView(curriculum, lessonsByTitle, premiumByTopic) {
    var wrap = h("div", { class: "course" });
    var rail = h("div", { class: "rail" });
    var main = h("div", { class: "main" });
    CTX = { curriculum: curriculum, byTitle: lessonsByTitle, byTopic: premiumByTopic,
      rail: rail, main: main, mod: curriculum[0],
      expanded: new Set([curriculum[0].title]) };  // which modules are expanded in the TOC

    buildRail();
    wrap.appendChild(rail); wrap.appendChild(main);
    clear(root); root.appendChild(wrap);
    renderOverview();   // open on the exam-readiness dashboard, not straight into module 1
  }

  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""); }

  // The subsections of a module, in reading order: its premium education pieces, its lessons,
  // then its question set. Each carries a stable id, a rail label, and a right-pane anchor.
  function moduleSubsections(mod) {
    var cfg = TOPIC_CFG[mod.title] || { premium: [], quiz: [] };
    var byTopic = CTX.byTopic, subs = [];
    cfg.premium.forEach(function (key) {
      (byTopic[key] || []).forEach(function (it) {
        if (it.kind === "education") subs.push({ type: "read", id: "e:" + it.body.title, label: it.body.title, anchor: "edu-" + slug(it.body.title) });
      });
    });
    mod.lessons.forEach(function (t) { subs.push({ type: "lesson", id: t, label: t, anchor: "lesson-" + slug(t) }); });
    if (hasMastery(mod)) subs.push({ type: "mastery", id: "m:" + mod.title, modTitle: mod.title, label: "Mastery check", anchor: "mastery-" + slug(mod.title) });
    return subs;
  }
  // Complete = the lesson is done, or (for education/questions) the section has been read.
  function isSubDone(s, done, read, mastery) {
    if (s.type === "lesson") return !!done[s.id];
    if (s.type === "mastery") { var r = mastery && mastery[s.modTitle]; return !!(r && r.passed); }
    return !!read[s.id];
  }

  function loadQuiz() { try { return JSON.parse(localStorage.getItem(COURSE_QUIZ_KEY) || "{}"); } catch (e) { return {}; } }
  var STATUS_LABEL = { "not-started": "Not started", "progress": "In progress", "review": "Needs review", "mastered": "Mastered" };

  // Exam readiness from local progress: per module (reads + quiz accuracy) and overall
  // (reads 45% + quiz accuracy 40% + best mock exam 15%). Drives the overview dashboard
  // and the "study next" nudge. Pure read of localStorage — nothing new stored.
  function computeReadiness() {
    var done = loadDone(), read = loadRead(), quiz = loadQuiz(), exam = loadExamBest(), mastery = loadMastery();
    var rSum = 0, rTot = 0, qRight = 0, qSeen = 0;
    var modules = CTX.curriculum.map(function (mod) {
      var subs = moduleSubsections(mod);
      var c = subs.filter(function (s) { return isSubDone(s, done, read, mastery); }).length;
      var q = quiz[mod.title] || { seen: 0, right: 0 };
      var acc = q.seen ? q.right / q.seen : null;
      var mr = mastery[mod.title] || { passed: false, attempts: 0 };
      rSum += c; rTot += subs.length; qRight += q.right; qSeen += q.seen;
      var status = CourseLogic.deriveModuleStatus(c, subs.length, q.seen, mr.attempts, mr.passed);
      return { mod: mod, subs: subs, c: c, total: subs.length, acc: acc, status: status };
    });
    var readPct = rTot ? rSum / rTot : 0, quizAcc = qSeen ? qRight / qSeen : 0;
    var examPct = exam && exam.bestPct != null ? exam.bestPct / 100 : 0;
    var overall = Math.round(100 * (0.45 * readPct + 0.40 * quizAcc + 0.15 * examPct));
    var band = overall >= 80 ? "Exam-ready" : overall >= 40 ? "Building" : "Getting started";
    var next = null;
    for (var i = 0; i < modules.length; i++) { if (modules[i].status !== "mastered") { next = modules[i]; break; } }
    return { modules: modules, overall: overall, band: band, next: next, exam: exam,
      quizAcc: Math.round(100 * quizAcc), readPct: Math.round(100 * readPct) };
  }

  // Self-serve refund: confirm, ask the edge function (it enforces window + ownership),
  // then reload on success (access is revoked server-side).
  function doRefund() {
    if (!confirm("Refund your course purchase and lose access? This cannot be undone.")) return;
    Accounts.requestRefund(COURSE).then(function (r) {
      if (r && r.error) { alert("Refund failed: " + (r.error.message || r.error)); return; }
      var body = (r && r.data) || {};
      if (body.ok) { alert("Refunded. Your course access has been removed."); location.reload(); }
      else { alert(body.error || "The refund could not be processed. Please email support."); }
    }).catch(function (e) { alert("Refund failed: " + (e.message || e)); });
  }

  // The course "home": an exam-readiness dashboard over local progress. CTX.mod == null.
  function renderOverview() {
    stopExam();
    if (CTX) CTX.mod = null;
    var main = CTX.main, r = computeReadiness();
    clear(main);
    main.appendChild(h("p", { class: "eyebrow", text: "Exam readiness" }));
    main.appendChild(h("h2", { text: "Your progress" }));
    main.appendChild(h("div", { class: "ready" }, [
      h("div", { class: "ready-num", text: r.overall + "%" }),
      h("div", { class: "ready-band", text: r.band }),
      h("div", { class: "bar wide" }, [h("i", { style: "width:" + r.overall + "%" })]),
      h("div", { class: "ready-sub", text: r.readPct + "% read · " + r.quizAcc + "% quiz accuracy"
        + (r.exam && r.exam.bestPct != null ? " · best mock " + r.exam.bestPct + "%" : "") }),
    ]));
    if (r.next) {
      main.appendChild(h("button", { class: "btn study-next", type: "button",
        onclick: function () { openModule(r.next.mod); } }, [
        document.createTextNode("Study next: " + r.next.mod.title),
        h("span", { class: "sn-why", text: r.next.status === "review" ? "quiz needs work"
          : r.next.c ? "keep going" : "not started yet" }),
      ]));
    } else {
      main.appendChild(h("p", { class: "lede", text: "Every module is mastered. Run a full practice exam to confirm you're ready." }));
    }
    main.appendChild(h("button", { class: "btn ghost-cta", type: "button", onclick: openExam, text: "Take a practice exam" }));
    if (!loadDiagnostic()) {
      main.appendChild(h("div", { class: "diag-card" }, [
        h("h3", { text: "New here? Take the placement test" }),
        h("p", { text: "20 questions across every topic, about 10 minutes. It finds your weakest areas and points you where to start. It does not affect your progress." }),
        h("button", { class: "btn", type: "button", text: "Start the placement test", onclick: startDiagnostic }),
      ]));
    } else {
      main.appendChild(h("p", { class: "diag-note" }, [
        document.createTextNode("Placement test taken. "),
        h("button", { type: "button", class: "diag-retake", text: "Retake", onclick: startDiagnostic }),
      ]));
    }
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
    var grid = h("div", { class: "ready-grid" });
    r.modules.forEach(function (m) {
      grid.appendChild(h("button", { class: "ready-row " + m.status, type: "button",
        onclick: function () { openModule(m.mod); } }, [
        h("span", { class: "rr-title", text: m.mod.title }),
        h("span", { class: "rr-read", text: m.c + "/" + m.total + " read" }),
        h("span", { class: "rr-quiz", text: m.acc == null ? "quiz —" : "quiz " + Math.round(100 * m.acc) + "%" }),
        h("span", { class: "rr-chip", text: STATUS_LABEL[m.status] }),
      ]));
    });
    main.appendChild(grid);
    main.appendChild(h("p", { style: "margin-top:36px;font-size:12px;color:var(--dim)" }, [
      document.createTextNode("Bought by mistake, or it's not for you? "),
      h("button", { type: "button", style: "background:none;border:none;color:var(--muted);font:inherit;font-size:12px;text-decoration:underline;cursor:pointer;padding:0",
        text: "Request a refund", onclick: doRefund }),
      document.createTextNode(" within 7 days."),
    ]));
    buildRail();
  }

  function openModule(mod) {
    CTX.expanded.add(mod.title);
    renderTopic(CTX.main, mod, CTX.byTitle, CTX.byTopic);
    buildRail();
    if (CTX.main && CTX.main.scrollTo) CTX.main.scrollTo(0, 0);
  }

  // (Re)build the collapsible table of contents: each module is a header that expands to its
  // subsections, each with a checkbox that ticks when its lesson is done or its section is read.
  function buildRail() {
    var curriculum = CTX.curriculum, rail = CTX.rail, done = loadDone(), read = loadRead(), mastery = loadMastery();
    var total = 0, complete = 0;
    var perMod = curriculum.map(function (mod) {
      var subs = moduleSubsections(mod);
      var c = subs.filter(function (s) { return isSubDone(s, done, read, mastery); }).length;
      total += subs.length; complete += c;
      return { mod: mod, subs: subs, c: c };
    });
    clear(rail);
    rail.appendChild(h("div", { class: "prog" }, [
      document.createTextNode(complete + " / " + total + " read"),
      h("div", { class: "bar" }, [h("i", { style: "width:" + (total ? Math.round(100 * complete / total) : 0) + "%" })]),
    ]));
    rail.appendChild(h("button", { class: "overview-cta" + (CTX.mod == null ? " on" : ""), type: "button",
      onclick: renderOverview, text: "Overview" }));
    rail.appendChild(h("button", { class: "exam-cta" + (EXAM ? " on" : ""), type: "button", onclick: openExam }, [
      document.createTextNode("Practice exam"),
      h("span", { class: "ec-sub", text: "Registry-style run across the whole bank" }),
    ]));
    perMod.forEach(function (pm) {
      var mod = pm.mod, subs = pm.subs;
      var modDone = subs.length && pm.c === subs.length;
      var expanded = CTX.expanded.has(mod.title);
      var subsWrap = h("div", { class: "mod-subs", hidden: !expanded });
      subs.forEach(function (s) {
        var d = isSubDone(s, done, read, mastery);
        subsWrap.appendChild(h("button", { class: "sub" + (d ? " done" : ""), type: "button",
          onclick: function () { gotoSub(mod, s); } }, [
          h("span", { class: "box" + (d ? " on" : ""), text: d ? "✓" : "" }),
          h("span", { class: "sl", text: s.label }),
        ]));
      });
      var header = h("button", { class: "mod-h" + (mod === CTX.mod ? " on" : ""), type: "button",
        onclick: function () {
          var wasActive = CTX.mod === mod;
          if (CTX.expanded.has(mod.title) && wasActive) CTX.expanded.delete(mod.title);
          else CTX.expanded.add(mod.title);
          if (!wasActive) renderTopic(CTX.main, mod, CTX.byTitle, CTX.byTopic);
          buildRail();
        } }, [
        h("span", { class: "caret" + (expanded ? " open" : ""), text: "▸" }),
        document.createTextNode(mod.title),
        h("span", { class: "mtk" + (modDone ? " done" : ""), text: modDone ? "✓" : pm.c + "/" + subs.length }),
      ]);
      rail.appendChild(h("div", { class: "mod" }, [header, subsWrap]));
    });
  }

  // Jump the right pane to a subsection (rendering its module first if needed) and scroll to it.
  function gotoSub(mod, s) {
    if (CTX.mod !== mod) {
      CTX.expanded.add(mod.title);
      renderTopic(CTX.main, mod, CTX.byTitle, CTX.byTopic);
      buildRail();
    }
    setTimeout(function () {
      var el = document.getElementById(s.anchor);
      if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 30);
  }

  // Re-sync the whole view with localStorage progress (after a lesson overlay closes).
  function refresh() {
    if (!CTX) return;
    buildRail();
    if (CTX.mod == null) renderOverview();
    else renderTopic(CTX.main, CTX.mod, CTX.byTitle, CTX.byTopic);
  }

  function renderTopic(main, mod, lessonsByTitle, premiumByTopic) {
    stopExam();  // leaving the practice exam (if any) for a topic
    if (CTX) CTX.mod = mod;
    var cfg = TOPIC_CFG[mod.title] || { premium: [], quiz: [] };
    clear(main);
    main.appendChild(h("h2", { text: mod.title }));
    main.appendChild(h("p", { class: "lede", text: mod.lessons.length + " lesson" + (mod.lessons.length === 1 ? "" : "s") + " in this topic" }));

    // 1) Premium education (exclusive; only present because RLS let us fetch it).
    var edu = [];
    cfg.premium.forEach(function (key) {
      (premiumByTopic[key] || []).forEach(function (it) { if (it.kind === "education") edu.push(it.body); });
    });
    if (edu.length) {
      var readState = loadRead();
      var esec = h("div", { class: "sec" }, [h("h3", { text: "Course material" })]);
      edu.forEach(function (b) {
        var rid = "e:" + b.title, isRead = !!readState[rid];
        var card = h("div", { class: "edu" + (isRead ? " read" : ""), id: "edu-" + slug(b.title), "data-subid": rid }, [h("h4", { text: b.title }), h("div", { class: "body", html: b.html })]);
        if (b.keypoints && b.keypoints.length) {
          var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
          var ul = h("ul");
          b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
          kp.appendChild(ul); card.appendChild(kp);
        }
        if (b.worked_example) {
          card.appendChild(h("div", { class: "edu-worked" }, [
            h("h5", { text: "Worked example" }),
            h("div", { class: "body", html: b.worked_example }),
          ]));
        }
        if (b.memory_hooks && b.memory_hooks.length) {
          var hk = h("div", { class: "edu-hooks" }, [h("h5", { text: "Memory hooks" })]);
          var hul = h("ul");
          b.memory_hooks.forEach(function (p) { hul.appendChild(h("li", { text: p })); });
          hk.appendChild(hul); card.appendChild(hk);
        }
        if (b.exam_traps && b.exam_traps.length) {
          var tp = h("div", { class: "edu-traps" }, [h("h5", { text: "Exam traps" })]);
          var tul = h("ul");
          b.exam_traps.forEach(function (p) { tul.appendChild(h("li", { text: p })); });
          tp.appendChild(tul); card.appendChild(tp);
        }
        var foot = h("div", { class: "edu-foot" });
        if (isRead) {
          foot.appendChild(h("span", { class: "edu-read-tag", text: "✓ Read" }));
        } else {
          foot.appendChild(h("button", { class: "mark-read", type: "button", text: "Mark as read", onclick: function () {
            markRead(rid);
            card.classList.add("read");
            clear(foot); foot.appendChild(h("span", { class: "edu-read-tag", text: "✓ Read" }));
            buildRail();
          } }));
        }
        card.appendChild(foot);
        esec.appendChild(card);
      });
      main.appendChild(esec);
    }

    // 2) Free interactive lessons — open each in place (iframe overlay) so the learner
    //    never leaves the course. A ✓ shows once the simulator marks it complete.
    var done = loadDone();
    var lsec = h("div", { class: "sec" }, [h("h3", { text: "Lessons" })]);
    mod.lessons.forEach(function (title) {
      var L = lessonsByTitle[title] || {};
      var isDone = !!done[title];
      lsec.appendChild(h("div", { class: "lcard" + (isDone ? " done" : ""), id: "lesson-" + slug(title) }, [
        h("div", { class: "grow" }, [
          h("div", { class: "lt" }, [
            isDone ? h("span", { class: "lk", text: "✓ " }) : document.createTextNode(""),
            document.createTextNode(title),
          ]),
          L.blurb ? h("div", { class: "lb", text: L.blurb }) : document.createTextNode(""),
        ]),
        h("button", { class: "launch", type: "button", text: isDone ? "▶ Review lesson" : "▶ Open lesson",
          onclick: function () { openLesson(title); } }),
      ]));
    });
    main.appendChild(lsec);

    // 3) Exclusive topic quiz (premium questions), inline; link out to the free topic quiz.
    var pq = [];
    cfg.premium.forEach(function (key) {
      (premiumByTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") pq.push(it.body); });
    });
    if (pq.length) {
      var qsec = h("div", { class: "sec", id: "quiz-" + slug(mod.title), "data-subid": "q:" + mod.title }, [h("h3", { text: "Test yourself · course questions" })]);
      pq.forEach(function (q, i) { qsec.appendChild(quizItem(mod.title, i, q)); });
      main.appendChild(qsec);
    }
    if (cfg.quiz.length) {
      var link = h("p", { class: "quiz-foot" }, [
        document.createTextNode("Also practice the "),
        h("a", { class: "linkout", href: "quiz.html?topic=" + encodeURIComponent(cfg.quiz[0]), text: "free interactive " + cfg.quiz[0] + " quiz" }),
        document.createTextNode(" (read-the-scan)."),
      ]);
      main.appendChild(link);
    }
    if (hasMastery(mod)) main.appendChild(masterySection(mod));
    window.scrollTo(0, 0);
  }

  // Premium image questions carry an `img` (a pre-rendered scan in web/img/course-quiz/).
  // Show it above the prompt; text-only questions have no img and are unaffected.
  function addQImg(box, q) {
    if (q && q.img) {
      box.insertBefore(h("img", { class: "q-img", src: "img/course-quiz/" + q.img, alt: "Scan for this question" }), box.firstChild);
    }
  }

  // One inline premium question: shuffled options, grade on click, reveal explanation.
  function quizItem(topicTitle, idx, q) {
    var order = q.options.map(function (_o, i) { return i; });
    for (var i = order.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)); var t = order[i]; order[i] = order[j]; order[j] = t;
    }
    var answered = false;
    var fb = h("div", { class: "fb", hidden: true });
    var box = h("div", { class: "q" }, [h("p", { class: "prompt", text: q.prompt })]);
    addQImg(box, q);
    order.forEach(function (orig) {
      var b = h("button", { class: "opt", text: q.options[orig], onclick: function () {
        if (answered) return; answered = true;
        var correct = orig === q.answer;
        b.classList.add(correct ? "correct" : "wrong");
        if (!correct) {
          [].forEach.call(box.querySelectorAll(".opt"), function (o, k) {
            if (order[k] === q.answer) o.classList.add("correct");
          });
        }
        [].forEach.call(box.querySelectorAll(".opt"), function (o) { o.disabled = true; });
        fb.hidden = false; fb.textContent = (correct ? "Correct. " : "Not quite. ") + q.explain;
        bumpScore(topicTitle, correct);
      } });
      box.appendChild(b);
    });
    box.appendChild(fb);
    return box;
  }

  // --- end-of-module mastery check ---------------------------------------- //
  // N questions from the module pool, no feedback until submit, >= PASS_PCT passes.
  // Reuses the exam shuffle; every answer bumps the dashboard quiz score.
  function masterySection(mod) {
    var sec = h("div", { class: "sec mchk", id: "mastery-" + slug(mod.title), "data-subid": "m:" + mod.title },
      [h("h3", { text: "Mastery check" })]);
    var body = h("div", { class: "mchk-body" });
    sec.appendChild(body);
    renderMasteryIntro(mod, body);
    return sec;
  }
  function renderMasteryIntro(mod, body) {
    clear(body);
    var pool = modulePool(mod), n = Math.min(CHECK_N, pool.length);
    var m = loadMastery()[mod.title];
    if (m && m.passed) {
      body.appendChild(h("p", { class: "mchk-status pass", text: "Mastered · best " + m.bestPct + "%." }));
    } else if (m && m.attempts) {
      body.appendChild(h("p", { class: "mchk-status fail", text: "Not passed yet · best " + m.bestPct + "%. You need " + PASS_PCT + "%." }));
    } else {
      body.appendChild(h("p", { class: "mchk-intro", text: "Answer " + n + " questions from this module with no feedback until you submit. Score " + PASS_PCT + "% or higher to master it." }));
    }
    body.appendChild(h("button", { class: "btn", type: "button",
      text: (m && (m.passed || m.attempts)) ? "Retake the mastery check" : "Take the mastery check · " + n + " questions",
      onclick: function () { startMastery(mod, body); } }));
  }
  function startMastery(mod, body) {
    var pool = modulePool(mod);
    var order = shuffleInts(pool.length).slice(0, Math.min(CHECK_N, pool.length));
    var questions = order.map(function (idx) { var q = pool[idx]; return { q: q, order: shuffleInts(q.options.length) }; });
    renderMasteryRun(mod, body, questions);
  }
  function renderMasteryRun(mod, body, questions) {
    clear(body);
    var picks = questions.map(function () { return -1; });
    questions.forEach(function (item, qi) {
      var box = h("div", { class: "q mchk-q" }, [
        h("p", { class: "mq-num", text: "Question " + (qi + 1) + " of " + questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
      addQImg(box, item.q);
      item.order.forEach(function (orig) {
        var opt = h("button", { class: "opt", type: "button", onclick: function () {
          picks[qi] = orig;
          [].forEach.call(box.querySelectorAll(".opt"), function (o) { o.classList.remove("sel"); });
          opt.classList.add("sel");
        } }, [document.createTextNode(item.q.options[orig])]);
        box.appendChild(opt);
      });
      body.appendChild(box);
    });
    body.appendChild(h("button", { class: "btn", type: "button", text: "Submit mastery check", onclick: function () {
      var blank = picks.filter(function (p) { return p < 0; }).length;
      if (blank > 0 && !window.confirm(blank + " unanswered question(s) will be marked wrong. Submit now?")) return;
      submitMastery(mod, body, questions, picks);
    } }));
  }
  function submitMastery(mod, body, questions, picks) {
    var correct = 0;
    questions.forEach(function (item, qi) {
      var right = picks[qi] === item.q.answer;
      if (right) correct += 1;
      bumpScore(mod.title, right);
    });
    var pct = Math.round(100 * correct / questions.length);
    saveMasteryResult(mod.title, pct);
    renderMasteryResult(mod, body, questions, picks, correct, pct);
    buildRail();
  }
  function renderMasteryResult(mod, body, questions, picks, correct, pct) {
    clear(body);
    var passed = pct >= PASS_PCT;
    body.appendChild(h("div", { class: "mchk-score " + (passed ? "pass" : "fail") }, [
      h("div", { class: "ms-pct", text: pct + "%" }),
      h("div", { class: "ms-line", text: correct + " of " + questions.length + (passed ? " · mastered" : " · need " + PASS_PCT + "%") }),
    ]));
    var missed = [];
    questions.forEach(function (item, qi) { if (picks[qi] !== item.q.answer) missed.push({ item: item, pick: picks[qi] }); });
    if (missed.length) {
      body.appendChild(h("h4", { class: "mchk-rev-h", text: "Review these" }));
      missed.forEach(function (mm) {
        var item = mm.item;
        var box = h("div", { class: "q reviewed miss" }, [h("p", { class: "prompt", text: item.q.prompt })]);
        addQImg(box, item.q);
        item.order.forEach(function (orig) {
          var cls = "opt"; if (orig === item.q.answer) cls += " correct"; else if (orig === mm.pick) cls += " wrong";
          box.appendChild(h("button", { class: cls, type: "button", disabled: true }, [document.createTextNode(item.q.options[orig])]));
        });
        box.appendChild(h("div", { class: "fb", text: item.q.explain }));
        body.appendChild(box);
      });
    }
    var actions = h("div", { class: "mchk-actions" });
    if (!passed) actions.appendChild(h("button", { class: "btn", type: "button", text: "Retry", onclick: function () { startMastery(mod, body); } }));
    actions.appendChild(h("button", { class: "btn ghost", type: "button", text: passed ? "Done" : "Back to module", onclick: function () { renderMasteryIntro(mod, body); } }));
    body.appendChild(actions);
  }

  // --- practice exam ------------------------------------------------------ //
  // A registry-style run over the WHOLE premium question bank: pick a length, answer
  // with no feedback, then submit for a score + per-question review. Best score is
  // kept locally (server-side sync comes later). Option order is fixed per run.
  function shuffleInts(n) {
    var a = []; for (var i = 0; i < n; i++) a.push(i);
    for (var k = a.length - 1; k > 0; k--) { var j = Math.floor(Math.random() * (k + 1)); var t = a[k]; a[k] = a[j]; a[j] = t; }
    return a;
  }
  function examPool() {
    var pool = [];
    Object.keys(CTX.byTopic).forEach(function (key) {
      (CTX.byTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") pool.push(it.body); });
    });
    return pool;
  }
  // Premium quiz bodies for one module (its TOPIC_CFG premium keys) — the mastery-check pool.
  function modulePool(mod) {
    var cfg = TOPIC_CFG[mod.title] || { premium: [], quiz: [] };
    var pool = [];
    cfg.premium.forEach(function (key) {
      (CTX.byTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") pool.push(it.body); });
    });
    return pool;
  }
  function hasMastery(mod) { return modulePool(mod).length >= MIN_POOL; }
  function clearExamTimer() { if (EXAM && EXAM.timer) { clearInterval(EXAM.timer); EXAM.timer = null; } }
  function stopExam() { clearExamTimer(); EXAM = null; }
  function fmtTime(s) { var m = Math.floor(s / 60), ss = s % 60; return m + ":" + (ss < 10 ? "0" : "") + ss; }

  // Setup screen: choose length + timing, then start.
  function openExam() {
    stopExam();
    EXAM = { setup: true };  // marks the CTA active; no timer yet
    CTX.mod = null;
    buildRail();
    renderExamSetup(CTX.main);
  }
  function renderExamSetup(main) {
    clear(main);
    main.appendChild(h("h2", { text: "Practice exam" }));
    var pool = examPool();
    if (!pool.length) {
      main.appendChild(h("p", { class: "lede", text: "No practice questions are available yet." }));
      window.scrollTo(0, 0); return;
    }
    main.appendChild(h("p", { class: "lede", text: "A registry-style run drawn at random from the full course bank of " + pool.length + " questions. You get no feedback until you submit." }));

    var lenOpts = [];
    [50, 100].forEach(function (n) { if (n < pool.length) lenOpts.push(n); });
    lenOpts.push(pool.length);
    var chosen = lenOpts[0], timed = false;

    var lenRow = h("div", { class: "exam-lens" });
    var lenBtns = [];
    lenOpts.forEach(function (n) {
      var label = n === pool.length ? "All (" + n + ")" : String(n);
      var b = h("button", { class: "exam-len" + (n === chosen ? " on" : ""), type: "button", onclick: function () {
        chosen = n; lenBtns.forEach(function (x) { x.el.classList.toggle("on", x.n === n); });
      } }, [document.createTextNode(label)]);
      lenBtns.push({ el: b, n: n }); lenRow.appendChild(b);
    });

    var check = h("input", { type: "checkbox", onchange: function () { timed = check.checked; } });
    var timedRow = h("label", { class: "exam-timed" }, [check, document.createTextNode("Timed run (about one minute per question, auto-submits at zero)")]);

    var best = loadExamBest();
    var bestLine = best && best.bestPct != null
      ? h("p", { class: "exam-note", text: "Your best so far: " + best.bestPct + "% (" + best.bestScore + " of " + best.bestTotal + ")." })
      : document.createTextNode("");

    var start = h("button", { class: "btn", text: "Start exam", onclick: function () { startExam(chosen, timed); } });

    main.appendChild(h("div", { class: "exam-setup" }, [
      h("h3", { text: "How many questions" }), lenRow, timedRow, bestLine, start,
    ]));
    window.scrollTo(0, 0);
  }
  function startExam(n, timed) {
    var pool = examPool();
    var order = shuffleInts(pool.length).slice(0, Math.min(n, pool.length));
    var questions = order.map(function (idx) { var q = pool[idx]; return { q: q, order: shuffleInts(q.options.length) }; });
    beginExam(questions, timed);
  }
  function retryMissed(missed) {
    beginExam(missed.map(function (q) { return { q: q, order: shuffleInts(q.options.length) }; }), false);
  }
  function beginExam(questions, timed, diag) {
    stopExam();
    EXAM = {
      questions: questions, picks: questions.map(function () { return -1; }),
      timed: timed, remaining: timed ? questions.length * 60 : 0, elapsed: 0,
      reviewing: false, timer: null,
      diagnostic: !!diag, modTitles: diag ? diag.modTitles : null,
    };
    CTX.mod = null;
    buildRail();
    renderExam(CTX.main);
    EXAM.timer = setInterval(tickExam, 1000);
  }
  function tickExam() {
    if (!EXAM || EXAM.reviewing) return;
    if (EXAM.timed) {
      EXAM.remaining -= 1;
      if (EXAM.remaining <= 0) { EXAM.remaining = 0; updateExamBar(); submitExam(); return; }
    } else { EXAM.elapsed += 1; }
    updateExamBar();
  }
  function renderExam(main) {
    clear(main);
    EXAM.barCount = h("span", { class: "eb-count" });
    EXAM.barTimer = h("span", { class: "eb-timer" });
    main.appendChild(h("div", { class: "exam-bar" }, [
      EXAM.barCount, h("span", { class: "sp" }), EXAM.barTimer,
      h("button", { class: "btn eb-submit", text: EXAM.diagnostic ? "Submit placement test" : "Submit exam", onclick: confirmSubmit }),
    ]));
    main.appendChild(h("h2", { text: EXAM.diagnostic ? "Placement test" : "Practice exam" }));
    EXAM.questions.forEach(function (item, qi) {
      var box = h("div", { class: "exam-q" }, [
        h("p", { class: "eq-num", text: "Question " + (qi + 1) + " of " + EXAM.questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
      addQImg(box, item.q);
      item.order.forEach(function (orig) {
        var opt = h("button", { class: "exam-opt", type: "button", onclick: function () { selectOpt(qi, orig, box, opt); } },
          [document.createTextNode(item.q.options[orig])]);
        box.appendChild(opt);
      });
      main.appendChild(box);
    });
    main.appendChild(h("div", { class: "exam-foot" }, [h("button", { class: "btn", text: "Submit exam", onclick: confirmSubmit })]));
    updateExamBar();
    window.scrollTo(0, 0);
  }
  function selectOpt(qi, orig, box, opt) {
    if (!EXAM || EXAM.reviewing) return;
    EXAM.picks[qi] = orig;
    [].forEach.call(box.querySelectorAll(".exam-opt"), function (o) { o.classList.remove("sel"); });
    opt.classList.add("sel");
    updateExamBar();
  }
  function updateExamBar() {
    if (!EXAM || !EXAM.barCount) return;
    var answered = EXAM.picks.filter(function (p) { return p >= 0; }).length;
    EXAM.barCount.textContent = answered + " / " + EXAM.questions.length + " answered";
    EXAM.barTimer.textContent = EXAM.timed ? "Time left " + fmtTime(EXAM.remaining) : "Elapsed " + fmtTime(EXAM.elapsed);
  }
  function confirmSubmit() {
    if (!EXAM || EXAM.reviewing) return;
    var blank = EXAM.picks.filter(function (p) { return p < 0; }).length;
    if (blank > 0 && !window.confirm(blank + " question(s) are unanswered and will be marked wrong. Submit now?")) return;
    submitExam();
  }
  function submitExam() {
    if (!EXAM || EXAM.reviewing) return;
    EXAM.reviewing = true;
    clearExamTimer();
    if (EXAM.diagnostic) { submitDiagnostic(); return; }
    var correct = 0;
    EXAM.questions.forEach(function (item, qi) { if (EXAM.picks[qi] === item.q.answer) correct += 1; });
    var total = EXAM.questions.length, pct = Math.round(100 * correct / total);
    saveExamBest(correct, total, pct);
    renderExamReview(correct, total, pct);
  }
  function renderExamReview(correct, total, pct) {
    var main = CTX.main; clear(main);
    var missed = [];
    EXAM.questions.forEach(function (item, qi) { if (EXAM.picks[qi] !== item.q.answer) missed.push(item.q); });
    var used = EXAM.timed ? (EXAM.questions.length * 60 - EXAM.remaining) : EXAM.elapsed;
    var best = loadExamBest();

    var actions = h("div", { class: "er-actions" });
    if (missed.length) actions.appendChild(h("button", { class: "btn", text: "Retry " + missed.length + " missed", onclick: function () { retryMissed(missed); } }));
    actions.appendChild(h("button", { class: "btn ghost", text: "New exam", onclick: openExam }));

    main.appendChild(h("h2", { text: "Exam results" }));
    main.appendChild(h("div", { class: "exam-result" }, [
      h("div", { class: "er-score", text: correct + " / " + total }),
      h("div", { class: "er-pct", text: pct + "%" }),
      h("div", { class: "er-meta", text: "Time " + fmtTime(used) + (best && best.bestPct != null ? " · best " + best.bestPct + "%" : "") }),
      actions,
    ]));

    EXAM.questions.forEach(function (item, qi) {
      var pick = EXAM.picks[qi], right = pick === item.q.answer;
      var num = h("p", { class: "eq-num" }, [document.createTextNode("Question " + (qi + 1))]);
      if (!right) num.appendChild(h("span", { class: "miss-tag", text: "Missed" }));
      var box = h("div", { class: "exam-q reviewed" + (right ? "" : " miss") }, [num, h("p", { class: "prompt", text: item.q.prompt })]);
      addQImg(box, item.q);
      item.order.forEach(function (orig) {
        var cls = "exam-opt";
        if (orig === item.q.answer) cls += " correct";
        else if (orig === pick) cls += " wrong";
        box.appendChild(h("button", { class: cls, type: "button", disabled: true }, [document.createTextNode(item.q.options[orig])]));
      });
      if (pick < 0) box.appendChild(h("div", { class: "fb muted", text: "You left this one blank." }));
      box.appendChild(h("div", { class: "fb", text: item.q.explain }));
      main.appendChild(box);
    });
    window.scrollTo(0, 0);
  }
  function loadExamBest() { try { return JSON.parse(localStorage.getItem(COURSE_EXAM_KEY) || "null"); } catch (e) { return null; } }
  function saveExamBest(score, total, pct) {
    try {
      var b = loadExamBest() || {};
      if (b.bestPct == null || pct > b.bestPct) { b.bestPct = pct; b.bestScore = score; b.bestTotal = total; b.at = Date.now(); }
      b.lastPct = pct; b.lastAt = Date.now();
      localStorage.setItem(COURSE_EXAM_KEY, JSON.stringify(b));
    } catch (e) { /* storage off */ }
  }

  // --- diagnostic placement test ------------------------------------------ //
  // Samples DIAG_PER_MODULE questions from each module (tagged with its title), runs them with no
  // feedback until submit (reusing the exam machine), scores per module, and stores a snapshot that
  // reorders "Study next". Does NOT bump quiz score or change readiness/mastery.
  function loadDiagnostic() { try { return JSON.parse(localStorage.getItem(COURSE_DIAG_KEY) || "null"); } catch (e) { return null; } }
  function saveDiagnostic(d) { try { localStorage.setItem(COURSE_DIAG_KEY, JSON.stringify(d)); } catch (e) { /* storage off */ } }

  function startDiagnostic() {
    var questions = [], modTitles = [];
    CTX.curriculum.forEach(function (mod) {
      var pool = modulePool(mod);
      var pick = shuffleInts(pool.length).slice(0, Math.min(DIAG_PER_MODULE, pool.length));
      pick.forEach(function (idx) {
        var q = pool[idx];
        questions.push({ q: q, order: shuffleInts(q.options.length) });
        modTitles.push(mod.title);
      });
    });
    if (!questions.length) { renderOverview(); return; }
    beginExam(questions, false, { modTitles: modTitles });
  }

  function submitDiagnostic() {
    var per = {}, correct = 0;
    EXAM.questions.forEach(function (item, qi) {
      var t = EXAM.modTitles[qi];
      var rec = per[t] || (per[t] = { asked: 0, right: 0 });
      rec.asked += 1;
      if (EXAM.picks[qi] === item.q.answer) { rec.right += 1; correct += 1; }
    });
    var titles = CTX.curriculum.map(function (m) { return m.title; });
    var order = CourseLogic.rankModulesByDiagnostic(per, titles);
    saveDiagnostic({ taken: true, ts: Date.now(), perModule: per, order: order });
    renderDiagnosticResult(per, order, correct, EXAM.questions.length);
    buildRail();
  }

  function renderDiagnosticResult(per, order, correct, total) {
    var main = CTX.main; clear(main);
    var pct = Math.round(100 * correct / total);
    main.appendChild(h("h2", { text: "Placement results" }));
    main.appendChild(h("div", { class: "exam-result" }, [
      h("div", { class: "er-score", text: correct + " / " + total }),
      h("div", { class: "er-pct", text: pct + "%" }),
      h("div", { class: "er-meta", text: "A snapshot to plan your studying. It does not change your progress." }),
    ]));
    main.appendChild(h("h3", { class: "ready-h", text: "By module, weakest first" }));
    var grid = h("div", { class: "diag-grid" });
    order.forEach(function (t) {
      var rec = per[t] || { asked: 0, right: 0 };
      var a = rec.asked ? Math.round(100 * rec.right / rec.asked) : null;
      grid.appendChild(h("div", { class: "diag-row" }, [
        h("span", { class: "dr-title", text: t }),
        h("span", { class: "dr-acc", text: a == null ? "not tested" : a + "%" }),
        h("div", { class: "bar" }, [h("i", { style: "width:" + (a == null ? 0 : a) + "%" })]),
      ]));
    });
    main.appendChild(grid);
    var startMod = null;
    for (var i = 0; i < CTX.curriculum.length; i++) { if (CTX.curriculum[i].title === order[0]) { startMod = CTX.curriculum[i]; break; } }
    var actions = h("div", { class: "er-actions" });
    if (startMod) actions.appendChild(h("button", { class: "btn", type: "button", text: "Start with " + order[0], onclick: function () { openModule(startMod); } }));
    actions.appendChild(h("button", { class: "btn ghost", type: "button", text: "Retake", onclick: startDiagnostic }));
    actions.appendChild(h("button", { class: "btn ghost", type: "button", text: "Back to overview", onclick: renderOverview }));
    main.appendChild(actions);
    window.scrollTo(0, 0);
  }

  // --- progress persistence (local, best-effort) -------------------------- //
  function loadDone() {
    try {
      var a = JSON.parse(localStorage.getItem(CURRICULUM_DONE_KEY) || "[]");
      var m = {}; (a || []).forEach(function (t) { m[t] = true; }); return m;
    } catch (e) { return {}; }
  }
  function loadRead() { try { return JSON.parse(localStorage.getItem(COURSE_READ_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function markRead(id) { try { var r = loadRead(); r[id] = true; localStorage.setItem(COURSE_READ_KEY, JSON.stringify(r)); } catch (e) { /* storage off */ } }
  function loadMastery() { try { return JSON.parse(localStorage.getItem(COURSE_MASTERY_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function saveMasteryResult(title, pct) {
    try {
      var m = loadMastery(), r = m[title] || { passed: false, bestPct: 0, attempts: 0 };
      r.attempts += 1;
      if (pct > r.bestPct) r.bestPct = pct;
      if (pct >= PASS_PCT) r.passed = true;
      r.ts = Date.now();
      m[title] = r; localStorage.setItem(COURSE_MASTERY_KEY, JSON.stringify(m));
      return r;
    } catch (e) { return { passed: pct >= PASS_PCT, bestPct: pct, attempts: 1 }; }
  }
  // Mark a lesson complete in the shared curriculum list (same array the simulator writes).
  function markDone(title) {
    try {
      var a = JSON.parse(localStorage.getItem(CURRICULUM_DONE_KEY) || "[]");
      if (a.indexOf(title) < 0) { a.push(title); localStorage.setItem(CURRICULUM_DONE_KEY, JSON.stringify(a)); }
    } catch (e) { /* storage off */ }
  }
  function bumpScore(topicTitle, correct) {
    try {
      var s = JSON.parse(localStorage.getItem(COURSE_QUIZ_KEY) || "{}");
      var r = s[topicTitle] || { right: 0, seen: 0 };
      r.seen += 1; if (correct) r.right += 1; s[topicTitle] = r;
      localStorage.setItem(COURSE_QUIZ_KEY, JSON.stringify(s));
    } catch (e) { /* storage off */ }
  }

  // --- illustrated lesson viewer ------------------------------------------ //
  // Each step shows its pre-rendered acquired image (web/img/lessons/<slug>/<i>.png,
  // built by scripts/prerender_lessons.py) + the step's teaching box, stepped through
  // with no engine/Pyodide load. The live interactive simulator is one click away.
  function openLesson(title) {
    var L = CTX.byTitle[title] || {};
    lessonState = { title: title, steps: L.steps || [], i: 0 };
    document.getElementById("lesson-title").textContent = title;
    document.getElementById("lesson-fullsim").href = "simulator.html?lesson=" + encodeURIComponent(title);
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    renderLessonStep();
  }
  function renderLessonStep() {
    var body = document.getElementById("lesson-body");
    var ls = lessonState, steps = ls.steps, i = ls.i, step = steps[i] || {};
    clear(body);
    var wrap = h("div", { class: "lv" });
    if (step.state) {                    // only steps with sim state have a rendered image
      var img = h("img", { src: "img/lessons/" + slug(ls.title) + "/" + i + ".jpg", alt: "Acquired image for this step" });
      var imgBox = h("div", { class: "lv-img" }, [img]);
      img.addEventListener("error", function () { imgBox.remove(); textCol.classList.add("solo"); });
      wrap.appendChild(imgBox);
    }
    var textCol = h("div", { class: "lv-text" + (step.state ? "" : " solo") }, [
      h("div", { class: "lv-step", text: "Step " + (i + 1) + " of " + steps.length }),
      h("div", { class: "lv-box", html: step.text || "" }),
    ]);
    var isLast = i >= steps.length - 1;
    var back = h("button", { class: "btn ghost", type: "button", text: "← Back",
      onclick: function () { if (ls.i > 0) { ls.i -= 1; renderLessonStep(); } } });
    back.disabled = i === 0;
    var next = h("button", { class: "btn", type: "button", text: isLast ? "Finish lesson" : "Next →",
      onclick: function () { if (isLast) { markDone(ls.title); closeLesson(); } else { ls.i += 1; renderLessonStep(); } } });
    textCol.appendChild(h("div", { class: "lv-nav" }, [back, next]));
    wrap.appendChild(textCol);
    body.appendChild(wrap);
    if (body.scrollTo) body.scrollTo(0, 0);
  }
  function closeLesson() {
    if (overlay.hidden) return;
    overlay.hidden = true;
    lessonState = null;
    document.body.style.overflow = "";
    refresh();                          // pick up the completion we just recorded
  }
  document.getElementById("lesson-close").addEventListener("click", closeLesson);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeLesson(); });

  // Load the curriculum + premium content and render the course. Extracted so both
  // the entitled path and the post-checkout path use one code path (DRY).
  function loadCourse() {
    return Promise.all([
      fetch("lessons.json").then(function (r) { return r.json(); }),
      Accounts.premiumContent(COURSE),
    ]).then(function (res) {
      var data = res[0], premium = res[1];
      var byTitle = {}; (data.lessons || []).forEach(function (L) { byTitle[L.title] = L; });
      var byTopic = {}; (premium || []).forEach(function (it) {
        (byTopic[it.topic] = byTopic[it.topic] || []).push(it);
      });
      courseView(data.curriculum || [], byTitle, byTopic);
    });
  }

  // After returning from Stripe, the webhook can lag the redirect by a few seconds.
  // Show an unlocking state and poll the DB for the entitlement (never trust the
  // URL). Resolves true once entitled, false after ~30s.
  function waitForEntitlement() {
    gate([h("h2", { text: "Payment received" }),
      h("p", { text: "Unlocking your course. This can take a few seconds." })]);
    var tries = 0;
    return new Promise(function (resolve) {
      (function poll() {
        Accounts.isEntitled(COURSE).then(function (ok) {
          if (ok) return resolve(true);
          if (++tries >= 15) return resolve(false);
          setTimeout(poll, 2000);
        }).catch(function () {
          if (++tries >= 15) return resolve(false);
          setTimeout(poll, 2000);
        });
      })();
    });
  }

  function pendingView() {
    gate([h("h2", { text: "Almost there" }),
      h("p", { text: "Your payment went through, but access is taking longer than usual to activate. Refresh this page in a minute. If it still does not unlock, email erolakkoc8@gmail.com and we will sort it out." }),
      h("button", { class: "btn", text: "Refresh", onclick: function () { location.reload(); } })]);
  }

  // --- boot: resolve the gate, then load the course --------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  var justPaid = /[?&]checkout=success(?:&|$)/.test(location.search);
  Accounts.getSession().then(function (session) {
    if (!session) { signInView(); return; }
    var email = session.user && session.user.email;
    var uid = session.user && session.user.id;
    chrome(email);
    return Accounts.isEntitled(COURSE).then(function (ok) {
      if (ok) { if (justPaid) history.replaceState(null, "", location.pathname); return loadCourse(); }
      if (justPaid) {
        return waitForEntitlement().then(function (granted) {
          history.replaceState(null, "", location.pathname);
          if (granted) return loadCourse();
          pendingView();
        });
      }
      paywallView(email, uid);
    });
  }).catch(function (e) {
    gate([h("h2", { text: "Something went wrong" }), h("p", { text: String(e.message || e) })]);
  });
})();
