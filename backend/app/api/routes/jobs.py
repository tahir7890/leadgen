"""Job management API routes."""
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import JobResponse, RunJobRequest
from app.services.job_runner import JobRunner, job_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/run", response_model=JobResponse, status_code=202)
def run_job(payload: RunJobRequest | None = None) -> dict:
    """Start a new batch lead generation job."""
    req = payload or RunJobRequest()
    try:
        job_id = JobRunner().start_batch(req.batch_size, req.concurrency)
        job = job_store.get(job_id)
        if job:
            return job
        return {"id": job_id, "status": "queued", "total": 0, "completed": 0,
                "failed": 0, "leads_found": 0, "leads_inserted": 0, "logs": []}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("", response_model=list[JobResponse])
def list_jobs(limit: int = 20) -> list[dict]:
    """List recent jobs."""
    return job_store.list_jobs(limit=min(limit, 100))


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> dict:
    """Get status and logs for a specific job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.get("/{job_id}/logs")
def get_job_logs(job_id: str, since: int = 0) -> dict:
    """Get job logs starting from a specific index (for polling)."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    logs = job_store.get_logs(job_id, since=since)
    return {
        "job_id": job_id,
        "status": job["status"],
        "logs": logs,
        "total_logs": len(job.get("logs", [])),
    }
