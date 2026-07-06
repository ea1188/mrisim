/* MRISim — Read-the-scan quiz.
 *
 * Reuses the existing Pyodide engine (worker.js + web_adapter.render): pick a topic,
 * then each question in quiz.json carries a render `setup`; the engine renders the
 * image live, the learner picks a multiple-choice answer and gets immediate feedback
 * + an explanation, with a running score and an end summary.
 */
"use strict";

const $ = (id) => document.getElementById(id);

// ---- engine worker bridge (mirrors app.js / protocol.js) ------------------- //
const worker = new Worker("worker.js");
let reqId = 0, workerDead = false;
const pending = new Map();
function call(type, payload) {
  if (workerDead) return Promise.reject(new Error("the engine has stopped — please reload"));
  return new Promise((resolve, reject) => {
    const id = ++reqId; pending.set(id, { resolve, reject });
    worker.postMessage({ id, type, payload });
  });
}
function onWorkerCrash(ev) {
  if (workerDead) return; workerDead = true;
  const msg = (ev && ev.message) || "the engine worker stopped";
  for (const [, p] of pending) p.reject(new Error(msg));
  pending.clear();
  $("splash-status").textContent = "The engine failed to start — please reload.";
}
worker.onerror = onWorkerCrash;
worker.onmessageerror = onWorkerCrash;
worker.onmessage = (e) => {
  const m = e.data;
  if (m.type === "progress") { $("splash-bar").style.width = m.pct + "%"; if (m.msg) $("splash-status").textContent = m.msg; return; }
  if (m.type === "ready") { onReady(); return; }
  if (m.type === "error") { $("splash-status").textContent = "Failed to start: " + m.msg; return; }
  const p = pending.get(m.id); if (!p) return;
  pending.delete(m.id);
  if (m.error) p.reject(new Error(m.error)); else p.resolve(m.result);
};

// ---- quiz state ----------------------------------------------------------- //
let allQuestions = [];     // every question from quiz.json
let categories = [];       // [{id, label}]
let pool = [];             // questions for the chosen topic
let idx = 0, score = 0, answered = false;
let correctIdx = 0;        // displayed position of the correct option after shuffling
let currentTopic = "all";  // topic id of the active run (best score is keyed by it)
let missed = [];           // questions answered wrong this run (for the review pass)
let reviewing = false;     // a review-the-missed run — don't overwrite the topic's best

const QUESTION_PARTS = ["qz-progress", "qz-imgwrap", "qz-prompt", "qz-options", "qz-feedback", "qz-next"];

// ---- progress (per-topic best score), persisted in localStorage ------------- //
const PROGRESS_KEY = "mrisim_quiz_progress_v1";
function loadProgress() {
  try { return JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {}; }
  catch (e) { return {}; }
}
function saveBest(topicId, sc, total) {
  if (!total) return;
  const prog = loadProgress();
  const prev = prog[topicId] || { best: 0, runs: 0 };
  prog[topicId] = { best: Math.max(prev.best || 0, sc), total, runs: (prev.runs || 0) + 1 };
  try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(prog)); } catch (e) { /* storage off */ }
}

async function onReady() {
  $("splash").hidden = true;
  $("qz-root").hidden = false;
  try {
    const data = await (await fetch("quiz.json")).json();
    allQuestions = data.questions || [];
    categories = data.categories || [];
  } catch (e) {
    $("qz-prompt").textContent = "Could not load the quiz.";
    return;
  }
  showMenu();
}

function buildMenu() {
  const wrap = $("qz-topics");
  wrap.innerHTML = "";
  const prog = loadProgress();
  const topics = [{ id: "all", label: "All topics" },
                  ...categories.filter((c) => allQuestions.some((q) => q.category === c.id))];
  for (const t of topics) {
    const n = t.id === "all" ? allQuestions.length : allQuestions.filter((q) => q.category === t.id).length;
    const best = prog[t.id];
    const bestTxt = best ? ` · best ${best.best}/${best.total}` : "";
    const b = document.createElement("button");
    b.className = "qz-topic"; b.type = "button";
    b.innerHTML = `<span>${t.label}</span><span class="n">${n} question${n === 1 ? "" : "s"}${bestTxt}</span>`;
    b.addEventListener("click", () => selectTopic(t.id));
    wrap.appendChild(b);
  }
}

function showMenu() {
  buildMenu();                              // rebuild so best scores reflect the latest run
  $("qz-menu").style.display = "block";
  $("qz-summary").style.display = "none";
  for (const id of QUESTION_PARTS) $(id).style.display = "none";
  $("qz-score").textContent = "";
}

function selectTopic(catId) {
  currentTopic = catId; reviewing = false;
  pool = catId === "all" ? allQuestions.slice() : allQuestions.filter((q) => q.category === catId);
  $("qz-menu").style.display = "none";
  startOver();
}

function startOver() {
  idx = 0; score = 0; missed = [];
  $("qz-summary").style.display = "none";
  showQuestion();
}

function setScore() {
  // graded so far: questions before the current one, plus this one if answered
  $("qz-score").textContent = `Score ${score} / ${idx + (answered ? 1 : 0)}`;
}

