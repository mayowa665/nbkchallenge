"""Pull Premier League fixtures involving the tracked teams, within the window.

Uses football-data.org (free tier covers the Premier League, competition code PL).
Each match object carries name/shortName/tla for both teams; we track teams by their
FIFA-style `tla` (MUN/ARS/BRE/TOT), which is the stable identifier the feed provides.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

PL_MATCHES_URL = "https://api.football-data.org/v4/competitions/PL/matches"
LIVE_STATUSES = {"IN_PLAY", "PAUSED", "LIVE", "SUSPENDED"}

# Preferred display names by FIFA tla (edit data/display_names.json to taste).
_NAMES_PATH = Path(__file__).resolve().parents[1] / "data" / "display_names.json"
try:
    DISPLAY_NAMES = json.loads(_NAMES_PATH.read_text(encoding="utf-8"))
except Exception:  # noqa: BLE001
    DISPLAY_NAMES = {}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_name(team: dict[str, Any]) -> str:
    # Prefer our colloquial override (Spurs, Wolves, Man Utd, ...) keyed by tla;
    # otherwise the feed's shortName, then full name.
    tla = (team.get("tla") or "").upper()
    if tla in DISPLAY_NAMES:
        return DISPLAY_NAMES[tla]
    return team.get("shortName") or team.get("name") or tla or "?"


def fetch_fixtures(
    tracked_tlas: list[str],
    window_start: str,
    window_end: str,
) -> list[dict[str, Any]]:
    """Return fixtures involving a tracked team with kickoff inside the window.

    Returns [] if no API key is configured, so the pipeline still runs locally.
    """
    token = os.getenv("FOOTBALL_DATA_API_KEY")
    if not token:
        return []

    response = requests.get(
        PL_MATCHES_URL,
        headers={"X-Auth-Token": token},
        timeout=30,
    )
    response.raise_for_status()

    tracked = {t.upper() for t in tracked_tlas}
    start = _parse_iso(window_start)
    end = _parse_iso(window_end)

    fixtures = []
    for match in response.json().get("matches", []):
        home = match.get("homeTeam") or {}
        away = match.get("awayTeam") or {}
        home_tla = (home.get("tla") or "").upper()
        away_tla = (away.get("tla") or "").upper()
        if home_tla not in tracked and away_tla not in tracked:
            continue

        utc_date = match.get("utcDate")
        if not utc_date:
            continue
        kickoff = _parse_iso(utc_date)
        if kickoff < start or kickoff > end:
            continue

        score = (match.get("score") or {}).get("fullTime") or {}
        fixtures.append(
            {
                "id": int(match["id"]),
                "matchday": match.get("matchday"),
                "home": _display_name(home),
                "away": _display_name(away),
                "home_tla": home_tla,
                "away_tla": away_tla,
                "kickoff_utc": utc_date,
                "status": match.get("status", "SCHEDULED"),
                "home_score": score.get("home"),
                "away_score": score.get("away"),
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
