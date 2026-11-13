"""Merkezi loglama: %APPDATA%\\ASCII_Mate\\logs altında dönen log dosyası ve sys.excepthook."""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def app_data_dir() -> Path:
    """Kullanıcıya özel veri klasörü (%APPDATA%\\ASCII_Mate); yoksa ev dizini altında."""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "ASCII_Mate"


def log_dir() -> Path:
    return app_data_dir() / "logs"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Dönen dosya log'unu kurar ve sys/threading excepthook'larını bağlar (idempotent)."""
    global _CONFIGURED
    root = logging.getLogger("ascii_mate")
    if _CONFIGURED:
        return root
    _CONFIGURED = True
    root.setLevel(level)
    try:
        d = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(d / "ascii_mate.log", maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(handler)
    except OSError:
        root.addHandler(logging.NullHandler())

    def _excepthook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        root.critical("Yakalanmayan istisna", exc_info=(exc_type, exc, tb))

    def _thread_hook(args) -> None:
        root.critical(
            "Yakalanmayan iş parçacığı istisnası (%s)", getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ascii_mate.{name}")
