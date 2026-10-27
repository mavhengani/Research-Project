"""Regression test for the Phase 1 ingestion pandas ``FutureWarning`` fix.

Covers Requirement 31 (Phase 1 Ingestion Housekeeping Fix):
- 31.1: ``run_ingestion`` SHALL NOT emit a pandas ``FutureWarning`` about
  concatenating empty or all-NA columns.
- 31.2: output records' columns SHALL be exactly ``CANONICAL_COLUMNS`` in the
  existing order after the fix.
- 31.4: the Test_Suite SHALL include a regression test asserting that running
  ``run_ingestion`` on representative synthetic tweet and review frames emits
  no ``FutureWarning``.
- 31.5: prepared-data generation SHALL complete without the concatenation
  ``FutureWarning`` (exercised here via the empty-source edge case that
  historically triggered the all-NA concat warning).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.ingest import (  # noqa: E402
    CANONICAL_COLUMNS,
    run_ingestion,
)
from banking_tasci.data.schema import REVIEW_REQUIRED_COLUMNS  # noqa: E402
from banking_tasci.logging_utils import _reset_for_tests  # noqa: E402

_BASE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "base.yaml"


def _make_cfg():
    return load_config(_BASE_CONFIG_PATH)


@pytest.fixture(autouse=True)
def _clean_logging_state():
    """Reset cached loggers/handlers so each test gets a fresh log file."""
    _reset_for_tests()
    yield
    _reset_for_tests()


def _reviews_df(**overrides) -> pd.DataFrame:
    base = {col: ["value"] for col in REVIEW_REQUIRED_COLUMNS}
    base["rating"] = [4]
    base["bank"] = ["SBI"]
    base["review"] = ["Great service overall"]
    base["review_title_by_user"] = ["Nice"]
    base["date"] = ["Mar 21, 2020"]
    base.update(overrides)
    return pd.DataFrame(base)


def _future_warnings(caught) -> list[warnings.WarningMessage]:
    return [w for w in caught if issubclass(w.category, FutureWarning)]


def test_run_ingestion_both_sources_populated_emits_no_future_warning() -> None:
    """Representative populated tweet + review frames emit no FutureWarning.

    The review ``rating`` is a float (as real data is, once NaNs appear),
    which combined with the tweet frame's all-NA ``rating`` column is the
    exact shape that historically triggered the pandas concatenation
    ``FutureWarning`` about empty or all-NA columns (Req 31.1).
    """
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": ["Tweet one", "Tweet two"]})
    reviews_df = _reviews_df(rating=[4.0])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_ingestion(tweets_df, reviews_df, cfg)

    assert _future_warnings(caught) == []
    assert list(result.records.columns) == CANONICAL_COLUMNS
    assert len(result.records) == 3


def test_run_ingestion_empty_tweets_source_emits_no_future_warning() -> None:
    """Edge case: one source yields zero rows (all-empty tweet text).

    This is the case that historically triggered the pandas all-NA
    concatenation FutureWarning (Req 31.1, 31.5).
    """
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": [None, "   ", ""]})
    reviews_df = _reviews_df()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_ingestion(tweets_df, reviews_df, cfg)

    assert _future_warnings(caught) == []
    assert list(result.records.columns) == CANONICAL_COLUMNS
    # Only the single review row survives; the empty tweet source drops out.
    assert len(result.records) == 1


def test_run_ingestion_both_sources_empty_emits_no_future_warning() -> None:
    """Edge case: both sources yield zero rows still emits no FutureWarning."""
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": [None]})
    reviews_df = _reviews_df(review=[""])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_ingestion(tweets_df, reviews_df, cfg)

    assert _future_warnings(caught) == []
    assert list(result.records.columns) == CANONICAL_COLUMNS
    assert len(result.records) == 0
