from datetime import timedelta

from sqlalchemy.orm import Session

from ..models.playlist_schedule import PlaylistSchedule
from ..time_utils import utcnow_naive


VALID_CADENCES = {"daily", "weekly"}
_CADENCE_DELTA = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}
MAX_SCHEDULES_PER_USER = 10


def cadence_delta(cadence: str) -> timedelta:
    return _CADENCE_DELTA.get(cadence, _CADENCE_DELTA["weekly"])


def compute_next_run(cadence: str, *, now=None):
    now = now or utcnow_naive()
    return now + cadence_delta(cadence)


def serialize_schedule(schedule: PlaylistSchedule) -> dict:
    return {
        "id": schedule.id,
        "name": schedule.name,
        "context_type": schedule.context_type,
        "min_known_ratio": schedule.min_known_ratio,
        "diversity": schedule.diversity,
        "familiarity": schedule.familiarity,
        "max_tracks": schedule.max_tracks,
        "cadence": schedule.cadence,
        "active": bool(schedule.active),
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "last_generated_playlist_id": schedule.last_generated_playlist_id,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
    }


def count_schedules(db: Session, *, user_id: str) -> int:
    return db.query(PlaylistSchedule).filter(PlaylistSchedule.user_id == user_id).count()


def create_schedule(
    db: Session,
    *,
    user_id: str,
    cadence: str,
    name: str | None = None,
    context_type: str | None = None,
    min_known_ratio: float = 0.6,
    diversity: float = 0.5,
    familiarity: float = 0.5,
    max_tracks: int = 30,
) -> PlaylistSchedule:
    now = utcnow_naive()
    schedule = PlaylistSchedule(
        user_id=user_id,
        name=(name or None),
        context_type=(context_type or None),
        min_known_ratio=float(min_known_ratio),
        diversity=float(diversity),
        familiarity=float(familiarity),
        max_tracks=max(1, min(int(max_tracks), 100)),
        cadence=cadence if cadence in VALID_CADENCES else "weekly",
        active=True,
        # Run on the next processing tick so the user sees it work right away.
        next_run_at=now,
        created_at=now,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def list_schedules(db: Session, *, user_id: str) -> list[PlaylistSchedule]:
    return (
        db.query(PlaylistSchedule)
        .filter(PlaylistSchedule.user_id == user_id)
        .order_by(PlaylistSchedule.created_at.desc())
        .all()
    )


def get_schedule(db: Session, *, schedule_id: int, user_id: str) -> PlaylistSchedule | None:
    return (
        db.query(PlaylistSchedule)
        .filter(PlaylistSchedule.id == schedule_id, PlaylistSchedule.user_id == user_id)
        .first()
    )


def delete_schedule(db: Session, *, schedule_id: int, user_id: str) -> bool:
    deleted = (
        db.query(PlaylistSchedule)
        .filter(PlaylistSchedule.id == schedule_id, PlaylistSchedule.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return bool(deleted)


def due_schedules(db: Session, *, user_id: str, now=None, limit: int = 5) -> list[PlaylistSchedule]:
    now = now or utcnow_naive()
    return (
        db.query(PlaylistSchedule)
        .filter(
            PlaylistSchedule.user_id == user_id,
            PlaylistSchedule.active.is_(True),
            PlaylistSchedule.next_run_at.isnot(None),
            PlaylistSchedule.next_run_at <= now,
        )
        .order_by(PlaylistSchedule.next_run_at.asc())
        .limit(max(1, limit))
        .all()
    )


def mark_ran(db: Session, *, schedule: PlaylistSchedule, generated_playlist_id: int | None, now=None):
    now = now or utcnow_naive()
    schedule.last_run_at = now
    schedule.next_run_at = compute_next_run(schedule.cadence, now=now)
    if generated_playlist_id is not None:
        schedule.last_generated_playlist_id = generated_playlist_id
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule
