"""Minimal Supabase REST (PostgREST) client for the GitHub Action.

Uses the service-role key (a GitHub secret), which bypasses Row Level Security, to
upsert fixtures and read every player's predictions. Plain `requests` — no SDK.

If SUPABASE_URL / SUPABASE_SERVICE_KEY are unset, fixtures upsert is a no-op and
predictions read returns [], so the pipeline still runs locally without Supabase.
"""

import os
from typing import Any

import requests


def _config() -> tuple[str, str] | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return url.rstrip("/"), key


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def upsert_fixtures(fixtures: list[dict[str, Any]]) -> None:
    """Write fixture id/teams/kickoff/score/status so the RPC can enforce the lock."""
    cfg = _config()
    if cfg is None or not fixtures:
        return
    url, key = cfg
    rows = [
        {
            "id": f["id"],
            "home": f["home"],
            "away": f["away"],
            "kickoff_utc": f["kickoff_utc"],
            "home_score": f.get("home_score"),
            "away_score": f.get("away_score"),
            "status": f.get("status", "SCHEDULED"),
        }
        for f in fixtures
    ]
    headers = _headers(key)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    response = requests.post(
        f"{url}/rest/v1/fixtures?on_conflict=id",
        headers=headers,
        json=rows,
        timeout=30,
    )
    response.raise_for_status()


def read_predictions() -> list[dict[str, Any]]:
    """All predictions (service role bypasses RLS). [] if Supabase isn't configured."""
    cfg = _config()
    if cfg is None:
        return []
    url, key = cfg
    response = requests.get(
        f"{url}/rest/v1/predictions",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"select": "player,fixture_id,home_pred,away_pred,updated_at"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
