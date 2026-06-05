"""Pull the tracked teams' Premier League fixtures from football-data.org.

The free tier covers the Premier League (competition code PL). We track teams by
their `tla` (MUN/ARS/BRE/TOT). Cup games aren't on this feed (or any free one) —
they come from data/manual_fixtures.json, merged in build_state.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

PL_MATCHES_URL = "https://api.football-data.org/v4/competitions/PL/matches"

# Preferred display names by tla (edit data/display_names.json).
_NAMES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "display_names.json")
try:
    with open(_NAMES_PATH, "r", encoding="utf-8") as _fh:
        DISPLAY_NAMES = json.load(_fh)
except Exception:  # noqa: BLE001
    DISPLAY_NAMES = {}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_name(team: dict[str, Any]) -> str:
    tla = (team.get("tla") or "").upper()
    if tla in DISPLAY_NAMES:
        return DISPLAY_NAMES[tla]
    return team.get("shortName") or team.get("name") or tla or "?"


def fetch_fixtures(
    tracked_tlas: list[str],
    window_start: str,
    window_end: str,
) -> list[dict[str, Any]]:
    """PL fixtures involving a tracked team, inside the window. [] if no API key."""
    token = os.getenv("FOOTBALL_DATA_API_KEY")
    if not token:
        return []

    response = requests.get(PL_MATCHES_URL, headers={"X-Auth-Token": token}, timeout=30)
    response.raise_for_status()

    tracked = {t.upper() for t in tracked_tlas}
    start, end = _parse_iso(window_start), _parse_iso(window_end)

    fixtures = []
    for match in response.json().get("matches", []):
        home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
        home_tla = (home.get("tla") or "").upper()
        away_tla = (away.get("tla") or "").upper()
        if home_tla not in tracked and away_tla not in tracked:
            continue

        utc_date = match.get("utcDate")
        if not utc_date:
            continue
        kickoff = _parse_iso(utc_date)
        if not (start <= kickoff <= end):
            continue

        status = match.get("status", "SCHEDULED")
        full_time = (match.get("score") or {}).get("fullTime") or {}
        matchday = match.get("matchday")
        fixtures.append(
            {
                "id": int(match["id"]),
                "competition": "Premier League",
                "matchday": matchday,
                "group_label": f"Week {matchday}" if matchday else "Premier League",
                "home": _display_name(home),
                "away": _display_name(away),
                "kickoff_utc": utc_date,
                "status": status,
                "home_score": full_time.get("home") if status == "FINISHED" else None,
                "away_score": full_time.get("away") if status == "FINISHED" else None,
            }
        )

    fixtures.sort(key=lambda f: f["kickoff_utc"])
    return fixtures


def is_finished(fixture: dict[str, Any]) -> bool:
    return (
        fixture.get("status") == "FINISHED"
        and fixture.get("home_score") is not None
        and fixture.get("away_score") is not None
    )


def has_kicked_off(fixture: dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    try:
        return now >= _parse_iso(fixture["kickoff_utc"])
    except (KeyError, ValueError):
        return False
