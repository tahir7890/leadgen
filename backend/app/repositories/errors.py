"""Supabase / PostgREST error formatting utilities."""
from __future__ import annotations


def _extract_error_info(error: Exception) -> tuple[str, str]:
    """Safely extract code and message from any postgrest/supabase error."""
    code = ""
    message = str(error)

    # postgrest-py >= 0.10 / supabase-py >= 2.x: APIError has code + message attrs
    if hasattr(error, "code"):
        code = str(error.code or "")
    if hasattr(error, "message"):
        msg = error.message  # type: ignore[attr-defined]
        if msg:
            message = str(msg)

    # Some versions store details in .details or .hint
    if hasattr(error, "details") and error.details:  # type: ignore[attr-defined]
        message = f"{message} | details: {error.details}"  # type: ignore[attr-defined]

    return code, message


def format_supabase_error(operation: str, error: Exception) -> Exception:
    """Convert a postgrest/supabase API error into an actionable RuntimeError."""
    code, message = _extract_error_info(error)

    msg_lower = message.lower()

    if code == "42501" or "row-level security" in msg_lower or "rls" in msg_lower:
        return RuntimeError(
            f"{operation}: Row-level security blocked this operation.\n"
            "Fix: Use SUPABASE_SERVICE_ROLE_KEY (the JWT secret, not the publishable key).\n"
            "Or run supabase/migrations/002_rls_policies.sql in Supabase SQL Editor."
        )

    if (
        "401" in message
        or "invalid api key" in msg_lower
        or code in ("PGRST301", "PGRST302")
        or "jwt" in msg_lower
    ):
        return RuntimeError(
            f"{operation}: Supabase authentication failed.\n"
            "Fix: Set SUPABASE_SERVICE_ROLE_KEY to the service_role JWT secret from "
            "Supabase Dashboard → Settings → API. It starts with 'eyJ...'."
        )

    if code == "23505" or "duplicate key" in msg_lower or "unique" in msg_lower:
        # Duplicate key — not a hard error, just a warning
        return RuntimeError(f"{operation}: Duplicate key violation — {message}")

    if code == "42P01" or "does not exist" in msg_lower:
        return RuntimeError(
            f"{operation}: Table not found — {message}\n"
            "Fix: Run supabase/migrations/001_create_tables.sql in Supabase SQL Editor."
        )

    return RuntimeError(f"{operation}: {message}")
