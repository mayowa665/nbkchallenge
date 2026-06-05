"""Pull the tracked teams' fixtures from API-Football (api-sports.io).

Free plan covers every competition, so a single key gives us the Premier League,
FA Cup and Carabao Cup (EFL Cup). We fetch per tracked team (one call each), keep
the configured competitions, and tag each game with a scorecard group label.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import requests

API_BASE = "https://v3.football.api-sports.io"
FINISHED_STATUSES = {"FT", "AET", "PEN"}
LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "INT", "SUSP"}

# Preferred display names. API-Football already uses short forms for most clubs;
# this just overrides the few we want different (edit data/display_names.json).
_NAMES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "display_names.json")
try:
    with open(_NAMES_PATH, "r", encoding="utf-8") as _fh:
        _RAW_NAMES = json.load(_fh)
except Exception:  # noqa: BLE001
    _RAW_NAMES = {}


def _norm(name: str) -> str:
    text = re.sub(r"\b(fc|afc)\b", " ", str(name).lower())
    return re.sub(r"[^a-z0-9]+", "", text)


_NAMES = {_norm(k): v for k, v in _RAW_NAMES.items()}


def _display_name(name: str) -> str:
    return _NAMES.get(_norm(name), name)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_utc_iso(value: str) -> str:
    return _parse_iso(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request(path: str, params: dict, key: str) -> dict:
    response = requests.get(
        f"{API_BASE}{path}", headers={"x-apisports-key": key}, params=params, timeout=30
    )
    response.raise_for_status()
    data = response.json()
    errors = data.get("errors")
    if errors:  # API-Football reports auth/quota problems here, often with HTTP 200
        raise RuntimeError(f"API-Football error: {errors}")
    return data


def fetch_fixtures(
    tracked_team_ids: list[int],
    competitions: dict[str, str],
    season: int,
    window_start: str,
    window_end: str,
) -> list[dict[str, Any]]:
    """Fixtures for the tracked teams in the configured comps, inside the window.

    Returns [] if no API key is set, so the pipeline still runs offline.
    """
    key = os.getenv("API_FOOTBALL_KEY")
    if not key:
        return []

    comp_labels = {int(cid): label for cid, label in competitions.items()}
    start, end = _parse_iso(window_start), _parse_iso(window_end)

    by_id: dict[int, dict[str, Any]] = {}
    for team_id in tracked_team_ids:
        data = _request("/fixtures", {"team": team_id, "season": season}, key)
        rows = data.get("response", [])
        if not rows:
            raise RuntimeError(
                f"API-Football returned no fixtures for team id {team_id} "
                f"(check tracked_team_ids / api_football_season / the API key)."
            )
        for item in rows:
            league_id = (item.get("league") or {}).get("id")
            if league_id not in comp_labels:
                continue
            fixture = _to_fixture(item, comp_labels[league_id], league_id)
            if fixture is None:
                continue
            kickoff = _parse_iso(fixture["kickoff_utc"])
            if start <= kickoff <= end:
                by_id[fixture["id"]] = fixture

    fixtures = sorted(by_id.values(), key=lambda f: f["kickoff_utc"])
    return fixtures


def _to_fixture(item: dict, competition: str, league_id: int) -> Optional[dict[str, Any]]:
    fixture = item.get("fixture") or {}
    teams = item.get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    date = fixture.get("date")
    if not date or not home.get("name") or not away.get("name"):
        return None

    status_short = (fixture.get("status") or {}).get("short", "NS")
    if status_short in FINISHED_STATUSES:
        status = "FINISHED"
    elif status_short in LIVE_STATUSES:
        status = "IN_PLAY"
    else:
        status = "SCHEDULED"

    # Score players predict = the 90-minute full-time score (ignore extra time / pens).
    full_time = (item.get("score") or {}).get("fulltime") or {}
    goals = item.get("goals") or {}
    home_score = full_time.get("home") if full_time.get("home") is not None else goals.get("home")
    away_score = full_time.get("away") if full_time.get("away") is not None else goals.get("away")
    if status != "FINISHED":
        home_score = away_score = None

    matchday, group_label = _round_info(league_id, competition, (item.get("league") or {}).get("round", ""))

    return {
        "id": int(fixture["id"]),
        "competition": competition,
        "matchday": matchday,
        "group_label": group_label,
        "home": _display_name(home["name"]),
        "away": _display_name(away["name"]),
        "kickoff_utc": _to_utc_iso(date),
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
    }


def _round_info(league_id: int, competition: str, round_str: str) -> tuple[Optional[int], str]:
    """Premier League -> ('Week N'); cups -> ('{Competition} · {Round}')."""
    if league_id == 39:
        match = re.search(r"(\d+)", round_str or "")
        if match:
            md = int(match.group(1))
            return md, f"Week {md}"
        return None, competition
    tidy = (round_str or "").strip() or "Cup tie"
    return None, f"{competition} · {tidy}"


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
