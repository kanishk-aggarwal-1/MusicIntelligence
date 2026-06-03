from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from ..database import Base


class PlaylistSchedule(Base):
    """A user's request to auto-regenerate a playlist on a cadence.

    Each run replays the existing generation pipeline with the stored params and
    records a fresh GeneratedPlaylist, so the user always has an up-to-date
    auto-built playlist waiting for them (and can one-click push it to Spotify).
    """

    __tablename__ = "playlist_schedules"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    context_type = Column(String, nullable=True)

    # Generation parameters (mirror PlaylistGeneratePayload).
    min_known_ratio = Column(Float, nullable=False, default=0.6)
    diversity = Column(Float, nullable=False, default=0.5)
    familiarity = Column(Float, nullable=False, default=0.5)
    max_tracks = Column(Integer, nullable=False, default=30)

    cadence = Column(String, nullable=False, default="weekly")  # 'daily' | 'weekly'
    active = Column(Boolean, nullable=False, default=True)

    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_generated_playlist_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)
