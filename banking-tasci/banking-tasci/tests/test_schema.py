"""Tests for the Schema_Validator (src/banking_tasci/data/schema.py).

Covers:
- Req 5.1: tweets dataframe requires the `text` column.
- Req 5.2: reviews dataframe requires its full column set.
- Req 5.3: missing required column(s) raise SchemaValidationError naming
  the file and the missing column(s).
- Req 5.4: successful validation logs the file name and row count
  (Property 4).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.schema import (  # noqa: E402
    REVIEW_REQUIRED_COLUMNS,
    TWEET_REQUIRED_COLUMNS,
    SchemaValidationError,
    missing_columns,
    validate_reviews_schema,
    validate_tweets_schema,
)
from banking_tasci.logging_utils import _reset_for_tests  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_logging_state(tmp_path):
    """Reset cached loggers/handlers so each test gets a fresh log file."""
    _reset_for_tests()
    yield
    _reset_for_tests()


# ---------------------------------------------------------------------------
# Unit tests (Req 5.1, 5.2, 5.3, 5.4)
# ---------------------------------------------------------------------------

def test_validate_tweets_schema_passes_with_text_column() -> None:
    df = pd.DataFrame({"text": ["hello", "world"]})

    validate_tweets_schema(df, "sampledbanktweet.csv")


def test_validate_tweets_schema_raises_when_text_missing() -> None:
    df = pd.DataFrame({"other_col": ["hello", "world"]})

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_tweets_schema(df, "sampledbanktweet.csv")

    err = exc_info.value
    assert err.file_path == "sampledbanktweet.csv"
    assert err.missing == ["text"]
    assert "sampledbanktweet.csv" in str(err)
    assert "text" in str(err)


def test_validate_reviews_schema_passes_with_all_required_columns() -> None:
    df = pd.DataFrame({col: ["value"] for col in REVIEW_REQUIRED_COLUMNS})

    validate_reviews_schema(df, "bank_reviews3.csv")


def test_validate_reviews_schema_raises_naming_all_missing_columns() -> None:
    present_cols = [c for c in REVIEW_REQUIRED_COLUMNS if c not in ("bank", "rating", "useful_count")]
    df = pd.DataFrame({col: ["value"] for col in present_cols})

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_reviews_schema(df, "bank_reviews3.csv")

    err = exc_info.value
    assert err.file_path == "bank_reviews3.csv"
    assert err.missing == sorted(["bank", "rating", "useful_count"])
    for missing_col in ("bank", "rating", "useful_count"):
        assert missing_col in str(err)


def test_missing_columns_is_order_preserved_pure_helper() -> None:
    df = pd.DataFrame({"a": [1], "c": [3]})

    assert missing_columns(df, ["a", "b", "c", "d"]) == ["b", "d"]
    # Pure: calling again with the same inputs gives the same result and
    # does not mutate the dataframe's columns.
    assert missing_columns(df, ["a", "b", "c", "d"]) == ["b", "d"]
    assert list(df.columns) == ["a", "c"]


def test_successful_validation_logs_file_name_and_row_count(tmp_path: Path) -> None:
    """Req 5.4: successful validation logs the file name and row count.

    The schema module's logger propagates=False (per Logging_Utility), so
    we assert against the run-scoped log file rather than caplog.
    """
    from banking_tasci.logging_utils import get_logger

    get_logger("banking_tasci.data.schema", log_dir=tmp_path)

    df = pd.DataFrame({"text": ["a", "b", "c"]})

    validate_tweets_schema(df, "sampledbanktweet.csv")

    log_files = list(Path(tmp_path).glob("*.log"))
    assert len(log_files) == 1
    contents = log_files[0].read_text(encoding="utf-8")
    assert "sampledbanktweet.csv: 3 rows validated" in contents


# ---------------------------------------------------------------------------
# Property 4: Schema validation detects exactly the missing required columns.
# Validates: Requirements 5.1, 5.2, 5.3
# ---------------------------------------------------------------------------

def _subsets(columns: list[str]):
    return st.lists(st.sampled_from(columns), min_size=0, max_size=len(columns), unique=True)


_extra_column_names = st.lists(
    st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=8),
    min_size=0,
    max_size=3,
    unique=True,
)


@settings(max_examples=100)
@given(present=_subsets(TWEET_REQUIRED_COLUMNS), extra_cols=_extra_column_names)
# Feature: banking-tasci-pipeline, Property 4: Schema validation detects exactly the missing required columns
def test_property_tweets_schema_detects_exactly_missing_columns(present, extra_cols) -> None:
    extra_cols = [c for c in extra_cols if c not in TWEET_REQUIRED_COLUMNS]
    columns = present + extra_cols
    df = pd.DataFrame({col: ["value"] for col in columns}) if columns else pd.DataFrame(index=[0])

    expected_missing = sorted(set(TWEET_REQUIRED_COLUMNS) - set(present))

    if expected_missing:
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_tweets_schema(df, "sampledbanktweet.csv")
        assert exc_info.value.missing == expected_missing
    else:
        validate_tweets_schema(df, "sampledbanktweet.csv")

    assert missing_columns(df, TWEET_REQUIRED_COLUMNS) == [
        c for c in TWEET_REQUIRED_COLUMNS if c not in present
    ]


@settings(max_examples=100)
@given(present=_subsets(REVIEW_REQUIRED_COLUMNS), extra_cols=_extra_column_names)
# Feature: banking-tasci-pipeline, Property 4: Schema validation detects exactly the missing required columns
def test_property_reviews_schema_detects_exactly_missing_columns(present, extra_cols) -> None:
    extra_cols = [c for c in extra_cols if c not in REVIEW_REQUIRED_COLUMNS]
    columns = present + extra_cols
    df = pd.DataFrame({col: ["value"] for col in columns}) if columns else pd.DataFrame(index=[0])

    expected_missing = sorted(set(REVIEW_REQUIRED_COLUMNS) - set(present))

    if expected_missing:
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_reviews_schema(df, "bank_reviews3.csv")
        assert exc_info.value.missing == expected_missing
    else:
        validate_reviews_schema(df, "bank_reviews3.csv")

    assert missing_columns(df, REVIEW_REQUIRED_COLUMNS) == [
        c for c in REVIEW_REQUIRED_COLUMNS if c not in present
    ]
