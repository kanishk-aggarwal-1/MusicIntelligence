from sqlalchemy import Column, DateTime, Integer, String, Text
from datetime import datetime

from ..database import Base


class DedupMergeLog(Base):

    __tablename__ = "dedup_merge_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    batch_id = Column(String, index=True)
    kept_song_id = Column(Integer, nullable=False, index=True)
    removed_song_id = Column(Integer, nullable=False, index=True)
    original_title = Column(String, nullable=True)
    original_artist = Column(String, nullable=True)
    snapshot_json = Column(Text, nullable=True)
    merged_at = Column(DateTime, default=datetime.utcnow, index=True)
