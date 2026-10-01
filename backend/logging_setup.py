"""Structured logging: JSON lines to file and console, plus an in-memory ring buffer that
the developer UI reads through /api/logs."""

from __future__ import annotations

import collections
import json
import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_to_dict(record), default=str)


def record_to_dict(record: logging.LogRecord) -> dict[str, Any]:
    d: dict[str, Any] = {
        "ts": round(record.created, 3),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)) + f".{int(record.msecs):03d}",
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    for k, v in record.__dict__.items():
        if k not in _RESERVED and not k.startswith("_"):
            d[k] = v
    if record.exc_info:
        d["exception"] = logging.Formatter().formatException(record.exc_info)
    return d


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self.buffer: collections.deque[dict] = collections.deque(maxlen=capacity)
        self._lock2 = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            d = record_to_dict(record)
            with self._lock2:
                self._seq += 1
                d["seq"] = self._seq
                self.buffer.append(d)
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def query(self, level: str | None = None, logger: str | None = None, limit: int = 200,
              after_seq: int = 0, text: str | None = None) -> list[dict]:
        lvl = logging.getLevelName(level.upper()) if level else 0
        with self._lock2:
            items = list(self.buffer)
        out = [r for r in items if r["seq"] > after_seq
               and logging.getLevelName(r["level"]) >= (lvl if isinstance(lvl, int) else 0)
               and (not logger or r["logger"].startswith(logger))
               and (not text or text.lower() in json.dumps(r).lower())]
        return out[-limit:]


RING = RingBufferHandler()


def configure_logging(level: str = "INFO", directory: Path | None = None, json_format: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt: logging.Formatter = JsonFormatter() if json_format else logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt if json_format else fmt)
    root.addHandler(console)
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(directory / "dartsense.log", maxBytes=10 * 1024 * 1024, backupCount=5,
                                 encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
    root.addHandler(RING)
    for noisy in ("uvicorn.access", "multipart", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
