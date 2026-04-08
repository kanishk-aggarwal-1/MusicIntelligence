from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from datetime import datetime

from ..database import Base


class RecommendationFeedback(Base):

    __tablename__ = "recommendation_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)  # like, dislike, skip
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
