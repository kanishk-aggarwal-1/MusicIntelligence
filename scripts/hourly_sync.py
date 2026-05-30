"""Render cron job script — triggers hourly listening-history sync for all users.

Render runs this as a one-shot cron job every hour. It calls the backend's
/ops/sync-all endpoint, which handles token refresh, Spotify fetch, and
Last.fm enrichment for every user with an active session.

Required env vars (set in render.yaml for the cron service):
  API_URL     — base URL of the backend, e.g. https://musicintelligence-api.onrender.com
  CRON_SECRET — shared secret matching CRON_SECRET on the web service
"""
import os
import sys

import requests

API_URL = os.environ.get("API_URL", "https://musicintelligence-api.onrender.com").rstrip("/")
CRON_SECRET = os.environ.get("CRON_SECRET", "")


def main():
    if not CRON_SECRET:
        print("ERROR: CRON_SECRET env var is not set", file=sys.stderr)
        sys.exit(1)

    url = f"{API_URL}/ops/sync-all"
    print(f"POST {url}")

    try:
        resp = requests.post(
            url,
            headers={"X-Cron-Secret": CRON_SECRET},
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        print(
            f"total={data.get('total_users')} "
            f"synced={data.get('synced')} "
            f"skipped={data.get('skipped')} "
            f"failed={data.get('failed')}"
        )
        sys.exit(0)
    except requests.HTTPError as exc:
        print(f"ERROR: HTTP {exc.response.status_code} — {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
