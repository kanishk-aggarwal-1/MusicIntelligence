from sqlalchemy import Column, Integer, ForeignKey, Float, String
from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint
from ..database import Base


class SongTag(Base):

    __tablename__ = "song_tags"

    __table_args__ = (
        UniqueConstraint("song_id", "tag_id"),
    )

    id = Column(Integer, primary_key=True)

    song_id = Column(Integer, ForeignKey("songs.id"))

    tag_id = Column(Integer, ForeignKey("tags.id"))

    weight = Column(Float)

    popularity = Column(Float)

    spotify_id = Column(String)

    song = relationship("Song", back_populates="song_tags")

    tag = relationship("Tag", back_populates="song_tags")