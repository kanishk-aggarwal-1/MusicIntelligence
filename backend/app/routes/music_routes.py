import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, nullslast
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..authz import require_capability
from ..models.generated_playlist_track import GeneratedPlaylistTrack
from ..models.generated_playlist import GeneratedPlaylist
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.user_song_pref import UserSongPref
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


def _top_tag_name(song: Song):
    tags = [st for st in (song.song_tags or []) if st.tag and st.tag.name]
    if not tags:
        return None
    tags.sort(key=lambda st: (float(st.weight or 0), st.tag.name.lower()), reverse=True)
    return tags[0].tag.name


VALID_SORTS = {"recent", "plays", "popularity", "alpha"}


def _sort_col(sort: str, last_listen_subq):
    if sort == "plays":
        return last_listen_subq.c.listening_count.desc()
    if sort == "popularity":
        return nullslast(Song.popularity_score.desc())
    if sort == "alpha":
        return Song.title.asc()
    return last_listen_subq.c.last_listened_at.desc()   # "recent" default


@router.get("/")
def get_songs(
    request: Request,
    q: str | None = None,
    sort: str = "recent",
    genre: str | None = None,
    limit: int = 500,
    offset: int = 0,
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

    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
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
        .join(GeneratedPlaylist, GeneratedPlaylist.id == GeneratedPlaylistTrack.generated_playlist_id)
        .filter(GeneratedPlaylist.user_id == user_id)
        .group_by(GeneratedPlaylistTrack.song_id)
        .subquery()
    )

    query = (
        db.query(Song, last_listen_subq.c.last_listened_at, last_listen_subq.c.listening_count, playlist_use_subq.c.playlist_inclusion_count)
        .options(joinedload(Song.artist), joinedload(Song.song_tags).joinedload(SongTag.tag))
        .join(last_listen_subq, last_listen_subq.c.song_id == Song.id)
        .outerjoin(playlist_use_subq, playlist_use_subq.c.song_id == Song.id)
    )

    # Fetch the set of song IDs this user has hidden (per-user, not global).
    _hidden_ids_rows = (
        db.query(UserSongPref.song_id)
        .filter(UserSongPref.user_id == user_id, UserSongPref.is_hidden.is_(True))
        .all()
    )
    hidden_song_ids = {r[0] for r in _hidden_ids_rows}

    # For the SQL-paginated path, exclude hidden songs at the DB level.
    if not include_deleted and not quick_filter and not q:
        if hidden_song_ids:
            query = query.filter(Song.id.notin_(hidden_song_ids))

    if genre:
        query = query.filter(Song.genre == genre)

    if enrichment_status:
        query = query.filter(Song.enrichment_status == enrichment_status)

    safe_sort = sort if sort in VALID_SORTS else "recent"

    # Push ORDER BY + LIMIT into SQL only for the simple case.
    # When quick_filter or q is set we need Python-side filtering first.
    if not quick_filter and not q:
        query = query.order_by(
            _sort_col(safe_sort, last_listen_subq),
            Song.title,
        ).limit(safe_limit).offset(safe_offset)

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
        top_tag = _top_tag_name(s)
        popularity_value = s.popularity_score or 0
        playlist_count = int(playlist_inclusion_count or 0)

        if q:
            q_lower = q.lower()
            artist_name = (s.artist.name if s.artist else "").lower()
            if q_lower not in (s.title or "").lower() and q_lower not in artist_name:
                continue

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
        is_hidden_for_user = s.id in hidden_song_ids
        # Also exclude hidden songs in the Python-filtered path (quick_filter / q).
        if not include_deleted and (quick_filter not in ("hidden", None) or q):
            if is_hidden_for_user and quick_filter != "hidden":
                continue

        if quick_filter == "hidden" and not is_hidden_for_user:
            continue
        if quick_filter == "active" and is_hidden_for_user:
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
                "top_tag": top_tag,
                "enrichment_status": s.enrichment_status,
                "enrichment_error": s.enrichment_error,
                "discovery_source": s.discovery_source,
                "discovery_confidence": s.discovery_confidence,
                "is_deleted": s.id in hidden_song_ids,
            }
        )

    if quick_filter or q:
        # Python-filtered results: sort and paginate here
        if safe_sort == "plays":
            filtered.sort(key=lambda r: (-(r["listening_count"] or 0), r["title"]))
        elif safe_sort == "popularity":
            filtered.sort(key=lambda r: (-(r["popularity_score"] or 0), r["title"]))
        elif safe_sort == "alpha":
            filtered.sort(key=lambda r: (r["title"] or "").lower())
        else:
            filtered.sort(key=lambda r: (r["last_listened_at"] is None, r["last_listened_at"] or "", r["title"]), reverse=True)
        return filtered[safe_offset:safe_offset + safe_limit]

    # Common path: SQL already applied ORDER BY + LIMIT + OFFSET
    return filtered


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
        .join(GeneratedPlaylist, GeneratedPlaylist.id == GeneratedPlaylistTrack.generated_playlist_id)
        .filter(
            GeneratedPlaylistTrack.song_id == song.id,
            GeneratedPlaylist.user_id == user_id,
        )
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
        "top_tag": _top_tag_name(song),
    }


@router.post("/{song_id}/hide")
def hide_song(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    require_capability(user_id, "mutate_library")

    if not db.query(Song).filter(Song.id == song_id).first():
        raise HTTPException(status_code=404, detail="Song not found")

    pref = db.query(UserSongPref).filter_by(user_id=user_id, song_id=song_id).first()
    if pref:
        pref.is_hidden = True
    else:
        db.add(UserSongPref(user_id=user_id, song_id=song_id, is_hidden=True))
    db.commit()
    return {"message": "Song hidden", "song_id": song_id}


@router.post("/{song_id}/restore")
def restore_song(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    require_capability(user_id, "mutate_library")

    if not db.query(Song).filter(Song.id == song_id).first():
        raise HTTPException(status_code=404, detail="Song not found")

    pref = db.query(UserSongPref).filter_by(user_id=user_id, song_id=song_id).first()
    if pref:
        pref.is_hidden = False
        db.commit()
    return {"message": "Song restored", "song_id": song_id}


@router.post("/{song_id}/retry-enrichment")
def retry_enrichment(song_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    require_capability(user_id, "enrich_metadata")

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
