"""Leads API routes."""
import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.schemas import LeadResponse
from app.repositories.leads import LeadsRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["leads"])
repo = LeadsRepository()


@router.get("", response_model=list[LeadResponse])
def list_leads(
    company_id: Optional[str] = Query(None, description="Filter by company ID"),
    limit: int = Query(500, ge=1, le=2000, description="Max results"),
) -> list[dict]:
    """List leads, optionally filtered by company."""
    try:
        return repo.list_all(limit=limit, company_id=company_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/{lead_id}")
def delete_lead(lead_id: str) -> dict[str, str]:
    """Delete a lead."""
    try:
        repo.delete(lead_id)
        return {"message": "Lead deleted successfully"}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))



@router.get("/export/csv")
def export_leads_csv(
    company_id: Optional[str] = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
) -> StreamingResponse:
    """Export leads as a CSV file download."""
    try:
        leads = repo.list_all(limit=limit, company_id=company_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    output = io.StringIO()
    fields = [
        "id", "full_name", "first_name", "last_name", "job_title",
        "seniority", "department", "company_name", "company_domain",
        "email", "phone", "linkedin_url", "location", "source",
        "confidence_score", "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        writer.writerow({f: lead.get(f, "") or "" for f in fields})

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )
