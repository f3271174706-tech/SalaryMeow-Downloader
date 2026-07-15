"""Logging setup with lightweight secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from .settings import AppSettings

SECRET_PATTERN = re.compile(r"(?i)(cookie|authorization|token|secret|password)=([^;\s&]+)")


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return SECRET_PATTERN.sub(r"\1=***", text)


def configure_logging(settings: AppSettings) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    formatter = RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    log_file = settings.paths.logs_dir / "app.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
