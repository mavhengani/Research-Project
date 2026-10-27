"""Cross-cutting Phase 1 confirmation tests (Task 14.2).

These are deliberately non-property-based, requirements-level confirmation
tests that exercise `run_ingestion` end-to-end (as opposed to
`tests/test_ingest.py`'s Property 9 and Property 10, which check the same
ground via Hypothesis-generated inputs and, for record_id, at the
`make_record_id` function level in isolation).

Covers:
- Req 10.3: `record_id` generation is deterministic for identical source and
  text input, confirmed here by running the full `run_ingestion` pipeline
  twice against identical input dataframes and comparing the resulting
  `record_id` columns.
- Req 10.4: ingestion of any record produces `context_available=False` and
  `previous_text="[NO_CONTEXT]"`, confirmed here across every row of a
  representative end-to-end `run_ingestion` result (mixing tweets and
  reviews).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.ingest import run_ingestion  # noqa: E402
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


def _representative_tweets_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "text": [
                "Great service at the branch today",
                "My card got blocked, very annoyed @bank_support",
                "Waited over an hour just to deposit a cheque",
            ]
        }
    )


def _representative_reviews_df() -> pd.DataFrame:
    n = 3
    base = {col: ["value"] * n for col in REVIEW_REQUIRED_COLUMNS}
    base["bank"] = ["SBI", "HDFC", "ICICI"]
    base["rating"] = [4, 2, 5]
    base["review"] = [
        "Great service overall",
        "Terrible wait times at the counter",
        "Loved how quick the loan approval was",
    ]
    base["review_title_by_user"] = ["Nice", "Slow", "Fast"]
    base["date"] = ["Mar 21, 2020", "Jan 5, 2021", "Jul 14, 2019"]
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# Req 10.4: context_available=False and previous_text="[NO_CONTEXT]" for
# every produced Canonical_Record, confirmed end-to-end via run_ingestion.
# ---------------------------------------------------------------------------

def test_run_ingestion_every_record_has_no_context_available() -> None:
    cfg = _make_cfg()
    tweets_df = _representative_tweets_df()
    reviews_df = _representative_reviews_df()

    result = run_ingestion(tweets_df, reviews_df, cfg)

    assert len(result.records) == len(tweets_df) + len(reviews_df)
    for _, row in result.records.iterrows():
        assert bool(row["context_available"]) is False
        assert row["previous_text"] == "[NO_CONTEXT]"


def test_run_ingestion_every_record_has_no_context_available_tweets_only() -> None:
    cfg = _make_cfg()
    tweets_df = _representative_tweets_df()
    reviews_df = _representative_reviews_df().iloc[0:0]

    result = run_ingestion(tweets_df, reviews_df, cfg)

    assert len(result.records) == len(tweets_df)
    for _, row in result.records.iterrows():
        assert bool(row["context_available"]) is False
        assert row["previous_text"] == "[NO_CONTEXT]"


def test_run_ingestion_every_record_has_no_context_available_reviews_only() -> None:
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": pd.Series(dtype="object")})
    reviews_df = _representative_reviews_df()

    result = run_ingestion(tweets_df, reviews_df, cfg)

    assert len(result.records) == len(reviews_df)
    for _, row in result.records.iterrows():
        assert bool(row["context_available"]) is False
        assert row["previous_text"] == "[NO_CONTEXT]"


# ---------------------------------------------------------------------------
# Req 10.3: record_id determinism across two full ingestion runs of
# identical input, confirmed at the run_ingestion (not make_record_id)
# level.
# ---------------------------------------------------------------------------

def test_run_ingestion_record_ids_identical_across_two_runs_same_input() -> None:
    cfg = _make_cfg()

    # Fresh copies each run to rule out mutation artifacts affecting the
    # second run's input.
    tweets_df_run1 = _representative_tweets_df().copy(deep=True)
    reviews_df_run1 = _representative_reviews_df().copy(deep=True)
    tweets_df_run2 = _representative_tweets_df().copy(deep=True)
    reviews_df_run2 = _representative_reviews_df().copy(deep=True)

    result1 = run_ingestion(tweets_df_run1, reviews_df_run1, cfg)
    result2 = run_ingestion(tweets_df_run2, reviews_df_run2, cfg)

    ids1 = result1.records["record_id"].tolist()
    ids2 = result2.records["record_id"].tolist()

    assert len(ids1) == len(tweets_df_run1) + len(reviews_df_run1)
    assert ids1 == ids2

    # Original input dataframes passed to the second run must not have been
    # mutated by the first run (sanity check on the "fresh copies" premise).
    pd.testing.assert_frame_equal(tweets_df_run2, _representative_tweets_df())
    pd.testing.assert_frame_equal(reviews_df_run2, _representative_reviews_df())


def test_run_ingestion_record_ids_identical_across_two_runs_with_duplicates() -> None:
    """Same check but with a repeated tweet text, to confirm determinism
    holds even when duplicate-removal/dedup logic is exercised.
    """
    cfg = _make_cfg()

    def _tweets_with_duplicate() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "text": [
                    "Great service at the branch today",
                    "Great service at the branch today",
                    "A completely different complaint about fees",
                ]
            }
        )

    tweets_df_run1 = _tweets_with_duplicate()
    reviews_df_run1 = _representative_reviews_df().copy(deep=True)
    tweets_df_run2 = _tweets_with_duplicate()
    reviews_df_run2 = _representative_reviews_df().copy(deep=True)

    result1 = run_ingestion(tweets_df_run1, reviews_df_run1, cfg)
    result2 = run_ingestion(tweets_df_run2, reviews_df_run2, cfg)

    assert result1.records["record_id"].tolist() == result2.records["record_id"].tolist()
