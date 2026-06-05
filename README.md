# NBK League — Football Score Predictor

A free, mostly-static site where 4 players predict the scorelines of every **Premier League,
FA Cup and Carabao Cup** game involving **Man Utd, Arsenal, Brentford and Tottenham**
(11 Dec → 2 May). A live league table ranks them; **last place is "NBK"**.

- **3 pts** for an exact score, **1 pt** for the correct result (W/D/L), 0 otherwise.
- Predictions are entered on the page and stored in a free **Supabase** database; they **lock at
  kickoff** (enforced server-side).
- A daily **GitHub Action** pulls results from **API-Football** (one free key covers the league
  and both cups), recomputes the table, and redeploys to **GitHub Pages**. Laptop can be off.

## How it works
```
API-Football (PL + FA Cup + Carabao) ─► daily GitHub Action (Python)
    fetch the 4 teams' games in window → upsert fixtures to Supabase →
    read locked predictions → score (3/1/0) → write state.json → deploy to Pages
Page: reads state.json (table + scorecards) · prediction form → Supabase RPC (PIN + kickoff lock)
```
No simulation, no odds — the table is pure arithmetic on real results, and NBK is simply whoever
is bottom (ties share it).

## Local development
```powershell
pip install -r requirements.txt
# Offline run using the sample data (no API key / Supabase needed):
python scripts/build_state.py --out state.json --fixtures test/fixtures.json --predictions test/predictions.json
python -m http.server 8139
```
Open `http://localhost:8139`. A live run (no `--fixtures`) needs `API_FOOTBALL_KEY`
(+ `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` to read predictions and write fixtures).

## Configure
- `data/players.json` — the 4 player names (shown in the table and the Predict dropdown).
- `data/competition.json` — window dates, the tracked **team ids**, the **competition ids**
  (39 PL, 45 FA Cup, 48 Carabao), `api_football_season`, and scoring values.
- `data/display_names.json` — pretty team names (Spurs, Wolves, Man Utd, …).
- `config.js` — your public Supabase URL + anon key (safe to commit; locked down by RLS).

Verify the team/competition ids against the live feed with
`python scripts/check_apifootball.py` (after setting `API_FOOTBALL_KEY`).

Full setup is in **DEPLOYMENT.md**.
