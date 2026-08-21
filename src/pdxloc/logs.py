"""The diagnostic log: the only answer to «it crashed».

A public release means other people's machines, ones you cannot walk up to.
Without a log there is nothing to say to «it does not work»: somebody else's mod,
somebody else's game and somebody else's Windows cannot be reproduced, while a
traceback arrives as a single file.

Three decisions, each with its own reason:

* **the file sits next to the application**, not in `%APPDATA%`. The application
  is portable — it lives on a flash drive if you like — and the log has to travel
  with it. `app_root()` already knows a build from the sources;
* **`RotatingFileHandler` from the standard library**. This project has one
  dependency, PySide6, and a second will not be added for writing to a file.
  Without rotation the file would grow forever on a machine nobody looks at;
* **`sys.excepthook`**. It is what all of this is for: an unhandled exception in
  a Qt application currently goes nowhere — the window stays up, the person sees
  «nothing happened», and has nothing to report it with.

The module **does not import Qt**: `--scan-cli` works without PySide6 and must
keep doing so, and it needs the log just as much.
"""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
from pathlib import Path

LOG_NAME = "pdx-translator.log"

# A megabyte is enough for several sessions with tracebacks, and two copies let
# you ask «what happened last time» — things usually break on a later run.
MAX_BYTES = 1_000_000
BACKUPS = 2

_configured = False


def log_path() -> Path:
    from pdxloc import settings

    return settings.app_root() / LOG_NAME


def setup(*, level: int = logging.INFO) -> Path | None:
    """Set up the log file and the catch for unhandled exceptions.

    Returns the path to the file, or None if writing was not possible. **The
    silent failure here is deliberate**: an application that will not start
    because it could not open a log is worse than an application with no log. The
    directory is sometimes read-only — a write-protected flash drive, `Program
    Files` without rights — and that is no reason to refuse to work.
    """
    global _configured
    if _configured:
        return log_path()

    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError:
        return None

    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True

    sys.excepthook = _log_uncaught
    _log_environment()
    return path


def _log_environment() -> None:
    """Three lines that answer half the questions before the traceback is read."""
    from pdxloc import __version__

    log = logging.getLogger("pdxloc")
    log.info("PDX Translator %s", __version__)
    log.info("Python %s", sys.version.replace("\n", " "))
    log.info("%s %s", platform.system(), platform.release())
    log.info("frozen=%s root=%s", getattr(sys, "frozen", False), log_path().parent)


def _log_uncaught(exc_type, exc, tb) -> None:
    """Log an unhandled exception and hand it on to the previous hook.

    Calling the previous one is mandatory: without it the familiar console output
    disappears when running from source, and `KeyboardInterrupt` stops looking
    like an interrupt.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("pdxloc").critical(
        "Необработанное исключение", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)
