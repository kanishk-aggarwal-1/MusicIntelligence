from sqlalchemy import Column, DateTime, Integer, String, Text
from datetime import datetime

from ..database import Base


class UserSession(Base):

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, nullable=False, index=True)

    token = Column(String, nullable=False)
    refresh_token = Column(String)
    token_expires_at = Column(DateTime, index=True)
    token_info_json = Column(Text)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
