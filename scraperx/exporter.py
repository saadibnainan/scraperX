"""CSV export via pandas.

Two modes:
  * :meth:`DataExporter.export` — write everything to one CSV.
  * :meth:`DataExporter.export_by_site` — group records by their source website
    (domain) and write one CSV per site, named after the domain
    (e.g. ``output/example.com.csv``).
"""

from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from typing import Dict, List, Optional
from urllib.parse import urlparse

import pandas as pd

log = logging.getLogger("scraperx.exporter")

# Stable, human-friendly column order. Any extra keys are appended after these.
_PREFERRED_COLUMNS = [
    "website",
    "source_url",
    "depth",
    "http_status",
    "record_type",
    "page_title",
    "meta_description",
    "meta_keywords",
    "meta_author",
    "og_title",
    "og_description",
    "og_image",
    "og_site_name",
    "canonical_url",
    "lang",
    "h1_text",
    "num_links",
    "num_images",
    "num_headings",
    "word_count",
    "selector",
    "element_index",
    "tag",
    "text",
    "href",
    "rel",
    "src",
    "element_id",
    "element_class",
    "alt",
    "title_attr",
    "html",
]

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def domain_slug(url: str) -> str:
    """Turn a URL (or bare host) into a filesystem-safe filename stem.

    ``https://sub.Example.com:8080/x`` -> ``sub.example.com_8080``
    Falls back to ``site`` when no host can be determined.
    """
    parsed = urlparse(url if "://" in (url or "") else f"http://{url}")
    host = (parsed.hostname or "").lower()
    if parsed.port:
        host = f"{host}_{parsed.port}"
    slug = _SAFE_CHARS.sub("_", host).strip("._-")
    return slug or "site"


class DataExporter:
    """Accumulate records and write them to CSV (single-file or per-site)."""

    def __init__(self, output_path: str = "output/results.csv"):
        self.output_path = output_path
        self._records: List[Dict] = []

    def add(self, record: Dict) -> None:
        self._records.append(record)

    def extend(self, records: List[Dict]) -> None:
        self._records.extend(records)

    def __len__(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    def _order_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        ordered = [c for c in _PREFERRED_COLUMNS if c in df.columns]
        extra = [c for c in df.columns if c not in ordered]
        return df[ordered + extra]

    def to_dataframe(self, records: Optional[List[Dict]] = None) -> pd.DataFrame:
        df = pd.DataFrame(records if records is not None else self._records)
        return self._order_columns(df)

    # ------------------------------------------------------------------
    def export(
        self,
        records: Optional[List[Dict]] = None,
        append: bool = False,
    ) -> str:
        """Write all records to ``output_path`` (single file) and return the path."""
        if records is not None:
            self._records = list(records)

        directory = os.path.dirname(os.path.abspath(self.output_path))
        os.makedirs(directory, exist_ok=True)

        df = self.to_dataframe()

        write_header = True
        mode = "w"
        if append and os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
            mode = "a"
            write_header = False

        df.to_csv(self.output_path, mode=mode, header=write_header, index=False)
        log.info("Wrote %d record(s) to %s", len(df), self.output_path)
        return self.output_path

    # ------------------------------------------------------------------
    def export_by_site(
        self,
        records: Optional[List[Dict]] = None,
        directory: Optional[str] = None,
    ) -> "OrderedDict[str, str]":
        """Group records by source website and write one CSV per domain.

        Filenames are derived from the domain (``example.com.csv``). Returns an
        ordered mapping of ``{domain: written_path}``.
        """
        if records is not None:
            self._records = list(records)

        # Default output directory: the directory part of output_path.
        out_dir = directory or os.path.dirname(self.output_path) or "output"
        os.makedirs(out_dir, exist_ok=True)

        # Group records by website (fall back to source_url's domain).
        groups: "OrderedDict[str, List[Dict]]" = OrderedDict()
        for rec in self._records:
            site = rec.get("website") or domain_slug(rec.get("source_url", ""))
            groups.setdefault(site or "site", []).append(rec)

        written: "OrderedDict[str, str]" = OrderedDict()
        for site, recs in groups.items():
            stem = domain_slug(site)
            path = os.path.join(out_dir, f"{stem}.csv")
            df = self.to_dataframe(recs)
            df.to_csv(path, index=False)
            log.info("Wrote %d record(s) for %s to %s", len(df), site, path)
            written[site] = path

        if not groups:
            log.info("No records to export.")
        return written
