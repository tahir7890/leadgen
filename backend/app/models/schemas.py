"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CompanyCreate(BaseModel):
    domain: str = Field(..., min_length=3, description="Company domain e.g. example.com")

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, v: str) -> str:
        return v.strip().lower()


class CompanyBulkCreate(BaseModel):
    domains: list[str] = Field(..., description="List of domains to add")

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("domains list must not be empty")
        cleaned = [d.strip().lower() for d in v if d.strip()]
        if not cleaned:
            raise ValueError("All provided domains are empty strings")
        return cleaned


class CompanyResponse(BaseModel):
    id: UUID
    domain: str
    processed: bool
    leads_found: Optional[int] = None
    processed_at: Optional[datetime] = None
    status: Optional[str] = None
    created_at: datetime


class LeadResponse(BaseModel):
    id: UUID
    company_id: UUID
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    source: str
    confidence_score: Optional[float] = None
    created_at: datetime


class JobResponse(BaseModel):
    id: str
    status: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    leads_found: int = 0
    leads_inserted: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    message: Optional[str] = None
    logs: list[str] = Field(default_factory=list)


class DashboardStats(BaseModel):
    total_companies: int
    processed_companies: int
    pending_companies: int
    total_leads: int
    leads_with_email: int
    leads_with_linkedin: int
    last_job_status: Optional[str] = None


class RunJobRequest(BaseModel):
    batch_size: Optional[int] = Field(None, ge=1, le=500)
    concurrency: Optional[int] = Field(None, ge=1, le=20)
