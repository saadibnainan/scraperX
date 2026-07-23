# scraperX

A **highly resilient, JavaScript-executing web scraper** for Linux. scraperX
drives a real headless Chromium browser (via Playwright + stealth patches) to
fully render dynamic pages and Single-Page Applications, extracts target
elements and crawls links out of the live DOM, and exports structured data to
CSV.

It ships in **two flavours** — a **CLI** and a **modern GUI** — and both can be
compiled into **standalone Linux binaries** with PyInstaller.

> **Project status:** Complete. The engine, CLI, GUI, and build script are all
> implemented. See [DESIGN.md](DESIGN.md) for the architecture.

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

## Quick Start

Get from zero to your first scrape in a few steps.

**1. Clone the project**
```bash
git clone <your-fork-url> scraperX && cd scraperX
```

**2. Create and activate a virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate
```

**3. Install the Python dependencies**
```bash
pip install -r requirements.txt
```

**4. Install the Chromium browser**
```bash
playwright install chromium
```
> You also need Chromium's system libraries (and Tk, if you use the GUI). See
> [System dependencies](#system-dependencies) for the one-time Arch/Debian commands.

**5. Create your config (optional)**
```bash
cp .env.example .env
```
Every setting has a sane default, so this step is optional. Edit `.env` only if
you need proxies, custom User-Agents, or different defaults.

**6. Run your first scrape (CLI)**
```bash
python -m scraperx.cli --url https://example.com --selector "h1, p" --output output/results.csv
```

**7. …or launch the GUI**
```bash
python -m scraperx.gui
```
Enter a URL and CSS selector, pick an output path, then click **Start**.

**8. Read your results**
The scraped rows are written to `output/results.csv` (or whatever you passed to
`--output` / set as `OUTPUT_PATH`). Open it in any spreadsheet or with pandas.

**9. Build standalone binaries (optional)**
```bash
./build.sh    # → dist/scraperx (CLI) and dist/scraperx-gui (GUI)
```

> **Tip:** run `pip install -e .` once to install scraperX as a package — then you
> can use the shorter `scraperx` and `scraperx-gui` commands anywhere, instead of
> the `python -m scraperx.cli` / `python -m scraperx.gui` module form.

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
| `CHROMIUM_EXECUTABLE_PATH` | *(none)*       | Path to a specific Chromium binary (else Playwright's default).|
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
| `OUTPUT_PATH`       | `output/results.csv`  | Output file (single-file mode) / output **directory** (per-site).|
| `GROUP_BY_SITE`     | `true`                | Write one CSV per website (named by domain) vs. one combined file.|
| `LOG_LEVEL`         | `INFO`                | `DEBUG` / `INFO` / `WARNING` / `ERROR`.                        |

> ⚠️ **Never commit `.env`.** It is gitignored; only `.env.example` is tracked.

---

## Usage

### CLI

```bash
# Basic: scrape a URL, extract elements by selector
# → writes output/example.com.csv (named after the website)
python -m scraperx.cli --url https://example.com --selector "article h2"

# Crawl links two hops deep
python -m scraperx.cli --url https://example.com --depth 2

# Put everything in one combined file instead of per-site files
python -m scraperx.cli --url https://example.com --single-file --output out.csv

# Debug a bot-wall in a visible browser window
python -m scraperx.cli --url https://example.com --headful

