# scraperX

A **highly resilient, JavaScript-executing web scraper** for Linux. scraperX
drives a real headless Chromium browser (via Playwright + stealth patches) to
fully render dynamic pages and Single-Page Applications, extracts target
elements and crawls links out of the live DOM, and exports structured data to
CSV.

It ships in **two flavours** — a **CLI** and a **modern GUI** — and both can be
compiled into **standalone Linux binaries** with PyInstaller.

> **Project status:** Phase 1 (Foundation & Architecture). This repository
> currently contains the project scaffolding and documentation. The scraping
> engine, interfaces, and build script land in later phases — see
> [DESIGN.md](DESIGN.md) for the full roadmap.

---

## Features

- **Real browser rendering** — executes JavaScript so SPAs and lazy-loaded
  content are fully materialised before extraction.
- **Element extraction** — pull specific nodes via CSS selectors.
- **Link crawling** — harvest `href`s from the rendered DOM and follow them to a
  configurable depth.
- **Resilient by design** — automatic retries with exponential backoff + jitter
  on timeouts, HTTP `429`, and `5xx` responses.
- **Anti-blocking** — rotating proxies and spoofed User-Agents / browser
  fingerprints, all driven from `.env`.
- **Headless by default, headful on demand** — flip to a visible window to debug
  CAPTCHAs and bot-walls.
- **Structured CSV output** — via pandas.
- **Two interfaces** — a `click` CLI and a CustomTkinter GUI, sharing one engine.
- **Standalone binaries** — one PyInstaller executable per interface.

---

## Requirements

- **OS:** Linux — primarily tested on **Arch**; **Debian/Ubuntu** supported.
- **Python:** 3.10+
- **Chromium** system libraries (installed once via Playwright, see below).

---

## Installation

```bash
# 1. Clone
git clone <your-fork-url> scraperX && cd scraperX

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install the Chromium browser used by Playwright
playwright install chromium
```

### System dependencies

Playwright needs a set of shared libraries to run Chromium.

**Debian / Ubuntu:**
```bash
playwright install-deps chromium
# or, manually:
sudo apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2
```

**Arch Linux** (`playwright install-deps` is not supported on Arch — install
manually):
```bash
sudo pacman -S --needed nss nspr atk at-spi2-atk cups libdrm libxkbcommon \
  libxcomposite libxdamage libxfixes libxrandr mesa alsa-lib
```

The GUI additionally needs Tk:
```bash
# Debian/Ubuntu
sudo apt-get install -y python3-tk
# Arch
sudo pacman -S --needed tk
```

---

## Configuration

scraperX is configured through a `.env` file. Copy the template and edit:

```bash
cp .env.example .env
```

Every setting has a sane default, so an empty `.env` still runs. Key variables:

| Variable            | Default               | Purpose                                                        |
| ------------------- | --------------------- | -------------------------------------------------------------- |
| `TARGET_URL`        | *(none)*              | Default start URL when none is given on CLI/GUI.               |
| `HEADLESS`          | `true`                | Run headless (`true`) or with a visible window (`false`).      |
| `PROXY_URL`         | *(none)*              | Single proxy, e.g. `http://host:port`.                         |
| `PROXY_USERNAME`    | *(none)*              | Auth username for the single proxy.                            |
| `PROXY_PASSWORD`    | *(none)*              | Auth password for the single proxy.                            |
| `PROXY_LIST`        | *(none)*              | Comma/newline list of proxies to rotate (overrides above).     |
| `USER_AGENTS`       | *(built-in pool)*     | Custom User-Agent strings to rotate.                           |
| `MAX_RETRIES`       | `4`                   | Retry attempts on timeout / `429` / `5xx`.                     |
| `BACKOFF_BASE`      | `2`                   | Exponential backoff base (seconds).                            |
| `BACKOFF_MAX`       | `60`                  | Cap on any single backoff delay (seconds).                     |
| `JITTER`            | `true`                | Add randomness to backoff delays.                              |
| `REQUEST_TIMEOUT_MS`| `30000`               | Per-request timeout.                                           |
| `NAV_TIMEOUT_MS`    | `45000`               | Page-navigation timeout.                                       |
| `CONCURRENCY`       | `1`                   | Pages fetched in parallel.                                     |
| `CRAWL_DEPTH`       | `1`                   | Link-hops to follow (`0` = start page only).                   |
| `RATE_LIMIT_MS`     | `1000`                | Minimum delay between requests to the same host.               |
| `OUTPUT_PATH`       | `output/results.csv`  | Where the CSV is written.                                      |
| `LOG_LEVEL`         | `INFO`                | `DEBUG` / `INFO` / `WARNING` / `ERROR`.                        |

> ⚠️ **Never commit `.env`.** It is gitignored; only `.env.example` is tracked.

---

## Usage

> The commands below reflect the **planned** interface (implemented in Phase 3).

### CLI

```bash
# Basic: scrape a URL, extract elements by selector, write CSV
scraperx --url https://example.com --selector "article h2" --output out.csv

# Crawl links two hops deep
scraperx --url https://example.com --depth 2

# Debug a bot-wall in a visible browser window
scraperx --url https://example.com --headful

# Route through a proxy
scraperx --url https://example.com --proxy http://user:pass@host:port
```

Common flags (planned): `--url`, `--selector`, `--output`, `--depth`,
`--headful/--headless`, `--proxy`, `--max-retries`, `--log-level`. Run
`scraperx --help` for the full list.

### GUI

```bash
scraperx-gui
```

The GUI exposes the same engine: a URL field, selector input, a headless/headful
toggle, proxy settings, a depth control, a live log pane, and a **Start / Stop**
control, with results written to the chosen CSV path.

---

## Building standalone binaries

A `build.sh` script (added in Phase 4) wraps the PyInstaller commands to produce
two self-contained executables in `dist/`:

```bash
./build.sh
# → dist/scraperx        (CLI)
# → dist/scraperx-gui    (GUI)
```

The built binaries still rely on a Playwright-installed Chromium on the host;
`build.sh` documents how the browser is located at runtime.

---

## Legal & ethical use

scraperX is intended for scraping content you are **authorised** to access.
Respect each site's Terms of Service and `robots.txt`, honour rate limits, and
comply with applicable laws (e.g. copyright, GDPR/CCPA) regarding the data you
collect. You are responsible for how you use this tool.

---

## Project layout & design

See **[DESIGN.md](DESIGN.md)** for the folder structure, library choices, class
architecture, and the phased execution plan.
