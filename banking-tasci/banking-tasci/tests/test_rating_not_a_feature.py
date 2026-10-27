"""Proof that the `rating` column is never used as an input feature
(Phase 3A Part 13 requirement).

Two structural guarantees:
1. The model-ready example dataclasses (IntentExample / SentimentExample) carry
   no `rating` field, so a rating value cannot reach a model through them.
2. The canonical ingestion carries `rating` as inert metadata only — changing
   the rating does not change any other canonical field (text, record_id, etc.).
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import Config  # noqa: E402
from banking_tasci.data.datasets import IntentExample, SentimentExample  # noqa: E402
from banking_tasci.data.ingest import ingest_reviews  # noqa: E402
from banking_tasci.data.schema import REVIEW_REQUIRED_COLUMNS  # noqa: E402


def test_example_dataclasses_have_no_rating_field():
    intent_fields = {f.name for f in dataclasses.fields(IntentExample)}
    sentiment_fields = {f.name for f in dataclasses.fields(SentimentExample)}
    assert "rating" not in intent_fields
    assert "rating" not in sentiment_fields
    # Also ensure no metadata leakage fields are present.
    for forbidden in ("region", "source", "bank", "title"):
        assert forbidden not in intent_fields
        assert forbidden not in sentiment_fields


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


def _reviews_df(rating) -> pd.DataFrame:
    base = {col: ["value"] for col in REVIEW_REQUIRED_COLUMNS}
    base["rating"] = [rating]
    base["bank"] = ["SBI"]
    base["review"] = ["great service overall"]
    base["review_title_by_user"] = ["Nice"]
    base["date"] = ["2020-03-21"]
    return pd.DataFrame(base)


def test_rating_is_inert_metadata_only():
    r1, _s1, _a1 = ingest_reviews(_reviews_df(1), _cfg())
    r5, _s5, _a5 = ingest_reviews(_reviews_df(5), _cfg())

    row1, row5 = r1.iloc[0], r5.iloc[0]
    # rating is carried through, but nothing else changes with it.
    assert row1["rating"] == 1 and row5["rating"] == 5
    for field in ("record_id", "text", "title", "created_at"):
        assert row1[field] == row5[field]

