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
  var A11y = window.A11y;   // accessibility helpers (a11y.js), loaded before this
  var TOPIC_CFG = {
    "1 · What an MRI image is":       { premium: ["instrumentation"], quiz: [] },
    "2 · Where contrast comes from":  { premium: ["contrast-weighting"], quiz: ["sequences"] },
    "3 · Making a tissue disappear":  { premium: ["fat-suppression"], quiz: [] },
    "4 · Reading pathology":          { premium: ["pathology", "procedures-anatomy"], quiz: ["pathology"] },
    "5 · Image quality & speed":      { premium: ["image-quality"], quiz: ["image-quality"] },
    "6 · How the image is built":     { premium: ["pulse-sequences", "data-acquisition"], quiz: ["image-quality"] },
    "7 · 3D imaging & reconstruction": { premium: ["three-d-recon"], quiz: [] },
    "8 · Flow, function & artifacts": { premium: ["flow-artifacts", "procedures-vascular"], quiz: ["artifacts"] },
    "9 · Putting it together":        { premium: ["procedures-protocols", "procedures-positioning"], quiz: [] },
    "10 · Safety & patient care":     { premium: ["safety", "patient-care", "contrast-agents"], quiz: ["safety", "patient-care"] },
    "11 · Perfusion & advanced imaging": { premium: ["perfusion"], quiz: ["perfusion"] },
    "12 · Advanced vascular imaging": { premium: ["vascular-advanced"], quiz: ["vascular-advanced"] },
    "13 · Advanced diffusion imaging": { premium: ["diffusion-advanced"], quiz: ["diffusion-advanced"] },
    "14 · Cardiac MRI":               { premium: ["cardiac-advanced"], quiz: ["cardiac-advanced"] },
    "15 · MR spectroscopy (MRS)":     { premium: ["mrs-advanced"], quiz: ["mrs-advanced"] },
    "16 · Functional MRI (BOLD)":     { premium: ["fmri-advanced"], quiz: ["fmri-advanced"] },
    "17 · Quantitative MRI":          { premium: ["quant-advanced"], quiz: ["quant-advanced"] },
    "18 · Breast MRI":                { premium: ["breast-advanced"], quiz: ["breast-advanced"] },
    "19 · Prostate mpMRI":            { premium: ["prostate-advanced"], quiz: ["prostate-advanced"] },
    "20 · Advanced MSK imaging":      { premium: ["msk-advanced"], quiz: ["msk-advanced"] },
    "21 · Body MRI & MRCP":           { premium: ["body-advanced"], quiz: ["body-advanced"] },
  };
  var CURRICULUM_DONE_KEY = "mrisim_curriculum";
  var COURSE_QUIZ_KEY = "mrisim_course_quiz_v1";
  var PREMIUM_TOPIC_KEY = "mrisim_premium_topic_progress_v1"; // per-premium-topic { right, seen }; feeds the ARRT readiness blend
  var COURSE_READ_KEY = "mrisim_course_read_v1";  // which education/question sections have been read
  var COURSE_EXAM_KEY = "mrisim_course_exam_v1";  // best/last practice-exam score
  var COURSE_MASTERY_KEY = "mrisim_course_mastery_v1"; // per-module mastery-check result
  var COURSE_DIAG_KEY = "mrisim_course_diagnostic_v1"; // placement-test snapshot (separate from progress)
  var COURSE_REVIEW_KEY = "mrisim_course_review_v1"; // spaced-review queue of missed questions
  var COURSE_COMPLETE_KEY = "mrisim_course_completed_v1"; // first course-completion record (synced)
  var COURSE_TARGET_KEY = "mrisim_course_target_v1"; // study-plan target date (local-only, not synced)
  var DIAG_PER_MODULE = 2;                              // questions sampled per module in the placement test
  var CORE_MODULE_COUNT = 10;                           // the placement test covers only the core curriculum (2 x 10 = 20 Qs)
  var EXAM = null;  // active practice exam: { questions, picks, timer, timed, remaining, elapsed, reviewing }
  var STRIPE = window.MRISIM_STRIPE || {};
  // Free mode (config.js MRISIM_COURSE.free): any signed-in user gets the full course,
  // the paywall and Buy button are skipped, and no refund prompt shows. The RLS policy
  // on course_content is relaxed to match (migration 0008). Reversible: flip both back.
  var FREE = !!(window.MRISIM_COURSE && window.MRISIM_COURSE.free);
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
  function clear(el) {
    // Repainting the main content pane hides the study rail by default; only
    // renderTopic re-shows it (so exams/overview/review never carry the rail).
    if (CTX && el === CTX.main) clearStudyRail();
    while (el.firstChild) el.removeChild(el.firstChild);
  }
  function clearStudyRail() {
    var sr = document.getElementById("studyrail");
    if (!sr) return;
    while (sr.firstChild) sr.removeChild(sr.firstChild);
    sr.hidden = true;
  }
  function gate(kids) { clear(root); root.appendChild(h("div", { class: "gate" }, [h("div", { class: "card" }, kids)])); }

  // --- gate screens ------------------------------------------------------- //
  function notConfigured() {
    gate([h("h2", { text: "Course unavailable" }),
      h("p", { text: "This deployment has no backend configured, so the guided course can't load. The free simulator, quiz and lessons all work without an account." }),
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
    // Show which address Google's consent screen will display (our Supabase auth
    // host) so the supabase.co URL doesn't read as a scam.
    var supaHost = ((window.MRISIM_SUPABASE && window.MRISIM_SUPABASE.url) || "").replace(/^https?:\/\//, "").replace(/\/+$/, "");
    var authNote = supaHost ? h("p", { style: "margin-top:12px;font-size:12.5px;color:var(--muted);line-height:1.5", text: "When you continue, Google will ask you to sign in to " + supaHost + ", our secure authentication provider. This is expected." }) : null;
    gate([h("h2", { text: "Sign in to your course" }),
      h("p", { text: "Your guided curriculum, saved progress and course content are all here. Sign in to pick up where you left off." }),
      gbtn, authNote, toggle, fallback, msg].filter(Boolean));
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
      Accounts.signOut().then(function () { clearAllProgress(); location.reload(); });
    } }));
  }

  // --- the course --------------------------------------------------------- //
  function courseView(curriculum, lessonsByTitle, premiumByTopic, assignments) {
    var wrap = h("div", { class: "course" });
    var rail = h("div", { class: "rail" });
    var main = h("div", { class: "main" });
    CTX = { curriculum: curriculum, byTitle: lessonsByTitle, byTopic: premiumByTopic,
      rail: rail, main: main, mod: curriculum[0],
      assign: assignIndex(assignments),
      expanded: new Set([curriculum[0].title]) };  // which modules are expanded in the TOC

    var studyrail = h("aside", { class: "studyrail", id: "studyrail", hidden: true });
    buildRail();
    wrap.appendChild(rail); wrap.appendChild(main); wrap.appendChild(studyrail);
    clear(root); root.appendChild(wrap);
    renderOverview();   // open on the exam-readiness dashboard, not straight into module 1
  }

  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""); }

  // Index the learner's assignments by "kind ref" -> the assignment row, for O(1)
  // badge lookup during render. Best-effort: absent/[] means no badges.
  function assignIndex(assignments) {
    var idx = {};
    (assignments || []).forEach(function (a) { idx[a.kind + " " + a.ref] = a; });
    return idx;
  }
  // A small "ASSIGNED" badge (+ due) if this (kind, ref) is assigned to the learner,
  // else null. Uses the pure dueLabel for the date text.
  function assignBadge(kind, ref) {
    var a = CTX && CTX.assign && CTX.assign[kind + " " + ref];
    if (!a) return null;
    var badge = h("span", { class: "abadge", text: "Assigned" });
    var due = window.Assignments ? window.Assignments.dueLabel(a.due_at) : null;
    if (due) badge.appendChild(h("span", { class: "due", text: due.text }));
    return badge;
  }

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

  var QUIZ_PROGRESS_KEY = "mrisim_quiz_progress_v1";
  function loadQuizProgress() {
    try { return JSON.parse(localStorage.getItem(QUIZ_PROGRESS_KEY) || "{}"); }
    catch (e) { return {}; }
  }

  function loadPremiumTopicProgress() {
    try { return JSON.parse(localStorage.getItem(PREMIUM_TOPIC_KEY) || "{}"); }
    catch (e) { return {}; }
  }

  // "Registry readiness" panel: quiz accuracy mapped onto the ARRT content categories,
  // weighted by each category's exam share. Reads the standalone quiz's local progress.
  function appendReadiness(main) {
    if (!window.Blueprint) return;
    var rd = window.Blueprint.readiness(loadQuizProgress(), loadPremiumTopicProgress());
    var panel = h("div", { class: "blueprint" }, [
      h("h3", { class: "bp-h", text: "Readiness by ARRT content category" }),
      h("div", { class: "bp-lbl", text: "Blends your free diagnostic quiz and the course question bank." }),
      h("div", { class: "bp-head" }, [
        h("div", {}, [
          h("div", { class: "bp-num", text: Math.round(rd.projected * 100) + "%" }),
          h("div", { class: "bp-lbl", text: "projected, weighted by ARRT exam share" }),
        ]),
        h("div", { class: "bp-cov", text: "You have practiced " + Math.round(rd.coverage * 100)
          + "% of the weighted blueprint" }),
      ]),
    ]);
    rd.categories.forEach(function (c) {
      var pct = c.accuracy == null ? null : Math.round(c.accuracy * 100);
      var row = h("div", { class: "bp-row" }, [
        h("div", { class: "bp-row-top" }, [
          h("span", { class: "bp-name", text: c.name }),
          h("span", { class: "bp-chip", text: Math.round(c.weight * 100) + "% of exam" }),
          h("span", { class: "bp-acc" + (pct == null ? " none" : ""),
            text: pct == null ? "Not started" : pct + "%" }),
        ]),
        h("div", { class: "bar" }, [h("i", { style: "width:" + (pct == null ? 0 : pct) + "%" })]),
        h("div", { class: "bp-cov-line", text: c.attempted + " of " + c.memberCount
          + " topic" + (c.memberCount === 1 ? "" : "s") + " practiced" }),
      ]);
      if (c.note) row.appendChild(h("div", { class: "bp-note", text: c.note }));
      panel.appendChild(row);
    });
    main.appendChild(panel);
  }

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
    var diag = loadDiagnostic();
    if (diag && diag.order) {
      var statusByTitle = {};
      modules.forEach(function (m) { statusByTitle[m.mod.title] = m.status; });
      var t = CourseLogic.diagnosticStudyNext(diag.order, statusByTitle);
      if (t) {
        for (var k = 0; k < modules.length; k++) { if (modules[k].mod.title === t) { next = modules[k]; break; } }
      }
    }
    return { modules: modules, overall: overall, band: band, next: next, exam: exam, diagnostic: diag,
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
    var completeRec = loadCompleted();
    var complete = !!completeRec || CourseLogic.isCourseComplete(r.modules.map(function (m) { return m.status; }), r.exam && r.exam.bestPct);
    if (complete && !completeRec && r.exam && r.exam.bestPct != null) {
      completeRec = { at: Date.now(), examPct: r.exam.bestPct };
      saveCompleted(completeRec); queueSync();
    }
    if (complete) {
      var cWhen = (completeRec && completeRec.at) ? new Date(completeRec.at).toLocaleDateString() : new Date().toLocaleDateString();
      var cPct = (completeRec && completeRec.examPct != null) ? completeRec.examPct : (r.exam && r.exam.bestPct);
      main.appendChild(h("div", { class: "complete-panel" }, [
        h("p", { class: "cp-eyebrow", text: "Course complete" }),
        h("h3", { class: "cp-title", text: "You have completed the MRISim guided course" }),
        h("p", { class: "cp-sub", text: "Every module is mastered and your best practice exam is " + cPct + "%. Completed " + cWhen + "." }),
        h("p", { class: "cp-note", text: "Keep reviewing to stay sharp. The practice exam and every module stay open below." }),
      ]));
    } else if (r.next) {
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
        h("p", { text: "20 questions across the core curriculum, about 10 minutes. It finds your weakest areas and points you where to start. It does not affect your progress." }),
        h("button", { class: "btn", type: "button", text: "Start the placement test", onclick: startDiagnostic }),
      ]));
    } else {
      main.appendChild(h("p", { class: "diag-note" }, [
        document.createTextNode("Placement test taken. "),
        h("button", { type: "button", class: "diag-retake", text: "Retake", onclick: startDiagnostic }),
      ]));
    }
    var reviewDue = CourseLogic.dueCount(loadReview(), Date.now());
    var revCard = h("div", { class: "diag-card" }, [h("h3", { text: "Spaced review" })]);
    if (reviewDue > 0) {
      revCard.appendChild(h("p", { text: reviewDue + " question" + (reviewDue === 1 ? "" : "s") + " you missed " + (reviewDue === 1 ? "is" : "are") + " due for review." }));
      revCard.appendChild(h("button", { class: "btn", type: "button", text: "Start review", onclick: startReview }));
    } else {
      revCard.appendChild(h("p", { text: "No items due for review. Questions you miss show up here on a spaced schedule." }));
    }
    main.appendChild(revCard);
    var planOrder = CourseLogic.remainingStudyOrder(
      r.modules.map(function (m) { return { title: m.mod.title, status: m.status }; }),
      r.diagnostic && r.diagnostic.order);
    if (planOrder.length) {
      var modByTitle = {};
      r.modules.forEach(function (m) { modByTitle[m.mod.title] = m; });
      var NEXT_ACTION = { "not-started": "Start the material", "progress": "Keep going", "review": "Retake the mastery check" };
      var plan = h("div", { class: "diag-card" }, [h("h3", { text: "Your study plan" })]);
      var plist = h("div", { class: "plan-list" });
      planOrder.forEach(function (t) {
        var m = modByTitle[t];
        plist.appendChild(h("button", { class: "plan-row", type: "button", onclick: function () { openModule(m.mod); } }, [
          h("span", { class: "pr-title", text: t }),
          h("span", { class: "pr-act", text: NEXT_ACTION[m.status] || "Continue" }),
        ]));
      });
      plan.appendChild(plist);
      var target = loadTarget();
      var tstr = target && target.date ? target.date : "";
      var dinput = h("input", { type: "date", class: "plan-date", value: tstr,
        onchange: function () { saveTarget(dinput.value); renderOverview(); } });
      plan.appendChild(h("div", { class: "plan-target" }, [h("label", { text: "Target date:" }), dinput]));
      var pace = tstr ? CourseLogic.pacePerWeek(planOrder.length, Date.parse(tstr + "T00:00:00"), Date.now()) : null;
      var paceText;
      if (pace) paceText = planOrder.length + " module" + (planOrder.length === 1 ? "" : "s") + " left. To finish by " + tstr + ", cover about " + pace.perWeek + " per week.";
      else if (tstr) paceText = "That date has passed, pick a new one.";
      else paceText = planOrder.length + " module" + (planOrder.length === 1 ? "" : "s") + " left. Pick a target date to see a weekly pace.";
      plan.appendChild(h("p", { class: "plan-pace", text: paceText }));
      main.appendChild(plan);
    }
    appendReadiness(main);
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
    main.appendChild(h("p", { style: "margin-top:28px;font-size:12px;color:var(--dim)" }, [
      document.createTextNode("Starting over? "),
      h("button", { type: "button", style: "background:none;border:none;color:var(--muted);font:inherit;font-size:12px;text-decoration:underline;cursor:pointer;padding:0",
        text: "Reset my progress", onclick: resetProgress }),
      document.createTextNode("."),
    ]));
    if (!FREE) main.appendChild(h("p", { style: "margin-top:36px;font-size:12px;color:var(--dim)" }, [
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
    rail.appendChild(h("button", { class: "exam-cta" + (EXAM && !EXAM.diagnostic ? " on" : ""), type: "button", onclick: openExam }, [
      document.createTextNode("Practice exam"),
      h("span", { class: "ec-sub", text: "Registry-style run across the whole bank" }),
    ]));
    rail.appendChild(h("button", { class: "exam-cta" + (EXAM && EXAM.diagnostic ? " on" : ""), type: "button", onclick: startDiagnostic }, [
      document.createTextNode("Placement test"),
      h("span", { class: "ec-sub", text: "Find your weakest areas first" }),
    ]));
    var railDue = CourseLogic.dueCount(loadReview(), Date.now());
    rail.appendChild(h("button", { class: "exam-cta", type: "button", onclick: startReview }, [
      document.createTextNode("Review" + (railDue ? " (" + railDue + ")" : "")),
      h("span", { class: "ec-sub", text: "Missed items, spaced" }),
    ]));
    perMod.forEach(function (pm, i) {
      if (i === 0) rail.appendChild(h("div", { class: "rail-section", text: "Core curriculum" }));
      if (i === CORE_MODULE_COUNT && curriculum.length > CORE_MODULE_COUNT) {
        rail.appendChild(h("div", { class: "rail-section", text: "Advanced imaging" }));
      }
      var mod = pm.mod, subs = pm.subs;
      var modDone = subs.length && pm.c === subs.length;
      var expanded = CTX.expanded.has(mod.title);
      var inner = h("div", { class: "ms-inner" });
      subs.forEach(function (s) {
        var d = isSubDone(s, done, read, mastery);
        inner.appendChild(h("button", { class: "sub" + (d ? " done" : ""), type: "button",
          onclick: function () { gotoSub(mod, s); } }, [
          h("span", { class: "box" + (d ? " on" : ""), text: d ? "✓" : "" }),
          h("span", { class: "sl", text: s.label }),
        ]));
      });
      var subsWrap = h("div", { class: "mod-subs" + (expanded ? " open" : "") }, [inner]);
      var caret = h("span", { class: "caret" + (expanded ? " open" : ""), text: "▸" });
      // Toggle in place so the expand/collapse animates; a full buildRail() would recreate
      // the element in its target state and skip the CSS transition. Rebuilds elsewhere
      // (marking read, navigation) still paint the resting state instantly, which is correct.
      var header = h("button", { class: "mod-h" + (mod === CTX.mod ? " on" : ""), type: "button",
        onclick: function () {
          var wasActive = CTX.mod === mod;
          if (wasActive && CTX.expanded.has(mod.title)) {
            CTX.expanded.delete(mod.title);
            subsWrap.classList.remove("open");
            caret.classList.remove("open");
            return;
          }
          CTX.expanded.add(mod.title);
          subsWrap.classList.add("open");
          caret.classList.add("open");
          if (!wasActive) {
            // Clear any active rail button (module header, Overview, or an exam CTA) so
            // navigating in place leaves exactly one highlight, matching a full buildRail().
            [].forEach.call(rail.querySelectorAll(".mod-h.on, .overview-cta.on, .exam-cta.on"),
              function (el) { el.classList.remove("on"); });
            header.classList.add("on");
            renderTopic(CTX.main, mod, CTX.byTitle, CTX.byTopic);
          }
        } }, [
        caret,
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

  // Deep-link from an assignment "open" link: course.html?module=<title> jumps to that
  // module; course.html?lesson=<title> jumps to (and scrolls to) that lesson inside its
  // module. Unknown or absent targets fall through, leaving the normal overview.
  function openFromQuery() {
    if (!CTX) return;
    var q = new URLSearchParams(location.search);
    var lessonRef = q.get("lesson"), modRef = q.get("module");
    if (!lessonRef && !modRef) return;
    // One-shot: drop the deep-link params (keep any others) so a later reload or in-app
    // navigation doesn't jump back to the assigned target.
    if (history.replaceState) {
      q.delete("lesson"); q.delete("module");
      var rest = q.toString();
      history.replaceState(null, "", location.pathname + (rest ? "?" + rest : ""));
    }
    if (lessonRef) {
      for (var i = 0; i < CTX.curriculum.length; i++) {
        var m = CTX.curriculum[i];
        if ((m.lessons || []).indexOf(lessonRef) < 0) continue;
        var subs = moduleSubsections(m);
        for (var j = 0; j < subs.length; j++) {
          if (subs[j].type === "lesson" && subs[j].id === lessonRef) { gotoSub(m, subs[j]); return; }
        }
      }
      return;
    }
    if (modRef) {
      for (var k = 0; k < CTX.curriculum.length; k++) {
        if (CTX.curriculum[k].title === modRef) { openModule(CTX.curriculum[k]); return; }
      }
    }
  }

  // Re-sync the whole view with localStorage progress (after a lesson overlay closes).
  function refresh() {
    if (!CTX) return;
    buildRail();
    if (CTX.mod == null) renderOverview();
    else renderTopic(CTX.main, CTX.mod, CTX.byTitle, CTX.byTopic);
  }

  // Right-hand study rail: a contextual "do next" panel for the current topic —
  // progress, jump into the simulator / quiz, and prev/next topic. Desktop-only
  // (CSS hides it under 1100px). hasPremiumQuiz gates the "course questions" jump.
  function buildStudyRail(mod, cfg, hasPremiumQuiz) {
    var sr = document.getElementById("studyrail");
    if (!sr) return;
    clear(sr);
    var done = loadDone(), read = loadRead(), mastery = loadMastery();
    var subs = moduleSubsections(mod);
    var doneN = subs.filter(function (s) { return isSubDone(s, done, read, mastery); }).length;
    var pct = subs.length ? Math.round((doneN / subs.length) * 100) : 0;

    var card = h("div", { class: "sr-card" }, [
      h("div", { class: "sr-h", text: "This topic" }),
      h("div", { class: "sr-title", text: mod.title }),
      h("div", { class: "sr-prog", text: doneN + " / " + subs.length + " done" }),
      h("div", { class: "bar" }, [h("i", { style: "width:" + pct + "%" })]),
    ]);

    var acts = h("div", { class: "sr-acts" });
    // Opens the next unfinished lesson in the in-course overlay (same as the Lessons
    // cards) so finishing returns here; the label advances with the learner's progress.
    var nl = CourseLogic.nextLesson(mod, done);
    if (nl.title) {
      var lessonLabel = nl.allDone ? "▶ Review lessons"
        : nl.index === 0 ? "▶ Start first lesson"
        : "▶ Continue lessons";
      acts.appendChild(h("button", { class: "sr-act", type: "button", text: lessonLabel,
        onclick: function () { openLesson(nl.title); } }));
    }
    if (cfg.quiz && cfg.quiz.length) {
      acts.appendChild(h("a", { class: "sr-act", href: "quiz.html?topic=" + encodeURIComponent(cfg.quiz[0]),
        text: "Practice: " + cfg.quiz[0] + " quiz" }));
    }
    if (hasPremiumQuiz) {
      acts.appendChild(h("button", { class: "sr-act", type: "button", text: "Jump to course questions",
        onclick: function () {
          var t = document.getElementById("quiz-" + slug(mod.title));
          if (t && t.scrollIntoView) t.scrollIntoView({ behavior: "smooth", block: "start" });
        } }));
    }
    card.appendChild(acts);

    var nav = CourseLogic.topicNav(CTX.curriculum, mod);
    var navRow = h("div", { class: "sr-nav" }, [
      h("button", { class: "sr-navbtn", type: "button", text: "‹ Prev", disabled: !nav.prev,
        onclick: function () { if (nav.prev) openModule(nav.prev); } }),
      h("button", { class: "sr-navbtn", type: "button", text: "Next ›", disabled: !nav.next,
        onclick: function () { if (nav.next) openModule(nav.next); } }),
    ]);
    card.appendChild(navRow);

    sr.appendChild(card);
    sr.hidden = false;
  }

  function renderTopic(main, mod, lessonsByTitle, premiumByTopic) {
    stopExam();  // leaving the practice exam (if any) for a topic
    if (CTX) CTX.mod = mod;
    var cfg = TOPIC_CFG[mod.title] || { premium: [], quiz: [] };
    clear(main);
    var modH = h("h2", { text: mod.title });
    var modBadge = assignBadge("module", mod.title);
    if (modBadge) modH.appendChild(modBadge);
    main.appendChild(modH);
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
        var eduH4 = h("h4", { text: b.title });
        var lb = listenBtn(function () {
          var t = b.title + ". " + textOf(b.html);
          (b.keypoints || []).forEach(function (kpt) { t += " Key point: " + kpt + "."; });
          if (b.worked_example) t += " Worked example. " + textOf(b.worked_example);
          (b.memory_hooks || []).forEach(function (hk) { t += " Memory hook: " + hk + "."; });
          (b.exam_traps || []).forEach(function (tp) { t += " Exam trap: " + tp + "."; });
          return t;
        }, (b._ptopic || "") + "|" + b.title, function () { return card; }, b);
        if (lb) eduH4.appendChild(lb);
        var card = h("div", { class: "edu" + (isRead ? " read" : ""), id: "edu-" + slug(b.title), "data-subid": rid }, [eduH4, h("div", { class: "body", html: b.html })]);
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
        if (window.CourseDiagrams) window.CourseDiagrams.attach(card, b.title);
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
            assignBadge("lesson", title) || document.createTextNode(""),
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
      cfg.quiz.forEach(function (topic) {
        var qb = assignBadge("quiz", topic);
        if (qb) link.appendChild(qb);
      });
      main.appendChild(link);
    }
    if (hasMastery(mod)) main.appendChild(masterySection(mod));
    buildStudyRail(mod, cfg, pq.length > 0);
    window.scrollTo(0, 0);
  }

  // A "Listen" toggle for any text getter. Prefers pre-rendered neural
  // narration (web/audio/cards, built by scripts/prerender_narration.py) when
  // the card has one; falls back to on-device speech (A11y). One player at a
  // time, aria-pressed while playing, speed applies live to both paths.
  var activeListen = null;
  var activeAudio = null;
  var narration = null;   // manifest: card title -> { file, seconds }
  fetch("audio/cards/manifest.json")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (m) { narration = m; })
    .catch(function () { narration = null; });

  // --- read-along highlighting ------------------------------------------- //
  // Sentences never cross block boundaries (textOf inserts a terminator at
  // every block end), so wrapping per block with the same A11y.chunks split
  // keeps span indices aligned with the audio chunk timeline.
  function wrapCardSentences(card, b) {
    if (!card || card.dataset.rsWrapped) return;
    var body = card.querySelector(".body");
    var blocks = body ? Array.prototype.slice.call(body.querySelectorAll("p, li, h5")) : [];
    if (body && !blocks.length) blocks = [body];
    var kpItems = Array.prototype.slice.call(card.querySelectorAll(".keypoints li"));
    var workedBody = card.querySelector(".edu-worked .body");
    var workedBlocks = workedBody
      ? (Array.prototype.slice.call(workedBody.querySelectorAll("p, li, h5")).length
          ? Array.prototype.slice.call(workedBody.querySelectorAll("p, li, h5")) : [workedBody])
      : [];
    var hookItems = Array.prototype.slice.call(card.querySelectorAll(".edu-hooks li"));
    var trapItems = Array.prototype.slice.call(card.querySelectorAll(".edu-traps li"));
    var plan = A11y.sentencePlan(b.title,
      blocks.map(function (el) { return el.textContent || ""; }),
      b.keypoints || [],
      workedBlocks.map(function (el) { return el.textContent || ""; }),
      b.memory_hooks || [],
      b.exam_traps || []);
    function markWhole(el, r) {
      if (!el || !r.count) return;
      var span = h("span", { class: "rs" });
      span.dataset.s0 = r.start; span.dataset.s1 = r.start + r.count - 1;
      while (el.firstChild) {
        var c = el.firstChild;
        if (c.classList && c.classList.contains("listen")) break;   // keep the button outside
        span.appendChild(c);
      }
      el.insertBefore(span, el.firstChild);
    }
    function wrapBlock(el, r) {
      if (!r.count) return;
      if (r.count === 1) { markWhole(el, r); return; }
      var idx = r.start, last = r.start + r.count - 1;
      var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      var nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(function (node) {
        var pieces = node.nodeValue.replace(/([.!?])\s+/g, "$1\u0000").split("\u0000");
        var frag = document.createDocumentFragment();
        pieces.forEach(function (piece, i) {
          var span = h("span", { class: "rs" });
          span.dataset.s0 = idx; span.dataset.s1 = idx;
          span.appendChild(document.createTextNode(piece));
          frag.appendChild(span);
          if (i < pieces.length - 1 && idx < last) idx++;
        });
        node.parentNode.replaceChild(frag, node);
      });
    }
    markWhole(card.querySelector("h4"), plan.title);
    blocks.forEach(function (el, i) { wrapBlock(el, plan.blocks[i]); });
    kpItems.forEach(function (el, i) { if (plan.keypoints[i]) markWhole(el, plan.keypoints[i]); });
    if (plan.workedHeader) markWhole(card.querySelector(".edu-worked h5"), plan.workedHeader);
    workedBlocks.forEach(function (el, i) { if (plan.workedBlocks[i]) wrapBlock(el, plan.workedBlocks[i]); });
    hookItems.forEach(function (el, i) { if (plan.hooks[i]) markWhole(el, plan.hooks[i]); });
    trapItems.forEach(function (el, i) { if (plan.traps[i]) markWhole(el, plan.traps[i]); });
    card.dataset.rsWrapped = "1";
  }

  var highlightedCard = null;
  function highlightSentence(card, idx) {
    if (highlightedCard && highlightedCard !== card) clearHighlight();
    highlightedCard = card;
    var spans = card.querySelectorAll(".rs");
    var target = null;
    for (var i = 0; i < spans.length; i++) {
      var on = +spans[i].dataset.s0 <= idx && idx <= +spans[i].dataset.s1;
      spans[i].classList.toggle("active", on);
      if (on && !target) target = spans[i];
    }
    if (target && target.scrollIntoView) target.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function clearHighlight() {
    if (!highlightedCard) return;
    highlightedCard.querySelectorAll(".rs.active").forEach(function (el) { el.classList.remove("active"); });
    highlightedCard = null;
  }

  function ttsProgress(mark) {
    return function (i) {
      var pos = A11y.position();
      setSeekUI(i, Math.max(1, pos.total - 1));
      if (mark) mark(i);
    };
  }

  function stopPlayback() {
    if (A11y) A11y.stop();
    if (activeAudio) { activeAudio.onended = null; activeAudio.pause(); activeAudio = null; }
    if (activeListen) { activeListen.setAttribute("aria-pressed", "false"); activeListen = null; }
    clearHighlight();
    hideTtsBar();
  }

  function listenBtn(getText, narrTitle, getCard, cardBody) {
    if (!A11y) return null;
    var btn = h("button", { class: "ghost listen", text: "Listen", "aria-pressed": "false" });
    btn.setAttribute("aria-label", "Read this section aloud");
    function finish() {
      btn.setAttribute("aria-pressed", "false");
      if (activeListen === btn) activeListen = null;
      clearHighlight();
      hideTtsBar();
    }
    btn.onclick = function () {
      var wasActive = activeListen === btn;
      stopPlayback();
      if (wasActive) return;
      activeListen = btn;
      btn.setAttribute("aria-pressed", "true");
      var card = getCard && getCard();
      var mark = null;
      if (card && cardBody) {
        try { wrapCardSentences(card, cardBody); mark = function (i) { highlightSentence(card, i); }; }
        catch (e) { mark = null; }   // highlighting is best-effort, never blocks audio
      }
      var rec = narrTitle && narration && narration[narrTitle];
      if (rec) {
        var a = new Audio("audio/cards/" + rec.file);
        a.playbackRate = (A11y.prefs().rate || 0.95);
        a.ontimeupdate = function () {
          setSeekUI(a.currentTime, rec.seconds || a.duration);
          if (mark && rec.starts && rec.starts.length) {
            var t = a.currentTime, i = 0;
            while (i + 1 < rec.starts.length && rec.starts[i + 1] <= t) i++;
            mark(i);
          }
        };
        a.onended = function () { activeAudio = null; finish(); };
        a.onerror = function () {           // missing/offline: fall back to TTS
          activeAudio = null;
          if (window.speechSynthesis) { showTtsBar(false); A11y.speak(getText(), finish, ttsProgress(mark)); }
          else finish();
        };
        activeAudio = a;
        showTtsBar(true);
        a.play();
      } else if (window.speechSynthesis) {
        showTtsBar(false);
        A11y.speak(getText(), finish, ttsProgress(mark));
      } else {
        finish();
      }
    };
    return btn;
  }
  function textOf(html) {
    var d = document.createElement("div");
    d.innerHTML = String(html || "").replace(/<\/(p|li|h[1-6]|div)>/gi, ". $&").replace(/<br\s*\/?>(?=.)/gi, ". ");
    return (d.textContent || "").replace(/\.\s*\./g, ".").replace(/\s{2,}/g, " ").trim();
  }

  // Floating audio bar: visible only while speech plays. Voice + speed are
  // remembered (A11y prefs) and apply from the next chunk onward.
  var ttsBar = null;
  var ttsVoiceSel = null;
  var ttsSeek = null;
  function setSeekUI(value, max) {
    if (!ttsSeek) return;
    if (max != null && isFinite(max) && max > 0) ttsSeek.max = String(max);
    if (document.activeElement !== ttsSeek) ttsSeek.value = String(value);
  }
  function showTtsBar(audioMode) {
    if (ttsBar) {
      ttsBar.hidden = false;
      if (ttsVoiceSel) ttsVoiceSel.hidden = !!audioMode;   // voice is fixed in a recording
      return;
    }
    var voiceSel = h("select", { "aria-label": "Reading voice" });
    function fillVoices() {
      clear(voiceSel);
      var p = A11y.prefs();
      var vs = A11y.voices().filter(function (v) { return /^en(-|_|$)/i.test(v.lang || ""); });
      var chosen = A11y.pickVoice(vs, p.voice);
      vs.forEach(function (v) {
        var o = h("option", { value: v.name }, [document.createTextNode(v.name)]);
        if (chosen && v.name === chosen.name) o.selected = true;
        voiceSel.appendChild(o);
      });
    }
    fillVoices();
    if (window.speechSynthesis) speechSynthesis.addEventListener("voiceschanged", fillVoices);
    voiceSel.onchange = function () { A11y.setPrefs({ voice: voiceSel.value }); A11y.refresh(); };
    var rateSel = h("select", { "aria-label": "Reading speed" }, [
      h("option", { value: "0.8" }, ["Slow"]),
      h("option", { value: "0.95", selected: "selected" }, ["Normal"]),
      h("option", { value: "1.15" }, ["Fast"]),
    ]);
    var saved = A11y.prefs().rate;
    if (saved) rateSel.value = String(saved);
    rateSel.onchange = function () {
      A11y.setPrefs({ rate: parseFloat(rateSel.value) });
      if (activeAudio) activeAudio.playbackRate = parseFloat(rateSel.value);
      else A11y.refresh();
    };
    var stopBtn = h("button", { class: "ghost", text: "Stop", onclick: stopPlayback });
    var seek = h("input", { type: "range", class: "tts-seek", min: "0", max: "1", step: "any", value: "0" });
    seek.setAttribute("aria-label", "Narration position");
    seek.addEventListener("input", function () {
      var v = parseFloat(seek.value);
      if (activeAudio) activeAudio.currentTime = v;
      else if (A11y.speaking()) A11y.seekChunk(v);
    });
    ttsSeek = seek;
    ttsBar = h("div", { class: "tts-bar" }, [voiceSel, rateSel, seek, stopBtn]);
    ttsVoiceSel = voiceSel;
    voiceSel.hidden = !!audioMode;
    document.body.appendChild(ttsBar);
  }
  function hideTtsBar() { if (ttsBar) ttsBar.hidden = true; }

  // Premium image questions carry an `img` (a pre-rendered scan in web/img/course-quiz/).
  // Show it above the prompt; text-only questions have no img and are unaffected.
  function addQImg(box, q) {
    if (!q || !q.img) return;
    var img = h("img", { class: "q-img", src: "img/course-quiz/" + q.img,
                 alt: A11y ? A11y.describeScan(q.setup) : "Scan for this question" });
    box.insertBefore(img, box.firstChild);
    if (q.credit && q.credit.license !== "Owner-Original") {
      var c = q.credit;
      var cap = h("p", { class: "q-credit" }, [
        document.createTextNode("Image: " + c.author + " · " + c.license + " · "),
        h("a", { class: "linkout", href: c.source_url, target: "_blank", rel: "noopener", text: "source" }),
      ]);
      box.insertBefore(cap, img.nextSibling);   // caption directly under the image
    }
  }

  // Human labels for premium topic keys, mirrored from reference.js TOPIC_LABELS.
  // Used to link a graded question to its matching reference topic.
  var REF_TOPIC_LABEL = {
    "contrast-weighting": "Contrast & weighting",
    "pulse-sequences": "Pulse sequences",
    "data-acquisition": "Data acquisition & k-space",
    "image-quality": "Image quality & speed",
    "fat-suppression": "Fat suppression",
    "flow-artifacts": "Flow & artifacts",
    "three-d-recon": "3D imaging & reconstruction",
    "pathology": "Pathology",
    "instrumentation": "Instrumentation & hardware",
    "safety": "Safety",
    "patient-care": "Patient care",
    "contrast-agents": "Contrast agents",
    "procedures-anatomy": "Anatomy & procedures",
    "procedures-protocols": "Protocols",
    "procedures-vascular": "Vascular imaging",
    "procedures-positioning": "Positioning & coils",
  };

  // True when the question's premium topic has at least one reference entry loaded
  // (CTX.byTopic carries every premium row, including kind='reference').
  function topicHasReference(key) {
    var arr = key && CTX && CTX.byTopic && CTX.byTopic[key];
    if (!arr) return false;
    for (var i = 0; i < arr.length; i++) { if (arr[i].kind === "reference") return true; }
    return false;
  }

  // A "Reference: <label>" deep-link for a graded question, appended to its feedback
  // box so a miss routes the learner to the topic in the reference. No-op when the
  // topic has no reference entries (defensive; every quiz topic currently has some).
  function appendRefLink(fb, q) {
    var key = q && q._ptopic;
    if (!topicHasReference(key)) return;
    var lbl = REF_TOPIC_LABEL[key] || key;
    fb.appendChild(h("a", { class: "linkout reflink",
      href: "reference.html?topic=" + encodeURIComponent(key),
      text: "Reference: " + lbl + " →" }));
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
        appendRefLink(fb, q);
        bumpScore(topicTitle, correct);
        bumpPremiumTopic(q._ptopic, correct);
        recordAnswer(q, correct, false);
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
      bumpPremiumTopic(item.q._ptopic, right);
      recordAnswer(item.q, right, false);
    });
    var pct = Math.round(100 * correct / questions.length);
    saveMasteryResult(mod.title, pct);
    // Formative sync so a class owner sees mastery per module (best-effort; no-op when signed out).
    if (window.Accounts) Accounts.logActivity("mastery_check", mod.title, pct, 100);
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
        var fbrev = h("div", { class: "fb", text: item.q.explain }); appendRefLink(fbrev, item.q); box.appendChild(fbrev);
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
    EXAM.questions.forEach(function (item, qi) {
      var right = EXAM.picks[qi] === item.q.answer;
      if (right) correct += 1;
      recordAnswer(item.q, right, false);
      bumpPremiumTopic(item.q._ptopic, right);
    });
    var total = EXAM.questions.length, pct = Math.round(100 * correct / total);
    saveExamBest(correct, total, pct);
    // Formative sync so a class owner sees mock-exam readiness (best-effort; no-op when signed out).
    if (window.Accounts) Accounts.logActivity("mock_exam", "mock", correct, total);
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
      queueSync();
    } catch (e) { /* storage off */ }
  }
  function loadTarget() { try { return JSON.parse(localStorage.getItem(COURSE_TARGET_KEY) || "null"); } catch (e) { return null; } }
  function saveTarget(dateStr) { try { localStorage.setItem(COURSE_TARGET_KEY, JSON.stringify({ date: dateStr })); } catch (e) { /* storage off */ } }
  function loadCompleted() { try { return JSON.parse(localStorage.getItem(COURSE_COMPLETE_KEY) || "null"); } catch (e) { return null; } }
  function saveCompleted(rec) { try { localStorage.setItem(COURSE_COMPLETE_KEY, JSON.stringify(rec)); } catch (e) { /* storage off */ } }

  // --- cross-device progress sync (best-effort, local-first) --------------- //
  var PROGRESS_KEYS = [CURRICULUM_DONE_KEY, COURSE_QUIZ_KEY, COURSE_READ_KEY, COURSE_EXAM_KEY, COURSE_MASTERY_KEY, COURSE_DIAG_KEY, COURSE_REVIEW_KEY, COURSE_COMPLETE_KEY, PREMIUM_TOPIC_KEY];
  // The user id the device's local progress currently belongs to. localStorage is
  // device-global, so on a shared device this marker is how bootSync tells "my own
  // progress from another device" (merge) from "a different account's" (discard).
  var PROGRESS_OWNER_KEY = "mrisim_progress_owner_v1";
  var _syncTimer = null;
  // Local pushes stay suppressed until bootSync has reconciled ownership. Before that,
  // the device's local blob may belong to a different account (shared device), and a
  // pagehide/visibilitychange flush must not push it up under the current user.
  var _synced = false;

  function readAllProgress() {
    var out = {};
    PROGRESS_KEYS.forEach(function (k) {
      try { var v = localStorage.getItem(k); if (v != null) out[k] = JSON.parse(v); } catch (e) { /* skip */ }
    });
    return out;
  }
  function loadOwner() { try { return localStorage.getItem(PROGRESS_OWNER_KEY); } catch (e) { return null; } }
  function saveOwner(uid) { try { localStorage.setItem(PROGRESS_OWNER_KEY, uid); } catch (e) { /* storage off */ } }
  // Wipe every course-progress key plus the owner marker. Used when the local blob
  // belongs to a different account, and on sign-out so the next user starts clean.
  function clearAllProgress() {
    PROGRESS_KEYS.forEach(function (k) { try { localStorage.removeItem(k); } catch (e) { /* storage off */ } });
    try { localStorage.removeItem(PROGRESS_OWNER_KEY); } catch (e) { /* storage off */ }
  }
  function writeAllProgress(state) {
    if (!state) return;
    PROGRESS_KEYS.forEach(function (k) {
      if (state[k] == null) return;
      try { localStorage.setItem(k, JSON.stringify(state[k])); } catch (e) { /* storage off */ }
    });
  }
  // User-initiated wipe of their own progress, local and server. The empty push here is
  // intentional (unlike the boot-time guard that avoids clobbering a real row with {}).
  // Wipe the SERVER row first and only clear locally + reload once it confirms: otherwise
  // an offline or failed wipe would clear local but leave the row to silently restore
  // everything on the next boot. Local-only mode (no backend / signed out) just clears.
  function resetProgress() {
    if (!window.confirm("Reset all your course progress? This clears your reading, quiz scores, mastery, and mock-exam history on every device signed in to this account. This cannot be undone.")) return;
    if (!syncOn()) { clearAllProgress(); location.reload(); return; }
    // Cancel any pending debounced push and suppress further ones during the wipe, so a
    // flush of the OLD local state can't race the {} upsert and restore the row.
    if (_syncTimer) { clearTimeout(_syncTimer); _syncTimer = null; }
    _synced = false;
    Accounts.saveProgress({}).then(function (ok) {
      if (!ok) { _synced = true; window.alert("Could not reach the server to reset your progress. Check your connection and try again."); return; }
      clearAllProgress();
      location.reload();
    });
  }
  function syncOn() { return !!(window.Accounts && Accounts.enabled() && Accounts.signedIn()); }
  // Debounced push of local progress to the server.
  function queueSync() {
    if (!syncOn() || !_synced) return;
    if (_syncTimer) clearTimeout(_syncTimer);
    _syncTimer = setTimeout(flushSync, 2000);
  }
  function flushSync() {
    if (_syncTimer) { clearTimeout(_syncTimer); _syncTimer = null; }
    if (!syncOn() || !_synced) return;
    Accounts.saveProgress(readAllProgress());
  }
  // Reconcile local and server progress at boot. Same owner as the local blob: merge
  // monotonically (this user's own progress from another device). Different or unstamped
  // owner: the local blob is a DIFFERENT account's data on a shared device, so discard it
  // and load the server copy alone — never union it in, which would both show and push
  // account A's progress under account B. Then stamp the current owner and push.
  function bootSync() {
    if (!syncOn()) return Promise.resolve();
    return Accounts.getUser().then(function (u) {
      var uid = u && u.id;
      if (!uid) return;
      return Accounts.loadProgress().then(function (remote) {
        var r = CourseLogic.reconcileBootProgress(loadOwner(), uid, readAllProgress(), remote);
        if (!r.sameOwner) clearAllProgress();   // foreign local blob: wipe before writing this user's state
        writeAllProgress(r.state);
        saveOwner(uid);
        _synced = true;                          // ownership reconciled: local is now this user's, safe to push
        // Push the reconciled state, EXCEPT when we discarded a foreign blob and the remote
        // came back empty. loadProgress returns null for both "no row" and a transient fetch
        // error, so pushing {} here could overwrite this user's real server row. Skipping it
        // is safe: queueSync recreates the row on the first real action.
        if (r.sameOwner || remote != null) Accounts.saveProgress(r.state);
      });
    }).catch(function () { /* best-effort */ });
  }
  if (window.addEventListener) {
    window.addEventListener("pagehide", flushSync);
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") flushSync(); });
  }

  // --- spaced review of missed items -------------------------------------- //
  function loadReview() { try { return JSON.parse(localStorage.getItem(COURSE_REVIEW_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function saveReview(map) { try { localStorage.setItem(COURSE_REVIEW_KEY, JSON.stringify(map)); queueSync(); } catch (e) { /* storage off */ } }

  // Record a graded answer into the spaced-review queue, keyed by the (unique) question prompt.
  // A miss enqueues/resets the question (due now). A correct answer during a review session
  // advances or graduates it. A correct answer anywhere else leaves the queue unchanged.
  function recordAnswer(q, correct, inReview) {
    if (!q || !q.prompt) return;
    var map = loadReview(), now = Date.now(), p = q.prompt;
    if (!correct) {
      map[p] = CourseLogic.reviewOnMiss(map[p], now);
    } else if (inReview) {
      var e = CourseLogic.reviewOnCorrect(map[p], now);
      if (e) map[p] = e; else delete map[p];
    } else {
      return;
    }
    saveReview(map);
  }

  // prompt -> full quiz body, from the loaded premium bank.
  function reviewPool() {
    var idx = {};
    Object.keys(CTX.byTopic).forEach(function (key) {
      (CTX.byTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") idx[it.body.prompt] = it.body; });
    });
    return idx;
  }
  // Due question bodies (due <= now), skipping prompts no longer in the bank.
  function dueReviewItems() {
    var map = loadReview(), pool = reviewPool(), now = Date.now(), out = [];
    Object.keys(map).forEach(function (p) { if (map[p] && map[p].due <= now && pool[p]) out.push(pool[p]); });
    return out;
  }

  function startReview() {
    stopExam();
    CTX.mod = null;
    var main = CTX.main; clear(main);
    main.appendChild(h("h2", { text: "Review" }));
    var items = dueReviewItems();
    if (!items.length) {
      main.appendChild(h("p", { class: "lede", text: "Nothing is due for review right now. Questions you miss in the quizzes, mastery checks, exams and placement test show up here on a spaced schedule." }));
      main.appendChild(h("button", { class: "btn ghost", type: "button", text: "Back to overview", onclick: renderOverview }));
      buildRail(); window.scrollTo(0, 0); return;
    }
    main.appendChild(h("p", { class: "lede", text: items.length + " item" + (items.length === 1 ? "" : "s") + " due. Answer each to reschedule it. Get it right a few times and it graduates out of review." }));
    var order = shuffleInts(items.length);
    order.forEach(function (idx) { main.appendChild(reviewCard(items[idx])); });
    main.appendChild(h("button", { class: "btn ghost", type: "button", text: "Done", onclick: renderOverview }));
    buildRail(); window.scrollTo(0, 0);
  }

  // One review question: shuffled options, immediate feedback, and reschedule on answer.
  // Mirrors quizItem's feedback pattern, but reschedules via recordAnswer(inReview=true) and
  // does not touch the per-module quiz score.
  function reviewCard(q) {
    var order = shuffleInts(q.options.length);
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
          [].forEach.call(box.querySelectorAll(".opt"), function (o, k) { if (order[k] === q.answer) o.classList.add("correct"); });
        }
        [].forEach.call(box.querySelectorAll(".opt"), function (o) { o.disabled = true; });
        fb.hidden = false; fb.textContent = (correct ? "Correct. " : "Not quite. ") + q.explain;
        appendRefLink(fb, q);
        recordAnswer(q, correct, true);
      } });
      box.appendChild(b);
    });
    box.appendChild(fb);
    return box;
  }

  // --- diagnostic placement test ------------------------------------------ //
  // Samples DIAG_PER_MODULE questions from each module (tagged with its title), runs them with no
  // feedback until submit (reusing the exam machine), scores per module, and stores a snapshot that
  // reorders "Study next". Does NOT bump quiz score or change readiness/mastery.
  function loadDiagnostic() { try { return JSON.parse(localStorage.getItem(COURSE_DIAG_KEY) || "null"); } catch (e) { return null; } }
  function saveDiagnostic(d) { try { localStorage.setItem(COURSE_DIAG_KEY, JSON.stringify(d)); queueSync(); } catch (e) { /* storage off */ } }

  function startDiagnostic() {
    var questions = [], modTitles = [];
    CTX.curriculum.slice(0, CORE_MODULE_COUNT).forEach(function (mod) {
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
      var right = EXAM.picks[qi] === item.q.answer;
      if (right) { rec.right += 1; correct += 1; }
      recordAnswer(item.q, right, false);
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
  function markRead(id) { try { var r = loadRead(); r[id] = true; localStorage.setItem(COURSE_READ_KEY, JSON.stringify(r)); queueSync(); } catch (e) { /* storage off */ } }
  function loadMastery() { try { return JSON.parse(localStorage.getItem(COURSE_MASTERY_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function saveMasteryResult(title, pct) {
    try {
      var m = loadMastery(), r = m[title] || { passed: false, bestPct: 0, attempts: 0 };
      r.attempts += 1;
      if (pct > r.bestPct) r.bestPct = pct;
      if (pct >= PASS_PCT) r.passed = true;
      r.ts = Date.now();
      m[title] = r; localStorage.setItem(COURSE_MASTERY_KEY, JSON.stringify(m));
      queueSync();
      return r;
    } catch (e) { return { passed: pct >= PASS_PCT, bestPct: pct, attempts: 1 }; }
  }
  // Mark a lesson complete in the shared curriculum list (same array the simulator writes).
  function markDone(title) {
    try {
      var a = JSON.parse(localStorage.getItem(CURRICULUM_DONE_KEY) || "[]");
      if (a.indexOf(title) < 0) { a.push(title); localStorage.setItem(CURRICULUM_DONE_KEY, JSON.stringify(a)); queueSync(); }
    } catch (e) { /* storage off */ }
  }
  function bumpScore(topicTitle, correct) {
    try {
      var s = JSON.parse(localStorage.getItem(COURSE_QUIZ_KEY) || "{}");
      var r = s[topicTitle] || { right: 0, seen: 0 };
      r.seen += 1; if (correct) r.right += 1; s[topicTitle] = r;
      localStorage.setItem(COURSE_QUIZ_KEY, JSON.stringify(s));
      queueSync();
    } catch (e) { /* storage off */ }
  }

  // Record one graded premium quiz answer by its ARRT premium topic (see PREMIUM_MAP
  // in blueprint.js). No-op when the body has no topic (e.g. free lessons).
  function bumpPremiumTopic(topicKey, correct) {
    if (!topicKey) return;
    try {
      var s = JSON.parse(localStorage.getItem(PREMIUM_TOPIC_KEY) || "{}");
      var r = s[topicKey] || { right: 0, seen: 0 };
      r.seen += 1; if (correct) r.right += 1; s[topicKey] = r;
      localStorage.setItem(PREMIUM_TOPIC_KEY, JSON.stringify(s));
      queueSync();
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
      var img = h("img", { src: "img/lessons/" + slug(ls.title) + "/" + i + ".jpg",
                   alt: "Acquired image for step " + (i + 1) + " of the lesson " + ls.title });
      var imgBox = h("div", { class: "lv-img" }, [img]);
      img.addEventListener("error", function () { imgBox.remove(); textCol.classList.add("solo"); });
      wrap.appendChild(imgBox);
    }
    var stepHead = h("div", { class: "lv-step", text: "Step " + (i + 1) + " of " + steps.length });
    var slb = listenBtn(function () { return textOf(step.text); });
    if (slb) stepHead.appendChild(slb);
    var textCol = h("div", { class: "lv-text" + (step.state ? "" : " solo") }, [
      stepHead,
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

  // Reading-progress bar: fill tracks how far the window is scrolled through the current view.
  // Stays at 0 (invisible) when there is nothing meaningful to scroll, e.g. the sign-in gate.
  (function initReadBar() {
    var fill = document.querySelector("#readbar > i");
    if (!fill) return;
    var ticking = false;
    function update() {
      ticking = false;
      var max = document.documentElement.scrollHeight - window.innerHeight;
      var pct = max > 40 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      fill.style.width = (pct * 100).toFixed(1) + "%";
    }
    function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(update); } }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    update();
  })();

  // Load the curriculum + premium content and render the course. Extracted so both
  // the entitled path and the post-checkout path use one code path (DRY).
  function loadCourse() {
    return Promise.all([
      fetch("lessons.json").then(function (r) { return r.json(); }),
      Accounts.premiumContent(COURSE),
      Accounts.myAssignments ? Accounts.myAssignments() : Promise.resolve([]),
    ]).then(function (res) {
      var data = res[0], premium = res[1], assignments = res[2];
      var byTitle = {}; (data.lessons || []).forEach(function (L) { byTitle[L.title] = L; });
      var byTopic = {}; (premium || []).forEach(function (it) {
        if (it.body) it.body._ptopic = it.topic;   // carry the premium topic onto pooled bodies for readiness
        (byTopic[it.topic] = byTopic[it.topic] || []).push(it);
      });
      return bootSync().then(function () {
        courseView(data.curriculum || [], byTitle, byTopic, assignments);
        openFromQuery();
      });
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
    if (FREE) { if (justPaid) history.replaceState(null, "", location.pathname); return loadCourse(); }
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
