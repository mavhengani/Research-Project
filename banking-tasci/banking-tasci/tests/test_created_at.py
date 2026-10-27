"""Tests for the canonical `created_at` contract (Phase 3A, Part 5).

Policy under test:
- a valid parseable date -> ISO 8601 (date-level) string in `created_at`,
  with `created_at_raw = None`;
- a missing/empty value -> `created_at = None`, `created_at_raw = None`;
- a present-but-unparseable value -> `created_at = None`, `created_at_raw`
  retains the original string for provenance.

`created_at` is therefore never an arbitrary raw string.

Also verifies that deterministic `record_id`s are independent of the date
field (record_id is a hash of source + normalised text), so changing the
date policy cannot change record ids.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import Config  # noqa: E402
from banking_tasci.data.ingest import (  # noqa: E402
    CANONICAL_COLUMNS,
    _normalise_created_at,
    ingest_reviews,
    make_record_id,
)
from banking_tasci.data.schema import REVIEW_REQUIRED_COLUMNS  # noqa: E402


def _cfg() -> Config:
    return Config(
        {
            "seed": 42,
            "anonymise": {
                "replace_amounts": False,
                "account_reference_pattern": r"\b\d{9,}\b",
                "phone_pattern": r"(?:\b\d{7,10}\b)",
            },
            "data": {
                "tweets_source_name": "international_bank_tweets",
                "reviews_source_name": "bank_reviews",
                "default_region": "international",
            },
        }
    )


def _reviews_df(date_value) -> pd.DataFrame:
    base = {col: ["value"] for col in REVIEW_REQUIRED_COLUMNS}
    base["rating"] = [4]
    base["bank"] = ["SBI"]
    base["review"] = ["great service overall"]
    base["review_title_by_user"] = ["Nice"]
    base["date"] = [date_value]
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# Unit tests for the normalisation helper.
# ---------------------------------------------------------------------------


def test_valid_date_becomes_iso_and_no_raw():
    iso, raw = _normalise_created_at("2020-03-21")
    assert iso == "2020-03-21"
    assert raw is None


def test_valid_timezone_aware_date_becomes_iso_date():
    iso, raw = _normalise_created_at("2020-03-21T15:30:00+02:00")
    assert iso == "2020-03-21"
    assert raw is None


def test_missing_value_is_null_null():
    assert _normalise_created_at(None) == (None, None)
    assert _normalise_created_at(float("nan")) == (None, None)


def test_empty_string_is_null_null():
    assert _normalise_created_at("") == (None, None)
    assert _normalise_created_at("   ") == (None, None)


def test_unparseable_value_preserved_in_raw_only():
    iso, raw = _normalise_created_at("not a date at all")
    assert iso is None
    assert raw == "not a date at all"


# ---------------------------------------------------------------------------
# Integration: created_at column contract via ingest_reviews.
# ---------------------------------------------------------------------------


def test_ingest_reviews_valid_date_contract():
    records, _stats, _audit = ingest_reviews(_reviews_df("2020-03-21"), _cfg())
    assert list(records.columns) == CANONICAL_COLUMNS
    row = records.iloc[0]
    assert row["created_at"] == "2020-03-21"
    assert row["created_at_raw"] is None


def test_ingest_reviews_unparseable_date_contract():
    records, _stats, _audit = ingest_reviews(_reviews_df("garbage-date"), _cfg())
    row = records.iloc[0]
    assert row["created_at"] is None
    assert row["created_at_raw"] == "garbage-date"


def test_ingest_reviews_empty_date_contract():
    records, _stats, _audit = ingest_reviews(_reviews_df(""), _cfg())
    row = records.iloc[0]
    assert row["created_at"] is None
    assert row["created_at_raw"] is None


def test_record_id_is_independent_of_date():
    """Deterministic record IDs must not depend on the date field."""
    records_valid, _s1, _a1 = ingest_reviews(_reviews_df("2020-03-21"), _cfg())
    records_garbage, _s2, _a2 = ingest_reviews(_reviews_df("garbage-date"), _cfg())
    records_empty, _s3, _a3 = ingest_reviews(_reviews_df(None), _cfg())

    # Same source + normalised text -> same record_id regardless of date.
    rid = records_valid.iloc[0]["record_id"]
    assert records_garbage.iloc[0]["record_id"] == rid
    assert records_empty.iloc[0]["record_id"] == rid
    # And it matches the pure hash of source + normalised text.
    assert rid == make_record_id("bank_reviews", "great service overall")


