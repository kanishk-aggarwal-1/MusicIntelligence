import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.generated_playlist_track import GeneratedPlaylistTrack
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..models.song_tag import SongTag
from ..services.enrichment_service import enrich_song
from ..services.recommendation_service import _apply_enrichment
from ..services.spotify_service import load_request_user_session

router = APIRouter(prefix="/songs", tags=["Songs"])


QUICK_FILTERS = {
    "failed_enrichment",
    "partial_enrichment",
    "missing_tags",
    "missing_popularity",
    "high_popularity",
    "recently_played",
    "never_used_in_playlist",
    "hidden",
    "active",
    "duplicate_candidates",
}


def _canonical_title(title: str):
    t = (title or "").lower()
    t = re.sub(r"\([^\)]*\)", "", t)
    t = re.sub(r"\b(remaster(ed)?|live|version|mono|stereo|edit|deluxe)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


@router.get("/")
def get_songs(
    request: Request,
    genre: str | None = None,
    limit: int = 1000,
    enrichment_status: str | None = None,
    quick_filter: str | None = None,
    include_deleted: bool = False,
    recently_played_days: int = 30,
    db: Session = Depends(get_db),
):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    safe_limit = max(1, min(limit, 5000))
    safe_days = max(1, min(recently_played_days, 365))

    if quick_filter and quick_filter not in QUICK_FILTERS:
        raise HTTPException(status_code=400, detail=f"Unknown quick_filter '{quick_filter}'")

    last_listen_subq = (
        db.query(
            ListeningHistory.song_id.label("song_id"),
            func.max(ListeningHistory.played_at).label("last_listened_at"),
            func.count(ListeningHistory.id).label("listening_count"),
        )
        .filter(ListeningHistory.user_id == user_id)
        .group_by(ListeningHistory.song_id)
        .subquery()
    )

    playlist_use_subq = (
        db.query(
            GeneratedPlaylistTrack.song_id.label("song_id"),
            func.count(GeneratedPlaylistTrack.id).label("playlist_inclusion_count"),
        )
        .group_by(GeneratedPlaylistTrack.song_id)
        .subquery()
    )

    query = (
        db.query(Song, last_listen_subq.c.last_listened_at, last_listen_subq.c.listening_count, playlist_use_subq.c.playlist_inclusion_count)
        .options(joinedload(Song.artist), joinedload(Song.song_tags).joinedload(SongTag.tag))
        .join(last_listen_subq, last_listen_subq.c.song_id == Song.id)
        .outerjoin(playlist_use_subq, playlist_use_subq.c.song_id == Song.id)
    )

    if not include_deleted:
        query = query.filter(Song.is_deleted.is_(False))

    if genre:
        query = query.filter(Song.genre == genre)

    if enrichment_status:
        query = query.filter(Song.enrichment_status == enrichment_status)

    rows = query.all()

    duplicate_keys = set()
    if quick_filter == "duplicate_candidates":
        counts = {}
        for s, *_ in rows:
            key = f"{(s.artist.name if s.artist else '').lower().strip()}::{_canonical_title(s.title)}"
            counts[key] = counts.get(key, 0) + 1
        duplicate_keys = {key for key, count in counts.items() if count > 1}

    filtered = []
    for s, last_listened_at, listening_count, playlist_inclusion_count in rows:
        tag_count = len(s.song_tags or [])
        popularity_value = s.popularity_score or 0
        playlist_count = int(playlist_inclusion_count or 0)

        if quick_filter == "failed_enrichment" and s.enrichment_status != "failed":
            continue
        if quick_filter == "partial_enrichment" and s.enrichment_status != "partial":
            continue
        if quick_filter == "missing_tags" and tag_count > 0:
            continue
        if quick_filter == "missing_popularity" and ((s.listeners or 0) > 0 or (s.playcount or 0) > 0):
            continue
        if quick_filter == "high_popularity" and popularity_value < 3:
            continue
        if quick_filter == "never_used_in_playlist" and playlist_count > 0:
            continue
        if quick_filter == "hidden" and not s.is_deleted:
            continue
        if quick_filter == "active" and s.is_deleted:
            continue
        if quick_filter == "duplicate_candidates":
            key = f"{(s.artist.name if s.artist else '').lower().strip()}::{_canonical_title(s.title)}"
            if key not in duplicate_keys:
                continue

        if quick_filter == "recently_played":
            from ..time_utils import utcnow_naive
            if not last_listened_at or (utcnow_naive() - last_listened_at).days > safe_days:
                continue

        filtered.append(
            {
                "id": s.id,
                "title": s.title,
                "artist": s.artist.name if s.artist else None,
                "spotify_id": s.spotify_id,
                "image_url": s.image_url,
                "preview_url": s.preview_url,
                "genre": s.genre,
                "listeners": s.listeners,
                "playcount": s.playcount,
                "popularity_score": s.popularity_score,
                "last_listened_at": last_listened_at.isoformat() if last_listened_at else None,
                "listening_count": int(listening_count or 0),
                "playlist_inclusion_count": playlist_count,
                "tag_count": tag_count,
                "enrichment_status": s.enrichment_status,
                "enrichment_error": s.enrichment_error,
                "discovery_source": s.discovery_source,
                "discovery_confidence": s.discovery_confidence,
                "is_deleted": bool(s.is_deleted),
            }
        )

    filtered.sort(key=lambda row: (row["last_listened_at"] is None, row["last_listened_at"] or "", row["title"]), reverse=True)
    return filtered[:safe_limit]


@router.get("/{song_id}")
def get_song_detail(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    song = (
        db.query(Song)
        .options(joinedload(Song.artist), joinedload(Song.song_tags).joinedload(SongTag.tag))
        .filter(Song.id == song_id)
        .first()
    )
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    listening_count = (
        db.query(func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.song_id == song.id)
        .scalar()
    ) or 0
    last_played = (
        db.query(func.max(ListeningHistory.played_at))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.song_id == song.id)
        .scalar()
    )
    playlist_inclusion_count = (
        db.query(func.count(GeneratedPlaylistTrack.id))
        .filter(GeneratedPlaylistTrack.song_id == song.id)
        .scalar()
    ) or 0

    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist.name if song.artist else None,
        "spotify_id": song.spotify_id,
        "image_url": song.image_url,
        "preview_url": song.preview_url,
        "genre": song.genre,
        "listeners": song.listeners,
        "playcount": song.playcount,
        "popularity_score": song.popularity_score,
        "enrichment_status": song.enrichment_status,
        "enrichment_error": song.enrichment_error,
        "discovery_source": song.discovery_source,
        "discovery_confidence": song.discovery_confidence,
        "listening_count": int(listening_count),
        "playlist_inclusion_count": int(playlist_inclusion_count),
        "last_listened_at": last_played.isoformat() if last_played else None,
        "is_deleted": bool(song.is_deleted),
        "tags": [st.tag.name for st in song.song_tags if st.tag and st.tag.name],
    }


@router.post("/{song_id}/hide")
def hide_song(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="User not logged in")

    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    song.is_deleted = True
    db.add(song)
    db.commit()
    return {"message": "Song hidden", "song_id": song_id}


@router.post("/{song_id}/restore")
def restore_song(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="User not logged in")

    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    song.is_deleted = False
    db.add(song)
    db.commit()
    return {"message": "Song restored", "song_id": song_id}


@router.post("/{song_id}/retry-enrichment")
def retry_enrichment(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="User not logged in")

    song = (
        db.query(Song)
        .options(joinedload(Song.artist), joinedload(Song.song_tags).joinedload(SongTag.tag))
        .filter(Song.id == song_id)
        .first()
    )
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    data = enrich_song(song)
    changed = _apply_enrichment(db, song, data)
    db.add(song)
    db.commit()
    db.refresh(song)

    return {
        "message": "Song enrichment retried",
        "song_id": song.id,
        "changed": changed,
        "enrichment_status": song.enrichment_status,
        "enrichment_error": song.enrichment_error,
        "genre": song.genre,
        "listeners": song.listeners,
        "playcount": song.playcount,
        "tag_count": len(song.song_tags or []),
    }
