"""CustomTkinter GUI for scraperX.

Exposes the same engine as the CLI through a small control panel: URL / selector
/ output inputs, a headless toggle, proxy and depth controls, a live log pane,
and Start / Stop. The scrape runs on a worker thread so the UI stays responsive;
log lines are marshalled back to the main thread through a queue.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
from typing import Optional

from . import __version__
from .config import Config
from .engine import ScraperEngine
from .exporter import DataExporter
from .logconf import setup_logging

log = logging.getLogger("scraperx.gui")

# CustomTkinter depends on Tk (the _tkinter C extension + libtk shared library).
# On a machine missing the Tk runtime the import raises ImportError. We catch it
# here so the GUI can exit with actionable install guidance instead of a raw
# traceback. ``_Base`` lets the class definition below succeed even without Tk.
try:
    import customtkinter as ctk  # noqa: E402

    _CTK_IMPORT_ERROR: Optional[BaseException] = None
    _Base = ctk.CTk
except BaseException as _exc:  # noqa: BLE001 — Tk can fail with more than ImportError
    ctk = None  # type: ignore[assignment]
    _CTK_IMPORT_ERROR = _exc
    _Base = object


_TK_HELP = """\
scraperX GUI could not start because Tk (the Tkinter GUI runtime) is not
available for this Python. CustomTkinter needs it.

Install Tk, then re-run `scraperx-gui` / `python -m scraperx.gui`:

  Arch / Manjaro:    sudo pacman -S tk
  Debian / Ubuntu:   sudo apt-get install python3-tk tk
  Fedora / RHEL:     sudo dnf install python3-tkinter tk
  openSUSE:          sudo zypper install python3-tk tk
  macOS (Homebrew):  brew install python-tk

If you use a virtualenv built against a Python that lacks Tk, recreate it with a
Python that has Tk support after installing the package above.

Prefer no GUI? The CLI needs no Tk:
  python -m scraperx.cli --url https://example.com --selector "h1, p"

