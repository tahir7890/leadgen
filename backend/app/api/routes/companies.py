"""Company management API routes."""
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import CompanyBulkCreate, CompanyCreate, CompanyResponse
from app.repositories.companies import CompaniesRepository
from app.services.job_runner import JobRunner
from app.services.lead_normalizer import normalize_domain

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])
repo = CompaniesRepository()


@router.get("", response_model=list[CompanyResponse])
def list_companies(limit: int = 200) -> list[dict]:
    """List all companies ordered by creation date (newest first)."""
    try:
        return repo.list_all(limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(payload: CompanyCreate) -> dict:
    """Add a single company domain for lead generation."""
    domain = normalize_domain(payload.domain)
    if not domain or len(domain) < 3:
        raise HTTPException(status_code=422, detail="Invalid domain")
    try:
        return repo.create(domain)
    except RuntimeError as e:
        error_str = str(e).lower()
        if "duplicate" in error_str or "unique" in error_str:
            raise HTTPException(status_code=409, detail=f"Domain '{domain}' already exists")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/bulk", response_model=list[CompanyResponse])
def bulk_create(payload: CompanyBulkCreate) -> list[dict]:
    """Add multiple company domains at once (duplicates are silently ignored)."""
    domains = [normalize_domain(d) for d in payload.domains if normalize_domain(d)]
    if not domains:
        raise HTTPException(status_code=422, detail="No valid domains provided")
    try:
        return repo.create_many(domains)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/{company_id}/reset")
def reset_company(company_id: str) -> dict:
    """Reset a company to pending status so it can be reprocessed."""
    try:
        if not repo.get_by_id(company_id):
            raise HTTPException(status_code=404, detail="Company not found")
        repo.reset(company_id)
        return {"message": "Company reset to pending", "company_id": company_id}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/{company_id}/process")
def process_company(company_id: str) -> dict:
    """Trigger immediate lead generation for a single company."""
    try:
        if not repo.get_by_id(company_id):
            raise HTTPException(status_code=404, detail="Company not found")
        job_id = JobRunner().start_single(company_id)
        return {"job_id": job_id, "company_id": company_id}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/{company_id}")
def delete_company(company_id: str) -> dict:
    """Delete a company and all its leads (cascade)."""
    try:
        from app.repositories.supabase_client import get_supabase
        company = repo.get_by_id(company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        get_supabase().table("companies").delete().eq("id", company_id).execute()
        return {"message": "Company deleted", "company_id": company_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
