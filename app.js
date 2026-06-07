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
    const missed = Math.max(0, r.played - r.predicted);
    return `
      <div class="trow player ${r.nbk ? "nbk" : ""}" data-i="${i}">
        <div class="t-rank">${String(i + 1).padStart(2, "0")}</div>
        <div class="t-name">${escapeHtml(r.player)} ${badge}</div>
        <div class="t-pts">${r.points}</div>
        <div class="t-breakdown"><div class="bd">
          <span><b>${r.predicted}</b>/${r.played} predicted</span>
          <span><b>${r.exact}</b> exact <span class="x">&times;3</span></span>
          <span><b>${r.results}</b> results <span class="x">&times;1</span></span>
          <span><b>${missed}</b> missed</span>
        </div></div>
      </div>`;
  }).join("");
  return `
    <div class="section-head"><h2>League Table</h2></div>
    <div class="table">
      <div class="trow head"><div>#</div><div>Player</div><div>Pts</div></div>
      ${rows}
    </div>
    <p class="hint">Tap a player for their points breakdown</p>`;
}

function wireTable() {
  document.querySelectorAll("#view .trow.player").forEach(row => {
    row.addEventListener("click", () => row.classList.toggle("open"));
  });
}

// ---------- Results ----------
const POINT_EMOJI = { 0: "0️⃣", 1: "1️⃣", 3: "3️⃣" };
function pointEmoji(p) { return POINT_EMOJI[p] != null ? POINT_EMOJI[p] : String(p); }

function groupLabel(f) {
  return f.group_label || (f.matchday ? `Week ${f.matchday}` : "Fixtures");
}

function resultsView() {
  const head = `<div class="section-head"><h2>Scorecards</h2><p>Negative Ball Knowledge</p></div>`;
  const played = state.fixtures.filter(f => f.kicked_off && f.finished);
  if (played.length === 0) return head + `<div class="empty-state">No games played yet.</div>`;

  const groups = {};
  played.forEach(f => { const k = groupLabel(f); (groups[k] = groups[k] || []).push(f); });
  const players = (state.players && state.players.length) ? state.players : state.table.map(r => r.player);

  // most recent group first (by latest kickoff in the group)
  const latest = label => Math.max(...groups[label].map(f => Date.parse(f.kickoff_utc)));
  const order = Object.keys(groups).sort((a, b) => latest(b) - latest(a));

  return head + order.map(label => {
    const fixtures = groups[label].slice().sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc));
    return weekCard(label, fixtures, players);
  }).join("");
}

function weekCard(title, fixtures, players) {
  const resultsLine = fixtures
    .map(f => `${escapeHtml(f.home)} ${f.home_score}-${f.away_score} ${escapeHtml(f.away)}`)
    .join("&nbsp;&nbsp;·&nbsp;&nbsp;");

  const pickByFixture = {};
  fixtures.forEach(f => {
    const m = {};
    (f.picks || []).forEach(p => { m[p.player] = p; });
    pickByFixture[f.id] = m;
  });

  const cards = players.map(player => {
    let wk = 0;
    const lines = fixtures.map(f => {
      const pick = pickByFixture[f.id][player];
      const pts = pick ? (pick.points || 0) : 0;
      wk += pts;
      const score = pick ? `${pick.home_pred}-${pick.away_pred}` : "X-X";
      const cls = pick ? "" : "missed";
      return `<div class="sc-line">
        <span class="sc-fixture ${cls}">${escapeHtml(f.home)}<b class="sc-score">${score}</b>${escapeHtml(f.away)}</span>
        <span class="pt-emoji" title="${pts} pt${pts === 1 ? "" : "s"}">${pointEmoji(pts)}</span>
      </div>`;
    }).join("");
    return `<div class="scorecard">
      <div class="scorecard-name">${escapeHtml(player)}<span class="wk-pts">${wk} pt${wk === 1 ? "" : "s"}</span></div>
      ${lines}
    </div>`;
  }).join("");

  return `<div class="week">
    <div class="week-head"><div class="week-title">${title}</div><div class="week-results">${resultsLine}</div></div>
    ${cards}
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
      <div class="pred-when">${f.group_label ? escapeHtml(f.group_label) + " · " : ""}${fmtKickoff(f.kickoff_utc)}</div>
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
  // Switching player wipes the boxes so you never see the previous person's picks.
  // Pure UI — wire it regardless of whether Supabase has loaded yet.
  const playerSel = document.getElementById("player");
  if (playerSel) {
    playerSel.addEventListener("change", () => {
      document.querySelectorAll(".pred-row").forEach(row => {
        row.querySelector(".ph").value = "";
        row.querySelector(".pa").value = "";
      });
      const msg = document.getElementById("predMsg");
      if (msg) { msg.className = "msg"; msg.textContent = ""; }
    });
  }

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
    // Reset every box first, so a player with no saved pick shows empty (not the
    // previous player's numbers), then fill in only this player's saved picks.
    document.querySelectorAll(".pred-row").forEach(row => {
      const d = byId[Number(row.dataset.fixture)];
      row.querySelector(".ph").value = d ? d.home_pred : "";
      row.querySelector(".pa").value = d ? d.away_pred : "";
      if (d) filled++;
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
  if (tab === "table") wireTable();
}

function fmtDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  // Format in UTC so the configured calendar date doesn't shift by viewer timezone.
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(d);
}

function renderMeta() {
  document.getElementById("startDate").textContent = fmtDate(state.window_start);
  document.getElementById("endDate").textContent = fmtDate(state.window_end);
  const pct = state.total > 0 ? Math.round((state.played / state.total) * 100) : 0;
  document.getElementById("progressFill").style.width = pct + "%";
  document.getElementById("progressLabel").textContent =
    state.total > 0 ? `${state.played} of ${state.total} games · ${pct}%` : "Not started";
  document.getElementById("updated").textContent = "Updated " + fmtRelative(state.updated_at);
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
