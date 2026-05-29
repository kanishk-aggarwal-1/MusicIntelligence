from datetime import datetime, timezone, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.models import api_cache, artist, dedup_merge_log, generated_playlist, generated_playlist_track, job, listening_goal, listening_history, recommendation_feedback, song, song_tag, tag, user_session  # noqa: F401


def _date_trunc(part, value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
    else:
        dt = value
    part = (part or "").lower()
    if part == "week":
        monday = dt - timedelta(days=dt.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(sep=" ")
    if part == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(sep=" ")
    return dt.isoformat(sep=" ")


@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("date_trunc", 2, _date_trunc)

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def testing_session_local(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture()
def db_session(testing_session_local):
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client_factory(db_session):
    def _make_client(*routers):
        app = FastAPI()
        for router in routers:
            app.include_router(router)

        def _override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db
        return TestClient(app)

    return _make_client
