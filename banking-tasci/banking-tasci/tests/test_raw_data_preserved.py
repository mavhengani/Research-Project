"""Cross-cutting test verifying raw source CSVs are never modified.

Covers:
- Req 7.7: the Ingestion_Pipeline writes its output under `data/interim/`
  and does not modify the original source CSV files under `data/raw/`.
- Req 10.5: the Test_Suite includes an automated test verifying that
  running the Ingestion_Pipeline does not modify the byte contents of the
  original source CSV files.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from banking_tasci.logging_utils import _reset_for_tests  # noqa: E402

import prepare_data  # noqa: E402

import pytest  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TWEETS_PATH = PROJECT_ROOT / "data" / "raw" / "sampledbanktweet.csv"
_REVIEWS_PATH = PROJECT_ROOT / "data" / "raw" / "bank_reviews3.csv"
_BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "base.yaml"


@pytest.fixture(autouse=True)
def _clean_logging_state():
    """Reset cached loggers/handlers so this test gets a fresh log file."""
    _reset_for_tests()
    yield
    _reset_for_tests()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_raw_source_csvs_unmodified_by_end_to_end_cli_run(tmp_path) -> None:
    assert _TWEETS_PATH.is_file(), f"expected raw fixture at {_TWEETS_PATH}"
    assert _REVIEWS_PATH.is_file(), f"expected raw fixture at {_REVIEWS_PATH}"

    tweets_hash_before = _sha256(_TWEETS_PATH)
    reviews_hash_before = _sha256(_REVIEWS_PATH)

    output_path = tmp_path / "prepared.csv"
    report_path = tmp_path / "report.json"

    exit_code = prepare_data.main(
        [
            "--tweets", str(_TWEETS_PATH),
            "--reviews", str(_REVIEWS_PATH),
            "--output", str(output_path),
            "--report", str(report_path),
            "--config", str(_BASE_CONFIG_PATH),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()

    tweets_hash_after = _sha256(_TWEETS_PATH)
    reviews_hash_after = _sha256(_REVIEWS_PATH)

    assert tweets_hash_after == tweets_hash_before
    assert reviews_hash_after == reviews_hash_before
