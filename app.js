const CONFIG = window.NBK_CONFIG || {};
const CONFIGURED =
  !!CONFIG.SUPABASE_URL && !CONFIG.SUPABASE_URL.includes("YOUR-PROJECT") &&
  !!CONFIG.SUPABASE_ANON_KEY && !CONFIG.SUPABASE_ANON_KEY.includes("YOUR-PUBLIC");
const db = CONFIGURED && window.supabase
  ? window.supabase.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY)
  : null;

let state = null;
let activeTab = "table";

// ---------- helpers ----------
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c]
  ));
}
function fmtRelative(iso) {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "—";
  const secs = Math.round((Date.now() - then.getTime()) / 1000);
  const units = [["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [unit, size] of units) {
    if (Math.abs(secs) >= size) {
      return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(-Math.round(secs / size), unit);
    }
  }
  return "just now";
}
function fmtKickoff(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(d);
}
function ptsClass(p) { return p === 3 ? "p3" : p === 1 ? "p1" : "p0"; }

// ---------- Table ----------
function tableView() {
  const rows = state.table.map((r, i) => {
    const badge = r.nbk ? `<span class="nbk-badge">NBK</span>` : "";
    const gap = r.nbk && r.gap_to_safety > 0
      ? `${r.gap_to_safety} off safety` : (r.nbk ? "rock bottom" : "");
    return `
      <div class="trow ${r.nbk ? "nbk" : ""}">
        <div class="t-rank">${String(i + 1).padStart(2, "0")}</div>
        <div class="t-name">${escapeHtml(r.player)} ${badge}</div>
        <div class="t-sub">${r.exact}×3</div>
        <div class="t-sub">${r.results}×1</div>
        <div class="t-pts">${r.points}</div>
        ${r.nbk ? `<div class="t-gap" style="grid-column:1/-1">${gap}</div>` : ""}
      </div>`;
  }).join("");
  return `
    <div class="section-head"><h2>League Table</h2>
      <p>${state.played > 0 ? "Lowest points = NBK" : "No games scored yet"}</p></div>
    <div class="table">
      <div class="trow head"><div>#</div><div>Player</div><div>Exact</div><div>Result</div><div>Pts</div></div>
      ${rows}
    </div>`;
}

// ---------- Results ----------
function resultsView() {
  const played = state.fixtures.filter(f => f.kicked_off).reverse();
  if (played.length === 0) return `<div class="empty-state">No games played yet.</div>`;
  return `<div class="section-head"><h2>Results</h2><p>Scores and everyone's picks</p></div>` +
    played.map(matchCard).join("");
}
function matchCard(f) {
  const scoreTxt = f.home_score != null ? `${f.home_score}–${f.away_score}` : "LIVE";
  const picks = (f.picks || []).map(p => {
    const pts = p.points;
    const ptsHtml = pts == null ? "" : `<span class="pts ${ptsClass(pts)}">${pts} pt${pts === 1 ? "" : "s"}</span>`;
    return `<div class="pick">
      <span class="who">${escapeHtml(p.player)}</span>
      <span class="guess">${p.home_pred}–${p.away_pred}</span>
      ${ptsHtml}
    </div>`;
  }).join("");
  return `
    <div class="match">
      <div class="match-top">
        <div class="home">${escapeHtml(f.home)}</div>
        <div class="match-score ${f.finished ? "" : "live"}">${scoreTxt}</div>
        <div class="away">${escapeHtml(f.away)}</div>
        <div class="match-date">${fmtKickoff(f.kickoff_utc)}</div>
      </div>
      ${picks ? `<div class="picks">${picks}</div>` : `<div class="picks"><div class="pick"><span class="who">No predictions</span></div></div>`}
    </div>`;
}

// ---------- Predict ----------
function predictView() {
  const upcoming = state.fixtures.filter(f => !f.kicked_off);
  const players = state.table.map(r => r.player);

  const notice = CONFIGURED ? "" :
    `<div class="notice">Predictions aren't connected yet — add your Supabase URL and anon key to <code>config.js</code>. (The table and results still work.)</div>`;

  if (upcoming.length === 0) {
    return `<div class="section-head"><h2>Predict</h2></div>${notice}
      <div class="empty-state">No upcoming fixtures to predict right now.</div>`;
  }

  const rows = upcoming.map(f => `
    <div class="pred-row" data-fixture="${f.id}">
      <div class="pred-team">${escapeHtml(f.home)}</div>
      <div class="pred-score">
        <input type="number" min="0" max="30" inputmode="numeric" class="ph" aria-label="${escapeHtml(f.home)} score">
        <span>–</span>
        <input type="number" min="0" max="30" inputmode="numeric" class="pa" aria-label="${escapeHtml(f.away)} score">
      </div>
      <div class="pred-team away">${escapeHtml(f.away)}</div>
      <div class="pred-when">${fmtKickoff(f.kickoff_utc)}</div>
    </div>`).join("");

  return `
    <div class="section-head"><h2>Predict</h2><p>Locks at kickoff for each game</p></div>
    ${notice}
    <div class="panel">
      <div class="identity">
        <div class="field"><label>Who are you?</label>
          <select id="player">${players.map(p => `<option>${escapeHtml(p)}</option>`).join("")}</select></div>
        <div class="field"><label>PIN</label>
          <input id="pin" type="password" inputmode="numeric" autocomplete="off" placeholder="group PIN"></div>
        <div class="field"><button class="action secondary" id="loadBtn" ${CONFIGURED ? "" : "disabled"}>Load my picks</button></div>
      </div>
      ${rows}
      <div class="save-bar">
        <button class="action" id="saveBtn" ${CONFIGURED ? "" : "disabled"}>Save predictions</button>
        <span class="msg" id="predMsg"></span>
      </div>
    </div>`;
}

function wirePredict() {
  const loadBtn = document.getElementById("loadBtn");
  const saveBtn = document.getElementById("saveBtn");
  if (!loadBtn || !db) return;

  loadBtn.addEventListener("click", async () => {
    const msg = document.getElementById("predMsg");
    const player = document.getElementById("player").value;
    const pin = document.getElementById("pin").value;
    msg.className = "msg"; msg.textContent = "Loading…";
    const { data, error } = await db.rpc("my_predictions", { p_player: player, p_pin: pin });
    if (error) { msg.className = "msg err"; msg.textContent = error.message || "Couldn't load."; return; }
    const byId = Object.fromEntries((data || []).map(d => [d.fixture_id, d]));
    let filled = 0;
    document.querySelectorAll(".pred-row").forEach(row => {
      const d = byId[Number(row.dataset.fixture)];
      if (d) { row.querySelector(".ph").value = d.home_pred; row.querySelector(".pa").value = d.away_pred; filled++; }
    });
    msg.className = "msg ok"; msg.textContent = filled ? `Loaded ${filled} saved pick(s).` : "No saved picks for upcoming games.";
  });

  saveBtn.addEventListener("click", async () => {
    const msg = document.getElementById("predMsg");
    const player = document.getElementById("player").value;
    const pin = document.getElementById("pin").value;
    if (!pin) { msg.className = "msg err"; msg.textContent = "Enter the PIN."; return; }

    const jobs = [];
    document.querySelectorAll(".pred-row").forEach(row => {
      const h = row.querySelector(".ph").value, a = row.querySelector(".pa").value;
      if (h === "" || a === "") return;
      jobs.push({ id: Number(row.dataset.fixture), h: Number(h), a: Number(a) });
    });
    if (jobs.length === 0) { msg.className = "msg err"; msg.textContent = "Enter at least one score."; return; }

    saveBtn.disabled = true; msg.className = "msg"; msg.textContent = "Saving…";
    let ok = 0; const errors = [];
    for (const j of jobs) {
      const { error } = await db.rpc("submit_prediction", {
        p_player: player, p_pin: pin, p_fixture_id: j.id, p_home: j.h, p_away: j.a,
      });
      if (error) errors.push(error.message || "error"); else ok++;
    }
    saveBtn.disabled = false;
    if (errors.length === 0) { msg.className = "msg ok"; msg.textContent = `Saved ${ok} prediction(s). Good luck.`; }
    else { msg.className = "msg err"; msg.textContent = `Saved ${ok}; ${errors.length} failed: ${[...new Set(errors)].join("; ")}`; }
  });
}

// ---------- shell ----------
const VIEWS = { table: tableView, predict: predictView, results: resultsView };

function setTab(tab) {
  if (!VIEWS[tab]) return;
  activeTab = tab;
  document.querySelectorAll(".tab").forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  const view = document.getElementById("view");
  if (!state) return;
  view.innerHTML = VIEWS[tab]();
  if (tab === "predict") wirePredict();
}

function renderMeta() {
  document.getElementById("played").textContent = `${state.played} of ${state.total}`;
  document.getElementById("updated").textContent = fmtRelative(state.updated_at);
  const foot = document.getElementById("season-foot");
  if (foot) foot.textContent = state.season_label ? `Season ${state.season_label}` : "";
}

async function init() {
  try {
    const res = await fetch("./state.json", { cache: "no-store" });
    if (!res.ok) throw new Error("state.json " + res.status);
    state = await res.json();
    renderMeta();
    setTab(activeTab);
  } catch (e) {
    document.getElementById("view").innerHTML =
      `<div class="empty-state">Couldn't load state.json — run the build once.</div>`;
  }
}

document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => setTab(b.dataset.tab)));
init();
