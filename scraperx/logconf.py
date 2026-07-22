"""Shared logging configuration."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure the root ``scraperx`` logger once, to stderr."""
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    root = logging.getLogger("scraperx")
    root.setLevel(numeric)

    # Avoid duplicate handlers if called more than once (e.g. GUI restarts).
    if not any(getattr(h, "_scraperx", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
        )
        handler._scraperx = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.propagate = False
