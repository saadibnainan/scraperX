"""The resilient scraping engine.

`ScraperEngine` drives a headless (or headful) Chromium via Playwright:
it renders JavaScript, extracts elements by CSS selector, harvests links, and
crawls to a configured depth. Every navigation is wrapped in a tenacity retry
policy (exponential backoff + optional jitter) that fires on timeouts and on
HTTP 429/5xx responses, rotating proxy and User-Agent between attempts.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import urldefrag, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from .config import Config
from .rotators import ProxyRotator, UserAgentRotator

log = logging.getLogger("scraperx.engine")

# Statuses worth retrying: rate-limiting and transient server errors.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}

# JS run in-page to pull the target elements in one round-trip.
_ELEMENT_JS = """(sel) => Array.from(document.querySelectorAll(sel)).map((e, i) => ({
    index: i,
    tag: e.tagName ? e.tagName.toLowerCase() : '',
    text: (e.textContent || '').trim(),
    html: e.outerHTML,
    href: e.getAttribute('href'),
    src: e.getAttribute('src'),
}))"""

# JS run in-page to collect anchors as absolute URLs.
_LINK_JS = """() => Array.from(document.querySelectorAll('a[href]')).map((e) => ({
    href: e.href,
    text: (e.textContent || '').trim(),
}))"""


class RetryableError(Exception):
    """Raised on a retryable condition (timeout or retryable HTTP status)."""


@dataclass
class FetchResult:
    """Outcome of fetching a single page."""

    url: str
    status: Optional[int]
    title: str = ""
    elements: List[Dict] = field(default_factory=list)
    links: List[Dict] = field(default_factory=list)


class ScraperEngine:
    """Playwright-backed engine. Use as a context manager or call start()/stop()."""

    def __init__(
        self,
        config: Config,
        proxy_rotator: Optional[ProxyRotator] = None,
        ua_rotator: Optional[UserAgentRotator] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.proxy_rotator = proxy_rotator or ProxyRotator.from_config(config)
        self.ua_rotator = ua_rotator or UserAgentRotator.from_config(config)
        self._should_stop = should_stop or (lambda: False)
        self._log_callback = log_callback

        self._pw = None
        self._browser = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def __enter__(self) -> "ScraperEngine":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        self._info("Launching Chromium "
                   f"({'headless' if self.config.headless else 'headful'})")
        self._pw = sync_playwright().start()
        launch_kwargs = {
            "headless": self.config.headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        }
        if self.config.chromium_executable_path:
            launch_kwargs["executable_path"] = self.config.chromium_executable_path
        self._browser = self._pw.chromium.launch(**launch_kwargs)

    def stop(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            self._browser = None
            if self._pw is not None:
                self._pw.stop()
                self._pw = None

    # ------------------------------------------------------------------
    # Logging helper (routes to the standard logger and any GUI callback)
    # ------------------------------------------------------------------
    def _info(self, msg: str) -> None:
        log.info(msg)
        if self._log_callback:
            self._log_callback(msg)

    def _warn(self, msg: str) -> None:
        log.warning(msg)
        if self._log_callback:
            self._log_callback("WARNING: " + msg)

    # ------------------------------------------------------------------
    # Single fetch (one attempt)
    # ------------------------------------------------------------------
    def _fetch_once(self, url: str) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("Engine not started; call start() first.")

        proxy = self.proxy_rotator.next()
        user_agent = self.ua_rotator.next()

        context = self._browser.new_context(
            user_agent=user_agent,
            proxy=proxy,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            ignore_https_errors=True,
        )
        try:
            page = context.new_page()
            page.set_default_timeout(self.config.request_timeout_ms)
            page.set_default_navigation_timeout(self.config.nav_timeout_ms)
            self._apply_stealth(page)

            try:
                response = page.goto(url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError as exc:
                raise RetryableError(f"navigation timeout: {exc}") from exc

            status = response.status if response is not None else None
            if status in RETRYABLE_STATUSES:
                raise RetryableError(f"HTTP {status}")

            # Give SPA/JS content a chance to settle. Network idle can legitimately
            # never fire on chatty pages, so a timeout here is non-fatal.
            try:
                page.wait_for_load_state("networkidle",
                                         timeout=self.config.nav_timeout_ms)
            except PlaywrightTimeoutError:
                pass

            elements: List[Dict] = []
            if self.config.selector:
                try:
                    page.wait_for_selector(
                        self.config.selector,
                        timeout=self.config.request_timeout_ms,
                        state="attached",
                    )
                except PlaywrightTimeoutError:
                    self._warn(f"selector {self.config.selector!r} not found on {url}")
                try:
                    elements = page.evaluate(_ELEMENT_JS, self.config.selector) or []
                except PlaywrightError as exc:
                    self._warn(f"element extraction failed on {url}: {exc}")

            links: List[Dict] = []
            try:
                links = page.evaluate(_LINK_JS) or []
            except PlaywrightError:
                links = []

            title = ""
            try:
                title = page.title()
            except PlaywrightError:
                pass

            return FetchResult(url=url, status=status, title=title,
                               elements=elements, links=links)
        finally:
            context.close()

    def _apply_stealth(self, page) -> None:
        """Apply playwright-stealth patches if the library is available.

        Supports both API lines defensively:
          * 1.x exposes the ``stealth_sync(page)`` function
          * 2.x exposes ``Stealth().apply_stealth_sync(page)``
        A missing or differently-versioned package never crashes a scrape.
        """
        # 1.x API
        try:
            from playwright_stealth import stealth_sync  # type: ignore

            stealth_sync(page)
            return
        except Exception:
            pass

        # 2.x API
        try:
            from playwright_stealth import Stealth  # type: ignore

            Stealth().apply_stealth_sync(page)
            return
        except Exception:
            # No usable stealth available — continue without it.
            pass

    # ------------------------------------------------------------------
    # Fetch with retry policy
    # ------------------------------------------------------------------
    def fetch(self, url: str) -> FetchResult:
        wait = wait_exponential(
            multiplier=1,
            exp_base=self.config.backoff_base,
            max=self.config.backoff_max,
        )
        if self.config.jitter:
            wait = wait + wait_random(0, 1)

        def _before_sleep(retry_state) -> None:
            exc = retry_state.outcome.exception()
            self._warn(
                f"retry {url} (attempt {retry_state.attempt_number}/"
                f"{self.config.max_retries + 1}): {exc}"
            )

        retryer = Retrying(
            stop=stop_after_attempt(self.config.max_retries + 1),
            wait=wait,
            retry=retry_if_exception_type(RetryableError),
            before_sleep=_before_sleep,
            reraise=True,
        )
        return retryer(self._fetch_once, url)

    # ------------------------------------------------------------------
    # Crawl (BFS to depth)
    # ------------------------------------------------------------------
    def run(self) -> List[Dict]:
        """Crawl from ``config.target_url`` and return a list of record dicts."""
        if not self.config.target_url:
            raise ValueError("No target URL configured.")

        start_url = self.config.target_url
        start_host = urlparse(start_url).netloc

        visited: set = set()
        queue: List[tuple] = [(start_url, 0)]
        records: List[Dict] = []

        while queue:
            if self._should_stop():
                self._info("Stop requested — halting crawl.")
                break

            url, depth = queue.pop(0)
            norm = self._normalize(url)
            if norm in visited:
                continue
            visited.add(norm)

            try:
                result = self.fetch(url)
            except RetryableError as exc:
                self._warn(f"giving up on {url} after retries: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — never let one page kill the crawl
                self._warn(f"error scraping {url}: {exc}")
                continue

            records.extend(self._build_records(result, depth))
            self._info(
                f"scraped {url} [status={result.status}] "
                f"elements={len(result.elements)} links={len(result.links)} "
                f"(depth {depth})"
            )

            if depth < self.config.crawl_depth:
                for link in result.links:
                    href = link.get("href")
                    if not href:
                        continue
                    if self.config.same_domain and urlparse(href).netloc != start_host:
                        continue
                    nnorm = self._normalize(href)
                    if nnorm not in visited:
                        queue.append((href, depth + 1))

            if self.config.rate_limit_ms > 0:
                time.sleep(self.config.rate_limit_ms / 1000.0)

        self._info(f"Crawl complete: {len(visited)} page(s), {len(records)} record(s).")
        return records

    # ------------------------------------------------------------------
    # Record shaping
    # ------------------------------------------------------------------
    def _build_records(self, result: FetchResult, depth: int) -> List[Dict]:
        rows: List[Dict] = []
        base = {
            "source_url": result.url,
            "depth": depth,
            "http_status": result.status,
            "page_title": result.title,
        }

        for el in result.elements:
            rows.append({
                **base,
                "record_type": "element",
                "selector": self.config.selector,
                "element_index": el.get("index"),
                "tag": el.get("tag"),
                "text": el.get("text"),
                "href": el.get("href"),
                "src": el.get("src"),
                "html": el.get("html"),
            })

        if self.config.extract_links:
            for link in result.links:
                rows.append({
                    **base,
                    "record_type": "link",
                    "text": link.get("text"),
                    "href": link.get("href"),
                })

        # If nothing was extracted and links weren't requested, still emit a
        # page-level row so the crawl is visible in the output.
        if not rows:
            rows.append({**base, "record_type": "page"})

        return rows

    @staticmethod
    def _normalize(url: str) -> str:
        """Strip the fragment so ``#a`` and ``#b`` aren't crawled as distinct."""
        return urldefrag(url)[0]
