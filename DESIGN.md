# scraperX — Design Document

This document describes the architecture of scraperX: the folder structure, the
library choices and their rationale, the class design, and the phased build
plan. It is the reference the implementation phases are built against.

---

## 1. Goals & constraints

- Fully **execute JavaScript** to render dynamic pages / SPAs before scraping.
- **Extract** specific DOM elements and **crawl** links (`href`s) to a
  configurable depth.
- Be **resilient**: survive aggressive anti-scraping via retries, exponential
  backoff, jitter, proxy rotation, and User-Agent / fingerprint spoofing.
- **Headless by default**, headful on demand for CAPTCHA debugging.
- Ship a **CLI** and a **GUI**, both importing one shared engine.
- Compile both into **standalone Linux binaries**.

---

## 2. Folder structure

```
scraperX/
├── .env.example          # committed config template
├── .env                  # local secrets (gitignored)
├── .gitignore
├── README.md             # setup / usage / build
├── DESIGN.md             # this document
├── requirements.txt
├── build.sh              # PyInstaller build commands            (Phase 4)
├── scraperx/             # the Python package
│   ├── __init__.py
│   ├── config.py         # Config: load & validate .env          (Phase 2)
│   ├── rotators.py       # ProxyRotator, UserAgentRotator        (Phase 2)
│   ├── engine.py         # ScraperEngine: Playwright + resilience (Phase 2)
│   ├── exporter.py       # DataExporter: pandas → CSV            (Phase 2)
│   ├── cli.py            # click entry point                     (Phase 3)
│   └── gui.py            # CustomTkinter entry point             (Phase 3)
├── output/               # runtime CSV output (gitignored)
└── tests/                # unit tests                            (later)
```

The two entry points (`cli.py`, `gui.py`) are thin: they parse
input/build a `Config`, invoke `ScraperEngine`, and hand results to
`DataExporter`. All scraping logic lives in the engine so both interfaces stay
in sync.

---

## 3. Library choices & rationale

| Concern            | Library            | Why                                                                                             |
| ------------------ | ------------------ | ----------------------------------------------------------------------------------------------- |
| Browser automation | **Playwright**     | First-class headless Chromium, robust auto-waiting for dynamic content, intercepts responses (needed to see `429`/`5xx` status codes), reliable on Linux. |
| Anti-bot           | **playwright-stealth** | Patches the well-known automation fingerprints (`navigator.webdriver`, WebGL, etc.).        |
| Config             | **python-dotenv**  | Simple, standard `.env` loading; keeps secrets out of the repo.                                  |
| Retries            | **tenacity**       | Declarative retry policies — exponential backoff, jitter, and per-exception conditions without hand-rolled loops. |
| User-Agents        | **fake-useragent** | Maintained pool of realistic UA strings; augmented by an optional user-supplied list.           |
| Data export        | **pandas**         | Flexible tabular handling (dedup, column ordering, easy future formats) with one-call CSV export. |
| CLI                | **click**          | Declarative options/flags, generated help, validation, colored output.                          |
| GUI                | **CustomTkinter**  | Modern themed widgets on pure-Python Tkinter; bundles into a small, dependency-light PyInstaller binary. |
| Packaging          | **PyInstaller**    | Mature single-file Linux binaries; well-understood hooks for Playwright and Tk.                 |

**Trade-off noted:** pandas materially increases binary size vs. the stdlib
`csv` module. This was an explicit product decision in favour of export
flexibility.

---

## 4. Class architecture

```
        ┌────────────┐        ┌──────────────────┐
        │   cli.py   │        │      gui.py      │
        │  (click)   │        │  (CustomTkinter) │
        └─────┬──────┘        └────────┬─────────┘
              │      builds Config      │
              └───────────┬─────────────┘
                          ▼
                   ┌─────────────┐
                   │   Config    │  loads & validates .env
                   └──────┬──────┘
                          ▼
                 ┌──────────────────┐        uses
                 │  ScraperEngine   │───────────────────┐
                 │  (Playwright)    │                   ▼
                 └───────┬──────────┘         ┌───────────────────┐
                         │                    │  ProxyRotator     │
                         │                    │  UserAgentRotator │
                         ▼                    └───────────────────┘
                 ┌───────────────┐
                 │ DataExporter  │  pandas → CSV
                 └───────────────┘
```

