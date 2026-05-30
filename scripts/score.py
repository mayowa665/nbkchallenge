"""Scoring and league-table construction. Pure arithmetic — no simulation.

3 pts for an exact score, 1 pt for the correct result (W/D/L), 0 otherwise; a missing
prediction scores 0. NBK = the player(s) on the fewest points (all tied share it).
"""

from typing import Any

from .fetch_results import _parse_iso, is_finished


def _result(home: int, away: int) -> str:
    if home > away:
        return "H"
    if away > home:
        return "A"
    return "D"


def points_for(pred: tuple[int, int], actual: tuple[int, int], scoring: dict[str, int]) -> int:
    if pred == actual:
        return scoring["exact"]
    if _result(*pred) == _result(*actual):
        return scoring["result"]
    return scoring["miss"]


def predictions_lookup(predictions: list[dict[str, Any]]) -> dict[tuple[str, int], tuple[int, int]]:
    """(player, fixture_id) -> (home_pred, away_pred)."""
    return {
        (p["player"], int(p["fixture_id"])): (int(p["home_pred"]), int(p["away_pred"]))
        for p in predictions
    }


def build_table(
    players: list[str],
    fixtures: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    scoring: dict[str, int],
) -> list[dict[str, Any]]:
    preds = predictions_lookup(predictions)
    finished = [f for f in fixtures if is_finished(f)]

    rows = []
    for player in players:
        points = exact = results = predicted = 0
        for fixture in finished:
            pred = preds.get((player, fixture["id"]))
            if pred is None:
                continue  # no prediction -> 0 points, not counted as predicted
            predicted += 1
            gained = points_for(
                pred, (int(fixture["home_score"]), int(fixture["away_score"])), scoring
            )
            points += gained
            if gained == scoring["exact"]:
                exact += 1
            elif gained == scoring["result"]:
                results += 1
        rows.append(
            {
                "player": player,
                "played": len(finished),
                "predicted": predicted,
                "exact": exact,
                "results": results,
                "points": points,
                "nbk": False,
                "gap_to_safety": 0,
            }
        )

    rows.sort(key=lambda r: (-r["points"], -r["exact"], -r["results"], r["player"].lower()))
    _tag_nbk(rows, played=len(finished))
    return rows


def _tag_nbk(rows: list[dict[str, Any]], played: int) -> None:
    """Flag every player on the minimum points as NBK (once any game is played)."""
    if not rows or played == 0:
        return
    lowest = min(r["points"] for r in rows)
    safe_above = [r["points"] for r in rows if r["points"] > lowest]
    next_up = min(safe_above) if safe_above else lowest
    for row in rows:
        if row["points"] == lowest:
            row["nbk"] = True
            row["gap_to_safety"] = max(0, (next_up - lowest) if safe_above else 0)
