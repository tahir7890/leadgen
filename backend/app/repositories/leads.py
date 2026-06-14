"""Leads repository — all Supabase interactions for the leads table."""
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
        raise
    except Exception as e:
        raise format_supabase_error(operation, e) from e


class LeadsRepository:
    def list_all(self, limit: int = 500, company_id: Optional[str] = None) -> list[dict[str, Any]]:
        def _query():
            q = (
                get_supabase()
                .table("leads")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if company_id:
                q = q.eq("company_id", company_id)
            return q.execute().data or []

        return _safe_execute("list leads", _query)

    # All valid column names in the leads table
    _LEAD_COLUMNS = frozenset({
        "company_id", "full_name", "first_name", "last_name",
        "job_title", "seniority", "department",
        "company_name", "company_domain",
        "linkedin_url", "email", "phone", "location",
        "source", "confidence_score", "dedupe_key",
        "updated_at",
    })

    def upsert_many(self, leads: list[dict[str, Any]]) -> dict[str, int]:
        if not leads:
            return {"inserted": 0, "skipped": 0}

        now = datetime.now(timezone.utc).isoformat()

        # Build payload: keep only known DB columns; keep None so DB stores explicit NULLs
        payload = []
        for lead in leads:
            row = {k: v for k, v in lead.items() if k in self._LEAD_COLUMNS}
            row["updated_at"] = now
            # dedupe_key is required
            if not row.get("dedupe_key"):
                logger.warning("Skipping lead with no dedupe_key: %s", row.get("full_name"))
                continue
            payload.append(row)

        if not payload:
            return {"inserted": 0, "skipped": len(leads)}

        inserted_count = 0
        skipped_count = 0

        try:
            # upsert with returning='representation' gives back inserted rows
            # ignore_duplicates=True: conflicting rows are skipped, not updated
            result = (
                get_supabase()
                .table("leads")
                .upsert(
                    payload,
                    on_conflict="dedupe_key",
                    ignore_duplicates=True,
                    returning="representation",
                )
                .execute()
            )
            inserted_count = len(result.data or [])
            skipped_count = len(payload) - inserted_count

        except Exception as e:
            error_str = str(e).lower()
            if "duplicate" in error_str or "unique" in error_str:
                # Batch conflict — try row-by-row
                logger.warning("Batch upsert had conflicts, falling back to row-by-row: %s", e)
                for row in payload:
                    try:
                        r = (
                            get_supabase()
                            .table("leads")
                            .upsert(row, on_conflict="dedupe_key", ignore_duplicates=True)
                            .execute()
                        )
                        if r.data:
                            inserted_count += 1
                        else:
                            skipped_count += 1
                    except Exception:
                        skipped_count += 1
            else:
                raise format_supabase_error("upsert leads", e) from e

        logger.info("Leads upsert: %d inserted, %d skipped", inserted_count, skipped_count)
        return {"inserted": inserted_count, "skipped": skipped_count}

    def stats(self) -> dict[str, int]:
        """Get lead stats using server-side count aggregation."""
        try:
            total_result = (
                get_supabase()
                .table("leads")
                .select("*", count="exact")
                .execute()
            )
            total = total_result.count or 0

            email_result = (
                get_supabase()
                .table("leads")
                .select("*", count="exact")
                .not_.is_("email", "null")
                .execute()
            )
            with_email = email_result.count or 0

            linkedin_result = (
                get_supabase()
                .table("leads")
                .select("*", count="exact")
                .not_.is_("linkedin_url", "null")
                .execute()
            )
            with_linkedin = linkedin_result.count or 0

            return {
                "total": total,
                "with_email": with_email,
                "with_linkedin": with_linkedin,
            }
        except Exception as e:
            logger.warning("Server-side stats failed, falling back to row scan: %s", e)
            try:
                rows = (
                    get_supabase()
                    .table("leads")
                    .select("id, email, linkedin_url")
                    .execute()
                    .data
                    or []
                )
                return {
                    "total": len(rows),
                    "with_email": sum(1 for r in rows if r.get("email")),
                    "with_linkedin": sum(1 for r in rows if r.get("linkedin_url")),
                }
            except Exception as e2:
                raise format_supabase_error("lead stats", e2) from e2

    def delete(self, lead_id: str) -> None:
        def _delete():
            get_supabase().table("leads").delete().eq("id", lead_id).execute()
        _safe_execute("delete lead", _delete)
