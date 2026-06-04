"""Live-metrics demo: exercise the REAL instrumented code paths (sync, enrichment,
playlist generation + resolution, cache hits/misses) against a throwaway SQLite DB,
then read GET /stats after each step and prove the counters persist across a restart.

Run:
    DATABASE_URL=sqlite:///./_demo_metrics.db PYTHONPATH=.:backend python scripts/demo_live_metrics.py

Only external network (Spotify search / Last.fm HTTP) is faked — every counter is
incremented by the same production code that runs on live traffic.
"""
import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_demo_metrics.db")
os.environ.setdefault("CRON_SECRET", "demo")

from fastapi.testclient import TestClient  # noqa: E402

import backend.app.main as main  # noqa: E402  (triggers create_all)
from backend.app.database import SessionLocal  # noqa: E402
from backend.app.models.artist import Artist  # noqa: E402
from backend.app.models.song import Song  # noqa: E402
from backend.app.models.user_session import UserSession  # noqa: E402
from backend.app.services import lastfm_service, recommendation_service  # noqa: E402
from backend.app.services.generated_playlist_service import create_playlist_preview_record  # noqa: E402
from backend.app.routes.playlist_routes import _resolve_playlist_track_ids  # noqa: E402

client = TestClient(main.app)


def show(step):
    stats = client.get("/stats").json()
    print(f"\n=== {step} ===")
    print(json.dumps(stats, indent=2))


class FakeSpotify:
    """Minimal stand-in: every .search returns one matching track with a unique id."""
    def __init__(self):
        self._n = 0

    def search(self, q=None, type=None, limit=None):
        self._n += 1
        return {"tracks": {"items": [{"id": f"spfake{self._n}", "artists": [{"name": "Demo Artist"}]}]}}


def main_demo():
    show("0) Baseline (fresh deploy)")

    db = SessionLocal()
    db.add(UserSession(user_id="demo-user", token="demo-token", token_info_json="{}"))
    db.commit()

    # 1) SYNC — real sync_listening_history with fake recent plays.
    tracks = [
        {"title": f"Track {i}", "artist": "Demo Artist", "spotify_id": None,
         "played_at": f"2026-06-0{(i % 9) + 1}T10:00:00Z"}
        for i in range(8)
    ]
    recommendation_service.sync_listening_history(db, "demo-user", tracks, enrich_inline=False)
    show("1) After sync (tracks.synced should rise)")

    # 2) CACHE + EXTERNAL — drive lastfm_request directly; repeats become cache hits.
    fake_payload = {"toptags": {"tag": [{"name": "indie", "count": 100}]}}

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_payload

    lastfm_service.time.sleep = lambda *_: None  # skip the rate-limit nap in the demo
    lastfm_service.requests.get = lambda *a, **k: FakeResp()

    for artist in ["Radiohead", "Aphex Twin", "Boards of Canada"]:
        lastfm_service.get_artist_tags(artist)        # MISS -> external Last.fm call
    for artist in ["Radiohead", "Aphex Twin"]:
        lastfm_service.get_artist_tags(artist)        # HIT -> call saved
    show("2) After Last.fm lookups (hits/misses/calls + saved %)")

    # 3) ENRICH — real _apply_enrichment marks tracks complete.
    enrich_payload = {
        "status": "complete", "genre": "electronic",
        "tags": ["indie", "ambient"],
        "listeners": 1000, "playcount": 5000, "_errors": [],
    }
    songs = db.query(Song).all()
    for song in songs:
        recommendation_service._apply_enrichment(db, song, dict(enrich_payload))
    db.commit()
    show("3) After enrichment (tracks.enriched should rise)")

    # 4) PLAYLIST — generate a record, then resolve its URIs via the real resolver.
    items = [{
        "song": s, "score": 0.9 - i * 0.05,
        "components": {"tfidf_similarity": 0.8, "familiarity_score": 0.6},
        "reasons": ["matches your indie taste"], "tag_names": ["indie"],
    } for i, s in enumerate(songs[:6])]
    record = create_playlist_preview_record(
        db, user_id="demo-user", name="Demo Mix", context_type=None,
        request_params={"max_tracks": 6}, candidate_pool_size=len(songs), items=items,
    )
    _resolve_playlist_track_ids(db, FakeSpotify(), record, "demo-user")
    show("4) After playlist generation + resolution (generated + resolution rate)")

    db.close()

    # 5) RESTART — dispose the engine and reconnect to the same DB file.
    main.engine.dispose()
    print("\n=== 5) Simulated restart — counters re-read from Postgres/SQLite ===")
    print(json.dumps(client.get("/stats").json(), indent=2))


if __name__ == "__main__":
    main_demo()
