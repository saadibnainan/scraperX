"""PyInstaller entry point for the CLI binary.

Kept as a top-level script so PyInstaller has a concrete module to analyse.
"""

from scraperx.cli import main

if __name__ == "__main__":
    main()
