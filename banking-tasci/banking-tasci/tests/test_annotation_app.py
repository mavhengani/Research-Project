"""Tests for the Streamlit-free pure logic in scripts/annotation_app.py
(Requirement 18).

Covers:
- Req 18.8: per-annotator output filename derivation; never overwriting
  another annotator's file; resuming from an existing annotator file;
  updating (not duplicating) an already-saved record by `record_id`.
- Req 18.9: navigation index clamping.
- Req 18.10: completed/total progress calculation.
- Req 18.11: aspect span offset bounds rejection (`start`/`end` outside
  `len(text)`, or `start >= end`).
- Req 18.5: adding/removing more than one aspect span per record.
- Req 18.6: intent/ambiguous/alternative_intent + the completed-status/
  intent-required interaction mirroring `check_completed_intent`.
- Structural note: `record_id`/`source`/`region`/`text`/`previous_text`/
  `context_available` are preserved unchanged when building an updated
  record.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
for _dir in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import pytest  # noqa: E402

from banking_tasci.data.annotations import AnnotationRecord, AspectSpan, read_jsonl, write_jsonl  # noqa: E402

from annotation_app import (  # noqa: E402
    add_aspect,
    annotator_output_path,
    aspect_dicts_from_record,
    aspect_spans_from_dicts,
    build_updated_record,
    clamp_index,
    compute_progress,
    load_session_records,
    remove_aspect,
    resolve_annotation_status,
    save_annotator_file,
    update_record_in_list,
    validate_span,
)


def _make_record(record_id="r1", text="The card fee is too high", annotator_id="", status="not_started"):
    return AnnotationRecord(
        record_id=record_id,
        source="bank_reviews",
        region="ZA",
        text=text,
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=[],
        intent=None,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id=annotator_id,
        annotation_status=status,
        notes="",
    )


# ---------------------------------------------------------------------------
# Req 18.11: offset bounds validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "start,end",
    [(-1, 4), (0, 100), (5, 5), (6, 5)],
)
def test_validate_span_rejects_invalid_offsets(start, end):
    text = "The card fee is too high"
    assert validate_span(text, start, end) is not None


def test_validate_span_accepts_valid_offset():
    text = "The card fee is too high"
    assert validate_span(text, 4, 8) is None


def test_add_aspect_rejects_out_of_bounds_span():
    text = "short"
    pending, error = add_aspect(pending_aspects=[], text=text, start=0, end=100, category="fees", sentiment="negative")
    assert pending == []
    assert error is not None


def test_add_aspect_rejects_start_ge_end():
    text = "short"
    pending, error = add_aspect(pending_aspects=[], text=text, start=3, end=3, category="fees", sentiment="negative")
    assert pending == []
    assert error is not None


def test_add_aspect_rejects_unknown_category_or_sentiment():
    text = "The card fee is too high"
    _, error_cat = add_aspect([], text, 4, 8, "not_a_category", "negative")
    assert error_cat is not None
    _, error_sent = add_aspect([], text, 4, 8, "cards", "mixed")
    assert error_sent is not None


# ---------------------------------------------------------------------------
# Req 18.5: multiple aspects per record, add/remove
# ---------------------------------------------------------------------------


def test_add_aspect_appends_without_mutating_original_list():
    text = "The card fee is too high"
    original = []
    updated, error = add_aspect(original, text, 4, 8, "cards", "negative")
    assert error is None
    assert original == []  # not mutated
    assert len(updated) == 1
    assert updated[0]["term"] == "card"
    assert updated[0]["category"] == "cards"
    assert updated[0]["sentiment"] == "negative"


def test_add_aspect_supports_more_than_one_span():
    text = "The card fee is too high"
    aspects, err1 = add_aspect([], text, 4, 8, "cards", "negative")
    assert err1 is None
    aspects, err2 = add_aspect(aspects, text, 9, 12, "fees", "negative")
    assert err2 is None
    assert len(aspects) == 2
    assert [a["term"] for a in aspects] == ["card", "fee"]


def test_remove_aspect_removes_by_index_without_mutating_original():
    aspects = [
        {"term": "card", "start": 4, "end": 8, "category": "cards", "sentiment": "negative"},
        {"term": "fee", "start": 9, "end": 12, "category": "fees", "sentiment": "negative"},
    ]
    updated = remove_aspect(aspects, 0)
    assert len(aspects) == 2  # not mutated
    assert updated == [aspects[1]]


def test_remove_aspect_out_of_range_is_noop():
    aspects = [{"term": "card", "start": 4, "end": 8, "category": "cards", "sentiment": "negative"}]
    assert remove_aspect(aspects, 5) == aspects
    assert remove_aspect(aspects, -1) == aspects


# ---------------------------------------------------------------------------
# Req 18.6: completed-status requires a non-null intent
# ---------------------------------------------------------------------------


def test_resolve_annotation_status_completed_with_intent():
    status, warning = resolve_annotation_status(True, "complaint")
    assert status == "completed"
    assert warning is None


@pytest.mark.parametrize("intent", [None, ""])
def test_resolve_annotation_status_completed_without_intent_falls_back(intent):
    status, warning = resolve_annotation_status(True, intent)
    assert status == "in_progress"
    assert warning is not None


def test_resolve_annotation_status_not_completed():
    status, warning = resolve_annotation_status(False, None)
    assert status == "in_progress"
    assert warning is None


# ---------------------------------------------------------------------------
# Structural note: preserved fields on update
# ---------------------------------------------------------------------------


def test_build_updated_record_preserves_immutable_fields():
    original = _make_record()
    updated = build_updated_record(
        original,
        aspects=[AspectSpan(term="card", start=4, end=8, category="cards", sentiment="negative")],
        intent="complaint",
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="alice",
        notes="looks fine",
        annotation_status="completed",
    )
    assert updated.record_id == original.record_id
    assert updated.source == original.source
    assert updated.region == original.region
    assert updated.text == original.text
    assert updated.previous_text == original.previous_text
    assert updated.context_available == original.context_available
    assert updated.intent == "complaint"
    assert updated.annotator_id == "alice"
    assert updated.annotation_status == "completed"
    assert updated.notes == "looks fine"
    assert len(updated.aspects) == 1


# ---------------------------------------------------------------------------
# Req 18.8: per-annotator file derivation, never-overwrite, resume, update
# ---------------------------------------------------------------------------


def test_annotator_output_path_is_derived_from_annotator_id(tmp_path):
    path_a = annotator_output_path("alice", tmp_path)
    path_b = annotator_output_path("bob", tmp_path)
    assert path_a != path_b
    assert path_a.name == "pilot_alice.jsonl"
    assert path_b.name == "pilot_bob.jsonl"


def test_save_annotator_file_never_touches_another_annotators_file(tmp_path):
    bob_record = _make_record(record_id="bob-r1", annotator_id="bob")
    bob_path = save_annotator_file([bob_record], "bob", tmp_path)
    bob_mtime_before = bob_path.stat().st_mtime_ns
    bob_contents_before = bob_path.read_text(encoding="utf-8")

    alice_record = _make_record(record_id="alice-r1", annotator_id="alice")
    alice_path = save_annotator_file([alice_record], "alice", tmp_path)

    assert alice_path != bob_path
    assert bob_path.read_text(encoding="utf-8") == bob_contents_before
    assert bob_path.stat().st_mtime_ns == bob_mtime_before


def test_load_session_records_resumes_from_existing_annotator_file(tmp_path):
    unannotated_path = tmp_path / "pilot_unannotated.jsonl"
    write_jsonl([_make_record(record_id="r1"), _make_record(record_id="r2")], unannotated_path)

    # Simulate alice having already saved partial progress.
    alice_progress = [
        _make_record(record_id="r1", annotator_id="alice", status="completed"),
        _make_record(record_id="r2", annotator_id="alice", status="not_started"),
    ]
    save_annotator_file(alice_progress, "alice", tmp_path)

    resumed = load_session_records("alice", unannotated_path, tmp_path)
    assert [r.record_id for r in resumed] == ["r1", "r2"]
    assert resumed[0].annotation_status == "completed"


def test_load_session_records_starts_fresh_from_unannotated_when_no_existing_file(tmp_path):
    unannotated_path = tmp_path / "pilot_unannotated.jsonl"
    write_jsonl([_make_record(record_id="r1"), _make_record(record_id="r2")], unannotated_path)

    fresh = load_session_records("carol", unannotated_path, tmp_path)
    assert [r.record_id for r in fresh] == ["r1", "r2"]
    assert all(r.annotator_id == "carol" for r in fresh)
    assert all(r.annotation_status == "not_started" for r in fresh)


def test_update_record_in_list_replaces_rather_than_duplicates():
    records = [_make_record(record_id="r1"), _make_record(record_id="r2")]
    updated_r1 = _make_record(record_id="r1", status="completed")
    new_records = update_record_in_list(records, "r1", updated_r1)
    assert len(new_records) == 2
    assert new_records[0].annotation_status == "completed"
    assert new_records[1].record_id == "r2"
    # Original list unchanged.
    assert records[0].annotation_status == "not_started"


def test_update_record_in_list_raises_for_unknown_record_id():
    records = [_make_record(record_id="r1")]
    with pytest.raises(ValueError):
        update_record_in_list(records, "does-not-exist", _make_record(record_id="does-not-exist"))


def test_full_save_cycle_writes_single_line_per_record_id(tmp_path):
    unannotated_path = tmp_path / "pilot_unannotated.jsonl"
    write_jsonl([_make_record(record_id="r1"), _make_record(record_id="r2")], unannotated_path)

    records = load_session_records("dave", unannotated_path, tmp_path)
    updated = build_updated_record(
        records[0],
        aspects=[],
        intent="compliment",
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="dave",
        notes="",
        annotation_status="completed",
    )
    records = update_record_in_list(records, "r1", updated)
    path = save_annotator_file(records, "dave", tmp_path)

    reloaded = read_jsonl(path)
    assert len(reloaded) == 2  # updating r1 must not duplicate it
    assert reloaded[0].intent == "compliment"
    assert reloaded[0].annotation_status == "completed"


# ---------------------------------------------------------------------------
# Req 18.9: navigation index clamping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "index,total,expected",
    [(-5, 10, 0), (0, 10, 0), (9, 10, 9), (15, 10, 9), (0, 0, 0)],
)
def test_clamp_index(index, total, expected):
    assert clamp_index(index, total) == expected


# ---------------------------------------------------------------------------
# Req 18.10: completed/total progress
# ---------------------------------------------------------------------------


def test_compute_progress_counts_completed_records():
    records = [
        _make_record(record_id="r1", status="completed"),
        _make_record(record_id="r2", status="not_started"),
        _make_record(record_id="r3", status="completed"),
    ]
    completed, total = compute_progress(records)
    assert completed == 2
    assert total == 3


def test_compute_progress_empty_list():
    assert compute_progress([]) == (0, 0)


# ---------------------------------------------------------------------------
# aspect dict <-> AspectSpan round trip helpers
# ---------------------------------------------------------------------------


def test_aspect_dicts_round_trip():
    record = _make_record()
    record.aspects = [AspectSpan(term="card", start=4, end=8, category="cards", sentiment="negative")]
    dicts = aspect_dicts_from_record(record)
    assert dicts == [{"term": "card", "start": 4, "end": 8, "category": "cards", "sentiment": "negative"}]
    spans = aspect_spans_from_dicts(dicts)
    assert len(spans) == 1
    assert spans[0].term == "card"
    assert spans[0].category == "cards"
