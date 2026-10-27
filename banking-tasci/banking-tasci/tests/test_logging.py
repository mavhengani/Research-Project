"""Unit tests for the Logging_Utility.

Covers:
- Req 4.2: get_logger("some.module") returns a logger named "some.module".
- Req 4.3: logger reads log level from a supplied Config.
- Req 4.4: emitted log record matches the required format containing
  timestamp, level, name, and message.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import Config  # noqa: E402
from banking_tasci.logging_utils import _reset_for_tests, get_logger  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_logging_state(tmp_path):
    """Reset cached loggers/handlers before and after each test.

    Ensures each test gets a fresh run-scoped log file under its own
    tmp_path log_dir instead of sharing state across tests.
    """
    _reset_for_tests()
    yield
    _reset_for_tests()


def test_get_logger_returns_logger_named_after_module(tmp_path: Path) -> None:
    """Req 4.2: get_logger("some.module") returns a logger named that."""
    logger = get_logger("some.module", log_dir=tmp_path)

    assert isinstance(logger, logging.Logger)
    assert logger.name == "some.module"


def test_get_logger_caches_logger_for_same_name(tmp_path: Path) -> None:
    first = get_logger("some.module", log_dir=tmp_path)
    second = get_logger("some.module", log_dir=tmp_path)

    assert first is second


def test_get_logger_reads_log_level_from_config(tmp_path: Path) -> None:
    """Req 4.3: logger reads log level from a supplied Config."""
    cfg = Config({"log_level": "DEBUG"})

    logger = get_logger("banking_tasci.debug_module", cfg=cfg, log_dir=tmp_path)

    assert logger.level == logging.DEBUG


def test_get_logger_defaults_to_info_without_config(tmp_path: Path) -> None:
    logger = get_logger("banking_tasci.no_config_module", log_dir=tmp_path)

    assert logger.level == logging.INFO


def test_log_record_matches_required_format(tmp_path: Path) -> None:
    """Req 4.4: emitted log record has timestamp, level, name, and message."""
    logger = get_logger("banking_tasci.format_module", log_dir=tmp_path)

    logger.info("hello world")

    log_files = list(Path(tmp_path).glob("*.log"))
    assert len(log_files) == 1
    contents = log_files[0].read_text(encoding="utf-8")

    pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \| INFO \| "
        r"banking_tasci\.format_module \| hello world$",
        re.MULTILINE,
    )
    assert pattern.search(contents) is not None


def test_get_logger_writes_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Req 4.1: attaches a stdout StreamHandler."""
    logger = get_logger("banking_tasci.stdout_module", log_dir=tmp_path)

    logger.info("visible on stdout")

    captured = capsys.readouterr()
    assert "visible on stdout" in captured.out
    assert "banking_tasci.stdout_module" in captured.out


def test_get_logger_creates_run_scoped_file_under_log_dir(tmp_path: Path) -> None:
    """Req 4.1: attaches a run-scoped FileHandler under log_dir."""
    get_logger("banking_tasci.file_module", log_dir=tmp_path)

    log_files = list(Path(tmp_path).glob("*.log"))
    assert len(log_files) == 1


def test_multiple_loggers_share_same_run_scoped_log_file(tmp_path: Path) -> None:
    """Only one log file is created per run, regardless of how many
    different logger names are requested."""
    get_logger("banking_tasci.module_one", log_dir=tmp_path)
    get_logger("banking_tasci.module_two", log_dir=tmp_path)

    log_files = list(Path(tmp_path).glob("*.log"))
    assert len(log_files) == 1
