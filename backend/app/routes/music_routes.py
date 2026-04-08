from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.listening_history import ListeningHistory
from ..models.song import Song

router = APIRouter(prefix="/songs", tags=["Songs"])


@router.get("/")
def get_songs(
    genre: str | None = None,
    limit: int = 1000,
    enrichment_status: str | None = None,
    db: Session = Depends(get_db)
):

    safe_limit = max(1, min(limit, 5000))

    last_listen_subq = (
        db.query(
            ListeningHistory.song_id.label("song_id"),
            func.max(ListeningHistory.played_at).label("last_listened_at"),
        )
        .group_by(ListeningHistory.song_id)
        .subquery()
    )

    query = (
        db.query(Song, last_listen_subq.c.last_listened_at)
        .options(joinedload(Song.artist))
        .outerjoin(last_listen_subq, last_listen_subq.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
    )

    if genre:
        query = query.filter(Song.genre == genre)

    if enrichment_status:
        query = query.filter(Song.enrichment_status == enrichment_status)

    rows = query.limit(safe_limit).all()

    return [
        {
            "id": s.id,
            "title": s.title,
            "artist": s.artist.name if s.artist else None,
            "spotify_id": s.spotify_id,
            "genre": s.genre,
            "listeners": s.listeners,
            "playcount": s.playcount,
            "popularity_score": s.popularity_score,
            "last_listened_at": last_listened_at.isoformat() if last_listened_at else None,
            "enrichment_status": s.enrichment_status,
            "enrichment_error": s.enrichment_error,
            "discovery_source": s.discovery_source,
            "discovery_confidence": s.discovery_confidence,
        }
        for s, last_listened_at in rows
    ]


