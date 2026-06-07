"""Pull the tracked teams' fixtures from football-data.org.

Competition code is read from data/competition.json (e.g. "WC" for the World Cup,
"PL" for the Premier League). Teams are tracked by their `tla`. Knockout rounds get
a stage label; group games get "Matchday N". Cup/extra games (or score corrections)
can still be layered in via data/manual_fixtures.json (merged in build_state).
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

# Preferred display names by tla (edit data/display_names.json). Most football-data
# names are already clean, so this only overrides the awkward ones.
_NAMES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "display_names.json")
try:
    with open(_NAMES_PATH, "r", encoding="utf-8") as _fh:
        DISPLAY_NAMES = json.load(_fh)
except Exception:  # noqa: BLE001
    DISPLAY_NAMES = {}

_STAGE_LABELS = {
    "LAST_32": "Round of 32",
    "LAST_16": "Round of 16",
    "QUARTER_FINALS": "Quarter-finals",
    "QUARTER_FINAL": "Quarter-finals",
    "SEMI_FINALS": "Semi-finals",
    "SEMI_FINAL": "Semi-finals",
    "THIRD_PLACE": "Third place",
    "FINAL": "Final",
}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_name(team: dict[str, Any]) -> str:
    tla = (team.get("tla") or "").upper()
    if tla in DISPLAY_NAMES:
        return DISPLAY_NAMES[tla]
    return team.get("shortName") or team.get("name") or tla or "?"


def _group_label(stage: Any, matchday: Any) -> str:
    s = str(stage or "").upper()
    if s in _STAGE_LABELS:
        return _STAGE_LABELS[s]
    if matchday:
        return f"Matchday {matchday}"
    return s.replace("_", " ").title() if s else "Fixtures"


def fetch_fixtures(
    competition_code: str,
    competition_label: str,
    tracked_tlas: list[str],
    window_start: str,
    window_end: str,
) -> list[dict[str, Any]]:
    """Fixtures involving a tracked team, inside the window. [] if no API key."""
    token = os.getenv("FOOTBALL_DATA_API_KEY")
    if not token:
        return []

    response = requests.get(
        f"https://api.football-data.org/v4/competitions/{competition_code}/matches",
        headers={"X-Auth-Token": token},
        timeout=30,
    )
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
        if not home.get("name") or not away.get("name"):
            continue  # knockout slot not assigned yet (TBD)

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
                "competition": competition_label,
                "matchday": matchday,
                "group_label": _group_label(match.get("stage"), matchday),
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
