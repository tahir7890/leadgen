"""Apify jiri-spilka/playwright-mcp-server HTTP MCP client.

The Playwright MCP server exposes tools with the 'browser_' prefix:
  - browser_navigate
  - browser_snapshot  (accessibility tree / page text)
  - browser_evaluate  (run JS in page context)
  - browser_wait_for  (wait for selector or ms timeout)
  - browser_click
  - browser_type
  - browser_screenshot

Reference: https://github.com/microsoft/playwright-mcp
Apify actor: https://apify.com/jiri-spilka/playwright-mcp-server
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

# Error texts that should NOT be retried — retrying makes them worse or wastes time
_NON_RETRYABLE_PHRASES = (
    "browser is already in use",
    "already in use",
    "401",
    "unauthorized",
    "not found",
    "404",
    "approve",
    "permission denied",
    "invalid api key",
    "no tool named",
    "unknown tool",
)


class McpError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable

    @classmethod
    def non_retryable(cls, msg: str) -> "McpError":
        return cls(msg, retryable=False)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, McpError):
        # Check for phrases that should never be retried
        msg_lower = str(exc).lower()
        if any(p in msg_lower for p in _NON_RETRYABLE_PHRASES):
            return False
        return exc.retryable
    return True


class PlaywrightMcpClient:
    """Synchronous HTTP client for the Playwright MCP server (JSON-RPC 2.0).

    Each instance generates a unique session ID so concurrent workers
    don't share the same browser profile (fixes 'browser already in use').
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.apify_mcp_url
        self._token = settings.apify_token
        # Session ID is assigned by the server during initialize.
        # We start with None and capture it from the response headers.
        self._session_id: Optional[str] = None
        self._request_id = 0
        self._connected = False
        self._client = httpx.Client(timeout=120.0)

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        """Send MCP initialize handshake and claim a dedicated browser session."""
        if not self._token:
            raise McpError.non_retryable(
                "APIFY_TOKEN is not set. Cannot connect to Playwright MCP server. "
                "Add APIFY_TOKEN=apify_api_... to your .env file."
            )

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lead-gen-backend", "version": "2.0.0"},
            },
        }
        try:
            response = self._post_raw(payload)
        except McpError as e:
            raise McpError.non_retryable(
                f"MCP initialize failed: {e}. "
                "Check APIFY_TOKEN and APIFY_MCP_URL in your .env file."
            ) from e

        if "error" in response:
            raise McpError.non_retryable(self._format_error(response["error"]))

        # Send initialized notification (fire-and-forget)
        try:
            self._post_raw(
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                expect_response=False,
            )
        except Exception:
            pass  # Non-fatal

        self._connected = True
        logger.info(
            "Connected to Playwright MCP at %s (session=%s)",
            self._url,
            (self._session_id or "none")[:16],
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        self._connected = False

    # ------------------------------------------------------------------ #
    # Core tool call (with retry)
    # ------------------------------------------------------------------ #

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=3, max=20),
        retry=retry_if_exception(_is_retryable),
        reraise=True,  # re-raises the original exception, not RetryError
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
        """Call a named MCP tool with arguments and return the parsed result."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        response = self._post_raw(payload)
        if "error" in response:
            err_msg = self._format_error(response["error"])
            # Detect non-retryable browser errors
            err_lower = err_msg.lower()
            retryable = not any(p in err_lower for p in _NON_RETRYABLE_PHRASES)
            raise McpError(err_msg, retryable=retryable)
        result = response.get("result", {})
        if isinstance(result, dict) and result.get("isError"):
            err_text = self._extract_text_content(result)
            err_lower = err_text.lower()
            retryable = not any(p in err_lower for p in _NON_RETRYABLE_PHRASES)
            raise McpError(err_text, retryable=retryable)
        return self._parse_result(result)

    # ------------------------------------------------------------------ #
    # High-level browser helpers (browser_* tool names)
    # ------------------------------------------------------------------ #

    def navigate(self, url: str) -> None:
        """Navigate the browser to a URL."""
        self.call_tool("browser_navigate", {"url": url})

    def snapshot(self) -> str:
        """Get the accessibility snapshot / page text via browser_snapshot."""
        result = self.call_tool("browser_snapshot")
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get("text", "") or str(result)
        return str(result) if result else ""

    def get_text(self) -> str:
        """Get visible page text from the accessibility snapshot."""
        try:
            return self.snapshot()
        except McpError:
            return ""

    def snapshot_refs(self) -> dict[str, str]:
        """Parse the accessibility snapshot to extract label->ref mappings.

        The snapshot YAML looks like:
          - textbox "Email" [ref=e23]
          - textbox "Password" [ref=e24]
          - button "Log in" [ref=e25]

        Returns a dict like: {'Email textbox': 'e23', 'Password textbox': 'e24', ...}
        """
        import re
        snap = self.snapshot()
        refs: dict[str, str] = {}
        # Match patterns like: - type "label" [ref=eXX]
        pattern = re.compile(
            r'-\s*(\w+)\s+"([^"]+)"[^\[]*\[ref=([^\]]+)\]',
            re.IGNORECASE,
        )
        for m in pattern.finditer(snap):
            kind = m.group(1).lower()   # textbox, button, link, etc.
            label = m.group(2)           # visible label
            ref = m.group(3)             # e23, e24, etc.
            refs[label] = ref
            refs[f"{label} {kind}"] = ref
            refs[f"{kind}:{label}"] = ref
        return refs

    def find_ref(self, *labels: str) -> tuple[str, str]:
        """Take a snapshot and find the first ref matching any of the given labels.

        Returns (label, ref) tuple or raises McpError if not found.
        """
        refs = self.snapshot_refs()
        snap_lower = {k.lower(): (k, v) for k, v in refs.items()}
        for label in labels:
            # Exact match
            if label in refs:
                return label, refs[label]
            # Case-insensitive
            if label.lower() in snap_lower:
                orig, ref = snap_lower[label.lower()]
                return orig, ref
            # Partial match
            for key, (orig, ref) in snap_lower.items():
                if label.lower() in key:
                    return orig, ref
        raise McpError(
            f"Element not found in snapshot. Tried: {labels}. "
            f"Available refs: {list(refs.keys())[:20]}"
        )

    def evaluate(self, code: str) -> Any:
        """Execute JavaScript in the browser page context."""
        result = self.call_tool("browser_evaluate", {"function": code})
        if isinstance(result, str):
            # Parse Playwright MCP v0.0.36 markdown response
            # Format: ### Result\n{ "json": "here" }\n\n### Ran Playwright code
            if "### Result" in result:
                import re
                import json
                match = re.search(r"### Result\s*\n(.*?)(?=\n### |$)", result, re.DOTALL)
                if match:
                    json_str = match.group(1).strip()
                    if json_str.startswith("```json"):
                        json_str = json_str[7:-3].strip()
                    elif json_str.startswith("```"):
                        json_str = json_str[3:-3].strip()
                    try:
                        return json.loads(json_str)
                    except Exception:
                        return json_str
        return result

    def click(self, element_label: str, ref: Optional[str] = None) -> None:
        """Click an element by its accessibility label + ref.

        If ref is None, takes a fresh snapshot to find the ref automatically.
        """
        if ref is None:
            try:
                found_label, ref = self.find_ref(element_label)
                element_label = found_label
            except McpError:
                raise McpError(f"Cannot click: element not found in snapshot: {element_label!r}")
        self.call_tool("browser_click", {"element": element_label, "ref": ref})

    def type_text(self, element_label: str, text: str, ref: Optional[str] = None, submit: bool = False) -> None:
        """Type text into an input by its accessibility label + ref.

        If ref is None, takes a fresh snapshot to find the ref automatically.
        """
        if ref is None:
            try:
                found_label, ref = self.find_ref(element_label)
                element_label = found_label
            except McpError:
                raise McpError(f"Cannot type: element not found in snapshot: {element_label!r}")
        args: dict[str, Any] = {"element": element_label, "ref": ref, "text": text}
        if submit:
            args["submit"] = True
        self.call_tool("browser_type", args)

    def fill_form(self, fields: list[dict[str, Any]]) -> None:
        """Fill multiple form fields at once using browser_fill_form.

        Each field dict must have 'element' (label) and 'ref' keys,
        plus 'value' for the text to fill.
        Example: [{'element': 'Email', 'ref': 'e23', 'value': 'me@example.com'}]
        """
        self.call_tool("browser_fill_form", {"fields": fields})

    def press_key(self, key: str) -> None:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        self.call_tool("browser_press_key", {"key": key})

    def wait(self, text: Optional[str] = None, text_gone: Optional[str] = None, seconds: float = 0) -> None:
        """Wait for text to appear, disappear, or just a time delay."""
        try:
            args: dict[str, Any] = {}
            if seconds > 0:
                args["time"] = seconds
            if text:
                args["text"] = text
            if text_gone:
                args["textGone"] = text_gone
            if args:
                self.call_tool("browser_wait_for", args)
            else:
                time.sleep(1)
        except McpError:
            pass

    def screenshot(self) -> Optional[str]:
        """Take a screenshot and return base64 PNG data."""
        try:
            result = self.call_tool("browser_take_screenshot")
            if isinstance(result, dict):
                return result.get("data") or result.get("image")
            return str(result) if result else None
        except McpError:
            return None

    def _extract_texts(self, obj: Any, out: list[str]) -> None:
        """Recursively extract text values from a nested dict/list."""
        if isinstance(obj, str):
            if obj.strip():
                out.append(obj.strip())
        elif isinstance(obj, dict):
            for v in obj.values():
                self._extract_texts(v, out)
        elif isinstance(obj, list):
            for item in obj:
                self._extract_texts(item, out)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        # Only send session ID after it has been assigned by the server
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    def _post_raw(
        self, payload: dict[str, Any], expect_response: bool = True
    ) -> dict[str, Any]:
        """Low-level POST — no retry logic. Raises McpError on transport failures."""
        try:
            response = self._client.post(
                self._url, headers=self._headers(), json=payload
            )
        except httpx.TimeoutException as e:
            raise McpError(f"Request timed out: {e}", retryable=True) from e
        except httpx.ConnectError as e:
            raise McpError(
                f"Cannot connect to MCP server at {self._url}: {e}. "
                "Check APIFY_MCP_URL and network access.",
                retryable=True,
            ) from e
        except httpx.HTTPError as e:
            raise McpError(f"HTTP error: {e}", retryable=True) from e

        # Capture session id from response headers (actor may assign one)
        resp_session = response.headers.get("mcp-session-id")
        if resp_session:
            self._session_id = resp_session

        if response.status_code == 401:
            raise McpError.non_retryable(
                "MCP server returned 401 Unauthorized. "
                "Check your APIFY_TOKEN in .env."
            )
        if response.status_code == 404:
            raise McpError.non_retryable(
                f"MCP server URL not found (404): {self._url}. "
                "Check APIFY_MCP_URL in .env."
            )
        if response.status_code >= 500:
            raise McpError(
                f"MCP server error {response.status_code}: {response.text[:300]}",
                retryable=True,
            )
        if response.status_code >= 400:
            raise McpError.non_retryable(
                f"MCP request failed {response.status_code}: {response.text[:300]}"
            )

        if not expect_response:
            return {}

        data = self._parse_body(response)
        return data if isinstance(data, dict) else {"result": data}

    def _parse_body(self, response: httpx.Response) -> Any:
        text = response.text.strip()
        if not text:
            return {}
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type or text.startswith("data:"):
            return self._parse_sse(text)
        try:
            return response.json()
        except Exception:
            return {"result": {"content": [{"type": "text", "text": text}]}}

    def _parse_sse(self, text: str) -> dict[str, Any]:
        """Parse Server-Sent Events.

        Finds the JSON-RPC response event (has 'result' or 'error' key).
        Falls back to the last valid JSON event if no explicit result found.
        """
        last: Optional[dict[str, Any]] = None
        result_event: Optional[dict[str, Any]] = None

        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    continue
                last = parsed
                # Prefer the event that has a JSON-RPC result or error
                if "result" in parsed or "error" in parsed:
                    result_event = parsed
            except json.JSONDecodeError:
                continue

        return result_event or last or {}

    def _parse_result(self, result: Any) -> Any:
        """Extract useful value from an MCP tool result."""
        if not isinstance(result, dict):
            return result
        content = result.get("content", [])
        if not content:
            return result
        texts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        combined = "\n".join(t for t in texts if t).strip()
        if not combined:
            return result
        try:
            return json.loads(combined)
        except json.JSONDecodeError:
            return combined

    def _extract_text_content(self, result: Any) -> str:
        if not isinstance(result, dict):
            return str(result)
        content = result.get("content", [])
        return "\n".join(
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )

    def _format_error(self, error: Any) -> str:
        if isinstance(error, dict):
            msg = error.get("message", str(error))
            code = error.get("code", "")
            msg_str = str(msg)
            if "approve" in msg_str.lower() or "permission" in msg_str.lower():
                return (
                    "Apify actor needs approval. "
                    "Go to https://console.apify.com, find 'jiri-spilka/playwright-mcp-server', "
                    "and approve it for your account. Then retry."
                )
            return f"[{code}] {msg_str}" if code else msg_str
        return str(error)


def _abort_stuck_apify_runs() -> int:
    """Use Apify REST API to abort all running actor instances to release the browser lock.

    Returns the number of runs aborted.
    """
    settings = get_settings()
    token = settings.apify_token
    if not token:
        return 0

    aborted = 0
    try:
        list_url = f"https://api.apify.com/v2/actor-runs?status=RUNNING&limit=10&token={token}"
        r = httpx.get(list_url, timeout=15)
        if r.status_code != 200:
            return 0
        items = r.json().get("data", {}).get("items", [])
        for item in items:
            run_id = item.get("id")
            if not run_id:
                continue
            abort_url = f"https://api.apify.com/v2/actor-runs/{run_id}/abort?token={token}"
            r2 = httpx.post(abort_url, timeout=15)
            if r2.status_code == 200:
                aborted += 1
                logger.info("Aborted Apify run %s to release browser lock", run_id)
            else:
                logger.warning(
                    "Failed to abort Apify run %s: %s", run_id, r2.text[:100]
                )
    except Exception as e:
        logger.warning("Could not abort Apify runs: %s", e)

    return aborted


def create_mcp_client(max_browser_lock_retries: int = 3) -> PlaywrightMcpClient:
    """Create and connect a new Playwright MCP client.

    The Apify actor uses a single shared Chrome process. If the browser is
    locked by a previous session that didn't clean up, we abort the stuck
    actor run via the Apify REST API and retry.
    """
    for attempt in range(max_browser_lock_retries + 1):
        client = PlaywrightMcpClient()
        try:
            client.connect()
            # Probe the browser immediately so we know it's actually free
            # before starting real work. Raises McpError('already in use')
            # if the Chrome profile is still locked by a previous run.
            client.snapshot()
            return client
        except McpError as e:
            msg = str(e).lower()
            if "already in use" in msg and attempt < max_browser_lock_retries:
                logger.warning(
                    "Browser locked on Apify (attempt %d/%d). "
                    "Aborting stuck runs via REST API...",
                    attempt + 1,
                    max_browser_lock_retries,
                )
                try:
                    client.close()
                except Exception:
                    pass
                # Abort stuck runs first
                aborted = _abort_stuck_apify_runs()
                # Wait for abort + Chrome process cleanup
                wait_secs = 10 + (5 * attempt)
                logger.info(
                    "Aborted %d runs. Waiting %ds for Chrome to release...",
                    aborted,
                    wait_secs,
                )
                time.sleep(wait_secs)
                continue
            # Non-retryable or ran out of retries
            try:
                client.close()
            except Exception:
                pass
            raise
    # Should not reach here
    raise McpError("Failed to acquire browser after retries", retryable=False)
