"""
Rotating file logging, in addition to the lightweight activity log kept in
SQLite (db.log) that powers the admin UI's log page. The file log is the
full-detail record (including tracebacks) for when something needs real
debugging; the SQLite log is the human-readable summary shown in the UI.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
LOG_FILE = LOG_DIR / "azan.log"


def setup_logging(level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("azan")
    root.setLevel(level)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.propagate = False