async function showQuestion() {
  answered = false;
  const q = pool[idx];
  $("qz-menu").style.display = "none";
  for (const id of ["qz-progress", "qz-imgwrap", "qz-prompt", "qz-options"]) $(id).style.display = "";
  $("qz-progress").textContent = `Question ${idx + 1} of ${pool.length}`;
  $("qz-feedback").style.display = "none";
  $("qz-next").style.display = "none";
  const isPair = q.type === "pair";
  // A question with no engine setup is a text/concept item (e.g. MR safety) — skip
  // the render entirely and collapse the image area so only the prompt + options show.
  const isText = !q.setup && !q.setupA;
  $("qz-imgwrap").style.display = isText ? "none" : "";
  $("qz-img").style.display = "none";
  $("qz-pair").style.display = isPair ? "flex" : "none";
  $("qz-imgmsg").style.display = "";
  $("qz-imgmsg").textContent = "Rendering…";
  $("qz-prompt").textContent = q.prompt;

  const opts = $("qz-options");
  opts.innerHTML = "";
  // Shuffle option order (Fisher–Yates) so the correct answer isn't always in the same
  // slot — the authored data is front-loaded on index 0, which would be a giveaway.
  const order = q.options.map((_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  correctIdx = order.indexOf(q.answer);
  window.__qzCorrect = correctIdx;          // exposed for the headless smoke (answers are already in quiz.json)
  order.forEach((orig, pos) => {
    const b = document.createElement("button");
    b.className = "qz-opt"; b.type = "button"; b.textContent = q.options[orig];
    b.addEventListener("click", () => answer(pos));
    opts.appendChild(b);
  });
  setScore();

  if (isText) return;                         // no image to render for a concept question

  try {
    if (isPair) {
      // "What changed?" — render both setups side by side; hide the prompt's spinner once
      // both have loaded so a slow second render doesn't look done early.
      const [ra, rb] = await Promise.all([call("render", q.setupA), call("render", q.setupB)]);
      const ia = $("qz-imgA"), ib = $("qz-imgB");
      let loaded = 0;
      const done = () => { if (++loaded === 2) $("qz-imgmsg").style.display = "none"; };
      ia.onload = done; ib.onload = done;
      ia.src = ra.image; ib.src = rb.image;
    } else {
      const r = await call("render", q.setup);
      const img = $("qz-img");
      img.onload = () => { img.style.display = "block"; $("qz-imgmsg").style.display = "none"; };
      img.src = r.image;
    }
  } catch (e) {
    $("qz-imgmsg").textContent = "Could not render this question — try the next one.";
  }
}

function answer(choice) {
  if (answered) return;
  answered = true;
  const q = pool[idx];
  [...$("qz-options").children].forEach((b, i) => {
    b.disabled = true;
    // Convey correct/wrong to assistive tech and colorblind users, not by
    // border colour alone (WCAG 1.4.1): annotate the accessible name.
    if (i === correctIdx) { b.classList.add("correct"); b.setAttribute("aria-label", `${b.textContent} — correct answer`); }
    else if (i === choice) { b.classList.add("wrong"); b.setAttribute("aria-label", `${b.textContent} — your answer, incorrect`); }
  });
  const correct = choice === correctIdx;
  if (correct) score++; else missed.push(q);
  $("qz-feedback").innerHTML =
    (correct ? '<b class="ok">Correct.</b> ' : '<b class="no">Not quite.</b> ') + (q.explain || "");
  $("qz-feedback").style.display = "block";
  $("qz-next").textContent = idx + 1 < pool.length ? "Next ▸" : "See results ▸";
  $("qz-next").style.display = "inline-block";
  setScore();
}

function showSummary() {
  for (const id of QUESTION_PARTS) $(id).style.display = "none";
  const n = pool.length;
  const pct = n ? Math.round((score / n) * 100) : 0;
  // A full topic run banks the best score; a review-the-missed run must not (it is scored
  // out of however many you missed, not the whole topic).
  if (!reviewing) saveBest(currentTopic, score, n);
  // Sync the run to the instructor backend when signed in (no-op otherwise).
  if (!reviewing && window.Accounts) Accounts.logActivity("quiz_attempt", currentTopic, score, n);
  $("qz-summary-score").textContent = `${score} / ${n}  (${pct}%)`;
  $("qz-summary-msg").textContent =
    pct >= 80 ? "Excellent — you can read these confidently." :
    pct >= 50 ? "Good start — review the ones you missed and try again." :
    "Worth another pass — the explanations after each answer are the study material.";
  // Offer a focused review of just the ones missed this run.
  const reviewBtn = $("qz-review");
  if (missed.length) {
    reviewBtn.textContent = `Review ${missed.length} missed ▸`;
    reviewBtn.style.display = "inline-block";
  } else {
    reviewBtn.style.display = "none";
  }
  $("qz-summary").style.display = "block";
  $("qz-score").textContent = `Score ${score} / ${n}`;
}

function reviewMissed() {
  if (!missed.length) return;
  reviewing = true;
  pool = missed.slice();                    // startOver resets `missed`; copy first
  $("qz-summary").style.display = "none";
  startOver();
}

$("qz-next").addEventListener("click", () => {
  idx++;
  if (idx < pool.length) showQuestion();
  else showSummary();
});
$("qz-restart").addEventListener("click", startOver);
$("qz-review").addEventListener("click", reviewMissed);
$("qz-topics-back").addEventListener("click", showMenu);
