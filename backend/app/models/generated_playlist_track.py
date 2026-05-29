from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class GeneratedPlaylistTrack(Base):
    __tablename__ = "generated_playlist_tracks"

    id = Column(Integer, primary_key=True, index=True)
    generated_playlist_id = Column(Integer, ForeignKey("generated_playlists.id"), nullable=False, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    final_score = Column(Float, nullable=False, default=0)
    score_breakdown_json = Column(Text)
    explanation_json = Column(Text)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    generated_playlist = relationship("GeneratedPlaylist", back_populates="tracks")
    song = relationship("Song")
