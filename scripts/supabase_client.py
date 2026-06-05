"""Minimal Supabase REST (PostgREST) client for the GitHub Action.

Uses the service key (a GitHub secret), which bypasses Row Level Security, to upsert
fixtures and read every player's predictions. Plain `requests` — no SDK.

Header note: the new-style keys (`sb_secret_…` / `sb_publishable_…`) must be sent in
the `apikey` header ONLY — if they're also placed in `Authorization: Bearer`, the
platform tries to parse them as a JWT and rejects the request (403). The legacy
`eyJ…` JWT keys, on the other hand, DO need the Bearer header to convey the role.

If SUPABASE_URL / SUPABASE_SERVICE_KEY are unset, fixtures upsert is a no-op and the
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


def _auth_headers(key: str) -> dict[str, str]:
    headers = {"apikey": key}
    # Only legacy JWT keys go in the Authorization header. New sb_* keys must not.
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


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
    headers = _auth_headers(key)
    headers["Content-Type"] = "application/json"
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    response = requests.post(
        f"{url}/rest/v1/fixtures?on_conflict=id",
        headers=headers,
        json=rows,
        timeout=30,
    )
    response.raise_for_status()


def read_predictions() -> list[dict[str, Any]]:
    """All predictions (service key bypasses RLS). [] if Supabase isn't configured."""
    cfg = _config()
    if cfg is None:
        return []
    url, key = cfg
    response = requests.get(
        f"{url}/rest/v1/predictions",
        headers=_auth_headers(key),
        params={"select": "player,fixture_id,home_pred,away_pred,updated_at"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
