"""Background job runner for batch lead generation processing."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import get_settings
from app.repositories.companies import CompaniesRepository
from app.repositories.leads import LeadsRepository
from app.services.lead_normalizer import normalize_leads

from app.services.mcp_client import McpError, PlaywrightMcpClient, create_mcp_client
from app.services.local_browser_client import (
    LocalBrowserClient,
    LocalBrowserError,
    create_local_browser_client,
)
from app.services.rocketreach import RocketReachService

logger = logging.getLogger(__name__)

# Maximum time (seconds) to process a single company before giving up
COMPANY_TIMEOUT_SECONDS = 300  # 5 minutes


class JobStore:
    """Thread-safe in-memory store for job status and logs."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, total: int) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "total": total,
                "completed": 0,
                "failed": 0,
                "leads_found": 0,
                "leads_inserted": 0,
                "started_at": None,
                "finished_at": None,
                "message": None,
                "logs": [],
            }
        return job_id

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.get("started_at") or "", reverse=True)
        return [dict(j) for j in jobs[:limit]]

    def update(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def log(self, job_id: str, message: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                entry = f"[{ts}] {message}"
                self._jobs[job_id]["logs"].append(entry)
                # Keep only last 500 log entries to avoid memory growth
                if len(self._jobs[job_id]["logs"]) > 500:
                    self._jobs[job_id]["logs"] = self._jobs[job_id]["logs"][-500:]

    def get_logs(self, job_id: str, since: int = 0) -> list[str]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return []
            return job["logs"][since:]


# Global singleton job store
job_store = JobStore()


class JobRunner:
    """Orchestrates batch and single-company lead generation jobs."""

    def __init__(self) -> None:
        self.companies = CompaniesRepository()
        self.leads = LeadsRepository()
        self.settings = get_settings()

    def start_batch(
        self, batch_size: Optional[int] = None, concurrency: Optional[int] = None
    ) -> str:
        size = batch_size or self.settings.batch_size
        workers = min(
            concurrency or self.settings.concurrency,
            self.settings.concurrency,
        )

        try:
            companies = self.companies.fetch_unprocessed(size)
        except RuntimeError as e:
            job_id = job_store.create(0)
            job_store.update(job_id, status="failed", message=f"DB error: {e}")
            return job_id

        job_id = job_store.create(len(companies))

        if not companies:
            job_store.update(
                job_id,
                status="completed",
                message="No unprocessed companies found",
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            return job_id

        threading.Thread(
            target=self._run,
            args=(job_id, companies, workers),
            daemon=True,
            name=f"job-{job_id[:8]}",
        ).start()
        return job_id

    def start_single(self, company_id: str) -> str:
        try:
            company = self.companies.get_by_id(company_id)
        except RuntimeError as e:
            job_id = job_store.create(0)
            job_store.update(job_id, status="failed", message=f"DB error: {e}")
            return job_id

        if not company:
            job_id = job_store.create(0)
            job_store.update(job_id, status="failed", message="Company not found")
            return job_id

        # Reset company to pending before reprocessing
        try:
            self.companies.reset(company_id)
        except RuntimeError as e:
            logger.warning("Failed to reset company %s: %s", company_id, e)

        job_id = job_store.create(1)
        threading.Thread(
            target=self._run,
            args=(job_id, [company], 1),
            daemon=True,
            name=f"job-single-{job_id[:8]}",
        ).start()
        return job_id

    def _run(self, job_id: str, companies: list[dict], concurrency: int) -> None:
        # Playwright relies heavily on asyncio, even in its sync API.
        # When running inside a threading.Thread on Windows, we MUST set
        # the Proactor event loop policy and explicitly attach a new loop
        # to this thread to prevent silent deadlocks.
        import asyncio
        import sys
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.new_event_loop())

        job_store.update(
            job_id,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        job_store.log(job_id, f"Batch started: {len(companies)} companies")

        settings = get_settings()
        use_local = settings.is_local_browser_mode()

        if use_local:
            job_store.log(
                job_id,
                "🖥️  LOCAL BROWSER MODE — a visible Chromium window will open. "
                "If a CAPTCHA appears, switch to the browser and solve it manually.",
            )
        else:
            # NOTE: Apify Playwright MCP actor uses a SINGLE shared browser instance.
            # All companies must be processed sequentially through ONE MCP session.
            job_store.log(job_id, "Connecting to Playwright MCP browser (Apify cloud)...")

        completed, failed, leads_found, leads_inserted = 0, 0, 0, 0
        mcp = None

        try:
            if use_local:
                mcp = create_local_browser_client(
                    headless=settings.local_browser_headless,
                    slow_mo=settings.local_browser_slow_mo,
                )
                job_store.log(job_id, "Local Chromium browser launched successfully.")
            else:
                mcp = create_mcp_client()
                job_store.log(job_id, f"MCP connected (session={mcp._session_id or 'none'})")
        except (McpError, LocalBrowserError) as e:
            logger.error("Failed to connect to browser: %s", e)
            job_store.update(
                job_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                message=f"Browser connection failed: {e}",
            )
            job_store.log(job_id, f"[FAIL] Browser connection failed: {e}")
            return

        try:
            for company in companies:
                domain = company.get("domain", "unknown")
                try:
                    r = self._process_company(company, mcp, job_id)
                    completed += 1
                    leads_found += r["leads_found"]
                    leads_inserted += r["leads_inserted"]
                    job_store.log(
                        job_id,
                        f"[OK] {domain}: {r['leads_found']} leads found, {r['leads_inserted']} inserted",
                    )
                # NOTE: RetryError is never raised because mcp_client uses reraise=True
                # (original exception is re-raised directly). McpError handles all MCP failures.
                except McpError as e:
                    failed += 1
                    try:
                        self.companies.mark_failed(company["id"], str(e))
                    except Exception:
                        pass
                    job_store.log(job_id, f"[FAIL] {domain}: MCP -- {e}")
                    # If the error is about browser being in use, abort remaining companies
                    if "already in use" in str(e).lower():
                        job_store.log(
                            job_id,
                            "[WARN] Browser locked -- aborting remaining companies. "
                            "Wait a minute and run the batch again.",
                        )
                        break
                except Exception as e:
                    failed += 1
                    try:
                        self.companies.mark_failed(company["id"], str(e))
                    except Exception:
                        pass
                    job_store.log(job_id, f"[FAIL] {domain}: {type(e).__name__} -- {e}")

                job_store.update(
                    job_id,
                    completed=completed,
                    failed=failed,
                    leads_found=leads_found,
                    leads_inserted=leads_inserted,
                )
        finally:
            if mcp is not None:
                mcp.close()
                job_store.log(job_id, "MCP session closed.")

        job_store.update(
            job_id,
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            message=f"Done: {completed} succeeded, {failed} failed, {leads_inserted} leads inserted",
        )
        job_store.log(
            job_id,
            f"Batch complete -- {completed} ok / {failed} failed / {leads_inserted} leads inserted",
        )

    def _process_company(
        self, company: dict, mcp: PlaywrightMcpClient, job_id: str
    ) -> dict[str, int]:
        """Process a single company: scrape -> normalize -> upsert."""
        cid = company["id"]
        domain = company["domain"]

        # Mark as processing
        try:
            self.companies.mark_processing(cid)
        except RuntimeError as e:
            logger.warning("Could not mark company as processing: %s", e)

        job_store.log(job_id, f"Processing {domain}...")

        # Scrape RocketReach
        rr = RocketReachService(mcp)
        raw_leads = rr.search_domain(domain)

        if not raw_leads:
            logger.info("No raw leads returned for %s", domain)
            try:
                self.companies.mark_processed(cid, 0, "no_results")
            except RuntimeError as e:
                logger.warning("Could not mark company as no_results: %s", e)
            return {"leads_found": 0, "leads_inserted": 0}

        # Normalize and deduplicate
        normalized = normalize_leads(cid, domain, raw_leads)
        logger.info("%s: %d raw -> %d normalized leads", domain, len(raw_leads), len(normalized))

        # Save to Supabase
        upsert_result = {"inserted": 0, "skipped": 0}
        if normalized:
            try:
                upsert_result = self.leads.upsert_many(normalized)
            except RuntimeError as e:
                logger.error("Failed to upsert leads for %s: %s", domain, e)
                # Don't re-raise — mark company as completed but log the error
                job_store.log(job_id, f"  [WARN] {domain}: DB upsert failed -- {e}")

        # Mark company as done
        status = "completed" if normalized else "no_results"
        try:
            self.companies.mark_processed(cid, len(normalized), status)
        except RuntimeError as e:
            logger.warning("Could not mark company as processed: %s", e)

        return {
            "leads_found": len(normalized),
            "leads_inserted": upsert_result["inserted"],
        }
