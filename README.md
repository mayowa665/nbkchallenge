# NBK League — Football Score Predictor

A free, mostly-static site where 4 players predict the scorelines of every game involving
**Man Utd, Arsenal, Brentford and Tottenham** — Premier League (automatic) plus FA Cup and
Carabao Cup ties (added by hand). A live league table ranks them; **last place is "NBK"**.

- **3 pts** for an exact score, **1 pt** for the correct result (W/D/L), 0 otherwise.
- Predictions are entered on the page and stored in a free **Supabase** database; they **lock at
  kickoff** (enforced server-side).
- A daily **GitHub Action** pulls PL results from **football-data.org**, merges any manual cup
  games, recomputes the table, and redeploys to **GitHub Pages**. Laptop can be off.

## How it works
```
football-data.org (PL)  +  data/manual_fixtures.json (cups) ─► daily GitHub Action (Python)
    fetch PL + merge cups → upsert fixtures to Supabase → read locked predictions →
    score (3/1/0) → write state.json → deploy to Pages
Page: reads state.json (table + scorecards) · prediction form → Supabase RPC (PIN + kickoff lock)
```
No free feed covers the English domestic cups, so FA Cup / Carabao games are added by hand in
`data/manual_fixtures.json` — only a handful of games across the season. That same file can also
override a Premier League score the feed gets wrong.

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
- `data/competition.json` — window dates, the tracked team codes (`tla`s: MUN/ARS/BRE/TOT), scoring.
- `data/manual_fixtures.json` — cup games + score corrections (instructions are inside the file).
- `data/display_names.json` — pretty team names (Spurs, Wolves, Man Utd, …).
- `config.js` — your public Supabase URL + anon key (safe to commit; locked down by RLS).

Full setup is in **DEPLOYMENT.md**.
