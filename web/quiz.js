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

const QUESTION_PARTS = ["qz-progress", "qz-imgwrap", "qz-prompt", "qz-options", "qz-feedback", "qz-next"];

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
  buildMenu();
  showMenu();
}

function buildMenu() {
  const wrap = $("qz-topics");
  wrap.innerHTML = "";
  const topics = [{ id: "all", label: "All topics" },
                  ...categories.filter((c) => allQuestions.some((q) => q.category === c.id))];
  for (const t of topics) {
    const n = t.id === "all" ? allQuestions.length : allQuestions.filter((q) => q.category === t.id).length;
    const b = document.createElement("button");
    b.className = "qz-topic"; b.type = "button";
    b.innerHTML = `<span>${t.label}</span><span class="n">${n} question${n === 1 ? "" : "s"}</span>`;
    b.addEventListener("click", () => selectTopic(t.id));
    wrap.appendChild(b);
  }
}

function showMenu() {
  $("qz-menu").style.display = "block";
  $("qz-summary").style.display = "none";
  for (const id of QUESTION_PARTS) $(id).style.display = "none";
  $("qz-score").textContent = "";
}

function selectTopic(catId) {
  pool = catId === "all" ? allQuestions.slice() : allQuestions.filter((q) => q.category === catId);
  $("qz-menu").style.display = "none";
  startOver();
}

function startOver() {
  idx = 0; score = 0;
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
  $("qz-img").style.display = "none";
  $("qz-imgmsg").style.display = "";
  $("qz-imgmsg").textContent = "Rendering…";
  $("qz-prompt").textContent = q.prompt;

  const opts = $("qz-options");
  opts.innerHTML = "";
  q.options.forEach((text, i) => {
    const b = document.createElement("button");
    b.className = "qz-opt"; b.type = "button"; b.textContent = text;
    b.addEventListener("click", () => answer(i));
    opts.appendChild(b);
  });
  setScore();

  try {
    const r = await call("render", q.setup);
    const img = $("qz-img");
    img.onload = () => { img.style.display = "block"; $("qz-imgmsg").style.display = "none"; };
    img.src = r.image;
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
    if (i === q.answer) b.classList.add("correct");
    else if (i === choice) b.classList.add("wrong");
  });
  const correct = choice === q.answer;
  if (correct) score++;
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
  $("qz-summary-score").textContent = `${score} / ${n}  (${pct}%)`;
  $("qz-summary-msg").textContent =
    pct >= 80 ? "Excellent — you can read these confidently." :
    pct >= 50 ? "Good start — review the ones you missed and try again." :
    "Worth another pass — the explanations after each answer are the study material.";
  $("qz-summary").style.display = "block";
  $("qz-score").textContent = `Score ${score} / ${n}`;
}

$("qz-next").addEventListener("click", () => {
  idx++;
  if (idx < pool.length) showQuestion();
  else showSummary();
});
$("qz-restart").addEventListener("click", startOver);
$("qz-topics-back").addEventListener("click", showMenu);
