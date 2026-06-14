"""Supabase client singleton with safe initialization."""
from __future__ import annotations

import logging
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()

    url = settings.supabase_url
    key = settings.supabase_service_role_key

    if not url:
        raise RuntimeError(
            "SUPABASE_URL is not set. "
            "Add it to your .env file (e.g. https://yourproject.supabase.co)."
        )
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not set. "
            "Get the service_role JWT from Supabase Dashboard → Settings → API."
        )
    if "publishable" in key.lower():
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is a publishable/anon key (sb_publishable_...). "
            "You must use the service_role JWT secret (starts with 'eyJ...').\n"
            "Go to Supabase Dashboard → Settings → API → service_role → Reveal."
        )

    try:
        import httpx
        from supabase import ClientOptions
        
        # Disable HTTP/2. httpx sync client on Windows throws WSAEWOULDBLOCK (10035) 
        # when sharing HTTP/2 multiplexed sockets across FastAPI threadpools.
        custom_http = httpx.Client(http2=False)
        opts = ClientOptions(httpx_client=custom_http)
        
        client = create_client(url, key, options=opts)
        logger.info("Supabase client initialized for project: %s", url)
        return client
    except Exception as exc:
        raise RuntimeError(f"Failed to create Supabase client: {exc}") from exc
