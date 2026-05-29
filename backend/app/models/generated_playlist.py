from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class GeneratedPlaylist(Base):
    __tablename__ = "generated_playlists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    spotify_playlist_id = Column(String, index=True)
    name = Column(String, nullable=False)
    context_type = Column(String, index=True)
    request_params_json = Column(Text)
    summary_json = Column(Text)
    algorithm_version = Column(String, nullable=False, default="v1")
    candidate_pool_size = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False, index=True)

    tracks = relationship("GeneratedPlaylistTrack", back_populates="generated_playlist", cascade="all, delete-orphan")
