"""Configuration for scraperX.

`Config` gathers every tunable in one typed object. Values come from the
environment (a `.env` file loaded via python-dotenv), each with a sensible
default, and may be overridden per-run by the CLI or GUI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_TRUE = {"1", "true", "t", "yes", "y", "on"}
_FALSE = {"0", "false", "f", "no", "n", "off"}


def _get(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return default if val is None else val


def _as_bool(value: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def _as_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_float(value: str, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_list(value: str) -> List[str]:
    """Split a comma- or newline-separated string into a clean list."""
    if not value:
        return []
    parts: List[str] = []
    for chunk in value.replace("\r", "\n").split("\n"):
        for item in chunk.split(","):
            item = item.strip()
            if item:
                parts.append(item)
    return parts


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration. Build with :meth:`from_env`."""

    # Target
    target_url: str = ""
    selector: str = ""

    # Browser
    headless: bool = True
    # Optional explicit Chromium binary (e.g. a bundled browser shipped with a
    # PyInstaller build, or a system Chromium). Empty = Playwright's default.
    chromium_executable_path: str = ""

    # Proxy — single
    proxy_url: str = ""
    proxy_username: str = ""
    proxy_password: str = ""
    # Proxy — rotation pool
    proxy_list: List[str] = field(default_factory=list)

    # Fingerprint / User-Agent
    user_agents: List[str] = field(default_factory=list)

    # Resilience
    max_retries: int = 4
    backoff_base: float = 2.0
    backoff_max: float = 60.0
    jitter: bool = True

    # Timeouts (ms)
    request_timeout_ms: int = 30000
    nav_timeout_ms: int = 45000

    # Crawl behaviour
    concurrency: int = 1
    crawl_depth: int = 1
    rate_limit_ms: int = 1000
    same_domain: bool = True
    extract_links: bool = True

    # Output & logging
    output_path: str = "output/results.csv"
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, dotenv_path: Optional[str] = None, **overrides) -> "Config":
        """Build a Config from environment/.env, then apply keyword overrides.

        Overrides whose value is ``None`` are ignored, so callers can pass
        optional CLI flags directly without clobbering env-derived values.
        """
        # load_dotenv is a no-op if the file is absent; never raises.
        load_dotenv(dotenv_path=dotenv_path, override=False)

        cfg = cls(
            target_url=_get("TARGET_URL"),
            selector=_get("SELECTOR"),
            headless=_as_bool(_get("HEADLESS"), True),
            chromium_executable_path=_get("CHROMIUM_EXECUTABLE_PATH"),
            proxy_url=_get("PROXY_URL"),
            proxy_username=_get("PROXY_USERNAME"),
            proxy_password=_get("PROXY_PASSWORD"),
            proxy_list=_as_list(_get("PROXY_LIST")),
            user_agents=_as_list(_get("USER_AGENTS")),
            max_retries=_as_int(_get("MAX_RETRIES"), 4),
            backoff_base=_as_float(_get("BACKOFF_BASE"), 2.0),
            backoff_max=_as_float(_get("BACKOFF_MAX"), 60.0),
            jitter=_as_bool(_get("JITTER"), True),
            request_timeout_ms=_as_int(_get("REQUEST_TIMEOUT_MS"), 30000),
            nav_timeout_ms=_as_int(_get("NAV_TIMEOUT_MS"), 45000),
            concurrency=_as_int(_get("CONCURRENCY"), 1),
            crawl_depth=_as_int(_get("CRAWL_DEPTH"), 1),
            rate_limit_ms=_as_int(_get("RATE_LIMIT_MS"), 1000),
            same_domain=_as_bool(_get("SAME_DOMAIN"), True),
            extract_links=_as_bool(_get("EXTRACT_LINKS"), True),
            output_path=_get("OUTPUT_PATH") or "output/results.csv",
            log_level=(_get("LOG_LEVEL") or "INFO").upper(),
        )

        for key, value in overrides.items():
            if value is None:
                continue
            if not hasattr(cfg, key):
                raise AttributeError(f"Unknown config override: {key!r}")
            setattr(cfg, key, value)

        cfg.validate()
        return cfg

    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Raise ValueError on nonsensical values."""
        errors = []
        if self.max_retries < 0:
            errors.append("max_retries must be >= 0")
        if self.backoff_base < 1:
            errors.append("backoff_base must be >= 1")
        if self.backoff_max <= 0:
            errors.append("backoff_max must be > 0")
        if self.crawl_depth < 0:
            errors.append("crawl_depth must be >= 0")
        if self.concurrency < 1:
            errors.append("concurrency must be >= 1")
        if self.rate_limit_ms < 0:
            errors.append("rate_limit_ms must be >= 0")
        if self.request_timeout_ms <= 0 or self.nav_timeout_ms <= 0:
            errors.append("timeouts must be > 0")
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level not in valid_levels:
            errors.append(f"log_level must be one of {sorted(valid_levels)}")
        if errors:
            raise ValueError("Invalid configuration: " + "; ".join(errors))

    # ------------------------------------------------------------------
    def redacted(self) -> dict:
        """Return a dict of the config with secrets masked, for logging."""
        def mask(v: str) -> str:
            return "***" if v else ""

        data = self.__dict__.copy()
        data["proxy_password"] = mask(self.proxy_password)
        data["proxy_username"] = mask(self.proxy_username)
        data["proxy_url"] = mask(self.proxy_url)
        data["proxy_list"] = [f"<{len(self.proxy_list)} proxies>"] if self.proxy_list else []
        return data
