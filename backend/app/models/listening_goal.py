from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..database import Base
from ..time_utils import utcnow_naive


class ListeningGoal(Base):

    __tablename__ = "listening_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    goal_type = Column(String, nullable=False, index=True)
    target_value = Column(Integer, nullable=False)
    period = Column(String, nullable=False, default="weekly")
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive, index=True)