# Route through a proxy
python -m scraperx.cli --url https://example.com --proxy http://user:pass@host:port
```

Common flags: `--url`, `--selector`, `--output`, `--depth`,
`--headful/--headless`, `--per-site/--single-file`, `--proxy`, `--max-retries`,
`--rate-limit-ms`, `--extract-links`, `--same-domain/--any-domain`, `--log-level`.
Run `python -m scraperx.cli --help` (or `scraperx --help` after `pip install -e .`)
for the full list.

> After `pip install -e .` you can use the shorter `scraperx` command instead of
> `python -m scraperx.cli`.

### GUI

```bash
scraperx-gui
```

The GUI exposes the same engine: a URL field, selector input, a headless/headful
toggle, proxy settings, a depth control, a live log pane, and a **Start / Stop**
control, with results written to the chosen CSV path.

---

## Output

By default scraperX writes **one CSV per website**, named after the site's
domain, into the directory of `OUTPUT_PATH`:

```
output/
├── example.com.csv
├── docs.example.com.csv
└── another-site.org.csv
```

- The filename is the source page's host (`sub.example.com` → `sub.example.com.csv`;
  a port becomes `host_8080.csv`). This is the default because a crawl of one site
  naturally lands in one file per site.
- Pass `--single-file` (or set `GROUP_BY_SITE=false`) to write everything into the
  single `--output` path instead.

### CSV schema

Every scraped page yields one **`page`** row of rich metadata, plus one
**`element`** row per selector match and (when link extraction is on) one
**`link`** row per anchor. Columns are a stable superset — a given row only fills
the ones relevant to its `record_type`:

| Column | Applies to | Meaning |
| ------ | ---------- | ------- |
| `website` | all | Source domain (also the file's name). |
| `source_url` | all | URL the row came from. |
| `depth` | all | Crawl depth (0 = start page). |
| `http_status` | all | HTTP status of the page. |
| `record_type` | all | `page`, `element`, or `link`. |
| `page_title` | all | `<title>` of the page. |
| `meta_description` / `meta_keywords` / `meta_author` | page | Standard `<meta>` tags. |
| `og_title` / `og_description` / `og_image` / `og_site_name` | page | OpenGraph tags. |
| `canonical_url` | page | `<link rel="canonical">`. |
| `lang` | page | `<html lang>`. |
| `h1_text` | page | First `<h1>` text. |
| `num_links` / `num_images` / `num_headings` / `word_count` | page | Page-level counts. |
| `selector` | element | The CSS selector that matched. |
| `element_index` / `tag` | element | Match index and tag name. |
| `text` | element, link | Normalised text content. |
| `href` / `src` | element, link | Link target / media source. |
| `rel` | link | Anchor `rel` attribute. |
| `element_id` / `element_class` / `alt` / `title_attr` | element | Element attributes. |
| `html` | element | The element's outer HTML. |

---

## Building standalone binaries

The `build.sh` script wraps the PyInstaller commands to produce two
self-contained executables in `dist/`:

```bash
./build.sh
# → dist/scraperx        (CLI)
# → dist/scraperx-gui    (GUI)
```

The built binaries still rely on a Playwright-installed Chromium on the host;
`build.sh` documents how the browser is located at runtime.

---

## Development & tests

```bash
pip install -e ".[dev]"     # install with dev extras (pytest, ruff, pyinstaller)
pytest -q                   # run the unit tests (no browser required)
```

The unit tests cover the browser-independent logic (config parsing/validation,
proxy & User-Agent rotation, CSV export, per-site file naming). The engine itself
is exercised manually against live or local pages.

---

## Troubleshooting

### GUI: `ImportError: libtk8.6.so` / `No module named 'tkinter'`

CustomTkinter needs the **Tk runtime**, which isn't bundled with Python. Install
it for your distro, then re-run the GUI:

```bash
# Arch / Manjaro
sudo pacman -S tk
# Debian / Ubuntu
sudo apt-get install python3-tk tk
# Fedora / RHEL
sudo dnf install python3-tkinter tk
```

If your virtualenv was built against a Python that lacks Tk, recreate the venv
**after** installing the package above. The CLI never needs Tk, so it works
regardless.

### `source .venv/bin/activate` fails in the fish shell

fish can't read the bash activation script (you'll see
`'case' builtin not inside of switch block`). Use the fish-specific one:

```fish
source .venv/bin/activate.fish
```

Or skip activation entirely and call the venv's Python directly:
`.venv/bin/python -m scraperx.cli --url https://example.com`.

### `No module named 'scraperx'`

`python -m scraperx.gui` / `scraperx.cli` only finds the package when **both** of
these are true:

1. Your **virtualenv is active** (otherwise you're on system Python, which lacks
   the dependencies — you'll see `/usr/bin/python` in the error).
2. You're running from the **repository root** (the folder that contains the
   `scraperx/` directory), because `-m` resolves packages from the current
   directory.

```fish
cd /path/to/scraperX
source .venv/bin/activate.fish     # bash/zsh: source .venv/bin/activate
python -m scraperx.gui
```

**Run from anywhere:** install the package once, then use the console commands —
they don't care about your working directory:

```fish
pip install -e .
scraperx-gui
scraperx --url https://example.com --selector "h1, p"
```

### Chromium fails to launch / can't be found

Ensure the browser is installed (`playwright install chromium`) and its system
libraries are present (see [System dependencies](#system-dependencies)). To use a
specific Chromium build, set `CHROMIUM_EXECUTABLE_PATH` in `.env`.

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
