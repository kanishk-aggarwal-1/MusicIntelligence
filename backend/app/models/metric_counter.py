from sqlalchemy import BigInteger, Column, DateTime, String

from ..database import Base
from ..time_utils import utcnow_naive


class MetricCounter(Base):
    """A single named, cumulative counter persisted in Postgres.

    Counters survive restarts/cold starts (unlike the in-process metrics_service)
    and hold only non-sensitive aggregates — never tokens or PII. Incremented
    atomically via an UPSERT so concurrent requests don't lose updates.
    """

    __tablename__ = "metric_counters"

    name = Column(String, primary_key=True)
    value = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=True)
