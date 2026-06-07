"""Build state.json from the parsed WhatsApp scorecards and public Supabase fixtures.

This is for backfilling the historical NBK scorecards: Supabase already has the
Premier League fixture IDs/scores, while data/whatsapp_scorecards_review.md has
the NBK week grouping and predictions.
Cup fixtures are loaded from data/manual_fixtures.json.

  python scripts/build_scorecard_state.py --out state.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import requests

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.build_state import fixtures_view, recent_results
from scripts.fetch_results import _parse_iso, is_finished
from scripts.score import build_table

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCORECARDS = ROOT / "data" / "whatsapp_scorecards_review.md"
MANUAL_FIXTURES = ROOT / "data" / "manual_fixtures.json"

TEAM_ALIASES = {
    "Tottenham": "Spurs",
    "Man United": "Man Utd",
    "United": "Man Utd",
    "City": "Man City",
    "Palace": "Crystal Palace",
}


def normalize_team(value: str) -> str:
    team = re.sub(r"\s+", " ", value.strip())
    return TEAM_ALIASES.get(team, team)


def split_fixture(value: str) -> tuple[str, str]:
    if " v " not in value:
        raise ValueError(f"Fixture is not in 'Home v Away' format: {value}")
    home, away = value.split(" v ", 1)
    return normalize_team(home), normalize_team(away)


def parse_score(value: str) -> tuple[int, int] | None:
    value = value.strip()
    if value.upper() == "X-X":
        return None
    match = re.fullmatch(r"(\d+)-(\d+)", value)
    if not match:
        raise ValueError(f"Invalid score value: {value}")
    return int(match.group(1)), int(match.group(2))


def parse_scorecards(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    week: int | None = None
    columns: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        week_match = re.fullmatch(r"## Week (\d+)", line)
        if week_match:
            week = int(week_match.group(1))
            columns = []
            continue

        if line.startswith("| Fixture |"):
            columns = [cell.strip() for cell in line.strip("|").split("|")]
            continue

        if not line.startswith("|") or line.startswith("| ---") or not columns or week is None:
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(columns):
            continue

        row = dict(zip(columns, cells))
        if not {"Fixture", "Player", "Prediction"}.issubset(row):
            continue

        home, away = split_fixture(row["Fixture"])
        source_result = row.get("Result shown in source")
        entries.append(
            {
                "week": week,
                "fixture": row["Fixture"],
                "home": home,
                "away": away,
                "player": row["Player"],
                "prediction": parse_score(row["Prediction"]),
                "source_result": parse_score(source_result) if source_result else None,
            }
        )

    return entries


def config_value(name: str, fallback_name: str | None = None) -> str | None:
    env_value = os.getenv(name)
    if env_value:
        return env_value
    if fallback_name:
        env_value = os.getenv(fallback_name)
        if env_value:
            return env_value

    config_path = ROOT / "config.js"
    if not config_path.exists():
        return None
    config = config_path.read_text(encoding="utf-8")
    match = re.search(rf"{name}\s*:\s*['\"]([^'\"]+)['\"]", config)
    return match.group(1) if match else None


def read_public_fixtures(url: str, anon_key: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{url.rstrip('/')}/rest/v1/fixtures",
        headers={"apikey": anon_key},
        params={
            "select": "id,home,away,kickoff_utc,status,home_score,away_score",
            "order": "kickoff_utc.asc",
        },
        timeout=30,
    )
    response.raise_for_status()
    return [
        {
            "competition": "Premier League",
            "matchday": None,
            "group_label": None,
            **fixture,
        }
        for fixture in response.json()
    ]


def read_manual_fixtures(path: Path = MANUAL_FIXTURES) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", []) if isinstance(data, dict) else data
    return [
        {
            "competition": fixture.get("competition", "Manual"),
            "matchday": fixture.get("matchday"),
            "group_label": fixture.get("group_label"),
            **fixture,
        }
        for fixture in fixtures
    ]


def source_result_fixtures(
    entries: list[dict[str, Any]],
    existing_fixtures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = {
        (
            fixture["home"],
            fixture["away"],
            fixture.get("home_score"),
            fixture.get("away_score"),
        )
        for fixture in existing_fixtures
    }
    source_groups = sorted(
        {
            (entry["week"], entry["home"], entry["away"], entry["source_result"])
            for entry in entries
            if entry["source_result"] is not None
        }
    )

    fallback = []
    per_week_index: dict[int, int] = defaultdict(int)
    first_week_date = datetime(2025, 12, 13, 12, 0, tzinfo=timezone.utc)
    for week, home, away, source_result in source_groups:
        home_score, away_score = source_result
        if (home, away, home_score, away_score) in existing:
            continue

        per_week_index[week] += 1
        kickoff = first_week_date + timedelta(days=(week - 1) * 7, hours=per_week_index[week] - 1)
        fallback.append(
            {
                "id": 9100000 + (week * 100) + per_week_index[week],
                "competition": "Scorecard Result",
                "matchday": None,
                "group_label": f"Week {week}",
                "home": home,
                "away": away,
                "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                "status": "FINISHED",
                "home_score": home_score,
                "away_score": away_score,
            }
        )
    return fallback


def fixture_group_key(entry: dict[str, Any]) -> tuple[int, str, str, tuple[int, int] | None]:
    return entry["week"], entry["home"], entry["away"], entry["source_result"]


def fixture_timestamp(fixture: dict[str, Any]) -> float:
    return _parse_iso(fixture["kickoff_utc"]).timestamp()


def match_scorecard_fixtures(
    entries: list[dict[str, Any]],
    all_fixtures: list[dict[str, Any]],
) -> tuple[dict[int, tuple[int, list[dict[str, Any]]]], list[dict[str, Any]]]:
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fixture in all_fixtures:
        by_pair[(fixture["home"], fixture["away"])].append(fixture)

    source_groups: dict[tuple[int, str, str, tuple[int, int] | None], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        source_groups[fixture_group_key(entry)].append(entry)

    skipped: list[dict[str, Any]] = []
    candidates_by_source: dict[tuple[int, str, str, tuple[int, int] | None], list[dict[str, Any]]] = {}

    for key, rows in source_groups.items():
        week, home, away, source_result = key
        candidates = by_pair.get((home, away), [])
        if source_result is not None:
            candidates = [
                fixture
                for fixture in candidates
                if (fixture.get("home_score"), fixture.get("away_score")) == source_result
            ]

        if candidates:
            candidates_by_source[key] = candidates
        else:
            skipped.append({"week": week, "fixture": f"{home} v {away}", "reason": "not in fixture DB"})

    week_times: dict[int, list[float]] = defaultdict(list)
    for key, candidates in candidates_by_source.items():
        if len(candidates) == 1:
            week_times[key[0]].append(fixture_timestamp(candidates[0]))
    week_anchor = {week: median(values) for week, values in week_times.items()}

    initial_matches: dict[tuple[int, str, str, tuple[int, int] | None], dict[str, Any]] = {}
    for key, candidates in candidates_by_source.items():
        if len(candidates) == 1:
            initial_matches[key] = candidates[0]
            continue

        week, home, away, _source_result = key
        if week not in week_anchor:
            skipped.append({"week": week, "fixture": f"{home} v {away}", "reason": "ambiguous fixture match"})
            continue

        initial_matches[key] = min(
            candidates,
            key=lambda fixture: (
                abs(fixture_timestamp(fixture) - week_anchor[week]),
                0 if fixture.get("competition") != "Premier League" else 1,
                int(fixture["id"]),
            ),
        )

    candidates_by_fixture: dict[int, list[tuple[tuple[int, str, str, tuple[int, int] | None], dict[str, Any]]]] = defaultdict(list)
    for key, fixture in initial_matches.items():
        candidates_by_fixture[int(fixture["id"])].append((key, fixture))

    selected: dict[int, tuple[int, list[dict[str, Any]]]] = {}
    for fixture_id, candidates in candidates_by_fixture.items():
        if len(candidates) == 1:
            key, fixture = candidates[0]
        else:
            key, fixture = min(
                candidates,
                key=lambda item: (
                    abs(fixture_timestamp(item[1]) - week_anchor.get(item[0][0], fixture_timestamp(item[1]))),
                    0 if item[0][3] is not None else 1,
                    item[0][0],
                ),
            )
            for rejected_key, _rejected_fixture in candidates:
                if rejected_key != key:
                    skipped.append(
                        {
                            "week": rejected_key[0],
                            "fixture": f"{rejected_key[1]} v {rejected_key[2]}",
                            "reason": f"duplicate source for PL fixture {fixture_id}",
                        }
                    )

        selected[fixture_id] = (key[0], source_groups[key])

    return selected, skipped


def build_predictions(
    selected: dict[int, tuple[int, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    predictions = []
    for fixture_id, (_week, rows) in selected.items():
        for row in rows:
            if row["prediction"] is None:
                continue
            home_pred, away_pred = row["prediction"]
            predictions.append(
                {
                    "player": row["player"],
                    "fixture_id": fixture_id,
                    "home_pred": home_pred,
                    "away_pred": away_pred,
                    "updated_at": "2026-06-05T00:00:00Z",
                }
            )
    return sorted(predictions, key=lambda item: (item["fixture_id"], item["player"].lower()))


def build_fixtures(
    all_fixtures: list[dict[str, Any]],
    selected: dict[int, tuple[int, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    fixtures = []
    for fixture in all_fixtures:
        fixture_id = int(fixture["id"])
        if fixture_id not in selected:
            continue
        week, _rows = selected[fixture_id]
        fixtures.append(
            {
                "id": fixture_id,
                "competition": fixture.get("competition", "Premier League"),
                "matchday": None,
                "group_label": f"Week {week}",
                "home": fixture["home"],
                "away": fixture["away"],
                "kickoff_utc": fixture["kickoff_utc"],
                "status": fixture.get("status", "SCHEDULED"),
                "home_score": fixture.get("home_score"),
                "away_score": fixture.get("away_score"),
            }
        )
    return sorted(fixtures, key=lambda item: item["kickoff_utc"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="state.json")
    parser.add_argument("--scorecards", default=str(DEFAULT_SCORECARDS))
    parser.add_argument("--supabase-url", default=config_value("SUPABASE_URL"))
    parser.add_argument("--supabase-anon-key", default=config_value("SUPABASE_ANON_KEY", "SUPABASE_KEY"))
    args = parser.parse_args()

    if not args.supabase_url or not args.supabase_anon_key:
        raise SystemExit("Supabase URL/anon key not found in env or config.js")

    players = json.loads((ROOT / "data" / "players.json").read_text(encoding="utf-8"))
    competition = json.loads((ROOT / "data" / "competition.json").read_text(encoding="utf-8"))
    scoring = competition["scoring"]

    scorecard_entries = parse_scorecards(Path(args.scorecards))
    all_fixtures = read_public_fixtures(args.supabase_url, args.supabase_anon_key)
    all_fixtures.extend(read_manual_fixtures())
    all_fixtures.extend(source_result_fixtures(scorecard_entries, all_fixtures))
    selected, skipped = match_scorecard_fixtures(scorecard_entries, all_fixtures)
    fixtures = build_fixtures(all_fixtures, selected)
    predictions = build_predictions(selected)

    table = build_table(players, fixtures, predictions, scoring)
    state = {
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "season_label": competition.get("season_label", ""),
        "window_start": competition.get("window_start"),
        "window_end": competition.get("window_end"),
        "players": players,
        "scoring": scoring,
        "played": sum(1 for fixture in fixtures if is_finished(fixture)),
        "total": len(fixtures),
        "table": table,
        "fixtures": fixtures_view(fixtures, predictions, scoring),
        "recent_results": recent_results(fixtures),
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}: {state['played']}/{state['total']} matched fixtures scored.")
    print(f"Parsed predictions: {len(predictions)}")
    if skipped:
        print(f"Skipped source fixture groups: {len(skipped)}")
        for item in skipped:
            print(f"  Week {item['week']}: {item['fixture']} ({item['reason']})")


if __name__ == "__main__":
    main()