from datetime import UTC, datetime


def utcnow():
    return datetime.now(UTC)


def utcnow_naive():
    return utcnow().replace(tzinfo=None)


def parse_utc_datetime(value: str | None):
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_naive_utc(value: datetime | None):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
