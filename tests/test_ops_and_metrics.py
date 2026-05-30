from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.error_handlers import install_error_handlers
from backend.app.routes import ops_routes
from backend.app.services.metrics_service import (
    get_metrics_snapshot,
    record_job,
    record_job_failure,
    record_request,
    record_timing,
)
from backend.app.services.rate_limit_service import enforce_rate_limit


class _DummyClient:
    host = "127.0.0.1"


class _DummyRequest:
    headers = {}
    client = _DummyClient()


def test_metrics_snapshot_includes_jobs_failures_requests_and_timings():
    record_job("succeeded", "sync_history")
    record_job_failure("sync_history", "RuntimeError")
    record_request("GET", "/ops/health", 200, 0.125)
    record_timing("job.sync_history", 1.5)

    snapshot = get_metrics_snapshot()

    assert snapshot["jobs"]["succeeded"] >= 1
    assert snapshot["jobs"]["sync_history.succeeded"] >= 1
    assert snapshot["job_failures"]["sync_history.RuntimeError"] >= 1
    assert snapshot["requests"]["GET /ops/health"] >= 1
    assert snapshot["request_statuses"]["200"] >= 1
    assert snapshot["timings"]["job.sync_history"]["avg_seconds"] >= 1.5


def test_ops_health_checks_database(client_factory, db_session):
    client = client_factory(ops_routes.router)

    resp = client.get("/ops/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["database"]["status"] == "ok"
    assert payload["time_utc"]


def test_security_and_request_headers_are_added(db_session):
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)

    resp = client.get("/ping")

    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["X-Request-ID"]


def test_rate_limit_returns_retry_after_header():
    request = _DummyRequest()
    namespace = "test-rate-limit"
    enforce_rate_limit(request, namespace=namespace, user_id="u1", limit=1, window_seconds=60)

    try:
        enforce_rate_limit(request, namespace=namespace, user_id="u1", limit=1, window_seconds=60)
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.headers["Retry-After"]
    else:
        raise AssertionError("Expected rate limit HTTPException")
