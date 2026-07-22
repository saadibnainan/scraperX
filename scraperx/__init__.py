"""scraperX — a resilient, JavaScript-executing web scraper.

Public API:
    Config          — runtime configuration (loaded from .env + overrides)
    ScraperEngine   — the Playwright-backed scraping/crawling engine
    ProxyRotator    — round-robin proxy selection
    UserAgentRotator— round-robin User-Agent selection
    DataExporter    — pandas-backed CSV export
"""

from .config import Config
from .rotators import ProxyRotator, UserAgentRotator
from .engine import ScraperEngine, FetchResult
from .exporter import DataExporter

__version__ = "0.1.0"

__all__ = [
    "Config",
    "ScraperEngine",
    "FetchResult",
    "ProxyRotator",
    "UserAgentRotator",
    "DataExporter",
    "__version__",
]
