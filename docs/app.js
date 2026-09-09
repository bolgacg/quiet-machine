/* The quiet machine, simulator. Plain JS, no libraries.
   1 real second = 10 simulated seconds. All sim numbers computed live. */
(function(){
"use strict";
const $ = s => document.querySelector(s);

/* ---------- faults: the five incidents, translated to a sorting line ---------- */
const FAULTS = [
  {id:"stall", name:"1 · silent stall",
   desc:"Incident 1 translated: the sorter keeps heartbeating but its item counter freezes. Files existed; work did not.",
   sick:["sorter"]},
  {id:"pressure", name:"2 · overload",
   desc:"Incident 2: the host saturates. Every station slows to a crawl, heartbeats still arrive, and the network looks guilty.",
   sick:["feeder","sorter","wash1","wash2","wash3"]},
  {id:"impostor", name:"3 · impostor",
   desc:"Incident 3: the sorter's health endpoint is answered by a different process. The check reads someone else's green.",
   sick:["sorter"]},
  {id:"halfhang", name:"4 · half-hang",
   desc:"Incident 4: wash lane 2 goes stale while the others flow. Total throughput dips a little; the aggregate looks fine.",
   sick:["wash2"]},
  {id:"refusals", name:"5 · silent refusals",
   desc:"Incident 5: the admission gate before the wash lanes refuses everything. The sorter still counts scans; nothing passes.",
   sick:["wash1","wash2","wash3"]},
];

const STATIONS = [
  {id:"feeder", nm:"Feeder", sub:"items in", base:60},
  {id:"sorter", nm:"Sorter", sub:"items sorted", base:58},
  {id:"wash1", nm:"Wash lane 1", sub:"items washed", base:19},
  {id:"wash2", nm:"Wash lane 2", sub:"items washed", base:19},
  {id:"wash3", nm:"Wash lane 3", sub:"items washed", base:19},
];

const TICK_MS = 500, SIM_PER_TICK = 5;   // 10 sim-seconds per real second
let simT = 0, fault = null, faultAt = null, injected = false;
let presFired = null, progFired = null, progAlert = "";
const hist = {}; STATIONS.forEach(s => hist[s.id] = []);
const state = {};
STATIONS.forEach(s => state[s.id] = {rate:s.base, lastOk:0, count:0});
let pressure = 0.3, identityBad = false, refusing = false;
const scores = {};   // faultId -> {pres, prog}

/* ---------- fault dynamics ---------- */
function rates(){
  const out = {};
  STATIONS.forEach(s => out[s.id] = s.base * (0.92 + 0.16*Math.random()));
  if (!fault) return out;
  if (fault === "stall") out.sorter = 0;
  if (fault === "pressure") STATIONS.forEach(s => out[s.id] *= 0.22);
  if (fault === "halfhang") out.wash2 = 0;
  if (fault === "refusals"){ out.wash1 = 0; out.wash2 = 0; out.wash3 = 0; }
  // impostor: rates unaffected; the sorter's real process crash-loops but the line coasts briefly
  if (fault === "impostor") out.sorter *= 0.9;
  return out;
}

function tick(){
  simT += SIM_PER_TICK;
  const r = rates();
  pressure = fault === "pressure" ? Math.min(28, pressure + 3) : Math.max(0.3, pressure - 4);
  identityBad = fault === "impostor";
  refusing = fault === "refusals";
  STATIONS.forEach(s => {
    const st = state[s.id];
    st.rate = r[s.id];
    const made = st.rate * SIM_PER_TICK / 60;
    st.count += made;
    if (made > 0.01) st.lastOk = simT;
    hist[s.id].push(st.rate);
    if (hist[s.id].length > 56) hist[s.id].shift();
  });

  /* presence monitor: process up + heartbeat within 90 sim-s. Heartbeats never stop in these faults. */
  const presFiring = false;

  /* progress rules */
  let firing = null;
  if (fault){
    const age = id => simT - state[id].lastOk;
    if (identityBad) firing = "IdentityMismatch: sorter /healthz answered by process 'labeler', pid differs";
    else if (pressure > 20) firing = "PressureStall: cpu pressure " + pressure.toFixed(0) + ", healthy is under 1";
    else if (age("sorter") > 60) firing = "QuietMachine: sorter heartbeats, but no item sorted for " + age("sorter") + " s";
    else if (age("wash2") > 60 && fault === "halfhang") firing = "HungPoller: wash lane 2 last success " + age("wash2") + " s ago; lanes 1 and 3 flow";
    else if (refusing && age("wash1") > 30) firing = "SilentRefusals: admissions to wash refused for " + age("wash1") + " s while sorter still scans";
  }
  if (fault && firing && progFired === null){
    progFired = simT - faultAt; progAlert = firing;
    scores[fault] = {pres: null, prog: progFired};
    renderScores();
  }
  render(presFiring, firing);
}

/* ---------- rendering ---------- */
function spark(id){
  const h = hist[id], W = 220, H = 34;
  if (!h.length) return "";
  const max = Math.max(...STATIONS.map(s => s.base)) * 1.15;
  const pts = h.map((v, i) => (i * (W / 55)).toFixed(1) + "," + (H - 3 - (v / max) * (H - 8)).toFixed(1)).join(" ");
  const sick = fault && FAULTS.find(f => f.id === fault).sick.includes(id);
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <polyline points="${pts}" fill="none" stroke="${sick ? "#b03a3a" : "#2f7d54"}" stroke-width="1.6"/></svg>`;
}

function render(presFiring, progFiring){
  const rows = STATIONS.map(s => {
    const sick = fault && FAULTS.find(f => f.id === fault).sick.includes(s.id);
    return `<div class="station ${sick ? "sick" : ""}">
      <div class="nm">${s.nm}<small>${s.sub}</small></div>${spark(s.id)}
      <div class="rate">${state[s.id].rate.toFixed(0)}<small>items / min</small></div></div>`;
  }).join("");
  $("#stations").innerHTML = rows;
  const mm = Math.floor(simT / 60), ss = String(simT % 60).padStart(2, "0");
  $("#simclock").textContent = `simulated time ${mm}:${ss} · 1 real second = 10 simulated seconds` +
    (fault ? ` · fault active: ${FAULTS.find(f => f.id === fault).name}` : " · line healthy");

  $("#pres-badge").className = "badge ok"; $("#pres-badge").textContent = "all green";
  $("#pres-why").textContent = fault
    ? "Process up. Heartbeat " + (simT % 10) + " s ago. Nothing to report."
    : "Nothing to report.";
  if (progFiring){
    $("#prog-badge").className = "badge firing"; $("#prog-badge").textContent = "FIRING";
    $("#prog-why").textContent = progFiring;
  } else {
    $("#prog-badge").className = "badge ok"; $("#prog-badge").textContent = "all quiet";
    $("#prog-why").textContent = fault && progFired === null ? "Rule window open, waiting for the evidence threshold…" : "Nothing firing.";
  }
}

function renderScores(){
  const keys = Object.keys(scores);
  if (!keys.length) return;
  $("#scorerows").innerHTML = keys.map(k => {
    const f = FAULTS.find(x => x.id === k), s = scores[k];
    return `<tr><td>${f.name}</td><td class="num miss">still green</td><td class="num hit">${s.prog} s</td></tr>`;
  }).join("");
  const caught = keys.length;
  $("#verdict1").innerHTML = `<b>The presence monitor has caught ${caught === 5 ? "none of the five" : "none so far"}.</b>
    ${caught} failure${caught > 1 ? "s" : ""} injected this session: the presence badge stayed green through every one,
    while the progress rules fired in ${keys.map(k => scores[k].prog + " s").join(", ")} of simulated time.
    Each rule demands positive evidence of work; that demand is the entire difference.`;
}

/* ---------- controls ---------- */
let selected = FAULTS[0].id;
function renderBtns(){
  $("#faultbtns").innerHTML = FAULTS.map(f =>
    `<button class="chip ${f.id === selected ? "on" : ""}" data-f="${f.id}">${f.name}</button>`).join("") +
    `<button class="chip danger ${injected ? "on" : ""}" id="injbtn">${injected ? "Clear the fault" : "Inject"}</button>`;
  document.querySelectorAll("#faultbtns .chip[data-f]").forEach(b =>
    b.onclick = () => { selected = b.dataset.f; if (injected){ clearFault(); } renderBtns(); });
  $("#injbtn").onclick = () => injected ? clearFault() : inject();
  $("#faultdesc").textContent = FAULTS.find(f => f.id === selected).desc;
}
function inject(){
  fault = selected; faultAt = simT; injected = true;
  presFired = null; progFired = null; progAlert = "";
  renderBtns();
}
function clearFault(){
  fault = null; faultAt = null; injected = false;
  progFired = null;
  STATIONS.forEach(s => state[s.id].lastOk = simT);
  renderBtns();
}
renderBtns();
setInterval(tick, TICK_MS);
/* first control starts selected and shows its result: auto-inject once, shortly after load */
setTimeout(() => { if (!injected && !Object.keys(scores).length) inject(); }, 2600);

/* ---------- pipeline drawing ---------- */
(function(){
  const boxes = [
    ["machine", "probe.py", "polls legs, writes frames,\nreports every 5 s"],
    ["bus", "NATS JetStream", "stream QM_TELEMETRY,\nkeeps an hour"],
    ["bridge", "bridge.py", "identity checked against\nthe subject; liars counted"],
    ["collector", "otelcol", "OTLP in,\nmetrics out"],
    ["watcher", "Prometheus", "8 rules in git,\nunit tested"],
    ["delivery", "Alertmanager", "one route,\nno silence rules"],
    ["ledger", "sink.py", "every notification\nappended to a file"],
  ];
  const W = 980, bw = 118, gap = (W - boxes.length * bw) / (boxes.length - 1 + 2);
  let html = "";
  boxes.forEach((b, i) => {
    const x = gap + i * (bw + gap * (boxes.length - 1) / (boxes.length - 1)) * 1.0;
    const bx = 10 + i * ((W - 20 - bw) / (boxes.length - 1));
    html += `<rect x="${bx}" y="26" width="${bw}" height="58" rx="7" fill="#ffffff" stroke="#c9c5be"/>`;
    html += `<text x="${bx + bw/2}" y="16" text-anchor="middle" fill="#8b95a1" font-size="10">${b[0]}</text>`;
    html += `<text x="${bx + bw/2}" y="46" text-anchor="middle" fill="#1a1d21" font-weight="500">${b[1]}</text>`;
    b[2].split("\n").forEach((line, li) => {
      html += `<text x="${bx + bw/2}" y="${60 + li * 12}" text-anchor="middle" font-size="9.5">${line}</text>`;
    });
    if (i < boxes.length - 1){
      const x1 = bx + bw, x2 = 10 + (i + 1) * ((W - 20 - bw) / (boxes.length - 1));
      html += `<line x1="${x1 + 3}" y1="55" x2="${x2 - 3}" y2="55" stroke="#8b95a1" stroke-width="1.5" stroke-dasharray="3 4"/>`;
    }
  });
  $("#pipesvg").innerHTML = html;
})();

/* ---------- guided tour (never blocks the page: overlay is pointer-events:none) ---------- */
(function(){
  const STEPS = [
    {sel:"header h1", k:"Welcome · 1 of 7", html:`This page argues one sentence: <b>the machine that stops reporting looks like a quiet machine.</b> Five real incidents, none of which produced an error, become five injectable failures below. The page stays fully clickable while this tour is open.`},
    {sel:"#faultbtns", k:"The failures · 2 of 7", html:`<b>Pick a failure, then press Inject.</b> Each one is a real incident translated to this sorting line; the line under the buttons says which. One is already running so you can see what injection does.`},
    {sel:"#linecard", k:"The line · 3 of 7", html:`Feeder, sorter, three wash lanes. Green sparklines are flowing work; a red one is the station the fault touches. Watch what the numbers do that the badges do not.`},
    {sel:"#mon-presence", k:"The baseline · 4 of 7", html:`The presence monitor is what most estates actually run: process up, heartbeat recent. Through all five failures it stays green, and that is the entire point of the page.`},
    {sel:"#mon-progress", k:"The kit's rules · 5 of 7", html:`The progress rules demand positive evidence: work advanced, identity matches, admissions flow. When one fires, this card names the rule and the evidence, in the same words the real kit's alerts use.`},
    {sel:"#act2 .proof, table.proof", k:"The real numbers · 6 of 7", html:`Act 2 leaves the cartoon: the actual kit ran on bare binaries, each fault was injected for real, and this table of fire and resolve latencies is quoted verbatim from the repository's proof run. Verdict line: PASS.`},
    {sel:"#fails .fails", k:"Limits · 7 of 7", html:`What this page does not claim, stated before you find it: the simulator is compressed and generous to no one, the proof run is one run, and the Docker path is CI-verified only. The coda has the one-line command that runs everything.`},
  ];
  const root = $("#tour"), hl = $("#tour-hl"), card = $("#tour-card");
  let idx = 0;
  function place(){
    const st = STEPS[idx];
    const elm = document.querySelector(st.sel);
    if (!elm){ next(); return; }
    const r = elm.getBoundingClientRect();
    const top = r.top + window.scrollY, left = r.left + window.scrollX;
    root.style.height = document.documentElement.scrollHeight + "px";
    hl.style.left = (left-8)+"px"; hl.style.top = (top-8)+"px";
    hl.style.width = (r.width+16)+"px"; hl.style.height = (r.height+16)+"px";
    const dots = STEPS.map((_,i)=>`<i class="${i===idx?'on':''}"></i>`).join("");
    card.innerHTML = `<div class="tk">${st.k}</div><p>${st.html}</p>
      <div class="tour-nav"><div class="dots">${dots}</div>
      ${idx>0?'<button class="tour-btn" id="tprev">Back</button>':""}
      <button class="tour-btn" id="tskip">Close</button>
      <button class="tour-btn primary" id="tnext">${idx<STEPS.length-1?"Next":"Done"}</button></div>`;
    const cw = Math.min(400, innerWidth-32);
    let cx = left + r.width + 18, cy = top;
    if (cx + cw > window.scrollX + document.documentElement.clientWidth - 16){ cx = Math.max(16, left); cy = top + r.height + 14; }
    card.style.left = cx+"px"; card.style.top = cy+"px";
    window.scrollTo({top: Math.max(0, top - 120), behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
    $("#tnext").onclick = next; $("#tskip").onclick = stop;
    const p = $("#tprev"); if (p) p.onclick = () => { idx = Math.max(0, idx-1); place(); };
  }
  function next(){ if (idx >= STEPS.length-1){ stop(); return; } idx++; place(); }
  function stop(){ root.classList.remove("on"); try{ localStorage.setItem("qm_tour","done"); }catch(e){} }
  function start(){ idx = 0; root.classList.add("on"); place(); }
  $("#tourbtn").addEventListener("click", start);
  let seen = null; try{ seen = localStorage.getItem("qm_tour"); }catch(e){}
  if (!seen) setTimeout(start, 900);
})();
})();
