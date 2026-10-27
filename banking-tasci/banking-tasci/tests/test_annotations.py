"""Tests for the Annotation_Record schema and validation rules
(src/banking_tasci/data/annotations.py).

Covers one test per validation rule plus the "never auto-correct" and
JSONL round-trip guarantees.

- Req 12.3, 12.4: offset semantics (start inclusive, end exclusive,
  case-sensitive text[start:end] == term).
- Req 12.6, 12.7, 12.8: empty aspects accepted; non-overlapping spans
  accepted; overlapping spans rejected.
- Req 19.2, 19.3, 19.4: unknown category/sentiment/intent rejected.
- Req 19.5: missing required field rejected.
- Req 19.6, 19.7: invalid/out-of-bounds offsets and offset-text mismatch
  rejected.
- Req 19.8, 19.9: overlapping and duplicate spans rejected.
- Req 19.10: context_available/previous_text inconsistency rejected.
- Req 19.11: annotation_status=completed with empty intent rejected;
  other statuses (e.g. not_started) with empty intent are NOT rejected by
  this check.
- Req 19.12: raw-identifier-in-text detection.
- Req 19.13: validate_record runs every check and never mutates the input.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.annotations import (  # noqa: E402
    AspectSpan,
    AnnotationRecord,
    check_completed_intent,
    check_context_consistency,
    check_labels,
    check_no_raw_identifiers,
    check_offsets,
    check_overlap,
    read_jsonl,
    validate_all,
    validate_record,
    write_jsonl,
)

_BASE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "base.yaml"


def _cfg():
    return load_config(_BASE_CONFIG_PATH)


def _valid_record(**overrides) -> AnnotationRecord:
    """A minimal, fully valid, completed AnnotationRecord."""
    base = dict(
        record_id="rec-1",
        source="bank_reviews",
        region="international",
        text="The mobile app is slow but customer support was helpful.",
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=[
            AspectSpan(term="mobile app", start=4, end=14, category="digital_banking", sentiment="negative"),
            AspectSpan(term="customer support", start=27, end=43, category="customer_support", sentiment="positive"),
        ],
        intent="general_feedback",
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="annotator_a",
        annotation_status="completed",
        notes="",
    )
    base.update(overrides)
    return AnnotationRecord(**base)


# ---------------------------------------------------------------------------
# Valid-record acceptance
# ---------------------------------------------------------------------------


def test_valid_record_has_no_errors():
    record = _valid_record()
    assert validate_record(record, cfg=_cfg()) == []


def test_valid_record_with_empty_aspects_is_accepted():
    record = _valid_record(aspects=[])
    assert validate_record(record, cfg=_cfg()) == []


# ---------------------------------------------------------------------------
# check_offsets
# ---------------------------------------------------------------------------


def test_offset_mismatch_is_rejected():
    record = _valid_record(
        aspects=[AspectSpan(term="wrong term", start=4, end=14, category="digital_banking", sentiment="negative")]
    )
    errors = check_offsets(record)
    assert any(e.error_type == "offset_mismatch" for e in errors)


def test_out_of_bounds_offset_is_rejected():
    record = _valid_record(
        aspects=[AspectSpan(term="mobile app", start=4, end=999, category="digital_banking", sentiment="negative")]
    )
    errors = check_offsets(record)
    assert any(e.error_type == "invalid_offset" for e in errors)


def test_start_greater_than_or_equal_end_is_rejected():
    record = _valid_record(
        aspects=[AspectSpan(term="", start=10, end=10, category="digital_banking", sentiment="negative")]
    )
    errors = check_offsets(record)
    assert any(e.error_type == "invalid_offset" for e in errors)


# ---------------------------------------------------------------------------
# check_overlap
# ---------------------------------------------------------------------------


def test_overlapping_spans_are_rejected():
    record = _valid_record(
        aspects=[
            AspectSpan(term="mobile app", start=4, end=14, category="digital_banking", sentiment="negative"),
            AspectSpan(term="app is slow", start=11, end=22, category="digital_banking", sentiment="negative"),
        ]
    )
    errors = check_overlap(record)
    assert any(e.error_type == "overlapping_spans" for e in errors)


def test_duplicate_spans_are_rejected():
    record = _valid_record(
        aspects=[
            AspectSpan(term="mobile app", start=4, end=14, category="digital_banking", sentiment="negative"),
            AspectSpan(term="mobile app", start=4, end=14, category="digital_banking", sentiment="positive"),
        ]
    )
    errors = check_overlap(record)
    assert any(e.error_type == "duplicate_span" for e in errors)


def test_non_overlapping_spans_are_accepted():
    record = _valid_record()
    assert check_overlap(record) == []


# ---------------------------------------------------------------------------
# check_labels
# ---------------------------------------------------------------------------


def test_unknown_category_is_rejected():
    record = _valid_record(
        aspects=[AspectSpan(term="mobile app", start=4, end=14, category="not_a_category", sentiment="negative")]
    )
    errors = check_labels(record)
    assert any(e.error_type == "unknown_category" for e in errors)


def test_unknown_sentiment_is_rejected():
    record = _valid_record(
        aspects=[AspectSpan(term="mobile app", start=4, end=14, category="digital_banking", sentiment="mixed")]
    )
    errors = check_labels(record)
    assert any(e.error_type == "unknown_sentiment" for e in errors)


def test_unknown_intent_is_rejected():
    record = _valid_record(intent="not_a_real_intent")
    errors = check_labels(record)
    assert any(e.error_type == "unknown_intent" for e in errors)


# ---------------------------------------------------------------------------
# Missing required field (structural, Req 19.5)
# ---------------------------------------------------------------------------


def test_missing_required_field_is_rejected():
    record = _valid_record()
    del record.__dict__["record_id"]  # simulate an absent key from JSONL
    errors = validate_record(record, cfg=_cfg())
    assert any(e.error_type == "missing_required_field" for e in errors)


# ---------------------------------------------------------------------------
# check_context_consistency
# ---------------------------------------------------------------------------


def test_context_false_with_non_placeholder_previous_text_is_rejected():
    record = _valid_record(context_available=False, previous_text="Some earlier sentence.")
    errors = check_context_consistency(record)
    assert any(e.error_type == "context_inconsistency" for e in errors)


def test_context_true_with_placeholder_previous_text_is_rejected():
    record = _valid_record(context_available=True, previous_text="[NO_CONTEXT]")
    errors = check_context_consistency(record)
    assert any(e.error_type == "context_inconsistency" for e in errors)


def test_context_consistent_pair_is_accepted():
    record = _valid_record(context_available=True, previous_text="Earlier sentence.")
    assert check_context_consistency(record) == []


# ---------------------------------------------------------------------------
# check_completed_intent
# ---------------------------------------------------------------------------


def test_completed_status_with_empty_intent_is_rejected():
    record = _valid_record(annotation_status="completed", intent=None)
    errors = check_completed_intent(record)
    assert any(e.error_type == "missing_intent" for e in errors)


def test_not_started_status_with_empty_intent_is_not_rejected():
    record = _valid_record(annotation_status="not_started", intent=None, aspects=[])
    errors = check_completed_intent(record)
    assert errors == []


# ---------------------------------------------------------------------------
# check_no_raw_identifiers
# ---------------------------------------------------------------------------


def test_raw_email_in_text_is_flagged():
    record = _valid_record(text="Email me at jane.doe@example.com please", aspects=[])
    errors = check_no_raw_identifiers(record, _cfg())
    assert any(e.error_type == "raw_identifier" for e in errors)


def test_raw_account_number_in_text_is_flagged():
    record = _valid_record(text="My account number is 123456789 thanks", aspects=[])
    errors = check_no_raw_identifiers(record, _cfg())
    assert any(e.error_type == "raw_identifier" for e in errors)


def test_raw_phone_number_in_text_is_flagged():
    record = _valid_record(text="Call me back on 555-123-4567 please", aspects=[])
    errors = check_no_raw_identifiers(record, _cfg())
    assert any(e.error_type == "raw_identifier" for e in errors)


def test_clean_text_has_no_raw_identifier_flags():
    record = _valid_record()
    assert check_no_raw_identifiers(record, _cfg()) == []


# ---------------------------------------------------------------------------
# validate_record runs every check, never mutates, never auto-corrects
# ---------------------------------------------------------------------------


def test_validate_record_reports_multiple_simultaneous_violations():
    record = _valid_record(
        context_available=True,
        previous_text="[NO_CONTEXT]",
        annotation_status="completed",
        intent=None,
        aspects=[AspectSpan(term="wrong", start=4, end=14, category="not_a_category", sentiment="mixed")],
    )
    errors = validate_record(record, cfg=_cfg())
    error_types = {e.error_type for e in errors}
    assert "context_inconsistency" in error_types
    assert "missing_intent" in error_types
    assert "unknown_category" in error_types
    assert "unknown_sentiment" in error_types
    assert "offset_mismatch" in error_types


def test_validate_record_does_not_mutate_input():
    record = _valid_record(intent="not_a_real_intent")
    snapshot = AnnotationRecord(**{**record.__dict__})
    validate_record(record, cfg=_cfg())
    assert record.__dict__ == snapshot.__dict__


def test_invalid_records_are_reported_not_auto_corrected():
    valid_record = _valid_record(record_id="valid-1")
    invalid_record = _valid_record(record_id="invalid-1", intent="bogus_intent")

    valid, invalid = validate_all([valid_record, invalid_record], cfg=_cfg())

    assert [r.record_id for r in valid] == ["valid-1"]
    assert "invalid-1" in invalid
    assert any(e.error_type == "unknown_intent" for e in invalid["invalid-1"])
    # The invalid record's stored intent is untouched, not silently fixed
    # or replaced with None/a valid value.
    assert invalid_record.intent == "bogus_intent"


# ---------------------------------------------------------------------------
# JSONL read/write round-trip
# ---------------------------------------------------------------------------


def test_write_then_read_jsonl_round_trips(tmp_path):
    records = [_valid_record(record_id="a"), _valid_record(record_id="b", aspects=[])]
    path = tmp_path / "records.jsonl"

    write_jsonl(records, path)
    loaded = read_jsonl(path)

    assert len(loaded) == 2
    assert loaded[0].record_id == "a"
    assert loaded[1].record_id == "b"
    assert loaded[1].aspects == []
    assert loaded[0].aspects[0].term == "mobile app"
