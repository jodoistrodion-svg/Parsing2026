from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler


_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(secret(?:_word|\s+answer)?\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
)


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(item for item in secrets if item and len(item) >= 6)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "***")
        for pattern in _SECRET_PATTERNS:
            message = pattern.sub(
                lambda match: match.group(1) + "***" if match.lastindex else "***",
                message,
            )
        record.msg = message
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    log_file: str,
    max_bytes: int,
    backup_count: int,
    *,
    level: str = "INFO",
    log_format: str = "plain",
    secrets: Iterable[str] = (),
) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    formatter: logging.Formatter
    if str(log_format).lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    redactor = SecretRedactionFilter(secrets)

    if not any(getattr(handler, "_parsing_console", False) for handler in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler._parsing_console = True  # type: ignore[attr-defined]
        stream_handler.addFilter(redactor)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    autobuy_logger = logging.getLogger("autobuy")
    autobuy_logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    target = os.path.abspath(log_file)
    has_file_handler = any(
        isinstance(handler, RotatingFileHandler)
        and os.path.abspath(getattr(handler, "baseFilename", "")) == target
        for handler in autobuy_logger.handlers
    )
    if not has_file_handler:
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.addFilter(redactor)
        file_handler.setFormatter(formatter)
        autobuy_logger.addHandler(file_handler)

    autobuy_logger.propagate = True
    return autobuy_logger
