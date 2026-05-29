from sqlalchemy import Column, DateTime, Integer, String, Text, Index

from ..database import Base
from ..time_utils import utcnow_naive


class ApiCache(Base):
    __tablename__ = "api_cache"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)
    cache_key = Column(String, nullable=False)
    response_json = Column(Text)
    status_code = Column(Integer)
    fetched_at = Column(DateTime, default=utcnow_naive, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    error = Column(Text)

    __table_args__ = (
        Index("uq_api_cache_provider_key", "provider", "cache_key", unique=True),
    )
