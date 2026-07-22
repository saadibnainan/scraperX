"""CSV export via pandas."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger("scraperx.exporter")

# Stable, human-friendly column order. Any extra keys are appended after these.
_PREFERRED_COLUMNS = [
    "source_url",
    "depth",
    "http_status",
    "page_title",
    "record_type",
    "selector",
    "element_index",
    "tag",
    "text",
    "href",
    "src",
    "html",
]


class DataExporter:
    """Accumulate records and write them to CSV."""

    def __init__(self, output_path: str = "output/results.csv"):
        self.output_path = output_path
        self._records: List[Dict] = []

    def add(self, record: Dict) -> None:
        self._records.append(record)

    def extend(self, records: List[Dict]) -> None:
        self._records.extend(records)

    def __len__(self) -> int:
        return len(self._records)

    def to_dataframe(self) -> pd.DataFrame:
        df = pd.DataFrame(self._records)
        if df.empty:
            return df
        ordered = [c for c in _PREFERRED_COLUMNS if c in df.columns]
        extra = [c for c in df.columns if c not in ordered]
        return df[ordered + extra]

    def export(
        self,
        records: Optional[List[Dict]] = None,
        append: bool = False,
    ) -> str:
        """Write records to ``output_path`` and return the path.

        If ``records`` is given it replaces the internal buffer for this write.
        With ``append=True`` and an existing file, rows are appended without a
        second header.
        """
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
