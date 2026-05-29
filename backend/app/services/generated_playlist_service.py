import json
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session, joinedload

from ..models.generated_playlist import GeneratedPlaylist
from ..models.generated_playlist_track import GeneratedPlaylistTrack
from ..time_utils import utcnow_naive

ALGORITHM_VERSION = "heuristic-v2"


def _loads(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _playlist_level_summary(items: list[dict[str, Any]], context_type: str | None = None):
    if not items:
        return {
            "familiar_ratio": 0,
            "discovery_ratio": 0,
            "artist_count": 0,
            "dominant_tags": [],
            "dominant_genres": [],
            "context_fit": context_type,
            "diversity_summary": "No tracks selected.",
        }

    familiar = sum(1 for item in items if item["components"].get("familiarity_score", 0) >= 0.5)
    artist_names = [item["song"].artist.name for item in items if item["song"].artist]
    genres = [item["song"].genre for item in items if item["song"].genre]
    tags = []
    for item in items:
        tags.extend(item.get("tag_names", []))

    tag_counts = Counter(tags)
    genre_counts = Counter(genres)
    unique_artists = len(set(artist_names))

    return {
        "familiar_ratio": round(familiar / max(1, len(items)), 3),
        "discovery_ratio": round(1 - (familiar / max(1, len(items))), 3),
        "artist_count": unique_artists,
        "dominant_tags": [name for name, _ in tag_counts.most_common(5)],
        "dominant_genres": [name for name, _ in genre_counts.most_common(5)],
        "context_fit": context_type,
        "diversity_summary": f"{unique_artists} unique artists across {len(items)} tracks.",
    }


def create_playlist_preview_record(
    db: Session,
    *,
    user_id: str,
    name: str,
    context_type: str | None,
    request_params: dict[str, Any],
    candidate_pool_size: int,
    items: list[dict[str, Any]],
    algorithm_version: str = ALGORITHM_VERSION,
):
    summary = _playlist_level_summary(items, context_type=context_type)
    record = GeneratedPlaylist(
        user_id=user_id,
        name=name,
        context_type=context_type,
        request_params_json=json.dumps(request_params),
        summary_json=json.dumps(summary),
        algorithm_version=algorithm_version,
        candidate_pool_size=max(0, int(candidate_pool_size or 0)),
        created_at=utcnow_naive(),
    )
    db.add(record)
    db.flush()

    for position, item in enumerate(items, start=1):
        explanation = {
            "reasons": item.get("reasons", []),
            "artist": item["song"].artist.name if item["song"].artist else None,
            "known_spotify": bool(item["song"].spotify_id),
            "context_type": context_type,
        }
        db.add(
            GeneratedPlaylistTrack(
                generated_playlist_id=record.id,
                song_id=item["song"].id,
                position=position,
                final_score=float(item.get("score") or 0),
                score_breakdown_json=json.dumps(item.get("components") or {}),
                explanation_json=json.dumps(explanation),
                created_at=utcnow_naive(),
            )
        )

    db.commit()
    db.refresh(record)
    return record


def get_generated_playlist(db: Session, *, generated_playlist_id: int, user_id: str) -> GeneratedPlaylist | None:
    return (
        db.query(GeneratedPlaylist)
        .options(joinedload(GeneratedPlaylist.tracks).joinedload(GeneratedPlaylistTrack.song))
        .filter(GeneratedPlaylist.id == generated_playlist_id, GeneratedPlaylist.user_id == user_id)
        .first()
    )


def list_generated_playlists(db: Session, *, user_id: str, limit: int = 50):
    safe_limit = max(1, min(limit, 100))
    return (
        db.query(GeneratedPlaylist)
        .filter(GeneratedPlaylist.user_id == user_id)
        .order_by(GeneratedPlaylist.created_at.desc())
        .limit(safe_limit)
        .all()
    )


def serialize_generated_playlist(record: GeneratedPlaylist, include_tracks: bool = True):
    payload = {
        "id": record.id,
        "user_id": record.user_id,
        "spotify_playlist_id": record.spotify_playlist_id,
        "name": record.name,
        "context_type": record.context_type,
        "request_params": _loads(record.request_params_json) or {},
        "summary": _loads(record.summary_json) or {},
        "algorithm_version": record.algorithm_version,
        "candidate_pool_size": record.candidate_pool_size,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
    if include_tracks:
        payload["tracks"] = [
            {
                "id": track.id,
                "song_id": track.song_id,
                "position": track.position,
                "final_score": round(float(track.final_score or 0), 4),
                "score_breakdown": _loads(track.score_breakdown_json) or {},
                "explanation": _loads(track.explanation_json) or {},
                "song": {
                    "title": track.song.title if track.song else None,
                    "spotify_id": track.song.spotify_id if track.song else None,
                    "genre": track.song.genre if track.song else None,
                    "artist": track.song.artist.name if track.song and track.song.artist else None,
                    "enrichment_status": track.song.enrichment_status if track.song else None,
                },
            }
            for track in sorted(record.tracks, key=lambda item: item.position)
        ]
    return payload


def mark_generated_playlist_created(db: Session, *, record: GeneratedPlaylist, spotify_playlist_id: str | None):
    record.spotify_playlist_id = spotify_playlist_id
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
