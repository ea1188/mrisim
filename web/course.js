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
  var frame = document.getElementById("lesson-frame");
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
    var email = h("input", { type: "email", placeholder: "you@school.edu", autocomplete: "email" });
    var msg = h("div", { class: "msg" });
    var btn = h("button", { class: "btn", text: "Email me a sign-in link", onclick: function () {
      var addr = email.value.trim();
      if (!addr) { msg.className = "msg err"; msg.textContent = "Enter your email."; return; }
      btn.disabled = true; msg.className = "msg"; msg.textContent = "Sending…";
      Accounts.signIn(addr).then(function (r) {
        btn.disabled = false;
        if (r && r.error) { msg.className = "msg err"; msg.textContent = r.error.message; return; }
        msg.className = "msg ok"; msg.textContent = "Check " + addr + " for a sign-in link.";
      }).catch(function (e) { btn.disabled = false; msg.className = "msg err"; msg.textContent = String(e.message || e); });
    } });
    gate([h("h2", { text: "Sign in to your course" }),
      h("p", { text: "The guided curriculum is a paid course. Sign in with the email your access is under — we'll email you a one-time sign-in link." }),
      h("label", { text: "Email" }), email, btn, msg]);
  }

  function paywallView(email) {
    gate([h("h2", { text: "You're signed in — but not enrolled yet" }),
      h("p", { text: "This guided curriculum is a paid course and " + (email || "your account") + " doesn't have access yet. If you've purchased or are joining a pilot, access is granted to this email — reach out and we'll enable it." }),
      h("a", { class: "btn", href: "mailto:erolakkoc8@gmail.com?subject=MRISim%20course%20access", text: "Request access" }),
      h("p", { class: "quiz-foot", html: "Meanwhile the <a class=\"linkout\" href=\"index.html\">free simulator, quiz and lessons</a> are open to everyone." })]);
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
      rail: rail, main: main, mod: curriculum[0] };

    buildRail();
    wrap.appendChild(rail); wrap.appendChild(main);
    clear(root); root.appendChild(wrap);
    renderTopic(main, curriculum[0], lessonsByTitle, premiumByTopic);
  }

  // (Re)build the topic rail from current progress; highlights CTX.mod. Called on load
  // and again after an inline lesson closes, so lesson completions tick through live.
  function buildRail() {
    var curriculum = CTX.curriculum, rail = CTX.rail, done = loadDone();
    var total = curriculum.reduce(function (n, m) { return n + m.lessons.length; }, 0);
    var doneCount = curriculum.reduce(function (n, m) {
      return n + m.lessons.filter(function (t) { return done[t]; }).length; }, 0);
    clear(rail);
    rail.appendChild(h("div", { class: "prog" }, [
      document.createTextNode(doneCount + " / " + total + " lessons"),
      h("div", { class: "bar" }, [h("i", { style: "width:" + (total ? Math.round(100 * doneCount / total) : 0) + "%" })]),
    ]));
    curriculum.forEach(function (mod) {
      var modDone = mod.lessons.length && mod.lessons.every(function (t) { return done[t]; });
      var btn = h("button", { class: "topic" + (mod === CTX.mod ? " on" : ""), onclick: function () {
        CTX.mod = mod;
        [].forEach.call(rail.querySelectorAll(".topic"), function (b) { b.classList.remove("on"); });
        btn.classList.add("on");
        renderTopic(CTX.main, mod, CTX.byTitle, CTX.byTopic);
      } }, [
        h("span", { class: "tk", text: modDone ? "✓" : "" }),
        document.createTextNode(mod.title),
      ]);
      rail.appendChild(btn);
    });
  }

  // Re-sync the whole view with localStorage progress (after a lesson overlay closes).
  function refresh() {
    if (!CTX) return;
    buildRail();
    renderTopic(CTX.main, CTX.mod, CTX.byTitle, CTX.byTopic);
  }

  function renderTopic(main, mod, lessonsByTitle, premiumByTopic) {
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
      var esec = h("div", { class: "sec" }, [h("h3", { text: "Course material" })]);
      edu.forEach(function (b) {
        var card = h("div", { class: "edu" }, [h("h4", { text: b.title }), h("div", { class: "body", html: b.html })]);
        if (b.keypoints && b.keypoints.length) {
          var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
          var ul = h("ul");
          b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
          kp.appendChild(ul); card.appendChild(kp);
        }
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
      lsec.appendChild(h("div", { class: "lcard" + (isDone ? " done" : "") }, [
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
      var qsec = h("div", { class: "sec" }, [h("h3", { text: "Test yourself · course questions" })]);
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
    main.scrollIntoView ? window.scrollTo(0, 0) : null;
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

  // --- progress persistence (local, best-effort) -------------------------- //
  function loadDone() {
    try {
      var a = JSON.parse(localStorage.getItem(CURRICULUM_DONE_KEY) || "[]");
      var m = {}; (a || []).forEach(function (t) { m[t] = true; }); return m;
    } catch (e) { return {}; }
  }
  function bumpScore(topicTitle, correct) {
    try {
      var s = JSON.parse(localStorage.getItem(COURSE_QUIZ_KEY) || "{}");
      var r = s[topicTitle] || { right: 0, seen: 0 };
      r.seen += 1; if (correct) r.right += 1; s[topicTitle] = r;
      localStorage.setItem(COURSE_QUIZ_KEY, JSON.stringify(s));
    } catch (e) { /* storage off */ }
  }

  // --- inline lesson overlay ---------------------------------------------- //
  // The lesson runs the real simulator in an iframe (simulator.html?lesson=…&embed=1),
  // so the learner stays on the course page. Same origin ⇒ shared localStorage, so any
  // completion the sim records is visible to refresh() the moment we close.
  function openLesson(title) {
    document.getElementById("lesson-title").textContent = title;
    frame.src = "simulator.html?lesson=" + encodeURIComponent(title) + "&embed=1";
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeLesson() {
    if (overlay.hidden) return;
    overlay.hidden = true;
    frame.src = "about:blank";          // tear down Pyodide / stop the worker
    document.body.style.overflow = "";
    refresh();                          // pick up any completion the sim just recorded
  }
  document.getElementById("lesson-close").addEventListener("click", closeLesson);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeLesson(); });

  // --- boot: resolve the gate, then load the course --------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  Accounts.getSession().then(function (session) {
    if (!session) { signInView(); return; }
    var email = session.user && session.user.email;
    chrome(email);
    return Accounts.isEntitled(COURSE).then(function (ok) {
      if (!ok) { paywallView(email); return; }
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
    });
  }).catch(function (e) {
    gate([h("h2", { text: "Something went wrong" }), h("p", { text: String(e.message || e) })]);
  });
})();
