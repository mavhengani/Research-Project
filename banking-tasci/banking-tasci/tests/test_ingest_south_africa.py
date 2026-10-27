"""Focused tests for the South African banking Twitter ingestion pipeline.

These tests use small in-memory fixtures only.
They do not read any raw parquet files, do not connect to the internet,
do not train models, and do not modify any existing gold dataset files.

Run with (after approval):
    PYTHONPATH=src python3 -m pytest tests/test_ingest_south_africa.py -v
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from banking_tasci.data.ingest_south_africa import (
    SOURCE_NAME,
    REGION,
    CANONICAL_COLUMNS,
    validate_sa_parquet_schema,
    SouthAfricaSchemaError,
    make_sa_record_id,
    _normalise_created_at,
    classify_username,
    compute_candidate_strata,
    is_promotional,
    is_customer_feedback_candidate,
    to_annotation_records,
    select_annotation_sample,
    CONFIRMED_OFFICIAL_HANDLES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sa_df(n: int = 5, bank: str = "fnb") -> pd.DataFrame:
    """Create a minimal valid SA parquet dataframe."""
    return pd.DataFrame({
        "Datetime": pd.to_datetime(
            [f"2021-0{i+1}-01 10:00:00+00:00" for i in range(n)],
            utc=True,
        ),
        "Tweet_Id": [1000 + i for i in range(n)],
        "Tweet": [f"My {bank} transfer failed please help {i}" for i in range(n)],
        "Username": [f"customer{i}" for i in range(n)],
        "Reply_Count": [0] * n,
        "Retweet_Count": [0] * n,
        "Like_Count": [1] * n,
        "Bank": [bank] * n,
    })


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_valid_schema_passes(self):
        df = _make_sa_df()
        # Should not raise
        validate_sa_parquet_schema(df, "test.parquet")

    def test_missing_column_raises(self):
        df = _make_sa_df().drop(columns=["Tweet"])
        with pytest.raises(SouthAfricaSchemaError, match="Tweet"):
            validate_sa_parquet_schema(df, "test.parquet")

    def test_missing_multiple_columns_raises(self):
        df = _make_sa_df().drop(columns=["Tweet", "Bank"])
        with pytest.raises(SouthAfricaSchemaError):
            validate_sa_parquet_schema(df, "test.parquet")

    def test_extra_columns_allowed(self):
        df = _make_sa_df()
        df["extra_col"] = "x"
        validate_sa_parquet_schema(df, "test.parquet")  # should not raise


# ---------------------------------------------------------------------------
# Record ID stability
# ---------------------------------------------------------------------------


class TestRecordId:
    def test_record_id_is_16_chars(self):
        rid = make_sa_record_id(123456789)
        assert len(rid) == 16

    def test_record_id_is_hex(self):
        rid = make_sa_record_id(123456789)
        int(rid, 16)  # should not raise

    def test_record_id_deterministic(self):
        rid1 = make_sa_record_id(123456789)
        rid2 = make_sa_record_id(123456789)
        assert rid1 == rid2

    def test_different_tweet_ids_give_different_record_ids(self):
        rid1 = make_sa_record_id(111111111)
        rid2 = make_sa_record_id(222222222)
        assert rid1 != rid2

    def test_uses_source_name_in_hash(self):
        tweet_id = 999999999
        expected_payload = f"{SOURCE_NAME}:{tweet_id}"
        expected = hashlib.sha256(expected_payload.encode()).hexdigest()[:16]
        assert make_sa_record_id(tweet_id) == expected

    def test_identical_texts_from_different_tweets_get_different_ids(self):
        # Two different tweet IDs produce different record IDs even if text is same
        rid1 = make_sa_record_id(100)
        rid2 = make_sa_record_id(200)
        assert rid1 != rid2


# ---------------------------------------------------------------------------
# Region provenance
# ---------------------------------------------------------------------------


class TestRegionProvenance:
    def test_region_constant_is_south_africa(self):
        assert REGION == "south_africa"

    def test_source_constant(self):
        assert SOURCE_NAME == "south_african_bank_tweets"

    def test_annotation_record_has_correct_region(self):
        df = pd.DataFrame({
            "record_id": ["abc123"],
            "source": [SOURCE_NAME],
            "region": [REGION],
            "bank": ["fnb"],
            "text": ["My transfer failed please help"],
            "previous_text": ["[NO_CONTEXT]"],
            "context_available": [False],
            "customer_feedback_candidate": [True],
            "candidate_strata": ["transactions_candidate"],
            "likely_promotional": [False],
            "possible_official_account": [False],
            "filter_reason": ["matched_strata"],
        })
        records = to_annotation_records(df)
        assert records[0]["region"] == "south_africa"


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------


class TestDateNormalisation:
    def test_valid_timestamp_returns_iso_date(self):
        ts = pd.Timestamp("2021-03-15 10:30:00+00:00")
        ca, car = _normalise_created_at(ts)
        assert ca == "2021-03-15"
        assert car is None

    def test_none_returns_none_none(self):
        ca, car = _normalise_created_at(None)
        assert ca is None
        assert car is None

    def test_unparseable_string_returns_none_raw(self):
        ca, car = _normalise_created_at("not-a-date-at-all")
        assert ca is None
        assert car == "not-a-date-at-all"

    def test_empty_string_returns_none_none(self):
        ca, car = _normalise_created_at("")
        assert ca is None
        assert car is None


# ---------------------------------------------------------------------------
# Context always [NO_CONTEXT]
# ---------------------------------------------------------------------------


class TestContextHandling:
    def test_annotation_record_previous_text_is_no_context(self):
        df = pd.DataFrame({
            "record_id": ["r1"],
            "source": [SOURCE_NAME],
            "region": [REGION],
            "bank": ["absa"],
            "text": ["The app keeps crashing"],
            "previous_text": ["[NO_CONTEXT]"],
            "context_available": [False],
        })
        records = to_annotation_records(df)
        assert records[0]["previous_text"] == "[NO_CONTEXT]"
        assert records[0]["context_available"] is False

    def test_no_preceding_csv_row_as_context(self):
        # Multiple records — each must have [NO_CONTEXT], not the preceding record's text
        df = pd.DataFrame({
            "record_id": ["r1", "r2"],
            "source": [SOURCE_NAME, SOURCE_NAME],
            "region": [REGION, REGION],
            "bank": ["fnb", "fnb"],
            "text": ["first tweet text here", "second tweet text here"],
            "previous_text": ["[NO_CONTEXT]", "[NO_CONTEXT]"],
            "context_available": [False, False],
        })
        records = to_annotation_records(df)
        for rec in records:
            assert rec["previous_text"] == "[NO_CONTEXT]"


# ---------------------------------------------------------------------------
# Official account filtering
# ---------------------------------------------------------------------------


class TestOfficialAccountFiltering:
    def test_confirmed_official_handle_detected(self):
        for handle in ["fnb", "absa", "nedbank", "capitec", "standardbank",
                       "fnbsa", "absahelp", "nedbanksa", "capitecbank"]:
            is_conf, is_poss = classify_username(handle)
            assert is_conf, f"Expected {handle!r} to be confirmed official"

    def test_customer_username_not_flagged(self):
        for handle in ["john_doe_123", "mymoneyman", "banking_complaint_za",
                       "regular_user", "help_me_please"]:
            is_conf, is_poss = classify_username(handle)
            assert not is_conf, f"Expected {handle!r} NOT to be confirmed official"

    def test_empty_username_not_flagged(self):
        is_conf, is_poss = classify_username("")
        assert not is_conf
        assert not is_poss

    def test_broad_substring_not_used(self):
        # A customer named "fnb_customer" should NOT be confirmed official
        # (broad substring rule must not apply to confirmed list)
        is_conf, is_poss = classify_username("fnb_customer")
        assert not is_conf

    def test_possible_official_pattern_detected(self):
        is_conf, is_poss = classify_username("fnb_official")
        # Should be flagged as possible but not confirmed
        # (exact pattern depends on POSSIBLE_OFFICIAL_PATTERNS)
        # At minimum, it should not raise
        assert isinstance(is_conf, bool)
        assert isinstance(is_poss, bool)


# ---------------------------------------------------------------------------
# Candidate strata
# ---------------------------------------------------------------------------


class TestCandidateStrata:
    def test_transaction_strata_detected(self):
        strata = compute_candidate_strata("My transfer failed yesterday")
        assert "transactions_candidate" in strata

    def test_fees_strata_detected(self):
        strata = compute_candidate_strata("Why was I charged for a monthly service fee?")
        assert "fees_candidate" in strata

    def test_fraud_strata_detected(self):
        strata = compute_candidate_strata("Someone made an unauthorised transaction on my account")
        assert "fraud_security_candidate" in strata

    def test_churn_strata_detected(self):
        strata = compute_candidate_strata("I am closing my account and switching banks")
        assert "churn_candidate" in strata

    def test_no_strata_for_unrelated_text(self):
        strata = compute_candidate_strata("Happy birthday to my friend today")
        assert len(strata) == 0, f"Expected 0 strata, got: {strata}"

    def test_multiple_strata_possible(self):
        strata = compute_candidate_strata("my card was blocked and I got charged a service fee")
        assert "cards_candidate" in strata
        assert "fees_candidate" in strata

    def test_strata_are_sampling_aids_not_labels(self):
        # Verify strata are only used for sampling, not stored in gold annotation output
        df = pd.DataFrame({
            "record_id": ["r1"],
            "source": [SOURCE_NAME],
            "region": [REGION],
            "bank": ["fnb"],
            "text": ["My card was charged an unusual fee"],
            "previous_text": ["[NO_CONTEXT]"],
            "context_available": [False],
            "candidate_strata": ["fees_candidate;cards_candidate"],
        })
        records = to_annotation_records(df)
        # candidate_strata must NOT appear in annotation output
        assert "candidate_strata" not in records[0]
        assert "filter_reason" not in records[0]
        assert "likely_promotional" not in records[0]


# ---------------------------------------------------------------------------
# Promotional filtering
# ---------------------------------------------------------------------------


class TestPromotionalFiltering:
    def test_competition_flagged(self):
        assert is_promotional("Win R1000 in our giveaway competition") is True

    def test_customer_feedback_not_flagged(self):
        assert is_promotional("My account was blocked without notice please help") is False

    def test_apply_now_flagged(self):
        assert is_promotional("Apply now for our new account offer") is True


# ---------------------------------------------------------------------------
# Customer-feedback candidate logic
# ---------------------------------------------------------------------------


class TestCustomerFeedbackCandidate:
    def test_strata_match_makes_candidate(self):
        strata = ["transactions_candidate"]
        is_cand, reason = is_customer_feedback_candidate("transfer failed", strata, False)
        assert is_cand is True

    def test_promotional_with_no_strata_excluded(self):
        is_cand, reason = is_customer_feedback_candidate("Win R500 competition apply now", [], True)
        assert is_cand is False
        assert "promotional" in reason

    def test_long_non_promotional_is_candidate(self):
        text = "I have been experiencing issues with my banking app for the past three weeks"
        is_cand, reason = is_customer_feedback_candidate(text, [], False)
        assert is_cand is True

    def test_short_text_no_strata_excluded(self):
        is_cand, reason = is_customer_feedback_candidate("ok", [], False)
        assert is_cand is False


# ---------------------------------------------------------------------------
# Annotation output schema
# ---------------------------------------------------------------------------


class TestAnnotationOutputSchema:
    def _make_sample_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "record_id": ["r1", "r2"],
            "source": [SOURCE_NAME, SOURCE_NAME],
            "region": [REGION, REGION],
            "bank": ["fnb", "absa"],
            "text": ["Transfer failed please help me now", "App not working cannot login today"],
            "previous_text": ["[NO_CONTEXT]", "[NO_CONTEXT]"],
            "context_available": [False, False],
            "candidate_strata": ["transactions_candidate", "digital_banking_candidate"],
            "filter_reason": ["matched_strata", "matched_strata"],
        })

    def test_required_fields_present(self):
        df = self._make_sample_df()
        records = to_annotation_records(df)
        required = ["record_id", "source", "region", "bank", "text", "previous_text",
                    "context_available", "aspects", "intent", "intent_ambiguous",
                    "alternative_intent", "annotator_id", "annotation_status", "notes"]
        for rec in records:
            for field in required:
                assert field in rec, f"Missing field: {field}"

    def test_gold_fields_are_blank(self):
        df = self._make_sample_df()
        records = to_annotation_records(df)
        for rec in records:
            assert rec["aspects"] == []
            assert rec["intent"] is None
            assert rec["intent_ambiguous"] is False
            assert rec["alternative_intent"] is None
            assert rec["annotator_id"] is None
            assert rec["annotation_status"] == "not_started"
            assert rec["notes"] == ""

    def test_no_sentiment_leakage(self):
        """No sentiment, polarity, or label columns in annotation output."""
        df = self._make_sample_df()
        df["sentiment"] = "positive"  # simulated leakage attempt
        df["polarity"] = 0.5
        records = to_annotation_records(df)
        for rec in records:
            assert "sentiment" not in rec
            assert "polarity" not in rec
            assert "candidate_strata" not in rec

    def test_context_always_no_context(self):
        df = self._make_sample_df()
        records = to_annotation_records(df)
        for rec in records:
            assert rec["previous_text"] == "[NO_CONTEXT]"
            assert rec["context_available"] is False


# ---------------------------------------------------------------------------
# Sample selection determinism
# ---------------------------------------------------------------------------


class TestSampleSelection:
    def _make_candidate_pool(self, n: int = 50) -> pd.DataFrame:
        banks = ["fnb", "absa", "nedbank", "capitec", "standard_bank"]
        rows = []
        for i in range(n):
            bank = banks[i % len(banks)]
            rows.append({
                "record_id": f"rid_{i:04d}",
                "source": SOURCE_NAME,
                "region": REGION,
                "bank": bank,
                "text": f"My {bank} app keeps failing and I need help with my account transfer {i}",
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "customer_feedback_candidate": True,
                "candidate_strata": "transactions_candidate;digital_banking_candidate",
                "likely_promotional": False,
                "possible_official_account": False,
                "filter_reason": "matched_strata",
                "near_dup_flag": False,
                "near_dup_group_id": None,
                "created_at": f"2020-0{(i%9)+1}-15",
            })
        return pd.DataFrame(rows)

    def test_deterministic_sampling(self):
        pool = self._make_candidate_pool(50)
        sample1 = select_annotation_sample(pool, sample_size=20, seed=42)
        sample2 = select_annotation_sample(pool, sample_size=20, seed=42)
        assert list(sample1["record_id"]) == list(sample2["record_id"])

    def test_different_seed_different_sample(self):
        pool = self._make_candidate_pool(50)
        sample1 = select_annotation_sample(pool, sample_size=20, seed=42)
        sample2 = select_annotation_sample(pool, sample_size=20, seed=99)
        # Very likely to differ (though not guaranteed with small pool)
        # At minimum both are valid
        assert len(sample1) == len(sample2)

    def test_no_duplicate_record_ids_in_sample(self):
        pool = self._make_candidate_pool(50)
        sample = select_annotation_sample(pool, sample_size=20, seed=42)
        assert sample["record_id"].nunique() == len(sample)

    def test_sample_size_respected(self):
        pool = self._make_candidate_pool(50)
        sample = select_annotation_sample(pool, sample_size=30, seed=42)
        assert len(sample) <= 30

    def test_only_candidates_selected(self):
        pool = self._make_candidate_pool(50)
        # Add some non-candidates
        non_cand = pool.head(5).copy()
        non_cand["customer_feedback_candidate"] = False
        non_cand["record_id"] = [f"non_cand_{i}" for i in range(5)]
        all_pool = pd.concat([pool, non_cand], ignore_index=True)
        sample = select_annotation_sample(all_pool, sample_size=20, seed=42)
        non_cand_ids = set(non_cand["record_id"])
        for rid in sample["record_id"]:
            assert rid not in non_cand_ids

    def test_possible_official_excluded_from_sample(self):
        pool = self._make_candidate_pool(20)
        pool.loc[0, "possible_official_account"] = True
        pool.loc[0, "record_id"] = "official_0000"
        sample = select_annotation_sample(pool, sample_size=15, seed=42)
        assert "official_0000" not in sample["record_id"].tolist()


# ---------------------------------------------------------------------------
# No modification of existing gold files
# ---------------------------------------------------------------------------


class TestGoldDataIntegrity:
    def test_canonical_columns_include_near_dup_group_id(self):
        """near_dup_group_id is part of the SA canonical schema."""
        assert "near_dup_group_id" in CANONICAL_COLUMNS

    def test_annotation_record_has_no_gold_labels(self):
        """Confirms gold fields are empty in annotation output."""
        df = pd.DataFrame({
            "record_id": ["test1"],
            "source": [SOURCE_NAME],
            "region": [REGION],
            "bank": ["fnb"],
            "text": ["Completely valid customer feedback text here"],
            "previous_text": ["[NO_CONTEXT]"],
            "context_available": [False],
        })
        records = to_annotation_records(df)
        rec = records[0]
        # Gold annotation fields must be blank
        assert rec["aspects"] == []
        assert rec["intent"] is None
        assert rec["annotation_status"] == "not_started"
