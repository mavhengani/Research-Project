"""Tests for the Ingestion_Pipeline (src/banking_tasci/data/ingest.py).

Covers:
- Req 7.1, 7.2: tweet-row and review-row mapping examples.
- Req 7.3: record_id determinism (Property 10).
- Req 7.4: context_available=False, previous_text="[NO_CONTEXT]" (Property 9).
- Req 7.5: rating never influences derived record content (Property 11).
- Req 7.6: empty-row and exact-duplicate removal counts logged separately.
- Req 7.8: zero-successfully-processed-record edge case still returns a
  DataFrame with CANONICAL_COLUMNS and zero rows.
- Req 7.9: schema-validation failure halts ingestion and surfaces
  SchemaValidationError unchanged to the caller.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.ingest import (  # noqa: E402
    CANONICAL_COLUMNS,
    IngestionResult,
    SourceStats,
    ingest_reviews,
    ingest_tweets,
    make_record_id,
    run_ingestion,
)
from banking_tasci.data.schema import (  # noqa: E402
    REVIEW_REQUIRED_COLUMNS,
    SchemaValidationError,
)
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


# ---------------------------------------------------------------------------
# Unit tests: tweet-row and review-row mapping examples (Req 7.1, 7.2)
# ---------------------------------------------------------------------------

def test_ingest_tweets_maps_row_to_canonical_record() -> None:
    cfg = _make_cfg()
    df = pd.DataFrame({"text": ["Great bank service today"]})

    records, stats, audit = ingest_tweets(df, cfg)

    assert list(records.columns) == CANONICAL_COLUMNS
    assert len(records) == 1
    row = records.iloc[0]
    assert row["source"] == cfg.data.tweets_source_name
    assert row["region"] == cfg.data.default_region
    assert row["bank"] is None
    assert row["rating"] is None
    assert row["title"] == ""
    assert row["text"] == "Great bank service today"
    assert row["previous_text"] == "[NO_CONTEXT]"
    assert bool(row["context_available"]) is False
    assert row["thread_id"] is None
    assert row["created_at"] is None
    assert row["split"] is None
    assert isinstance(stats, SourceStats)
    assert stats.rows_before == 1
    assert stats.rows_after == 1


def test_ingest_reviews_maps_row_to_canonical_record() -> None:
    cfg = _make_cfg()
    df = _reviews_df()

    records, stats, audit = ingest_reviews(df, cfg)

    assert list(records.columns) == CANONICAL_COLUMNS
    assert len(records) == 1
    row = records.iloc[0]
    assert row["source"] == cfg.data.reviews_source_name
    assert row["region"] == cfg.data.default_region
    assert row["bank"] == "SBI"
    assert row["rating"] == 4
    assert row["title"] == "Nice"
    assert row["text"] == "Great service overall"
    assert row["previous_text"] == "[NO_CONTEXT]"
    assert bool(row["context_available"]) is False
    assert row["thread_id"] is None
    assert row["created_at"] == "2020-03-21"
    assert row["split"] is None
    assert isinstance(stats, SourceStats)


def test_run_ingestion_concatenates_both_sources() -> None:
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": ["Tweet one", "Tweet two"]})
    reviews_df = _reviews_df()

    result = run_ingestion(tweets_df, reviews_df, cfg)

    assert isinstance(result, IngestionResult)
    assert list(result.records.columns) == CANONICAL_COLUMNS
    assert len(result.records) == 3
    assert len(result.per_source_stats) == 2
    sources = set(result.records["source"])
    assert sources == {cfg.data.tweets_source_name, cfg.data.reviews_source_name}


# ---------------------------------------------------------------------------
# Req 7.8: zero-successfully-processed-record edge case still returns a
# DataFrame with CANONICAL_COLUMNS and zero rows.
# ---------------------------------------------------------------------------

def test_ingest_tweets_all_empty_returns_zero_row_canonical_df() -> None:
    cfg = _make_cfg()
    df = pd.DataFrame({"text": [None, "   ", ""]})

    records, stats, audit = ingest_tweets(df, cfg)

    assert list(records.columns) == CANONICAL_COLUMNS
    assert len(records) == 0
    assert stats.rows_before == 3
    assert stats.rows_after == 0
    assert stats.empty_removed == 3


def test_ingest_reviews_all_empty_returns_zero_row_canonical_df() -> None:
    cfg = _make_cfg()
    df = _reviews_df(review=[None])

    records, stats, audit = ingest_reviews(df, cfg)

    assert list(records.columns) == CANONICAL_COLUMNS
    assert len(records) == 0
    assert stats.rows_after == 0
    assert stats.empty_removed == 1


def test_run_ingestion_both_sources_empty_returns_zero_row_canonical_df() -> None:
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": [None]})
    reviews_df = _reviews_df(review=[""])

    result = run_ingestion(tweets_df, reviews_df, cfg)

    assert list(result.records.columns) == CANONICAL_COLUMNS
    assert len(result.records) == 0


# ---------------------------------------------------------------------------
# Req 7.9: schema-validation failure halts ingestion and surfaces
# SchemaValidationError unchanged to the caller.
# ---------------------------------------------------------------------------

def test_ingest_tweets_propagates_schema_validation_error() -> None:
    cfg = _make_cfg()
    df = pd.DataFrame({"not_text": ["hello"]})

    with pytest.raises(SchemaValidationError) as exc_info:
        ingest_tweets(df, cfg)

    assert exc_info.value.missing == ["text"]


def test_ingest_reviews_propagates_schema_validation_error() -> None:
    cfg = _make_cfg()
    df = _reviews_df()
    df = df.drop(columns=["bank", "rating"])

    with pytest.raises(SchemaValidationError) as exc_info:
        ingest_reviews(df, cfg)

    assert exc_info.value.missing == sorted(["bank", "rating"])


def test_run_ingestion_propagates_schema_validation_error_from_tweets() -> None:
    cfg = _make_cfg()
    bad_tweets_df = pd.DataFrame({"not_text": ["hello"]})
    reviews_df = _reviews_df()

    with pytest.raises(SchemaValidationError):
        run_ingestion(bad_tweets_df, reviews_df, cfg)


# ---------------------------------------------------------------------------
# Req 7.6: empty-row and exact-duplicate removal counts are logged
# separately.
# ---------------------------------------------------------------------------

def test_ingest_tweets_logs_empty_and_duplicate_counts_separately(tmp_path: Path) -> None:
    from banking_tasci.logging_utils import get_logger

    get_logger("banking_tasci.data.ingest", log_dir=tmp_path)

    cfg = _make_cfg()
    df = pd.DataFrame({"text": ["hello world", None, "hello world", "another one"]})

    ingest_tweets(df, cfg)

    log_files = list(Path(tmp_path).glob("*.log"))
    assert len(log_files) == 1
    contents = log_files[0].read_text(encoding="utf-8")
    assert "empty_removed=1" in contents
    assert "exact_duplicate_removed=1" in contents


def test_ingest_reviews_logs_empty_and_duplicate_counts_separately(tmp_path: Path) -> None:
    from banking_tasci.logging_utils import get_logger

    get_logger("banking_tasci.data.ingest", log_dir=tmp_path)

    cfg = _make_cfg()
    df = pd.DataFrame(
        {
            **{col: ["value"] * 4 for col in REVIEW_REQUIRED_COLUMNS},
            "review": ["Great service", None, "Great service", "Another review"],
            "review_title_by_user": ["a", "b", "c", "d"],
            "bank": ["SBI"] * 4,
            "rating": [4, 3, 4, 5],
            "date": ["Mar 21, 2020"] * 4,
        }
    )

    ingest_reviews(df, cfg)

    log_files = list(Path(tmp_path).glob("*.log"))
    assert len(log_files) == 1
    contents = log_files[0].read_text(encoding="utf-8")
    assert "empty_removed=1" in contents
    assert "exact_duplicate_removed=1" in contents


# ---------------------------------------------------------------------------
# Property 9: Every canonical record carries the required fields with
# correct fixed/derived values.
# Validates: Requirements 7.1, 7.2, 7.4
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters=" "),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() != "")


@settings(max_examples=100)
@given(text=_safe_text)
# Feature: banking-tasci-pipeline, Property 9: Every canonical record carries the required fields with correct fixed/derived values
def test_property_tweet_canonical_record_fields(text) -> None:
    cfg = _make_cfg()
    df = pd.DataFrame({"text": [text]})

    records, _, _ = ingest_tweets(df, cfg)

    assert len(records) == 1
    row = records.iloc[0]
    for col in CANONICAL_COLUMNS:
        assert col in records.columns
    assert bool(row["context_available"]) is False
    assert row["previous_text"] == "[NO_CONTEXT]"


@settings(max_examples=100)
@given(review=_safe_text, title=_safe_text, bank=st.sampled_from(["SBI", "HDFC", "ICICI"]))
# Feature: banking-tasci-pipeline, Property 9: Every canonical record carries the required fields with correct fixed/derived values
def test_property_review_canonical_record_fields(review, title, bank) -> None:
    cfg = _make_cfg()
    df = _reviews_df(review=[review], review_title_by_user=[title], bank=[bank])

    records, _, _ = ingest_reviews(df, cfg)

    assert len(records) == 1
    row = records.iloc[0]
    for col in CANONICAL_COLUMNS:
        assert col in records.columns
    assert bool(row["context_available"]) is False
    assert row["previous_text"] == "[NO_CONTEXT]"
    from banking_tasci.data.anonymise import anonymise_text
    from banking_tasci.data.clean import normalise_text

    expected_text, _ = anonymise_text(normalise_text(review), cfg)
    expected_title, _ = anonymise_text(normalise_text(title), cfg)
    assert row["text"] == expected_text
    assert row["title"] == expected_title


# ---------------------------------------------------------------------------
# Property 10: record_id is a deterministic function of source and
# normalised text.
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    source_a=st.text(min_size=1, max_size=20),
    source_b=st.text(min_size=1, max_size=20),
    text_a=st.text(min_size=0, max_size=40),
    text_b=st.text(min_size=0, max_size=40),
)
# Feature: banking-tasci-pipeline, Property 10: record_id is a deterministic function of source and normalised text
def test_property_record_id_deterministic(source_a, source_b, text_a, text_b) -> None:
    id_a1 = make_record_id(source_a, text_a)
    id_a2 = make_record_id(source_a, text_a)
    assert id_a1 == id_a2

    id_b = make_record_id(source_b, text_b)
    if source_a != source_b or text_a != text_b:
        assert id_a1 != id_b


# ---------------------------------------------------------------------------
# Property 11: rating never influences derived record content.
# Validates: Requirements 7.5
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    review=_safe_text,
    title=_safe_text,
    bank=st.sampled_from(["SBI", "HDFC", "ICICI"]),
    rating_a=st.integers(min_value=1, max_value=5),
    rating_b=st.integers(min_value=1, max_value=5),
)
# Feature: banking-tasci-pipeline, Property 11: rating never influences derived record content
def test_property_rating_never_influences_derived_content(review, title, bank, rating_a, rating_b) -> None:
    cfg = _make_cfg()
    df_a = _reviews_df(review=[review], review_title_by_user=[title], bank=[bank], rating=[rating_a])
    df_b = _reviews_df(review=[review], review_title_by_user=[title], bank=[bank], rating=[rating_b])

    records_a, _, _ = ingest_reviews(df_a, cfg)
    records_b, _, _ = ingest_reviews(df_b, cfg)

    assert len(records_a) == 1
    assert len(records_b) == 1
    row_a = records_a.iloc[0]
    row_b = records_b.iloc[0]

    for col in CANONICAL_COLUMNS:
        if col == "rating":
            continue
        assert row_a[col] == row_b[col] or (pd.isna(row_a[col]) and pd.isna(row_b[col]))


# ---------------------------------------------------------------------------
# Data_Quality_Reporter: write_data_quality_report (Task 11)
# ---------------------------------------------------------------------------

import json  # noqa: E402

from banking_tasci.data.anonymise import AnonymisationAudit  # noqa: E402
from banking_tasci.data.ingest import write_data_quality_report  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests (Req 8.1, 8.2)
# ---------------------------------------------------------------------------

def test_write_data_quality_report_contains_required_top_level_fields(tmp_path: Path) -> None:
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": ["Great bank service today", None, "Great bank service today"]})
    reviews_df = _reviews_df()

    result = run_ingestion(tweets_df, reviews_df, cfg)
    report_path = tmp_path / "reports" / "data_report.json"

    write_data_quality_report(result, report_path)

    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert set(report.keys()) == {"generated_at", "overall", "per_source", "anonymisation_audit"}
    for key in ("rows_before", "rows_after", "empty_removed", "exact_duplicate_removed"):
        assert key in report["overall"]

    expected_sources = {stats.source for stats in result.per_source_stats}
    assert set(report["per_source"].keys()) == expected_sources
    for source_report in report["per_source"].values():
        for key in ("rows_before", "rows_after", "empty_removed", "exact_duplicate_removed"):
            assert key in source_report

    assert report["anonymisation_audit"] == result.anonymisation_audit.to_dict()


def test_write_data_quality_report_writes_to_supplied_path(tmp_path: Path) -> None:
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": ["Tweet one"]})
    reviews_df = _reviews_df()
    result = run_ingestion(tweets_df, reviews_df, cfg)

    report_path = tmp_path / "nested" / "dir" / "report.json"
    assert not report_path.parent.exists()

    write_data_quality_report(result, report_path)

    assert report_path.is_file()
    # Written to exactly the path supplied, not some derived path.
    other_candidate = tmp_path / "report.json"
    assert not other_candidate.exists()


def test_write_data_quality_report_overall_sums_per_source_stats(tmp_path: Path) -> None:
    cfg = _make_cfg()
    tweets_df = pd.DataFrame({"text": ["Tweet one", "Tweet two", None]})
    reviews_df = _reviews_df()
    result = run_ingestion(tweets_df, reviews_df, cfg)

    report_path = tmp_path / "report.json"
    write_data_quality_report(result, report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    for key in ("rows_before", "rows_after", "empty_removed", "exact_duplicate_removed"):
        expected = sum(getattr(stats, key) for stats in result.per_source_stats)
        assert report["overall"][key] == expected


# ---------------------------------------------------------------------------
# Property 12: Per-source row-count breakdown sums to the overall totals.
# Validates: Requirements 8.3
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    tweet_texts=st.lists(
        st.one_of(st.none(), st.just(""), st.text(min_size=1, max_size=15)),
        min_size=0,
        max_size=8,
    ),
    review_texts=st.lists(
        st.one_of(st.none(), st.just(""), st.text(min_size=1, max_size=15)),
        min_size=0,
        max_size=8,
    ),
)
def test_property_per_source_breakdown_sums_to_overall(tweet_texts, review_texts) -> None:
    cfg = _make_cfg()

    if len(tweet_texts) == 0:
        tweets_df = pd.DataFrame({"text": pd.Series(dtype="object")})
    else:
        tweets_df = pd.DataFrame({"text": tweet_texts})

    if len(review_texts) == 0:
        reviews_df = _reviews_df()
        reviews_df = reviews_df.iloc[0:0]
    else:
        reviews_df = pd.DataFrame(
            {
                **{col: ["value"] * len(review_texts) for col in REVIEW_REQUIRED_COLUMNS},
                "review": review_texts,
                "review_title_by_user": ["t"] * len(review_texts),
                "bank": ["SBI"] * len(review_texts),
                "rating": [4] * len(review_texts),
                "date": ["Mar 21, 2020"] * len(review_texts),
            }
        )

    result = run_ingestion(tweets_df, reviews_df, cfg)

    with tempfile.TemporaryDirectory() as tmp_dir:
        report_path = Path(tmp_dir) / "prop12_report.json"
        write_data_quality_report(result, report_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))

    total_rows_before = sum(v["rows_before"] for v in report["per_source"].values())
    total_rows_after = sum(v["rows_after"] for v in report["per_source"].values())

    assert total_rows_before == report["overall"]["rows_before"]
    assert total_rows_after == report["overall"]["rows_after"]
    assert total_rows_before == len(tweet_texts) + len(review_texts)
    assert total_rows_after == len(result.records)
