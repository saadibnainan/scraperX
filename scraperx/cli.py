"""Command-line interface for scraperX (click).

Thin wrapper: parse flags → build :class:`Config` → run :class:`ScraperEngine`
→ export via :class:`DataExporter`.
"""

from __future__ import annotations

import logging
import sys

import click

from . import __version__
from .config import Config
from .engine import ScraperEngine
from .exporter import DataExporter
from .logconf import setup_logging

log = logging.getLogger("scraperx.cli")


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--url", "target_url", default=None,
              help="Start URL to scrape. Overrides TARGET_URL from .env.")
@click.option("--selector", default=None,
              help="CSS selector for target elements to extract.")
@click.option("--output", "output_path", default=None,
              help="CSV output path (default: OUTPUT_PATH or output/results.csv).")
@click.option("--depth", "crawl_depth", type=int, default=None,
              help="Link-crawl depth (0 = start page only).")
@click.option("--headful/--headless", "headful", default=None,
              help="Show a visible browser window (for CAPTCHA debugging).")
@click.option("--proxy", "proxy_url", default=None,
              help="Single proxy URL, e.g. http://user:pass@host:port.")
@click.option("--max-retries", type=int, default=None,
              help="Retry attempts on timeout / 429 / 5xx.")
@click.option("--rate-limit-ms", type=int, default=None,
              help="Minimum delay between requests to the same host (ms).")
@click.option("--extract-links/--no-extract-links", "extract_links", default=None,
              help="Include discovered links as rows in the CSV.")
@click.option("--per-site/--single-file", "group_by_site", default=None,
              help="Write one CSV per website named after its domain (default), "
                   "or everything into a single --output file.")
@click.option("--same-domain/--any-domain", "same_domain", default=None,
              help="Restrict crawling to the start URL's domain (default: same-domain).")
@click.option("--append", is_flag=True, default=False,
              help="Append to the output file instead of overwriting.")
@click.option("--log-level", default=None,
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                                case_sensitive=False),
              help="Logging verbosity.")
@click.version_option(version=__version__, prog_name="scraperX")
def main(
    target_url,
    selector,
    output_path,
    crawl_depth,
    headful,
    proxy_url,
    max_retries,
    rate_limit_ms,
    extract_links,
    same_domain,
    group_by_site,
    append,
    log_level,
):
    """Resilient, JavaScript-executing web scraper.

    Renders dynamic pages in a real browser, extracts elements and links,
    and writes structured data to CSV.
    """
    # Translate the tri-state --headful/--headless flag into config.headless.
    headless = None
    if headful is not None:
        headless = not headful

    try:
        config = Config.from_env(
            target_url=target_url,
            selector=selector,
            output_path=output_path,
            crawl_depth=crawl_depth,
            headless=headless,
            proxy_url=proxy_url,
            max_retries=max_retries,
            rate_limit_ms=rate_limit_ms,
            extract_links=extract_links,
            same_domain=same_domain,
            group_by_site=group_by_site,
            log_level=(log_level.upper() if log_level else None),
        )
    except (ValueError, AttributeError) as exc:
        raise click.ClickException(str(exc))

    setup_logging(config.log_level)

    if not config.target_url:
        raise click.ClickException(
            "No target URL. Pass --url or set TARGET_URL in your .env."
        )

    log.info("Starting scrape of %s (depth=%d, headless=%s)",
             config.target_url, config.crawl_depth, config.headless)

    exporter = DataExporter(config.output_path)
    try:
        with ScraperEngine(config) as engine:
            records = engine.run()
    except KeyboardInterrupt:
        click.echo("Interrupted.", err=True)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"Scrape failed: {exc}")

    if not records:
        click.echo("No records extracted.", err=True)

    if config.group_by_site:
        written = exporter.export_by_site(records)
        click.echo(f"Done. Wrote {len(records)} record(s) across {len(written)} site file(s):")
        for site, path in written.items():
            click.echo(f"  {site} -> {path}")
    else:
        path = exporter.export(records, append=append)
        click.echo(f"Done. Wrote {len(records)} record(s) to {path}")


if __name__ == "__main__":
    main()
