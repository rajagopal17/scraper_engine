from __future__ import annotations

import logging
import os

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .config import Settings
from .models import AuthConfig

logger = logging.getLogger(__name__)

_RETRYABLE = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError)

_USER_AGENT = "scraper-engine/1.0 (+authorized data collection)"


class NonRetryableFetchError(Exception):
    """4xx (other than throttling) / blocked / parse failure — do not retry within this run."""


def fetch_static(url: str, settings: Settings) -> str:
    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential_jitter(initial=settings.retry_backoff_base_seconds, max=settings.retry_backoff_max_seconds),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    def _get() -> httpx.Response:
        return httpx.get(
            url,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )

    resp = _get()
    if resp.status_code == 404 or resp.status_code == 403:
        raise NonRetryableFetchError(f"{resp.status_code} for {url}")
    resp.raise_for_status()
    return resp.text


def fetch_rendered(url: str, settings: Settings, auth: AuthConfig | None = None) -> str:
    """Fetch a JS-rendered page via Playwright, optionally logging in first.

    Login is performed once per call (callers should reuse a session/context
    across all requests to the same domain within a run, not log in per field).
    """
    from playwright.sync_api import sync_playwright  # imported lazily: heavy, optional dep

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(user_agent=_USER_AGENT)
        page = context.new_page()
        page.set_default_timeout(settings.http_timeout_seconds * 1000)

        if auth and auth.login_type == "form":
            username = os.environ.get(auth.username_env or "", "")
            password = os.environ.get(auth.password_env or "", "")
            if not username or not password:
                raise NonRetryableFetchError(
                    f"login required for {url} but credentials env vars "
                    f"{auth.username_env!r}/{auth.password_env!r} are not set"
                )
            page.goto(auth.login_url or url)
            page.fill(auth.username_selector, username)
            page.fill(auth.password_selector, password)
            page.click(auth.submit_selector)
            page.wait_for_load_state("networkidle")

        page.goto(url)
        page.wait_for_load_state("networkidle")
        html = page.content()
        browser.close()
        return html


def fetch(url: str, settings: Settings, fetch_method: str, auth: AuthConfig | None = None) -> str:
    if fetch_method == "rendered":
        return fetch_rendered(url, settings, auth)
    return fetch_static(url, settings)
