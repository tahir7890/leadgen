import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    rocketreach_email: str = ""
    rocketreach_password: str = ""
    rocketreach_login_url: str = "https://rocketreach.co/login"
    rocketreach_search_url: str = "https://rocketreach.co/person"

    apify_token: str = ""
    # Use the jiri-spilka Playwright MCP server (standard browser_* tools)
    apify_mcp_url: str = "https://jiri-spilka--playwright-mcp-server.apify.actor/mcp"

    concurrency: int = Field(default=2, ge=1, le=20)
    batch_size: int = Field(default=50, ge=1, le=500)
    max_retries: int = Field(default=3, ge=0, le=10)
    request_delay_ms: int = Field(default=2000, ge=0)

    log_level: str = "info"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ------------------------------------------------------------------
    # Local browser mode  (LOCAL_BROWSER_MODE=true in .env)
    # ------------------------------------------------------------------
    # When true, a local visible Chromium window is used instead of the
    # Apify cloud browser.  The browser window stays open so the user can
    # solve CAPTCHAs manually.  Automation resumes automatically once the
    # CAPTCHA page is gone.
    local_browser_mode: bool = False
    local_browser_headless: bool = False   # True = hidden (CI only)
    local_browser_slow_mo: int = Field(default=50, ge=0, le=2000)  # ms between actions
    captcha_wait_timeout: int = Field(default=300, ge=30, le=900)  # seconds user has to solve

    @field_validator("supabase_service_role_key")
    @classmethod
    def validate_service_role_key(cls, v: str) -> str:
        if not v:
            logger.warning(
                "SUPABASE_SERVICE_ROLE_KEY is not set. "
                "Database operations will fail. "
                "Set it to the service_role key from "
                "Supabase Dashboard → Settings → API."
            )
            return v
        lowered = v.lower()
        if "publishable" in lowered or lowered.startswith("sb_publishable"):
            logger.error(
                "SUPABASE_SERVICE_ROLE_KEY looks like a publishable/anon key "
                "(starts with sb_publishable_...). "
                "You MUST use the service_role JWT secret from "
                "Supabase Dashboard -> Settings -> API -> service_role. It starts with 'eyJ...' and is much longer."
            )
            # Don't crash — let the app start and show proper errors on DB calls
            return v
        if len(v) < 40:
            logger.warning(
                "SUPABASE_SERVICE_ROLE_KEY appears too short. "
                "Copy the full service_role key from Supabase Dashboard → Settings → API."
            )
        return v

    def is_supabase_configured(self) -> bool:
        """Return True if Supabase credentials look valid."""
        key = self.supabase_service_role_key
        return bool(
            self.supabase_url
            and key
            and "publishable" not in key.lower()
            and len(key) >= 40
        )

    def is_apify_configured(self) -> bool:
        """Return True if Apify token is set."""
        return bool(self.apify_token and len(self.apify_token) > 10)

    def is_local_browser_mode(self) -> bool:
        """Return True when local visible browser mode is active."""
        return self.local_browser_mode


@lru_cache
def get_settings() -> Settings:
    return Settings()
