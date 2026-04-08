from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from ..database import Base


class ListeningHistory(Base):

    __tablename__ = "listening_history"
    __table_args__ = (
        UniqueConstraint("user_id", "song_id", "played_at", name="uq_listening_history_user_song_played_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, index=True)

    song_id = Column(Integer, ForeignKey("songs.id"))

    played_at = Column(DateTime, default=datetime.utcnow)

    song = relationship("Song", back_populates="listening_history")
