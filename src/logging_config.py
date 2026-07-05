from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        if hasattr(record, "worker_id"):
            log_entry["worker_id"] = record.worker_id
        return json.dumps(log_entry)


def setup_logging() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(console)

    file_handler = logging.FileHandler(log_dir / "crawler.log")
    file_handler.setFormatter(StructuredFormatter())
    root.addHandler(file_handler)
