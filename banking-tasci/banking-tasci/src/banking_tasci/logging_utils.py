"""Shared logging utility for the banking-tasci project.

Provides a single `get_logger` entry point so every module and CLI in the
project produces consistent, timestamped log output (console + a
run-specific log file) instead of ad hoc `print` statements.

Requirements:
- 4.1: return a configured logger writing to stdout and to a run-specific
  log file.
- 4.2: a logger requested for a named module is identified by that name.
- 4.3: the configured log level is read from the loaded configuration.
- 4.4: each log record is formatted with a timestamp, level, module name,
  and message.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

PathLike = Union[str, Path]

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DEFAULT_LOG_LEVEL = "INFO"

# Process-wide cache of loggers already configured by get_logger, keyed by
# name (Requirement 4.2 caching).
_loggers: dict = {}

# Handlers shared across every logger created within this process/run, and
# the path of the run-scoped log file they were built for. These are only
# created once — the first time *any* name is requested — so repeated
# get_logger calls don't open a new log file per module.
_shared_handlers: Optional[list] = None
_run_log_path: Optional[Path] = None


def _resolve_log_level(cfg: Any) -> int:
    """Resolve a logging level int from `cfg.log_level`, defaulting to INFO.

    Accepts either a string level name (e.g. "INFO", "debug") or an int
    already-resolved level. Falls back to INFO for missing/unrecognised
    values rather than raising, since an invalid log level should not
    prevent logging from working (Requirement 4.3).
    """
    level = getattr(cfg, "log_level", None) if cfg is not None else None
    if level is None:
        level = _DEFAULT_LOG_LEVEL
    if isinstance(level, int):
        return level
    resolved = logging.getLevelName(str(level).upper())
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


def _build_shared_handlers(log_dir: Path) -> list:
    """Create the stdout + run-scoped file handlers, shared by all loggers."""
    global _run_log_path

    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    _run_log_path = log_dir / f"run_{run_id}.log"

    formatter = logging.Formatter(_LOG_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(_run_log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    return [stream_handler, file_handler]


def get_logger(name: str, cfg: Any = None, log_dir: PathLike = "outputs/logs") -> logging.Logger:
    """Return (and cache) a logger named `name`.

    Attaches a stdout `StreamHandler` and a run-scoped `FileHandler` under
    `log_dir` the first time a given run/process requests any logger; every
    subsequently requested logger (any name) reuses those same handler
    instances rather than opening additional log files. The log level comes
    from `cfg.log_level` when `cfg` is given, else defaults to INFO.
    """
    if name in _loggers:
        return _loggers[name]

    global _shared_handlers
    if _shared_handlers is None:
        _shared_handlers = _build_shared_handlers(Path(log_dir))

    logger = logging.getLogger(name)
    logger.setLevel(_resolve_log_level(cfg))
    logger.propagate = False

    for handler in _shared_handlers:
        logger.addHandler(handler)

    _loggers[name] = logger
    return logger


def _reset_for_tests() -> None:
    """Clear cached loggers/handlers so tests can start from a clean state.

    Not part of the public API — intended for use in test fixtures only, so
    each test can point `get_logger` at its own tmp_path log_dir and inspect
    a fresh run-scoped log file.
    """
    global _shared_handlers, _run_log_path

    for logger in _loggers.values():
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
    _loggers.clear()
    _shared_handlers = None
    _run_log_path = None
