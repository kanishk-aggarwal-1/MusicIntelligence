from functools import partial

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.discovery_workflow_service import accept_discovery_candidates, build_discovery_preview
from ..services.job_service import create_job, get_job, run_job, serialize_job
from ..services.spotify_service import load_request_user_session

router = APIRouter(prefix="/discoveries", tags=["Discoveries"])


class DiscoveryAcceptPayload(BaseModel):
    job_id: str
    candidate_ids: list[int] = []


def _run_discovery_preview_job(db: Session, progress, *, user_id: str, seed_limit: int, max_candidates: int):
    progress.update(total=3, current=0, message="Selecting seed artists")
    preview = build_discovery_preview(db, user_id, seed_limit=seed_limit, max_candidates=max_candidates)
    progress.update(total=3, current=2, message="Discovery preview complete")
    return {
        "message": "Discovery preview ready",
        "progress_current": 3,
        "progress_total": 3,
        **preview,
    }


@router.post("/preview/job")
def discovery_preview_job(
    request: Request,
    background_tasks: BackgroundTasks,
    seed_limit: int = 8,
    max_candidates: int = 80,
    db: Session = Depends(get_db),
):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    job = create_job(
        db,
        user_id=user_id,
        job_type="discovery_preview",
        message="Queued discovery preview",
        progress_total=3,
    )
    background_tasks.add_task(
        run_job,
        job.id,
        partial(_run_discovery_preview_job, user_id=user_id, seed_limit=seed_limit, max_candidates=max_candidates),
    )
    return serialize_job(job)


@router.post("/accept")
def accept_preview(payload: DiscoveryAcceptPayload, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    job = get_job(db, job_id=payload.job_id, user_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    if job.job_type != "discovery_preview":
        raise HTTPException(status_code=400, detail="Job is not a discovery preview")
    if job.status != "succeeded":
        raise HTTPException(status_code=400, detail="Discovery preview job is not finished")

    return accept_discovery_candidates(db, job, user_id=user_id, candidate_ids=payload.candidate_ids)
