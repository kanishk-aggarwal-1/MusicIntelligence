from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..authz import require_capability
from ..database import get_db
from ..deps import require_user_id
from ..services.job_service import cancel_job, get_job, list_jobs, serialize_job

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("")
def jobs_list(request: Request, limit: int = 30, db: Session = Depends(get_db)):
    user_id = require_user_id(db, request)

    jobs = list_jobs(db, user_id=user_id, limit=limit)
    return {"items": [serialize_job(job) for job in jobs]}


@router.get("/{job_id}")
def job_detail(job_id: str, request: Request, db: Session = Depends(get_db)):
    user_id = require_user_id(db, request)

    job = get_job(db, job_id=job_id, user_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)


@router.post("/{job_id}/cancel")
def cancel(job_id: str, request: Request, db: Session = Depends(get_db)):
    user_id = require_user_id(db, request)
    require_capability(user_id, "mutate_library")

    job = cancel_job(db, job_id=job_id, user_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)
