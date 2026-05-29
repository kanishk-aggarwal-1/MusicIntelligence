from sqlalchemy import Column, DateTime, Integer, String, Text

from ..database import Base
from ..time_utils import utcnow_naive


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    job_type = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False)
    progress_current = Column(Integer, default=0, nullable=False)
    progress_total = Column(Integer, default=0, nullable=False)
    message = Column(String)
    error = Column(Text)
    result_json = Column(Text)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False, index=True)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
