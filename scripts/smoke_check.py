"""Small production smoke check for the deployed backend.

This intentionally avoids authenticated endpoints. Use it after Render deploys
to confirm the public backend is reachable before testing Spotify login in the
browser.
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urljoin

import requests


def _get_json(base_url: str, path: str):
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return url, response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check the MusicIntelligence backend")
    parser.add_argument("--api", required=True, help="Backend base URL, e.g. https://musicintelligence-api.onrender.com")
    args = parser.parse_args()

    checks = [
        ("health", "/ops/health"),
        ("metrics", "/ops/metrics"),
    ]

    for label, path in checks:
        try:
            url, payload = _get_json(args.api, path)
        except Exception as exc:
            print(f"FAIL {label}: {exc}", file=sys.stderr)
            return 1
        print(f"OK {label}: {url} -> {payload}")

    print("Smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
