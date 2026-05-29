import json
import random
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.artist import Artist
from ..models.job import Job
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..services.discovery_service import discover_songs_from_artist
from ..services.recommendation_service import store_discovered_songs
from ..time_utils import utcnow


def _seed_artists(db: Session, user_id: str, seed_limit: int):
    rows = (
        db.query(Artist.name, func.count(ListeningHistory.id).label("plays"))
        .join(Song, Song.artist_id == Artist.id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False), Artist.name.is_not(None))
        .group_by(Artist.name)
        .all()
    )
    weighted = [(name, int(plays or 0)) for name, plays in rows if name]
    if not weighted:
        return []

    limit = max(1, min(seed_limit, len(weighted)))
    rng = random.Random(utcnow().strftime("%Y%m%d%H"))
    pool = weighted[:]
    selected = []
    while pool and len(selected) < limit:
        total_weight = sum(max(1, weight) for _, weight in pool)
        pick = rng.uniform(0, total_weight)
        upto = 0.0
        chosen_index = 0
        for idx, (_, weight) in enumerate(pool):
            upto += max(1, weight)
            if upto >= pick:
                chosen_index = idx
                break
        selected.append(pool.pop(chosen_index)[0])
    return selected


def build_discovery_preview(db: Session, user_id: str, *, seed_limit: int = 8, max_candidates: int = 80):
    seeds = _seed_artists(db, user_id, seed_limit)
    candidates: list[dict[str, Any]] = []
    seen = set()

    for artist_name in seeds:
        try:
            discovered = discover_songs_from_artist(artist_name)
        except Exception:
            continue
        for item in discovered:
            key = ((item.get("title") or "").lower().strip(), (item.get("artist") or "").lower().strip())
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "candidate_id": len(candidates) + 1,
                    "seed_artist": artist_name,
                    "title": item.get("title"),
                    "artist": item.get("artist"),
                    "discovery_source": item.get("discovery_source") or "lastfm_top_tracks",
                    "discovery_confidence": item.get("discovery_confidence") or 0.7,
                }
            )
            if len(candidates) >= max_candidates:
                break
        if len(candidates) >= max_candidates:
            break

    return {
        "seed_artists": seeds,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def accept_discovery_candidates(db: Session, job: Job, *, user_id: str, candidate_ids: list[int] | None = None):
    payload = json.loads(job.result_json or "{}")
    candidates = payload.get("candidates") or []
    if candidate_ids:
        wanted = {int(item) for item in candidate_ids}
        selected = [item for item in candidates if int(item.get("candidate_id") or 0) in wanted]
    else:
        selected = candidates

    if not selected:
        return {"accepted": 0, "message": "No discovery candidates selected"}

    store_summary = store_discovered_songs(db, selected, user_id=user_id, limit=len(selected))
    return {
        "accepted": len(selected),
        "store_summary": store_summary,
        "message": "Discovery candidates accepted into library",
    }
