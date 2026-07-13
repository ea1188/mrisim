/* MRISim reference library — the deep, searchable Q&A reference.
 * Same gate as the course (window.Accounts): not configured → signed out → then either
 * free mode (any signed-in user) or the entitlement check. When access is granted we fetch
 * the content and show every course_content row of kind='reference' (RLS already limits the
 * rows; the client gate is only UX). Left = search + topic filter; right = collapsible entries. */
(function () {
  "use strict";
  var COURSE = "mri-core";
  // Free mode (config.js MRISIM_COURSE.free): any signed-in user gets the reference library,
  // the entitlement check is skipped. Mirrors course.js. RLS still guards the rows server-side.
  var FREE = !!(window.MRISIM_COURSE && window.MRISIM_COURSE.free);
  var root = document.getElementById("reference-root");
  var whoami = document.getElementById("whoami");
  var REF = null;  // { entries:[{topic,body}], byTopic:{}, order:[topicKey], topic:"all", q:"", main, side }

  // Human labels for the topic keys used in course_content.
  var TOPIC_LABELS = {
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
  function label(key) { return TOPIC_LABELS[key] || key; }

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

  // --- gate screens (mirror course.js) ------------------------------------ //
  function notConfigured() {
    gate([h("h2", { text: "Reference unavailable" }),
      h("p", { text: "This deployment has no backend configured, so the reference library can't load. The free simulator, quiz and lessons all work without an account." }),
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
    gate([h("h2", { text: "Sign in to the reference" }),
      h("p", { text: "The reference library is part of the guided course, currently free to signed-in users. Enter your email and we'll send you a one-time sign-in link." }),
      h("label", { text: "Email" }), email, btn, msg]);
  }
  function paywallView(email) {
    gate([h("h2", { text: "You're signed in — but not enrolled yet" }),
      h("p", { text: "The reference library is part of the paid course and " + (email || "your account") + " doesn't have access yet. If you've purchased or are joining a pilot, access is granted to this email — reach out and we'll enable it." }),
      h("a", { class: "btn", href: "mailto:erolakkoc8@gmail.com?subject=MRISim%20course%20access", text: "Request access" }),
      h("p", { class: "msg", html: "Meanwhile the <a class=\"linkout\" href=\"index.html\">free simulator, quiz and lessons</a> are open to everyone." })]);
  }
  function chrome(email) {
    whoami.hidden = false; clear(whoami);
    whoami.appendChild(document.createTextNode((email || "") + " · "));
    whoami.appendChild(h("button", { text: "Sign out", onclick: function () {
      Accounts.signOut().then(function () { location.reload(); });
    } }));
  }

  // --- search helpers ----------------------------------------------------- //
  // Flatten a trusted HTML body to plain text for matching (body is our own content).
  function stripHtml(html) { var d = document.createElement("div"); d.innerHTML = html || ""; return d.textContent || ""; }
  function haystack(body) {
    return (body.title + " " + stripHtml(body.html) + " " + (body.keypoints || []).join(" ")).toLowerCase();
  }
  // Title with case-insensitive query occurrences wrapped in <mark>, as an array of nodes.
  function highlight(text, q) {
    if (!q) return [document.createTextNode(text)];
    var out = [], low = text.toLowerCase(), ql = q.toLowerCase(), i = 0, at;
    while ((at = low.indexOf(ql, i)) !== -1) {
      if (at > i) out.push(document.createTextNode(text.slice(i, at)));
      out.push(h("mark", { text: text.slice(at, at + ql.length) }));
      i = at + ql.length;
    }
    if (i < text.length) out.push(document.createTextNode(text.slice(i)));
    return out;
  }

  // Deep-link support: reference.html?topic=<key> opens filtered to that topic
  // (e.g. a graded quiz question links here). Returns the key or "" if absent.
  function paramTopic() {
    try { return new URLSearchParams(location.search).get("topic") || ""; }
    catch (e) { return ""; }
  }

  // --- render ------------------------------------------------------------- //
  function referenceView(entries) {
    var byTopic = {}, order = [];
    entries.forEach(function (e) {
      if (!byTopic[e.topic]) { byTopic[e.topic] = []; order.push(e.topic); }
      byTopic[e.topic].push(e);
    });
    order.sort(function (a, b) { return label(a).localeCompare(label(b)); });
    var wrap = h("div", { class: "ref" });
    var side = h("div", { class: "rside" });
    var main = h("div", { class: "rmain" });
    var startTopic = paramTopic();
    if (!(startTopic && byTopic[startTopic])) startTopic = "all";
    REF = { entries: entries, byTopic: byTopic, order: order, topic: startTopic, q: "", main: main, side: side };
    wrap.appendChild(side); wrap.appendChild(main);
    clear(root); root.appendChild(wrap);
    buildSide(); renderMain();
  }

  function buildSide() {
    var side = REF.side; clear(side);
    var input = h("input", { type: "search", placeholder: "Search the reference…", value: REF.q,
      oninput: function () { REF.q = input.value.trim(); renderMain(); } });
    side.appendChild(h("div", { class: "rsearch" }, [input]));
    side.appendChild(topicBtn("all", "All topics", REF.entries.length));
    REF.order.forEach(function (key) { side.appendChild(topicBtn(key, label(key), REF.byTopic[key].length)); });
  }
  function topicBtn(key, text, count) {
    return h("button", { class: "rtopic" + (REF.topic === key ? " on" : ""), type: "button",
      onclick: function () { REF.topic = key; buildSide(); renderMain(); window.scrollTo(0, 0); } }, [
      document.createTextNode(text), h("span", { class: "rc", text: String(count) }),
    ]);
  }

  function renderMain() {
    var main = REF.main; clear(main);
    var q = REF.q.toLowerCase();
    var scope = REF.q ? REF.entries : (REF.topic === "all" ? REF.entries : REF.byTopic[REF.topic] || []);
    var hits = scope.filter(function (e) { return !q || haystack(e.body).indexOf(q) !== -1; });

    var title = REF.q ? "Search" : (REF.topic === "all" ? "Reference library" : label(REF.topic));
    main.appendChild(h("h2", { text: title }));
    main.appendChild(h("p", { class: "lede", text: REF.q
      ? hits.length + " match" + (hits.length === 1 ? "" : "es") + " for “" + REF.q + "”"
      : hits.length + " entr" + (hits.length === 1 ? "y" : "ies") + (REF.topic === "all" ? " across " + REF.order.length + " topics" : "") }));

    if (!hits.length) { main.appendChild(h("p", { class: "empty", text: "Nothing here yet. Try another search or topic." })); return; }

    // Group results by topic when showing everything or a search; single list for one topic.
    var grouped = REF.q || REF.topic === "all";
    if (!grouped) { hits.forEach(function (e) { main.appendChild(entryCard(e, REF.q)); }); return; }
    REF.order.forEach(function (key) {
      var g = hits.filter(function (e) { return e.topic === key; });
      if (!g.length) return;
      var group = h("div", { class: "rgroup" }, [h("h3", { text: label(key) })]);
      g.forEach(function (e) { group.appendChild(entryCard(e, REF.q)); });
      main.appendChild(group);
    });
  }

  // One collapsible entry. Auto-expanded while searching so matches are visible.
  function entryCard(e, q) {
    var b = e.body, open = !!q;
    var body = h("div", { class: "ebody", hidden: !open, html: b.html });
    if (b.keypoints && b.keypoints.length) {
      var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
      var ul = h("ul");
      b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
      kp.appendChild(ul); body.appendChild(kp);
    }
    var card = h("div", { class: "entry" + (open ? " open" : "") });
    var head = h("button", { class: "eh", type: "button", onclick: function () {
      var nowOpen = body.hidden;
      body.hidden = !nowOpen;
      card.classList.toggle("open", nowOpen);
    } }, [h("span", { class: "car", text: "▸" }), h("span", { class: "et" }, highlight(b.title, q))]);
    card.appendChild(head); card.appendChild(body);
    return card;
  }

  // --- boot --------------------------------------------------------------- //
  if (!window.Accounts || !Accounts.enabled()) { notConfigured(); return; }
  // Fetch the reference rows and render. Shared by the free path and the entitled path.
  function loadReference() {
    return Accounts.premiumContent(COURSE).then(function (premium) {
      var entries = (premium || []).filter(function (it) { return it.kind === "reference"; })
        .map(function (it) { return { topic: it.topic, body: it.body, ord: it.ord }; });
      if (!entries.length) {
        gate([h("h2", { text: "Reference library" }),
          h("p", { text: "No reference entries have been published yet. Check back soon." }),
          h("a", { class: "btn", href: "course.html", text: "Go to the course" })]);
        return;
      }
      referenceView(entries);
    });
  }

  Accounts.getSession().then(function (session) {
    if (!session) { signInView(); return; }
    var email = session.user && session.user.email;
    chrome(email);
    if (FREE) return loadReference();
    return Accounts.isEntitled(COURSE).then(function (ok) {
      if (!ok) { paywallView(email); return; }
      return loadReference();
    });
  }).catch(function (e) {
    gate([h("h2", { text: "Something went wrong" }), h("p", { text: String(e.message || e) })]);
  });
})();
