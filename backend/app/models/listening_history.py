from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class ListeningHistory(Base):

    __tablename__ = "listening_history"
    __table_args__ = (
        UniqueConstraint("user_id", "song_id", "played_at", name="uq_listening_history_user_song_played_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"))
    played_at = Column(DateTime, default=utcnow_naive)
    ms_played = Column(Integer, nullable=True)
    skipped = Column(Boolean, nullable=True)
    platform = Column(String, nullable=True)
    country = Column(String, nullable=True)
    offline = Column(Boolean, nullable=True)
    incognito = Column(Boolean, nullable=True)

    song = relationship("Song", back_populates="listening_history")