Underlying import error: {error}
"""


def _tk_unavailable_message() -> str:
    return _TK_HELP.format(error=_CTK_IMPORT_ERROR)


class _QueueLogHandler(logging.Handler):
    """Logging handler that pushes formatted lines onto a thread-safe queue."""

    def __init__(self, q: "queue.Queue[str]"):
        super().__init__()
        self._q = q
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put_nowait(self.format(record))
        except Exception:
            pass


class ScraperApp(_Base):
    def __init__(self):
        super().__init__()
        self.title(f"scraperX {__version__}")
        self.geometry("820x680")
        self.minsize(700, 560)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        self._build_widgets()
        self._attach_log_handler()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkLabel(self, text="scraperX — resilient web scraper",
                              font=ctk.CTkFont(size=20, weight="bold"))
        header.grid(row=0, column=0, padx=20, pady=(18, 6), sticky="w")

        form = ctk.CTkFrame(self)
        form.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        for c in (1, 3):
            form.grid_columnconfigure(c, weight=1)

        cfg = Config.from_env()  # seed defaults from .env

        def _row(r, label):
            ctk.CTkLabel(form, text=label).grid(row=r, column=0, padx=(14, 6),
                                                pady=6, sticky="w")

        _row(0, "URL")
        self.url_entry = ctk.CTkEntry(form, placeholder_text="https://example.com")
        self.url_entry.grid(row=0, column=1, columnspan=3, padx=(0, 14), pady=6, sticky="ew")
        if cfg.target_url:
            self.url_entry.insert(0, cfg.target_url)

        _row(1, "CSS selector")
        self.selector_entry = ctk.CTkEntry(form, placeholder_text="article h2  (optional)")
        self.selector_entry.grid(row=1, column=1, columnspan=3, padx=(0, 14), pady=6, sticky="ew")

        _row(2, "Output CSV")
        self.output_entry = ctk.CTkEntry(form)
        self.output_entry.grid(row=2, column=1, columnspan=3, padx=(0, 14), pady=6, sticky="ew")
        self.output_entry.insert(0, cfg.output_path)

        _row(3, "Proxy")
        self.proxy_entry = ctk.CTkEntry(form,
                                        placeholder_text="http://user:pass@host:port  (optional)")
        self.proxy_entry.grid(row=3, column=1, columnspan=3, padx=(0, 14), pady=6, sticky="ew")
        if cfg.proxy_url:
            self.proxy_entry.insert(0, cfg.proxy_url)

        # Depth + retries on one row
        _row(4, "Crawl depth")
        self.depth_entry = ctk.CTkEntry(form, width=80)
        self.depth_entry.grid(row=4, column=1, padx=(0, 14), pady=6, sticky="w")
        self.depth_entry.insert(0, str(cfg.crawl_depth))

        ctk.CTkLabel(form, text="Max retries").grid(row=4, column=2, padx=(0, 6),
                                                    pady=6, sticky="e")
        self.retries_entry = ctk.CTkEntry(form, width=80)
        self.retries_entry.grid(row=4, column=3, padx=(0, 14), pady=6, sticky="w")
        self.retries_entry.insert(0, str(cfg.max_retries))

        # Toggles
        toggles = ctk.CTkFrame(form, fg_color="transparent")
        toggles.grid(row=5, column=0, columnspan=4, padx=8, pady=(6, 12), sticky="w")

        self.headless_switch = ctk.CTkSwitch(toggles, text="Headless")
        self.headless_switch.pack(side="left", padx=10)
        if cfg.headless:
            self.headless_switch.select()

        self.links_switch = ctk.CTkSwitch(toggles, text="Extract links")
        self.links_switch.pack(side="left", padx=10)
        if cfg.extract_links:
            self.links_switch.select()

        self.same_domain_switch = ctk.CTkSwitch(toggles, text="Same domain only")
        self.same_domain_switch.pack(side="left", padx=10)
        if cfg.same_domain:
            self.same_domain_switch.select()

        self.per_site_switch = ctk.CTkSwitch(toggles, text="One CSV per site")
        self.per_site_switch.pack(side="left", padx=10)
        if cfg.group_by_site:
            self.per_site_switch.select()

        # Buttons
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="ew")
        self.start_button = ctk.CTkButton(buttons, text="Start", command=self._on_start)
        self.start_button.pack(side="left", padx=(0, 10))
        self.stop_button = ctk.CTkButton(buttons, text="Stop", command=self._on_stop,
                                         state="disabled", fg_color="#8a2b2b",
                                         hover_color="#6f2222")
        self.stop_button.pack(side="left")
        self.status_label = ctk.CTkLabel(buttons, text="Idle", anchor="e")
        self.status_label.pack(side="right", padx=6)

        # Log pane
        self.log_box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="monospace", size=12))
        self.log_box.grid(row=2, column=0, padx=20, pady=8, sticky="nsew")
        self.log_box.configure(state="disabled")

    def _attach_log_handler(self) -> None:
        handler = _QueueLogHandler(self._log_queue)
        root = logging.getLogger("scraperx")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.propagate = False

    # ------------------------------------------------------------------
    # Log plumbing
    # ------------------------------------------------------------------
    def _append_log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                self._append_log(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(120, self._drain_log_queue)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        try:
            config = Config.from_env(
                target_url=self.url_entry.get().strip() or None,
                selector=self.selector_entry.get().strip() or None,
                output_path=self.output_entry.get().strip() or None,
                proxy_url=self.proxy_entry.get().strip() or None,
                crawl_depth=int(self.depth_entry.get() or 0),
                max_retries=int(self.retries_entry.get() or 0),
                headless=bool(self.headless_switch.get()),
                extract_links=bool(self.links_switch.get()),
                same_domain=bool(self.same_domain_switch.get()),
                group_by_site=bool(self.per_site_switch.get()),
            )
        except (ValueError, AttributeError) as exc:
            self._append_log(f"Config error: {exc}")
            return

        if not config.target_url:
            self._append_log("Please enter a URL.")
            return

        self._stop_event.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text="Running…")

        self._worker = threading.Thread(target=self._run_scrape, args=(config,), daemon=True)
        self._worker.start()

    def _on_stop(self) -> None:
        self._stop_event.set()
        self.status_label.configure(text="Stopping…")
        self._append_log("Stop requested — finishing current page.")

    def _run_scrape(self, config: Config) -> None:
        exporter = DataExporter(config.output_path)
        try:
            with ScraperEngine(config, should_stop=self._stop_event.is_set) as engine:
                records = engine.run()
            if config.group_by_site:
                written = exporter.export_by_site(records)
                self._log_queue.put(
                    f"Done. Wrote {len(records)} record(s) across "
                    f"{len(written)} site file(s):"
                )
                for site, path in written.items():
                    self._log_queue.put(f"  {site} -> {path}")
            else:
                path = exporter.export(records)
                self._log_queue.put(f"Done. Wrote {len(records)} record(s) to {path}")
            self.after(0, lambda: self.status_label.configure(text=f"Done ({len(records)})"))
        except Exception as exc:  # noqa: BLE001
            self._log_queue.put(f"ERROR: {exc}")
            self.after(0, lambda: self.status_label.configure(text="Error"))
        finally:
            self.after(0, self._reset_buttons)

    def _reset_buttons(self) -> None:
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _on_close(self) -> None:
        self._stop_event.set()
        self.destroy()


def main() -> None:
    if ctk is None:
        # Tk isn't available — print actionable guidance instead of a traceback.
        print(_tk_unavailable_message(), file=sys.stderr)
        raise SystemExit(1)
    setup_logging("INFO")
    app = ScraperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
