# NBK League — Premier League Score Predictor

A free, mostly-static site where 4 players predict the scorelines of every Premier League
fixture involving **Man Utd, Arsenal, Brentford and Tottenham** (11 Dec → 2 May). A live league
table ranks them; **last place is "NBK"**.

- **3 pts** for an exact score, **1 pt** for the correct result (W/D/L), 0 otherwise.
- Predictions are entered on the page and stored in a free **Supabase** database; they **lock at
  kickoff** (enforced server-side).
- A daily **GitHub Action** pulls results from football-data.org, recomputes the table, and
  redeploys to **GitHub Pages**. No server to run; your laptop can be off.

## How it works
```
football-data.org (PL) ─► daily GitHub Action (Python)
    fetch results for the 4 teams in window → upsert fixtures to Supabase →
    read locked predictions → score (3/1/0) → write state.json → deploy to Pages
Page: reads state.json (table + results) · prediction form → Supabase RPC (PIN + kickoff lock)
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
Open `http://localhost:8139`. A live run (no `--fixtures`) needs `FOOTBALL_DATA_API_KEY`
(+ `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` to read predictions and write fixtures).

## Configure
- `data/players.json` — the 4 player names (shown in the table and the Predict dropdown).
- `data/competition.json` — window dates, the 4 tracked team codes (`tla`s), scoring values.
- `config.js` — your public Supabase URL + anon key (safe to commit; locked down by RLS).

Full setup is in **DEPLOYMENT.md**.
