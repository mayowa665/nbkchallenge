"""Diagnostic: confirm the API-Football key + team/league ids are right.

Run locally (key stays in your shell, never in code):

  cd nbk-predictor
  $env:API_FOOTBALL_KEY="...your api-sports.io key..."
  python scripts/check_apifootball.py

Prints, for each tracked team id, the team name the API returns and a couple of its
upcoming/recent fixtures across the configured competitions. If a team id is wrong you'll
see the wrong club (or an error) here, before it ever hits the live site.
"""

import json
import os
from pathlib import Path

import requests

KEY = os.environ["API_FOOTBALL_KEY"]
cfg = json.loads((Path(__file__).resolve().parents[1] / "data" / "competition.json").read_text("utf-8"))
season = cfg["api_football_season"]
comps = {int(k): v for k, v in cfg["competitions"].items()}
print(f"season {season} · competitions {comps}\n")

for tid in cfg["tracked_team_ids"]:
    r = requests.get(
        "https://v3.football.api-sports.io/fixtures",
        headers={"x-apisports-key": KEY},
        params={"team": tid, "season": season},
        timeout=30,
    )
    data = r.json()
    if data.get("errors"):
        print(f"team {tid}: ERROR {data['errors']}")
        continue
    rows = data.get("response", [])
    name = rows[0]["teams"]["home"]["name"] if rows and rows[0]["teams"]["home"]["id"] == tid \
        else (rows[0]["teams"]["away"]["name"] if rows else "?")
    in_comps = [x for x in rows if (x.get("league") or {}).get("id") in comps]
    print(f"team {tid}: {name}  ·  {len(rows)} fixtures, {len(in_comps)} in tracked comps")
    for x in in_comps[:3]:
        lg = x["league"]
        t = x["teams"]
        print(f"    [{comps.get(lg['id'])}] {lg.get('round')}: {t['home']['name']} v {t['away']['name']}  ({x['fixture']['date'][:10]})")
