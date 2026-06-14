"""Local visible Playwright browser client.

Drop-in replacement for PlaywrightMcpClient that runs a *local* Chromium
window (headless=False).  The user can see the browser, interact with it,
and solve CAPTCHAs manually.

Usage (set LOCAL_BROWSER_MODE=true in .env):
    The job_runner will call create_local_browser_client() instead of
    create_mcp_client() when this flag is active.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors — same interface as McpError so job_runner doesn't care which client
# ---------------------------------------------------------------------------

class LocalBrowserError(Exception):
    """Raised for unrecoverable local browser failures."""
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable

    @classmethod
    def non_retryable(cls, msg: str) -> "LocalBrowserError":
        return cls(msg, retryable=False)


# Re-export as McpError-compatible alias so callers can catch either
McpError = LocalBrowserError


# ---------------------------------------------------------------------------
# CAPTCHA wait timeout (seconds).  User has this long to solve it.
# ---------------------------------------------------------------------------
CAPTCHA_WAIT_SECONDS = 300   # 5 minutes


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class LocalBrowserClient:
    """Synchronous wrapper around a local headful Playwright Chromium browser.

    Implements the same public interface as PlaywrightMcpClient:
        navigate(), snapshot(), get_text(), evaluate(), click(),
        type_text(), wait(), screenshot(), close()

    The browser window is visible — the user can interact with it directly
    to solve CAPTCHAs or any other challenge that appears.
    """

    def __init__(self, headless: bool = False, slow_mo: int = 0) -> None:
        """
        Args:
            headless:  False = visible browser (recommended).  True = hidden.
            slow_mo:   Milliseconds to slow each Playwright action (useful for
                       watching the automation at human speed).
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._connected = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        """Launch the local Chromium browser and open a tab."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise LocalBrowserError.non_retryable(
                "playwright is not installed. Run: pip install playwright && "
                "playwright install chromium"
            )

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )
        except Exception as e:
            raise LocalBrowserError.non_retryable(
                f"Failed to launch Chromium: {e}. "
                "Run: playwright install chromium"
            ) from e

        self._context = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            # Spoof webdriver flag to avoid trivial bot detection
            java_script_enabled=True,
        )
        # Remove navigator.webdriver flag
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._page = self._context.new_page()
        self._connected = True
        logger.info(
            "Local Chromium browser launched (headless=%s)", self.headless
        )

    def close(self) -> None:
        """Close the browser and clean up."""
        for obj, method in [
            (self._page, "close"),
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ]:
            if obj is not None:
                try:
                    getattr(obj, method)()
                except Exception:
                    pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._connected = False
        logger.info("Local Chromium browser closed.")

    # ------------------------------------------------------------------ #
    # Core browser actions — same interface as PlaywrightMcpClient
    # ------------------------------------------------------------------ #

    def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the page to be interactive."""
        self._assert_connected()
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            # Give React/SPA time to hydrate — wait for network to quiet down
            try:
                self._page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass  # networkidle timeout is non-fatal
        except Exception as e:
            raise LocalBrowserError(f"Navigation failed to {url}: {e}") from e

    def snapshot(self) -> str:
        """Return visible page text (approximates MCP accessibility snapshot)."""
        self._assert_connected()
        try:
            return self._page.inner_text("body") or ""
        except Exception:
            return ""

    def get_text(self) -> str:
        """Alias for snapshot() — returns visible page text."""
        return self.snapshot()

    def evaluate(self, code: str) -> Any:
        """Execute JavaScript in the page context and return the result."""
        self._assert_connected()
        # The MCP client wraps JS in `() => { ... }` arrow functions.
        # Playwright's evaluate() accepts that format directly.
        try:
            result = self._page.evaluate(code)
            return result
        except Exception as e:
            raise LocalBrowserError(f"JS evaluation failed: {e}") from e

    def click(self, element_label: str, ref: Optional[str] = None) -> None:
        """Click the first visible, enabled element matching the given label.

        Uses Playwright's semantic locators in priority order so it handles
        React's dynamic DOM and shadow DOM correctly.
        """
        self._assert_connected()
        page = self._page
        timeout = 4_000

        # Strategy 1: semantic role locators (most reliable for buttons/links)
        for role in ("button", "link", "menuitem", "tab", "option"):
            try:
                loc = page.get_by_role(role, name=element_label)  # exact=False by default
                if loc.first.is_visible():
                    loc.first.click(timeout=timeout)
                    return
            except Exception:
                pass
            # Case-insensitive partial match
            try:
                loc = page.get_by_role(role, name=element_label, exact=False)
                visible = [el for el in loc.all() if el.is_visible()]
                if visible:
                    visible[0].click(timeout=timeout)
                    return
            except Exception:
                pass

        # Strategy 2: get_by_text (exact, then partial)
        for exact in (True, False):
            try:
                loc = page.get_by_text(element_label, exact=exact)
                visible = [el for el in loc.all() if el.is_visible()]
                if visible:
                    visible[0].click(timeout=timeout)
                    return
            except Exception:
                pass

        # Strategy 3: CSS / attribute selectors
        css_selectors = [
            f'[aria-label="{element_label}"]',
            f'[aria-label*="{element_label}" i]',
            f'[title="{element_label}"]',
            f'[title*="{element_label}" i]',
            f'[data-testid*="{element_label.lower().replace(" ", "-")}"]',
            f'button:has-text("{element_label}")',
            f'a:has-text("{element_label}")',
            f'[type="submit"]',   # last resort for form submission
        ]
        for sel in css_selectors:
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    loc.click(timeout=timeout)
                    return
            except Exception:
                continue

        raise LocalBrowserError(
            f"Cannot click: element not found: {element_label!r}. "
            f"Page title: {page.title()!r}"
        )

    def type_text(
        self,
        element_label: str,
        text: str,
        ref: Optional[str] = None,
        submit: bool = False,
    ) -> None:
        """Find an input field and fill it — works with React controlled inputs.

        Tries Playwright's semantic locators first, then CSS attribute selectors.
        Uses fill() which correctly triggers React's onChange synthetic event.
        """
        self._assert_connected()
        page = self._page
        timeout = 4_000

        # Strategy 1: get_by_label (matches <label> elements, aria-label, aria-labelledby)
        try:
            loc = page.get_by_label(element_label, exact=False)
            visible = [el for el in loc.all() if el.is_visible()]
            if visible:
                self._react_fill(visible[0], text, submit)
                return
        except Exception:
            pass

        # Strategy 2: get_by_placeholder
        try:
            loc = page.get_by_placeholder(element_label, exact=False)
            visible = [el for el in loc.all() if el.is_visible()]
            if visible:
                self._react_fill(visible[0], text, submit)
                return
        except Exception:
            pass

        # Strategy 3: CSS attribute selectors
        label_lower = element_label.lower()
        css_selectors = [
            f'input[placeholder*="{element_label}" i]',
            f'input[aria-label*="{element_label}" i]',
            f'input[name*="{label_lower}"]',
            f'input[id*="{label_lower}"]',
            f'textarea[placeholder*="{element_label}" i]',
            f'textarea[aria-label*="{element_label}" i]',
        ]
        # For common field names add type-specific selectors
        if label_lower in ("email", "e-mail"):
            css_selectors = ['input[type="email"]'] + css_selectors
        elif label_lower == "password":
            css_selectors = ['input[type="password"]'] + css_selectors

        for sel in css_selectors:
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    self._react_fill(loc, text, submit)
                    return
            except Exception:
                continue

        raise LocalBrowserError(
            f"Cannot type: input field not found: {element_label!r}. "
            f"Page title: {page.title()!r}"
        )

    def _react_fill(self, locator: Any, text: str, submit: bool = False) -> None:
        """Fill an input and dispatch React synthetic events so state updates.

        Playwright's fill() triggers the 'input' event, which is enough for
        most React forms.  For stubborn controlled inputs we also dispatch
        'change'.  Then optionally press Enter if submit=True.
        """
        locator.click(timeout=3_000)        # focus the field
        locator.fill(text, timeout=5_000)   # triggers React's onChange via 'input' event
        # Dispatch additional events for React that requires 'change'
        try:
            locator.dispatch_event("change")
        except Exception:
            pass
        if submit:
            locator.press("Enter")

    def wait(
        self,
        text: Optional[str] = None,
        text_gone: Optional[str] = None,
        seconds: float = 0,
    ) -> None:
        """Wait for text to appear, disappear, or a fixed delay."""
        self._assert_connected()
        try:
            if seconds > 0:
                time.sleep(seconds)
            if text:
                self._page.wait_for_selector(
                    f"text={text}", timeout=30_000
                )
            if text_gone:
                self._page.wait_for_selector(
                    f"text={text_gone}", state="hidden", timeout=30_000
                )
        except Exception:
            pass

    def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        self._assert_connected()
        try:
            self._page.keyboard.press(key)
        except Exception as e:
            raise LocalBrowserError(f"Press key failed: {e}") from e

    def screenshot(self) -> Optional[str]:
        """Take a screenshot and return base64-encoded PNG."""
        self._assert_connected()
        try:
            import base64
            data = self._page.screenshot()
            return base64.b64encode(data).decode()
        except Exception:
            return None

    # snapshot_refs is used by PlaywrightMcpClient — provide a stub
    def snapshot_refs(self) -> dict[str, str]:
        return {}

    # find_ref is used by PlaywrightMcpClient — provide a stub
    def find_ref(self, *labels: str) -> tuple[str, str]:
        raise LocalBrowserError(f"find_ref not available in local browser mode: {labels}")

    # ------------------------------------------------------------------ #
    # CAPTCHA / verification page detection and pause
    # ------------------------------------------------------------------ #

    def wait_for_human_captcha_solve(self, timeout: int = CAPTCHA_WAIT_SECONDS) -> None:
        """
        Print a prominent banner to the console, then poll the page every 3 seconds
        until the CAPTCHA / verification page is gone.

        The browser window is already visible — the user just needs to switch to it
        and solve the challenge.  Once the page is past the CAPTCHA, execution resumes
        automatically.

        Args:
            timeout: Maximum seconds to wait before giving up.

        Raises:
            LocalBrowserError: If the CAPTCHA is not solved within `timeout` seconds.
        """
        self._assert_connected()

        _print_captcha_banner(timeout)

        deadline = time.time() + timeout
        poll_interval = 3
        elapsed = 0

        while time.time() < deadline:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                page_text = (self._page.inner_text("body") or "").lower()[:3000]
                title = (self._page.title() or "").lower()
                url = self._page.url or ""
            except Exception:
                continue

            still_captcha = (
                "captcha" in page_text
                or "robot" in page_text
                or "cloudflare" in page_text
                or "verify you" in page_text
                or "just a moment" in title
                or "challenge" in url
            )

            if not still_captcha:
                remaining = int(deadline - time.time())
                logger.info(
                    "✅ CAPTCHA solved by user after %ds — resuming automation.",
                    elapsed,
                )
                _print_captcha_resolved()
                return

            remaining = int(deadline - time.time())
            logger.info(
                "⏳ Waiting for CAPTCHA to be solved... %ds remaining "
                "(switch to the browser window and solve it)",
                remaining,
            )

        raise LocalBrowserError(
            f"CAPTCHA was not solved within {timeout}s. "
            "Please solve it faster next time and retry.",
            retryable=False,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _assert_connected(self) -> None:
        if not self._connected or self._page is None:
            raise LocalBrowserError.non_retryable(
                "LocalBrowserClient is not connected. Call connect() first."
            )


# ---------------------------------------------------------------------------
# Console banners
# ---------------------------------------------------------------------------

def _print_captcha_banner(timeout: int) -> None:
    sep = "=" * 65
    msg = f"""
{sep}
  🔴  CAPTCHA DETECTED — HUMAN ACTION REQUIRED
{sep}

  A CAPTCHA or verification page has appeared in the browser.

  👉  Switch to the browser window that just opened.
  👉  Complete the CAPTCHA / verification challenge.
  👉  Do NOT close the browser window.

  ⏱️  You have {timeout // 60} minutes ({timeout}s) to solve it.
      Automation will resume automatically once the page is clear.

{sep}
"""
    print(msg, flush=True)
    logger.warning("CAPTCHA detected — waiting for manual solve (timeout=%ds)", timeout)


def _print_captcha_resolved() -> None:
    sep = "=" * 65
    msg = f"""
{sep}
  ✅  CAPTCHA SOLVED — Resuming automation...
{sep}
"""
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Factory function (mirrors create_mcp_client API)
# ---------------------------------------------------------------------------

def create_local_browser_client(headless: bool = False, slow_mo: int = 50) -> LocalBrowserClient:
    """Create and connect a local visible Chromium browser client.

    Args:
        headless: Set True only for testing without display.
        slow_mo:  Milliseconds delay between each Playwright action
                  (makes automation easier to follow visually).
    Returns:
        A connected LocalBrowserClient ready to use.
    """
    client = LocalBrowserClient(headless=headless, slow_mo=slow_mo)
    client.connect()
    return client
