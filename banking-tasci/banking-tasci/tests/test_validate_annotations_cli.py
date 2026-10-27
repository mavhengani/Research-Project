"""Tests for the Annotation_Validator CLI (scripts/validate_annotations.py).

Covers:
- Req 19.14: the JSON validation report written to `--output` contains every
  required top-level field with correct counts for a fixture containing a
  mix of valid and invalid records (valid/invalid counts, errors grouped by
  type with affected record IDs, label distributions over valid records,
  aspect count, zero-aspect count, ambiguous-intent count).
- Req 19.1: an unreadable/unparsable `--input` produces a non-zero exit code
  and does not require a report to be written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
for _dir in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from banking_tasci.data.annotations import (  # noqa: E402
    AnnotationRecord,
    AspectSpan,
    write_jsonl,
)

from validate_annotations import main  # noqa: E402


def _valid_record(
    record_id: str,
    *,
    text: str,
    aspects: list,
    intent,
    intent_ambiguous: bool = False,
) -> AnnotationRecord:
    """Build a schema-valid Annotation_Record. `annotation_status` is
    `"completed"` with a concrete `intent` so the completed-intent check
    passes; context fields are internally consistent (no context)."""
    return AnnotationRecord(
        record_id=record_id,
        source="bank_reviews",
        region="international",
        text=text,
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=aspects,
        intent=intent,
        intent_ambiguous=intent_ambiguous,
        alternative_intent=None,
        annotator_id="ann_a",
        annotation_status="completed",
        notes="",
    )


def test_report_structure_with_mixed_records(tmp_path):
    """A fixture mixing valid and invalid records yields a report with all
    required fields and correct counts (Req 19.14)."""
    # Valid record 1: two aspects (customer_support/positive, fees/negative),
    # intent=complaint, intent_ambiguous=True.
    text1 = "the staff were great but the fees are high"
    valid1 = _valid_record(
        "rec_valid_1",
        text=text1,
        aspects=[
            AspectSpan(term="staff", start=text1.index("staff"), end=text1.index("staff") + 5,
                       category="customer_support", sentiment="positive"),
            AspectSpan(term="fees", start=text1.index("fees"), end=text1.index("fees") + 4,
                       category="fees", sentiment="negative"),
        ],
        intent="complaint",
        intent_ambiguous=True,
    )

    # Valid record 2: zero aspects, intent=compliment, not ambiguous.
    valid2 = _valid_record(
        "rec_valid_2",
        text="everything was fine",
        aspects=[],
        intent="compliment",
    )

    # Invalid record 1: unknown aspect category.
    text_bad_cat = "the app is slow"
    invalid_cat = _valid_record(
        "rec_invalid_cat",
        text=text_bad_cat,
        aspects=[
            AspectSpan(term="app", start=text_bad_cat.index("app"), end=text_bad_cat.index("app") + 3,
                       category="not_a_category", sentiment="negative"),
        ],
        intent="complaint",
    )

    # Invalid record 2: offset mismatch (term does not match text[start:end]).
    text_bad_offset = "the card was declined"
    invalid_offset = _valid_record(
        "rec_invalid_offset",
        text=text_bad_offset,
        aspects=[
            AspectSpan(term="card", start=0, end=4, category="cards", sentiment="negative"),
        ],
        intent="complaint",
    )

    records = [valid1, valid2, invalid_cat, invalid_offset]
    fixture = tmp_path / "annotations.jsonl"
    write_jsonl(records, fixture)

    report_path = tmp_path / "report.json"
    exit_code = main(["--input", str(fixture), "--output", str(report_path)])

    assert exit_code == 0
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Required top-level fields present.
    for key in (
        "valid_count",
        "invalid_count",
        "errors_by_type",
        "affected_record_ids",
        "label_distributions",
        "aspect_count",
        "zero_aspect_count",
        "ambiguous_intent_count",
    ):
        assert key in report, f"missing report field: {key}"

    # Counts.
    assert report["valid_count"] == 2
    assert report["invalid_count"] == 2

    # Errors grouped by type + affected record IDs.
    assert "unknown_category" in report["errors_by_type"]
    assert "offset_mismatch" in report["errors_by_type"]
    assert "rec_invalid_cat" in report["affected_record_ids"]["unknown_category"]
    assert "rec_invalid_offset" in report["affected_record_ids"]["offset_mismatch"]

    # Label distributions over VALID records only (invalid records excluded).
    label_dist = report["label_distributions"]
    assert label_dist["aspect_category"] == {"customer_support": 1, "fees": 1}
    assert label_dist["sentiment"] == {"positive": 1, "negative": 1}
    assert label_dist["intent"] == {"complaint": 1, "compliment": 1}

    # Aspect / zero-aspect / ambiguous counts over valid records.
    assert report["aspect_count"] == 2
    assert report["zero_aspect_count"] == 1
    assert report["ambiguous_intent_count"] == 1


def test_missing_input_returns_nonzero(tmp_path):
    """A nonexistent `--input` path yields a non-zero exit code (Req 19.1)."""
    missing = tmp_path / "does_not_exist.jsonl"
    report_path = tmp_path / "report.json"

    exit_code = main(["--input", str(missing), "--output", str(report_path)])

    assert exit_code != 0


def test_unparsable_input_returns_nonzero(tmp_path):
    """A file whose lines are not valid JSON yields a non-zero exit code and
    is not required to have produced a report (Req 19.1)."""
    garbage = tmp_path / "garbage.jsonl"
    garbage.write_text("this is not json\n{also not valid\n", encoding="utf-8")
    report_path = tmp_path / "report.json"

    exit_code = main(["--input", str(garbage), "--output", str(report_path)])

    assert exit_code != 0
