"""Tests for the Prepare_Data_CLI (scripts/prepare_data.py).

Covers:
- Req 9.2: `--help` prints usage and exits 0.
- Req 9.3: missing/unreadable `--tweets`/`--reviews` path prints a
  descriptive stderr message and exits non-zero before config loading.
- Req 9.4: a successful `--output` write exits 0 even when the
  `--report` write fails.
- Req 9.5: CLI status output goes through the Logging_Utility rather than
  bare `print()`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from banking_tasci.data.schema import REVIEW_REQUIRED_COLUMNS  # noqa: E402
from banking_tasci.logging_utils import _reset_for_tests  # noqa: E402

import prepare_data  # noqa: E402

_BASE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "base.yaml"


@pytest.fixture(autouse=True)
def _clean_logging_state():
    """Reset cached loggers/handlers so each test gets a fresh log file."""
    _reset_for_tests()
    yield
    _reset_for_tests()


def _write_tweets_csv(path: Path) -> None:
    pd.DataFrame({"text": ["Great bank service today", "Terrible wait time"]}).to_csv(path, index=False)


def _write_reviews_csv(path: Path) -> None:
    base = {col: ["value"] for col in REVIEW_REQUIRED_COLUMNS}
    base["rating"] = [4]
    base["bank"] = ["SBI"]
    base["review"] = ["Great service overall"]
    base["review_title_by_user"] = ["Nice"]
    base["date"] = ["Mar 21, 2020"]
    pd.DataFrame(base).to_csv(path, index=False)


# ---------------------------------------------------------------------------
# Req 9.2: --help prints usage and exits 0.
# ---------------------------------------------------------------------------

def test_help_exits_zero_and_prints_usage(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        prepare_data.build_arg_parser().parse_args(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


# ---------------------------------------------------------------------------
# Req 9.3: missing/unreadable --tweets/--reviews path prints a descriptive
# stderr message and exits non-zero before config loading.
# ---------------------------------------------------------------------------

def test_missing_tweets_path_exits_nonzero_with_stderr_message(tmp_path, capsys) -> None:
    reviews_path = tmp_path / "reviews.csv"
    _write_reviews_csv(reviews_path)

    exit_code = prepare_data.main(
        [
            "--tweets", str(tmp_path / "does_not_exist.csv"),
            "--reviews", str(reviews_path),
            "--output", str(tmp_path / "out.csv"),
            "--report", str(tmp_path / "report.json"),
        ]
    )

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "tweets" in captured.err.lower()
    assert "does_not_exist.csv" in captured.err


def test_missing_reviews_path_exits_nonzero_with_stderr_message(tmp_path, capsys) -> None:
    tweets_path = tmp_path / "tweets.csv"
    _write_tweets_csv(tweets_path)

    exit_code = prepare_data.main(
        [
            "--tweets", str(tweets_path),
            "--reviews", str(tmp_path / "missing_reviews.csv"),
            "--output", str(tmp_path / "out.csv"),
            "--report", str(tmp_path / "report.json"),
        ]
    )

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "reviews" in captured.err.lower()
    assert not (tmp_path / "out.csv").exists()


def test_unreadable_tweets_path_exits_nonzero_before_output_written(tmp_path, capsys) -> None:
    tweets_path = tmp_path / "tweets.csv"
    _write_tweets_csv(tweets_path)
    os.chmod(tweets_path, 0o000)

    reviews_path = tmp_path / "reviews.csv"
    _write_reviews_csv(reviews_path)

    try:
        if os.access(tweets_path, os.R_OK):
            pytest.skip("Running as a user that can read files regardless of permission bits")

        exit_code = prepare_data.main(
            [
                "--tweets", str(tweets_path),
                "--reviews", str(reviews_path),
                "--output", str(tmp_path / "out.csv"),
                "--report", str(tmp_path / "report.json"),
            ]
        )

        assert exit_code != 0
        captured = capsys.readouterr()
        assert "tweets" in captured.err.lower()
        assert not (tmp_path / "out.csv").exists()
    finally:
        os.chmod(tweets_path, 0o644)


# ---------------------------------------------------------------------------
# Req 9.4: successful --output write exits 0 even when --report write fails.
# ---------------------------------------------------------------------------

def test_output_written_exits_zero_even_if_report_write_fails(tmp_path) -> None:
    tweets_path = tmp_path / "tweets.csv"
    _write_tweets_csv(tweets_path)
    reviews_path = tmp_path / "reviews.csv"
    _write_reviews_csv(reviews_path)
    output_path = tmp_path / "out.csv"

    # Point --report at a path whose parent is a file, not a directory, so
    # the write_data_quality_report call fails when it tries to mkdir/write.
    blocking_file = tmp_path / "blocking_file"
    blocking_file.write_text("not a directory", encoding="utf-8")
    report_path = blocking_file / "report.json"

    exit_code = prepare_data.main(
        [
            "--tweets", str(tweets_path),
            "--reviews", str(reviews_path),
            "--output", str(output_path),
            "--report", str(report_path),
            "--config", str(_BASE_CONFIG_PATH),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert not report_path.exists()


def test_output_and_report_both_written_on_success(tmp_path) -> None:
    tweets_path = tmp_path / "tweets.csv"
    _write_tweets_csv(tweets_path)
    reviews_path = tmp_path / "reviews.csv"
    _write_reviews_csv(reviews_path)
    output_path = tmp_path / "out.csv"
    report_path = tmp_path / "report.json"

    exit_code = prepare_data.main(
        [
            "--tweets", str(tweets_path),
            "--reviews", str(reviews_path),
            "--output", str(output_path),
            "--report", str(report_path),
            "--config", str(_BASE_CONFIG_PATH),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert report_path.exists()


# ---------------------------------------------------------------------------
# Req 9.5: CLI status output goes through the Logging_Utility rather than
# bare print().
# ---------------------------------------------------------------------------

def test_status_output_goes_through_logging_utility(tmp_path, capsys) -> None:
    tweets_path = tmp_path / "tweets.csv"
    _write_tweets_csv(tweets_path)
    reviews_path = tmp_path / "reviews.csv"
    _write_reviews_csv(reviews_path)
    output_path = tmp_path / "out.csv"
    report_path = tmp_path / "report.json"
    log_dir = tmp_path / "logs"

    from banking_tasci.logging_utils import get_logger

    # Prime the shared handlers to write into a tmp_path log dir so we can
    # inspect the run-scoped log file contents.
    get_logger("prepare_data", log_dir=log_dir)

    exit_code = prepare_data.main(
        [
            "--tweets", str(tweets_path),
            "--reviews", str(reviews_path),
            "--output", str(output_path),
            "--report", str(report_path),
            "--config", str(_BASE_CONFIG_PATH),
        ]
    )

    assert exit_code == 0

    log_files = list(log_dir.glob("*.log"))
    assert len(log_files) == 1
    contents = log_files[0].read_text(encoding="utf-8")
    assert "Wrote canonical output" in contents
    assert "Wrote data quality report" in contents
