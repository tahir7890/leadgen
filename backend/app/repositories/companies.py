"""Companies repository — all Supabase interactions for the companies table."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories.errors import format_supabase_error
from app.repositories.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _safe_execute(operation: str, fn):
    """Execute a Supabase query, converting any API errors to RuntimeErrors."""
    try:
        return fn()
    except RuntimeError:
        raise  # already formatted
    except Exception as e:
        raise format_supabase_error(operation, e) from e


class CompaniesRepository:
    def list_all(self, limit: int = 200) -> list[dict[str, Any]]:
        return _safe_execute(
            "list companies",
            lambda: (
                get_supabase()
                .table("companies")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            ),
        )

    def fetch_unprocessed(self, batch_size: int) -> list[dict[str, Any]]:
        return _safe_execute(
            "fetch unprocessed companies",
            lambda: (
                get_supabase()
                .table("companies")
                .select("*")
                .in_("status", ["pending", "failed"])
                .order("created_at")
                .limit(batch_size)
                .execute()
                .data
                or []
            ),
        )

    def create(self, domain: str) -> dict[str, Any]:
        result = _safe_execute(
            "create company",
            lambda: get_supabase()
            .table("companies")
            .insert({"domain": domain, "status": "pending"})
            .execute(),
        )
        if not result.data:
            raise RuntimeError("Failed to create company — empty response from Supabase")
        return result.data[0]

    def create_many(self, domains: list[str]) -> list[dict[str, Any]]:
        if not domains:
            return []
        payload = [{"domain": d, "status": "pending"} for d in domains]
        result = _safe_execute(
            "bulk create companies",
            lambda: get_supabase()
            .table("companies")
            .upsert(payload, on_conflict="domain", ignore_duplicates=True)
            .execute(),
        )
        return result.data or []

    def mark_processing(self, company_id: str) -> None:
        _safe_execute(
            "mark processing",
            lambda: get_supabase()
            .table("companies")
            .update({"status": "processing"})
            .eq("id", company_id)
            .execute(),
        )

    def mark_processed(self, company_id: str, leads_found: int, status: str) -> None:
        valid_statuses = {"completed", "failed", "no_results"}
        safe_status = status if status in valid_statuses else "completed"
        _safe_execute(
            "mark processed",
            lambda: get_supabase()
            .table("companies")
            .update(
                {
                    "processed": True,
                    "leads_found": leads_found,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "status": safe_status,
                }
            )
            .eq("id", company_id)
            .execute(),
        )

    def mark_failed(self, company_id: str, error_message: str = "") -> None:
        _safe_execute(
            "mark failed",
            lambda: get_supabase()
            .table("companies")
            .update(
                {
                    "processed": False,
                    "status": "failed",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", company_id)
            .execute(),
        )

    def reset(self, company_id: str) -> None:
        _safe_execute(
            "reset company",
            lambda: get_supabase()
            .table("companies")
            .update(
                {
                    "processed": False,
                    "status": "pending",
                    "leads_found": 0,
                    "processed_at": None,
                }
            )
            .eq("id", company_id)
            .execute(),
        )

    def count(self) -> dict[str, int]:
        """Get company counts using server-side aggregation (no full table scan)."""
        try:
            # Use count=exact for total
            total_result = (
                get_supabase()
                .table("companies")
                .select("*", count="exact")
                .execute()
            )
            total = total_result.count or 0

            processed_result = (
                get_supabase()
                .table("companies")
                .select("*", count="exact")
                .eq("processed", True)
                .execute()
            )
            processed = processed_result.count or 0

            return {
                "total": total,
                "processed": processed,
                "pending": total - processed,
            }
        except Exception as e:
            # Fallback: load rows and count in Python
            logger.warning("Server-side count failed, falling back to row scan: %s", e)
            try:
                rows = (
                    get_supabase()
                    .table("companies")
                    .select("id, processed")
                    .execute()
                    .data
                    or []
                )
                processed = sum(1 for r in rows if r.get("processed"))
                return {"total": len(rows), "processed": processed, "pending": len(rows) - processed}
            except Exception as e2:
                raise format_supabase_error("count companies", e2) from e2

    def get_by_id(self, company_id: str) -> Optional[dict[str, Any]]:
        rows = _safe_execute(
            "get company",
            lambda: get_supabase()
            .table("companies")
            .select("*")
            .eq("id", company_id)
            .limit(1)
            .execute()
            .data
            or [],
        )
        return rows[0] if rows else None
