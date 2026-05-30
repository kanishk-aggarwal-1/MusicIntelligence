from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class Artist(Base):

    __tablename__ = "artists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    spotify_id = Column(String, unique=True, nullable=True, index=True)
    genres = Column(Text, nullable=True)  # JSON-encoded list of Spotify genre strings

    songs = relationship("Song", back_populates="artist")
