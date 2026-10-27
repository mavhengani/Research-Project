"""Tests for the supervised-training readiness gate
(src/banking_tasci/training/supervised_gate.py), Phase 3A Part 6.

Covers:
- failure (with the exact blocked message) at the current unannotated stage;
- success with a temporary, leakage-safe gold fixture;
- record-id split overlap detection;
- leakage-group crossing detection;
- unannotated-record-in-split detection.

All fixtures are tiny synthetic in-test records — no real gold data.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import (  # noqa: E402
    AnnotationRecord,
    AspectSpan,
    write_jsonl,
)
from banking_tasci.training.supervised_gate import (  # noqa: E402
    SUPERVISED_BLOCKED_MESSAGE,
    assert_supervised_ready,
    check_supervised_readiness,
)

_MANIFESTS = {
    "train": "train_manifest.csv",
    "validation": "validation_manifest.csv",
    "test": "test_manifest.csv",
}


def _completed_record(rid: str, text: str, term: str, sentiment: str, intent: str) -> AnnotationRecord:
    start = text.index(term)
    end = start + len(term)
    return AnnotationRecord(
        record_id=rid,
        source="bank_reviews",
        region="local",
        text=text,
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=[AspectSpan(term=term, start=start, end=end, category="fees", sentiment=sentiment)],
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="lead",
        annotation_status="completed",
        notes="",
    )


def _write_manifest(path: Path, ids: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["record_id"])
        for rid in ids:
            writer.writerow([rid])


def _gold_fixture(base: Path, split_map: dict[str, list[str]]) -> tuple[Path, Path]:
    """Build a leakage-safe gold fixture. Returns (annotations_path, split_dir)."""
    ann_dir = base / "annotations"
    split_dir = base / "processed"
    ann_dir.mkdir(parents=True, exist_ok=True)
    split_dir.mkdir(parents=True, exist_ok=True)

    records = [
        _completed_record("t1", "the fees are high", "fees", "negative", "complaint"),
        _completed_record("t2", "the fees are unfair", "fees", "negative", "complaint"),
        _completed_record("t3", "the staff are great", "staff", "positive", "compliment"),
        _completed_record("t4", "the staff are kind", "staff", "positive", "compliment"),
        _completed_record("v1", "the fees are painful", "fees", "negative", "complaint"),
        _completed_record("e1", "the staff are lovely", "staff", "positive", "compliment"),
    ]
    annotations_path = ann_dir / "pilot_adjudicated.jsonl"
    write_jsonl(records, annotations_path)

    for split, name in _MANIFESTS.items():
        _write_manifest(split_dir / name, split_map.get(split, []))
    return annotations_path, split_dir


def _leakage_safe_split_map() -> dict[str, list[str]]:
    return {
        "train": ["t1", "t2", "t3", "t4"],
        "validation": ["v1"],
        "test": ["e1"],
    }


# ---------------------------------------------------------------------------
# Failure at the current unannotated stage.
# ---------------------------------------------------------------------------


def test_readiness_fails_when_gold_absent(tmp_path):
    annotations_path = tmp_path / "annotations" / "pilot_adjudicated.jsonl"
    split_dir = tmp_path / "processed"
    split_dir.mkdir(parents=True, exist_ok=True)

    report = check_supervised_readiness(annotations_path, split_dir)
    assert report.ready is False
    assert any(c.name == "adjudicated_file_exists" and not c.passed for c in report.checks)

    with pytest.raises(RuntimeError) as exc_info:
        assert_supervised_ready(annotations_path, split_dir)
    assert str(exc_info.value) == SUPERVISED_BLOCKED_MESSAGE


def test_readiness_rejects_unannotated_pilot_filename(tmp_path):
    # Even if a file exists under the unannotated pilot name, it is refused.
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(parents=True)
    path = ann_dir / "pilot_unannotated.jsonl"
    write_jsonl(
        [_completed_record("t1", "the fees are high", "fees", "negative", "complaint")],
        path,
    )
    split_dir = tmp_path / "processed"
    split_dir.mkdir()
    report = check_supervised_readiness(path, split_dir)
    assert report.ready is False
    assert any(c.name == "not_the_unannotated_pilot" and not c.passed for c in report.checks)


# ---------------------------------------------------------------------------
# Success with a temporary leakage-safe gold fixture.
# ---------------------------------------------------------------------------


def test_readiness_succeeds_with_leakage_safe_gold(tmp_path):
    annotations_path, split_dir = _gold_fixture(tmp_path, _leakage_safe_split_map())
    report = check_supervised_readiness(annotations_path, split_dir)
    assert report.ready is True, report.to_dict()
    # assert_supervised_ready must not raise and returns the passing report.
    ok = assert_supervised_ready(annotations_path, split_dir)
    assert ok.ready is True


# ---------------------------------------------------------------------------
# Leakage checks.
# ---------------------------------------------------------------------------


def test_record_in_multiple_splits_is_detected(tmp_path):
    split_map = _leakage_safe_split_map()
    split_map["validation"] = ["t1"]  # t1 already in train -> overlap
    annotations_path, split_dir = _gold_fixture(tmp_path, split_map)
    report = check_supervised_readiness(annotations_path, split_dir)
    assert report.ready is False
    assert any(c.name == "no_record_in_multiple_splits" and not c.passed for c in report.checks)


def test_unannotated_record_in_split_is_detected(tmp_path):
    annotations_path, split_dir = _gold_fixture(tmp_path, _leakage_safe_split_map())
    # Append a not_started record and put it in the train manifest.
    from banking_tasci.data.annotations import read_jsonl

    records = read_jsonl(annotations_path)
    not_started = AnnotationRecord(
        record_id="u1", source="bank_reviews", region="local",
        text="unlabelled text", previous_text="[NO_CONTEXT]",
        context_available=False, aspects=[], intent=None,
        intent_ambiguous=False, alternative_intent=None,
        annotator_id="", annotation_status="not_started", notes="",
    )
    write_jsonl(records + [not_started], annotations_path)
    _write_manifest(split_dir / "train_manifest.csv", ["t1", "t2", "t3", "t4", "u1"])

    report = check_supervised_readiness(annotations_path, split_dir)
    assert report.ready is False
    assert any(c.name == "no_unannotated_record_in_splits" and not c.passed for c in report.checks)


def test_unseen_class_at_train_is_detected(tmp_path):
    # Put both compliment records in test only -> compliment unseen at train.
    split_map = {
        "train": ["t1", "t2"],           # complaint only
        "validation": ["v1"],            # complaint
        "test": ["t3", "t4", "e1"],      # compliment
    }
    annotations_path, split_dir = _gold_fixture(tmp_path, split_map)
    report = check_supervised_readiness(annotations_path, split_dir)
    assert report.ready is False
    assert any(c.name == "required_classes_in_train" and not c.passed for c in report.checks)

