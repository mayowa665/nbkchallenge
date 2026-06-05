"""One-off diagnostic: does SUPABASE_SERVICE_KEY actually have write access?

Run locally (key stays in your shell, never in code):

  cd nbk-predictor
  $env:SUPABASE_URL="https://YOUR.supabase.co"
  $env:SUPABASE_SERVICE_KEY="sb_secret_...your secret key..."
  python scripts/check_supabase.py

It POSTs a throwaway test row two ways (apikey-only, and apikey+Authorization) and
prints the exact status + body for each, then cleans up. Uses only the stdlib.
"""

import json
import os
import urllib.error
import urllib.request

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
print(f"key starts with: {KEY[:14]!r}  (length {len(KEY)})")

BODY = json.dumps([{
    "id": 999999, "home": "DiagHome", "away": "DiagAway",
    "kickoff_utc": "2030-01-01T00:00:00Z", "status": "SCHEDULED",
}]).encode()
BASE = {"Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal"}


def attempt(label: str, headers: dict) -> None:
    req = urllib.request.Request(
        f"{URL}/rest/v1/fixtures?on_conflict=id", data=BODY, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            print(f"[{label}] {r.status} OK")
    except urllib.error.HTTPError as e:
        print(f"[{label}] {e.code} {e.read()[:400].decode(errors='replace')}")
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] ERROR {e}")


attempt("apikey-only", {"apikey": KEY, **BASE})
attempt("apikey+bearer", {"apikey": KEY, "Authorization": f"Bearer {KEY}", **BASE})

# best-effort cleanup of the test row
try:
    urllib.request.urlopen(urllib.request.Request(
        f"{URL}/rest/v1/fixtures?id=eq.999999",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, method="DELETE"))
except Exception:
    pass