### `Config` (`config.py`)
- Loads `.env` via python-dotenv and normalises types (bools, ints, lists).
- Holds all tunables: target URL, headless flag, proxy settings, UA pool,
  retry/backoff params, timeouts, concurrency, crawl depth, rate limit, output
  path, log level.
- Overridable per-run (CLI flags / GUI fields take precedence over `.env`).
- Validates values and raises clear errors on bad input.

### `ProxyRotator` / `UserAgentRotator` (`rotators.py`)
- `ProxyRotator`: yields the next proxy from `PROXY_LIST` (round-robin), or the
  single `PROXY_URL`, or none. Parses embedded credentials.
- `UserAgentRotator`: yields the next UA from the user pool or the
  fake-useragent/built-in pool; assigned per browser context to vary the
  fingerprint.

### `ScraperEngine` (`engine.py`)
The core. Responsibilities:
1. **Lifecycle** — launch Playwright/Chromium with the chosen headless mode,
   proxy, and User-Agent; apply stealth patches; create/close contexts.
2. **Navigation with resilience** — a tenacity-wrapped `navigate()` that retries
   on timeouts and on responses with status `429` or `5xx`, using exponential
   backoff (`BACKOFF_BASE ** attempt`, capped at `BACKOFF_MAX`) plus optional
   jitter; rotates proxy/UA between attempts.
3. **Rendering** — wait for network idle / selector presence so JS-driven
   content is materialised.
4. **Extraction** — evaluate CSS selectors against the live DOM to pull target
   elements' text/attributes.
5. **Link crawling** — collect `href`s from the DOM, normalise/dedupe them, and
   recurse to `CRAWL_DEPTH`, honouring `RATE_LIMIT_MS` and `CONCURRENCY`.
6. **Yielding records** — emit structured rows (e.g. source URL, extracted
   fields, discovered links) to the exporter.

### `DataExporter` (`exporter.py`)
- Accumulates records into a pandas DataFrame.
- Writes CSV to `OUTPUT_PATH`, creating parent dirs; supports append vs.
  overwrite and stable column ordering.

### Entry points
- **`cli.py`** — `click` command exposing the config surface as flags
  (`--url`, `--selector`, `--output`, `--depth`, `--headful/--headless`,
  `--proxy`, `--max-retries`, `--log-level`, …); builds `Config`, runs the
  engine, calls the exporter.
- **`gui.py`** — CustomTkinter window with the same controls, a headless/headful
  toggle, a live log pane, and Start/Stop. Runs the engine on a worker thread so
  the UI stays responsive.

---

## 5. Resilience strategy (detail)

- **Retry triggers:** navigation timeouts, HTTP `429`, HTTP `5xx`.
- **Backoff:** `delay = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)`, optionally
  jittered by a random factor to de-correlate concurrent workers.
- **Rotation on retry:** pick a fresh proxy and User-Agent between attempts so a
  blocked identity isn't reused.
- **Politeness:** `RATE_LIMIT_MS` enforces a minimum gap between same-host
  requests; `CONCURRENCY` bounds parallelism.
- **Stealth:** playwright-stealth removes automation tells; headful mode is
  available to solve CAPTCHAs manually.

---

## 6. Phased execution plan

| Phase | Scope                                                                                          | Status          |
| ----- | ---------------------------------------------------------------------------------------------- | --------------- |
| **1** | Foundation & Architecture: `.gitignore`, `.env.example`, `README.md`, `DESIGN.md`, `requirements.txt` | **This phase**  |
| **2** | Core Engine: `config.py`, `rotators.py`, `engine.py`, `exporter.py`                            | Awaits approval |
| **3** | Interfaces: `cli.py` (click), then `gui.py` (CustomTkinter)                                    | Awaits approval |
| **4** | Compilation: `build.sh` with exact PyInstaller commands for both binaries                      | Awaits approval |

Each phase is reviewed and approved before the next begins.
