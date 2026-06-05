"""Orchestrator: fetch fixtures + predictions, score them, write state.json.

  python scripts/build_state.py --out state.json
  python scripts/build_state.py --out /tmp/s.json --fixtures test/fixtures.json --predictions test/preds.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.fetch_results import fetch_fixtures, has_kicked_off, is_finished
from scripts.score import build_table, predictions_lookup
from scripts.supabase_client import read_predictions, upsert_fixtures

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="state.json")
    parser.add_argument("--fixtures", help="Local fixtures JSON (test/offline mode; skips Supabase upsert).")
    parser.add_argument("--predictions", help="Local predictions JSON (test/offline mode).")
    args = parser.parse_args()

    players = load_json(ROOT / "data" / "players.json")
    competition = load_json(ROOT / "data" / "competition.json")
    scoring = competition["scoring"]

    test_mode = bool(args.fixtures)
    if args.fixtures:
        fixtures = load_json(Path(args.fixtures))
    else:
        fixtures = fetch_fixtures(
            competition["tracked_team_ids"],
            competition["competitions"],
            competition["api_football_season"],
            competition["window_start"],
            competition["window_end"],
        )

    # Keep Supabase's fixture table (kickoffs/scores) current so the RPC lock works.
    if not test_mode:
        upsert_fixtures(fixtures)

    if args.predictions:
        predictions = load_json(Path(args.predictions))
    else:
        predictions = read_predictions()

    table = build_table(players, fixtures, predictions, scoring)
    state = {
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "season_label": competition.get("season_label", ""),
        "window_start": competition.get("window_start"),
        "window_end": competition.get("window_end"),
        "players": players,
        "scoring": scoring,
        "played": sum(1 for f in fixtures if is_finished(f)),
        "total": len(fixtures),
        "table": table,
        "fixtures": fixtures_view(fixtures, predictions, scoring),
        "recent_results": recent_results(fixtures),
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}: {state['played']}/{state['total']} played, {len(players)} players.")


def fixtures_view(
    fixtures: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    scoring: dict[str, int],
) -> list[dict[str, Any]]:
    """Public fixture list. Picks are exposed ONLY after kickoff (no pre-kickoff leak)."""
    from scripts.score import points_for

    preds = predictions_lookup(predictions)
    by_player = {}
    for (player, fid), pred in preds.items():
        by_player.setdefault(fid, []).append((player, pred))

    view = []
    for fixture in fixtures:
        kicked = has_kicked_off(fixture)
        finished = is_finished(fixture)
        picks = []
        if kicked:
            for player, (hp, ap) in sorted(by_player.get(fixture["id"], []), key=lambda x: x[0].lower()):
                pick = {"player": player, "home_pred": hp, "away_pred": ap}
                if finished:
                    pick["points"] = points_for(
                        (hp, ap), (int(fixture["home_score"]), int(fixture["away_score"])), scoring
                    )
                picks.append(pick)
        view.append(
            {
                "id": fixture["id"],
                "matchday": fixture.get("matchday"),
                "competition": fixture.get("competition"),
                "group_label": fixture.get("group_label"),
                "home": fixture["home"],
                "away": fixture["away"],
                "kickoff_utc": fixture["kickoff_utc"],
                "status": fixture.get("status", "SCHEDULED"),
                "home_score": fixture.get("home_score"),
                "away_score": fixture.get("away_score"),
                "kicked_off": kicked,
                "finished": finished,
                "picks": picks,
            }
        )
    return view


def recent_results(fixtures: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    finished = [f for f in fixtures if is_finished(f)]
    finished.sort(key=lambda f: f["kickoff_utc"], reverse=True)
    return [
        {
            "home": f["home"],
            "away": f["away"],
            "score": f"{f['home_score']}-{f['away_score']}",
            "date": f["kickoff_utc"][:10],
        }
        for f in finished[:limit]
    ]


if __name__ == "__main__":
    main()
