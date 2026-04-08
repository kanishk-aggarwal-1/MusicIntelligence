import json
import re
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.artist import Artist
from ..models.dedup_merge_log import DedupMergeLog
from ..models.listening_goal import ListeningGoal
from ..models.listening_history import ListeningHistory
from ..models.recommendation_feedback import RecommendationFeedback
from ..models.song import Song
from ..models.song_tag import SongTag
from ..services.recommendation_service import build_discovery_feed
from ..services.spotify_service import load_request_user_session

router = APIRouter(prefix="/insights", tags=["Insights"])


class FeedbackPayload(BaseModel):
    song_id: int
    action: str  # like, dislike, skip


class GoalPayload(BaseModel):
    goal_type: str
    target_value: int
    period: str = "weekly"


def _canonical_title(title: str):
    t = (title or "").lower()
    t = re.sub(r"\([^\)]*\)", "", t)
    t = re.sub(r"\b(remaster(ed)?|live|version|mono|stereo|edit|deluxe)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _duplicate_groups(db: Session, user_id: str):
    rows = (
        db.query(Song.id, Song.title, Song.spotify_id, Song.genre, Artist.name, Song.artist_id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .join(Artist, Artist.id == Song.artist_id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .distinct()
        .all()
    )

    groups = {}

    for song_id, title, spotify_id, genre, artist_name, artist_id in rows:
        key = f"{(artist_name or '').lower().strip()}::{_canonical_title(title or '')}"
        groups.setdefault(key, []).append(
            {
                "song_id": song_id,
                "title": title,
                "artist": artist_name,
                "artist_id": artist_id,
                "spotify_id": spotify_id,
                "genre": genre,
            }
        )

    duplicates = [
        {"group_key": k, "songs": sorted(v, key=lambda x: x["song_id"]), "count": len(v)}
        for k, v in groups.items()
        if len(v) > 1
    ]

    duplicates.sort(key=lambda x: x["count"], reverse=True)
    return duplicates


def _require_user_id(db: Session, request: Request):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    return user_id


@router.get("/taste-timeline")
def taste_timeline(request: Request, months: int = 6, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    safe_months = max(1, min(months, 24))

    artist_rows = (
        db.query(
            func.date_trunc("month", ListeningHistory.played_at).label("month"),
            Artist.name,
            func.count(ListeningHistory.id).label("plays"),
        )
        .join(Song, Song.id == ListeningHistory.song_id)
        .join(Artist, Artist.id == Song.artist_id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .group_by(func.date_trunc("month", ListeningHistory.played_at), Artist.name)
        .order_by(func.date_trunc("month", ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc())
        .limit(safe_months * 5)
        .all()
    )

    genre_rows = (
        db.query(
            func.date_trunc("month", ListeningHistory.played_at).label("month"),
            Song.genre,
            func.count(ListeningHistory.id).label("plays"),
        )
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id, Song.genre.is_not(None), Song.is_deleted.is_(False))
        .group_by(func.date_trunc("month", ListeningHistory.played_at), Song.genre)
        .order_by(func.date_trunc("month", ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc())
        .limit(safe_months * 5)
        .all()
    )

    monthly_top_artists = [
        {"month": str(m), "artist": a, "plays": int(p)}
        for m, a, p in artist_rows
    ]

    monthly_top_genres = [
        {"month": str(m), "genre": g, "plays": int(p)}
        for m, g, p in genre_rows
    ]

    return {
        "monthly_top_artists": monthly_top_artists,
        "monthly_top_genres": monthly_top_genres,
    }


@router.get("/discovery-feed")
def discovery_feed(request: Request, limit: int = 20, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    safe_limit = max(1, min(limit, 100))
    feed = build_discovery_feed(db, user_id, limit=safe_limit)
    return {"items": feed}


@router.post("/feedback")
def add_feedback(payload: FeedbackPayload, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    action = payload.action.lower().strip()
    if action not in {"like", "dislike", "skip"}:
        raise HTTPException(status_code=400, detail="action must be one of like/dislike/skip")

    db.add(RecommendationFeedback(user_id=user_id, song_id=payload.song_id, action=action))
    db.commit()

    return {"message": "Feedback saved", "song_id": payload.song_id, "action": action}


@router.get("/feedback-summary")
def feedback_summary(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    rows = (
        db.query(RecommendationFeedback.action, func.count(RecommendationFeedback.id))
        .filter(RecommendationFeedback.user_id == user_id)
        .group_by(RecommendationFeedback.action)
        .all()
    )

    return {"summary": [{"action": a, "count": int(c)} for a, c in rows]}


@router.post("/goals")
def create_goal(payload: GoalPayload, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    goal = ListeningGoal(
        user_id=user_id,
        goal_type=payload.goal_type,
        target_value=payload.target_value,
        period=payload.period,
        active=True,
    )
    db.add(goal)
    db.commit()

    return {"message": "Goal created", "goal_id": goal.id}


@router.get("/goals-status")
def goals_status(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    goals = (
        db.query(ListeningGoal)
        .filter(ListeningGoal.user_id == user_id, ListeningGoal.active.is_(True))
        .all()
    )

    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())

    total_events = (
        db.query(func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= week_start)
        .scalar()
    ) or 0

    distinct_songs = (
        db.query(func.count(func.distinct(ListeningHistory.song_id)))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= week_start)
        .scalar()
    ) or 0

    active_days = (
        db.query(func.count(func.distinct(func.date(ListeningHistory.played_at))))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= week_start)
        .scalar()
    ) or 0

    repeat_rate = ((total_events - distinct_songs) / total_events) if total_events > 0 else 0

    statuses = []

    for goal in goals:
        progress = 0

        if goal.goal_type == "new_songs_per_week":
            progress = distinct_songs
        elif goal.goal_type == "listening_days_per_week":
            progress = active_days
        elif goal.goal_type == "repeat_rate_max":
            progress = round(repeat_rate * 100)

        statuses.append(
            {
                "goal_id": goal.id,
                "goal_type": goal.goal_type,
                "target": goal.target_value,
                "progress": progress,
                "period": goal.period,
                "status": "on_track" if progress >= goal.target_value and goal.goal_type != "repeat_rate_max" else "check",
            }
        )

    return {"goals": statuses}


@router.get("/data-quality")
def data_quality(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )

    base_songs = db.query(Song.id).join(user_song_ids, user_song_ids.c.song_id == Song.id).filter(Song.is_deleted.is_(False))
    total_songs = base_songs.count()

    with_genre = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.genre.is_not(None), Song.is_deleted.is_(False))
        .scalar()
    ) or 0
    with_spotify = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.spotify_id.is_not(None), Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    with_tags = (
        db.query(func.count(func.distinct(SongTag.song_id)))
        .join(Song, Song.id == SongTag.song_id)
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    with_history = (
        db.query(func.count(func.distinct(ListeningHistory.song_id)))
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    status_rows = (
        db.query(Song.enrichment_status, func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .group_by(Song.enrichment_status)
        .all()
    )

    def pct(value):
        return round((value / total_songs) * 100, 2) if total_songs else 0

    return {
        "total_songs": total_songs,
        "coverage": [
            {"metric": "Songs with Genre", "count": with_genre, "percent": pct(with_genre)},
            {"metric": "Songs with Spotify ID", "count": with_spotify, "percent": pct(with_spotify)},
            {"metric": "Songs with Tags", "count": with_tags, "percent": pct(with_tags)},
            {"metric": "Songs with Listen History", "count": with_history, "percent": pct(with_history)},
        ],
        "enrichment_status": [
            {"status": s or "unknown", "count": int(c)}
            for s, c in status_rows
        ],
    }


@router.get("/dedup-preview")
def dedup_preview(request: Request, limit_groups: int = 50, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    duplicates = _duplicate_groups(db, user_id)
    return {"duplicate_groups": duplicates[: max(1, min(limit_groups, 200))]}


@router.post("/dedup-apply")
def dedup_apply(request: Request, limit_groups: int = 20, dry_run: bool = False, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    duplicates = _duplicate_groups(db, user_id)[: max(1, min(limit_groups, 200))]

    if dry_run:
        return {
            "message": "Dry run complete",
            "groups": len(duplicates),
            "potential_merges": sum(max(0, g["count"] - 1) for g in duplicates),
            "duplicate_groups": duplicates,
        }

    batch_id = str(uuid.uuid4())
    merged = 0

    for group in duplicates:
        songs = group["songs"]
        keep_id = songs[0]["song_id"]

        for duplicate in songs[1:]:
            dup_id = duplicate["song_id"]

            history_row_ids = [
                row[0]
                for row in db.query(ListeningHistory.id).filter(ListeningHistory.song_id == dup_id).all()
            ]
            tag_rows = db.query(SongTag.tag_id, SongTag.weight, SongTag.popularity, SongTag.spotify_id).filter(SongTag.song_id == dup_id).all()

            snapshot = {
                "history_row_ids": history_row_ids,
                "tag_rows": [
                    {
                        "tag_id": int(tid),
                        "weight": weight,
                        "popularity": popularity,
                        "spotify_id": sid,
                    }
                    for tid, weight, popularity, sid in tag_rows
                ],
            }

            db.query(ListeningHistory).filter(ListeningHistory.song_id == dup_id).update(
                {ListeningHistory.song_id: keep_id},
                synchronize_session=False,
            )

            keep_tag_ids = {
                row[0]
                for row in db.query(SongTag.tag_id).filter(SongTag.song_id == keep_id).all()
            }

            for tag_id, weight, popularity, spotify_id in tag_rows:
                if tag_id not in keep_tag_ids:
                    db.add(
                        SongTag(
                            song_id=keep_id,
                            tag_id=tag_id,
                            weight=weight,
                            popularity=popularity,
                            spotify_id=spotify_id,
                        )
                    )

            db.query(SongTag).filter(SongTag.song_id == dup_id).delete(synchronize_session=False)

            db.add(
                DedupMergeLog(
                    user_id=user_id,
                    batch_id=batch_id,
                    kept_song_id=keep_id,
                    removed_song_id=dup_id,
                    original_title=duplicate.get("title"),
                    original_artist=duplicate.get("artist"),
                    snapshot_json=json.dumps(snapshot),
                )
            )

            db.query(Song).filter(Song.id == dup_id).update(
                {Song.is_deleted: True},
                synchronize_session=False,
            )
            merged += 1

    db.commit()

    return {"message": "Deduplication complete", "merged_songs": merged, "batch_id": batch_id}


@router.post("/dedup-undo/{batch_id}")
def dedup_undo(batch_id: str, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    rows = db.query(DedupMergeLog).filter(DedupMergeLog.user_id == user_id, DedupMergeLog.batch_id == batch_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Batch not found")

    undone = 0

    for row in rows:
        db.query(Song).filter(Song.id == row.removed_song_id).update(
            {Song.is_deleted: False},
            synchronize_session=False,
        )

        snapshot = {}
        try:
            snapshot = json.loads(row.snapshot_json or "{}")
        except Exception:
            snapshot = {}

        history_ids = snapshot.get("history_row_ids", [])
        if history_ids:
            db.query(ListeningHistory).filter(ListeningHistory.id.in_(history_ids)).update(
                {ListeningHistory.song_id: row.removed_song_id},
                synchronize_session=False,
            )

        for tag_item in snapshot.get("tag_rows", []):
            exists = db.query(SongTag).filter(
                SongTag.song_id == row.removed_song_id,
                SongTag.tag_id == tag_item.get("tag_id"),
            ).first()
            if exists:
                continue
            db.add(
                SongTag(
                    song_id=row.removed_song_id,
                    tag_id=tag_item.get("tag_id"),
                    weight=tag_item.get("weight"),
                    popularity=tag_item.get("popularity"),
                    spotify_id=tag_item.get("spotify_id"),
                )
            )

        undone += 1

    db.commit()

    return {"message": "Undo complete", "batch_id": batch_id, "restored": undone}


