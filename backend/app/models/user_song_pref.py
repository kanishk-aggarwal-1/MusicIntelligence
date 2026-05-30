from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint

from ..database import Base


class UserSongPref(Base):
    """Per-user song preferences — currently tracks whether a user has hidden a song.

    Replaces the global Song.is_deleted flag so that one user hiding a song
    does not affect any other user's library view.
    """

    __tablename__ = "user_song_prefs"

    id      = Column(Integer, primary_key=True)
    user_id = Column(String,  nullable=False, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    is_hidden = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "song_id", name="uq_user_song_pref"),
    )
