# Deployment — step by step

Three free services, ~20 minutes, then it runs itself: **Supabase** (stores predictions),
**GitHub** (hosts the page + runs the daily update), **API-Football** (results feed — covers the
Premier League, FA Cup and Carabao Cup on its free plan).

---

## Part 1 — Edit the two data files first
1. `data/players.json` — replace the placeholders with your 4 players' names.
2. `data/competition.json` — check `window_start` / `window_end` (default 11 Dec 2025 → 2 May 2026),
   `tracked_team_ids` (33 Man Utd, 42 Arsenal, 55 Brentford, 47 Spurs), `competitions`
   (39 PL, 45 FA Cup, 48 Carabao Cup) and `api_football_season` (2025 for 2025/26).
   You can confirm these against the live feed in Part 4 with `python scripts/check_apifootball.py`.

---

## Part 2 — Supabase (stores the predictions)
1. Create a free account at **https://supabase.com** → **New project** (pick any name + a strong
   database password; the free tier is plenty).
2. Left sidebar → **SQL Editor** → **New query** → paste the entire contents of
   `supabase/schema.sql` → **Run**.
3. Set your shared PIN: run this once in the SQL editor (change `1234` to your chosen PIN):
   ```sql
   insert into public.app_config (id, pin_hash)
   values (1, extensions.crypt('1234', extensions.gen_salt('bf')))
   on conflict (id) do update set pin_hash = excluded.pin_hash;
   ```
4. Left sidebar → **Project Settings → API**, and copy three values:
   - **Project URL** (e.g. `https://abcd1234.supabase.co`)
   - **anon public** key (safe to expose)
   - **service_role** key (SECRET — used only by the GitHub Action; never put it in `config.js`)

---

## Part 3 — Fill in `config.js`
Put your **Project URL** and **anon public** key into `config.js`:
```js
window.NBK_CONFIG = {
  SUPABASE_URL: "https://abcd1234.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOi...your-anon-key...",
};
```
This file is public — that's fine. The anon key can only call the two locked-down functions.

---

## Part 4 — API-Football key
1. Sign up free at **https://www.api-football.com/** (or via the dashboard at
   **https://dashboard.api-football.com/register**). The free plan covers the Premier League,
   FA Cup and Carabao Cup (≈100 requests/day; this site uses ~4/day).
2. Copy your API key from the dashboard.
3. (Recommended) Verify the ids are right before deploying:
   ```powershell
   $env:API_FOOTBALL_KEY="...your key..."
   python scripts/check_apifootball.py
   ```
   It should print "Man Utd", "Arsenal", "Brentford", "Spurs" with some of their PL/cup fixtures.
   If a wrong club shows, fix that id in `data/competition.json`.

---

## Part 5 — GitHub
1. Create a new **public** repo and push this folder to `main`.
2. **Settings → Secrets and variables → Actions → New repository secret**, add three:
   - `API_FOOTBALL_KEY` — your API-Football key
   - `SUPABASE_URL` — the Project URL
   - `SUPABASE_SERVICE_KEY` — the **service_role** key
3. **Settings → Pages → Build and deployment → Source = GitHub Actions**.
4. **Actions → Deploy NBK League → Run workflow** (use *Run workflow*, not *Re-run*).
   - Green ✓ → open the Pages URL shown in the run. Share it.
   - If it goes red, open the **Recompute table** step and read the error.

---

## What happens automatically
- Every day at **06:00 UTC** the Action fetches results, refreshes the Supabase fixtures
  (kickoff times power the prediction lock), recomputes the table, and redeploys.
- Players open the page → **Predict** tab → pick their name, enter the PIN, type scores, **Save**.
  A prediction is rejected once that game has kicked off.
- The daily Action's Supabase access also keeps the free project from auto-pausing.

## Troubleshooting
- **"Predictions aren't connected"** on the page → `config.js` still has placeholder values.
- **Save says "Invalid PIN"** → the PIN doesn't match the one set in Part 2 step 3.
- **Save says "Predictions locked"** → that game has already kicked off (working as intended).
- **Action red on "Recompute table"** → check the three secrets exist and are spelled exactly.
- **No fixtures to predict** → the window dates in `competition.json`, or the Action hasn't run yet.
