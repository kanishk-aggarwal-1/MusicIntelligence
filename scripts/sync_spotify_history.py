import os

import spotipy

from backend.app.services.spotify_service import fetch_recent_tracks


def main():
    token = os.getenv("SPOTIFY_ACCESS_TOKEN")

    if not token:
        raise SystemExit("Set SPOTIFY_ACCESS_TOKEN before running this script.")

    sp = spotipy.Spotify(auth=token)
    history = fetch_recent_tracks(sp)

    for item in history:
        print(f"{item['played_at']} | {item['artist']} - {item['title']}")


if __name__ == "__main__":
    main()
