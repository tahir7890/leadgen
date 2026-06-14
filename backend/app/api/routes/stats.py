"""Dashboard statistics endpoint."""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.schemas import DashboardStats
from app.repositories.companies import CompaniesRepository
from app.repositories.leads import LeadsRepository
from app.services.job_runner import job_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=DashboardStats)
def stats() -> dict:
    """Return dashboard statistics — companies, leads, and last job status."""
    cs = {"total": 0, "processed": 0, "pending": 0}
    ls = {"total": 0, "with_email": 0, "with_linkedin": 0}

    try:
        cs = CompaniesRepository().count()
    except RuntimeError as e:
        logger.warning("Could not fetch company stats: %s", e)

    try:
        ls = LeadsRepository().stats()
    except RuntimeError as e:
        logger.warning("Could not fetch lead stats: %s", e)

    jobs = job_store.list_jobs(1)
    last_status = jobs[0]["status"] if jobs else None

    return {
        "total_companies": cs["total"],
        "processed_companies": cs["processed"],
        "pending_companies": cs["pending"],
        "total_leads": ls["total"],
        "leads_with_email": ls["with_email"],
        "leads_with_linkedin": ls["with_linkedin"],
        "last_job_status": last_status,
    }
