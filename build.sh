#!/usr/bin/env bash
# ===========================================================================
# scraperX — build standalone Linux binaries with PyInstaller
# ---------------------------------------------------------------------------
# Produces two one-file executables in ./dist:
#     dist/scraperx        (CLI)
#     dist/scraperx-gui    (GUI)
#
# Prerequisites (see README.md):
#     pip install -r requirements.txt
#     playwright install chromium
#
# IMPORTANT — Playwright browser at runtime:
#   PyInstaller bundles the Python code but NOT the Chromium browser binary.
#   The built executable locates Chromium via Playwright's normal lookup:
#     * the machine running the binary must have a browser installed
#       (`playwright install chromium`), OR
#     * set PLAYWRIGHT_BROWSERS_PATH to a directory you ship alongside the app.
#   To pin a bundled browser, install into a local folder before building:
#       PLAYWRIGHT_BROWSERS_PATH=./ms-playwright playwright install chromium
#   and set the same env var when running the binary.
# ===========================================================================

set -euo pipefail

cd "$(dirname "$0")"

# --- sanity checks ---------------------------------------------------------
if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "error: pyinstaller not found. Install it with:  pip install pyinstaller" >&2
    exit 1
fi

echo ">> Cleaning previous build artifacts..."
rm -rf build dist ./*.spec

COMMON_OPTS=(
    --noconfirm
    --clean
    --onefile
    --collect-all playwright
    --collect-all playwright_stealth
    --collect-data fake_useragent
)

# --- CLI binary ------------------------------------------------------------
echo ">> Building CLI binary (scraperx)..."
pyinstaller "${COMMON_OPTS[@]}" \
    --name scraperx \
    --console \
    cli_entry.py

# --- GUI binary ------------------------------------------------------------
# customtkinter ships theme/asset data files that must be collected.
echo ">> Building GUI binary (scraperx-gui)..."
pyinstaller "${COMMON_OPTS[@]}" \
    --name scraperx-gui \
    --console \
    --collect-all customtkinter \
    gui_entry.py

echo ""
echo ">> Build complete. Binaries are in ./dist :"
ls -lh dist/scraperx dist/scraperx-gui 2>/dev/null || ls -lh dist/
echo ""
echo "Run them with, e.g.:"
echo "    ./dist/scraperx --url https://example.com --selector 'h1' --output out.csv"
echo "    ./dist/scraperx-gui"
