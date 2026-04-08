from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Song(Base):

    __tablename__ = "songs"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)

    artist_id = Column(Integer, ForeignKey("artists.id"))

    spotify_id = Column(String, unique=True, index=True)

    genre = Column(String)


    listeners = Column(Integer, default=0)

    playcount = Column(Integer, default=0)

    popularity_score = Column(Float)

    enrichment_status = Column(String, default="pending", index=True)
    enrichment_error = Column(String)
    discovery_source = Column(String)
    discovery_confidence = Column(Float)

    is_deleted = Column(Boolean, default=False, index=True)

    artist = relationship("Artist", back_populates="songs")

    song_tags = relationship("SongTag", back_populates="song")

    listening_history = relationship("ListeningHistory", back_populates="song")
