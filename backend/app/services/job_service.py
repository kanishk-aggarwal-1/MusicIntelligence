import json
import logging
import time
import uuid
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.job import Job
from ..services.metrics_service import record_job, record_job_failure, record_timing
from ..time_utils import utcnow_naive

logger = logging.getLogger(__name__)
ACTIVE_JOB_MAX_AGE = timedelta(hours=2)


class JobProgress:
    def __init__(self, db: Session, job: Job):
        self.db = db
        self.job = job

    def update(self, *, current: int | None = None, total: int | None = None, message: str | None = None, status: str | None = None):
        if current is not None:
            self.job.progress_current = max(0, int(current))
        if total is not None:
            self.job.progress_total = max(0, int(total))
        if message is not None:
            self.job.message = message
        if status is not None:
            self.job.status = status
        self.db.add(self.job)
        self.db.commit()
        self.db.refresh(self.job)


def serialize_job(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress_current": int(job.progress_current or 0),
        "progress_total": int(job.progress_total or 0),
        "message": job.message,
        "error": job.error,
        "result": json.loads(job.result_json) if job.result_json else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def create_job(db: Session, *, user_id: str, job_type: str, message: str = "Queued", progress_total: int = 0) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        user_id=user_id,
        job_type=job_type,
        status="queued",
        progress_current=0,
        progress_total=max(0, int(progress_total or 0)),
        message=message,
        created_at=utcnow_naive(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    record_job("queued", job_type)
    return job


def get_job(db: Session, *, job_id: str, user_id: str | None = None) -> Job | None:
    query = db.query(Job).filter(Job.id == job_id)
    if user_id:
        query = query.filter(Job.user_id == user_id)
    return query.first()


def _job_age_anchor(job: Job):
    return job.started_at or job.created_at


def get_active_job(db: Session, *, user_id: str, job_type: str) -> Job | None:
    now = utcnow_naive()
    active_jobs = (
        db.query(Job)
        .filter(
            Job.user_id == user_id,
            Job.job_type == job_type,
            Job.status.in_(("queued", "running")),
        )
        .order_by(Job.created_at.desc())
        .all()
    )

    for job in active_jobs:
        anchor = _job_age_anchor(job)
        if anchor and now - anchor > ACTIVE_JOB_MAX_AGE:
            job.status = "failed"
            job.error = "Job marked stale after exceeding active job timeout"
            job.finished_at = now
            job.message = "Job timed out before completing"
            db.add(job)
            db.commit()
            logger.warning("job.marked_stale job_id=%s user_id=%s job_type=%s", job.id, user_id, job_type)
            record_job("failed", job_type)
            record_job_failure(job_type, "stale_timeout")
            continue
        return job

    return None


def list_jobs(db: Session, *, user_id: str, limit: int = 50) -> list[Job]:
    safe_limit = max(1, min(limit, 200))
    return (
        db.query(Job)
        .filter(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .limit(safe_limit)
        .all()
    )


def cancel_job(db: Session, *, job_id: str, user_id: str) -> Job | None:
    job = get_job(db, job_id=job_id, user_id=user_id)
    if not job:
        return None
    if job.status in {"succeeded", "failed", "cancelled"}:
        return job
    job.status = "cancelled"
    job.finished_at = utcnow_naive()
    job.message = job.message or "Cancelled"
    db.add(job)
    db.commit()
    db.refresh(job)
    record_job("cancelled", job.job_type)
    return job


def run_job(job_id: str, handler: Callable[[Session, JobProgress], dict[str, Any] | None]):
    db = SessionLocal()
    started_perf = time.perf_counter()
    metric_job_type = "unknown"
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        metric_job_type = job.job_type
        if job.status == "cancelled":
            return

        job.status = "running"
        job.started_at = utcnow_naive()
        job.message = job.message or "Running"
        db.add(job)
        db.commit()
        db.refresh(job)
        record_job("running", job.job_type)

        progress = JobProgress(db, job)
        result = handler(db, progress) or {}

        db.refresh(job)
        if job.status == "cancelled":
            if not job.finished_at:
                job.finished_at = utcnow_naive()
            db.add(job)
            db.commit()
            record_job("cancelled", job.job_type)
            return

        job.status = "succeeded"
        job.finished_at = utcnow_naive()
        job.message = result.get("message") or job.message or "Completed"
        if "progress_current" in result:
            job.progress_current = int(result["progress_current"] or 0)
        if "progress_total" in result:
            job.progress_total = int(result["progress_total"] or 0)
        if result:
            job.result_json = json.dumps(result)
        db.add(job)
        db.commit()
        record_job("succeeded", job.job_type)
    except Exception as exc:
        db.rollback()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            metric_job_type = job.job_type
            logger.exception("job.failed job_id=%s user_id=%s job_type=%s", job.id, job.user_id, job.job_type)
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = utcnow_naive()
            db.add(job)
            db.commit()
        record_job("failed", metric_job_type)
        record_job_failure(metric_job_type, type(exc).__name__)
    finally:
        record_timing(f"job.{metric_job_type}", time.perf_counter() - started_perf)
        db.close()
