# Deployment — step by step

Three free services, ~20 minutes, then it runs itself: **Supabase** (stores predictions),
**GitHub** (hosts the page + runs the daily update), **football-data.org** (Premier League results).
FA Cup / Carabao Cup games are added by hand (no free feed covers them) — see the bottom section.

---

## Part 1 — Edit the two data files first
1. `data/players.json` — replace the placeholders with your 4 players' names.
2. `data/competition.json` — check `window_start` / `window_end` (default 11 Dec 2025 → 2 May 2026)
   and `tracked_tlas` (`MUN`, `ARS`, `BRE`, `TOT`). Adjust the season window if needed.

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

## Part 4 — football-data.org key
Get a free key at **https://www.football-data.org/client/register** (the free tier includes the
Premier League). Copy the token from your account / the confirmation email.

---

## Part 5 — GitHub
1. Create a new **public** repo and push this folder to `main`.
2. **Settings → Secrets and variables → Actions → New repository secret**, add three:
   - `FOOTBALL_DATA_API_KEY` — your football-data token
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

## Adding cup games (FA Cup / Carabao Cup)
No free feed has the English cups, so they're added by hand in `data/manual_fixtures.json`
(instructions are inside the file). The flow:
1. **A few days before** a cup tie, add it with `"status": "SCHEDULED"` and `null` scores — this
   lets players predict it (and locks at kickoff like any game).
2. **After** it's played, set `"status": "FINISHED"` and fill `home_score` / `away_score`.
3. Commit + push (or just send the details to whoever maintains the repo). The next daily run —
   or a manual **Run workflow** — picks it up.

The same file can **correct a wrong Premier League score**: add an entry whose `id` is that game's
id and it overrides the feed.

## Troubleshooting
- **"Predictions aren't connected"** on the page → `config.js` still has placeholder values.
- **Save says "Invalid PIN"** → the PIN doesn't match the one set in Part 2 step 3.
- **Save says "Predictions locked"** → that game has already kicked off (working as intended).
- **Action red on "Recompute table"** → check the three secrets exist and are spelled exactly
  (`FOOTBALL_DATA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`).
- **No fixtures to predict** → the window dates in `competition.json`, or the Action hasn't run yet.
