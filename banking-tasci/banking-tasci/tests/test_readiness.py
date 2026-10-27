"""Tests for the Readiness_Gate (src/banking_tasci/training/readiness.py).

Covers:
- Property 1 (Feature: banking-tasci-phase-3a): over synthetic combinations
  of (adjudicated-file-present, each-manifest-present, has-a-completed-
  labelled-record), `check_readiness(...).ready` is True IFF (adjudicated
  file exists AND all three manifests exist AND >=1 completed record with a
  non-empty intent); and whenever not ready, `assert_ready(...)` raises a
  `RuntimeError` whose `str()` equals `BLOCKED_MESSAGE` exactly
  (Req 30.1, 30.2, 30.4).
- An example test mirroring the CURRENT repo state (no adjudicated file, no
  manifests) asserting not-ready and the exact blocked message (Req 30.5).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pytest  # noqa: E402

from banking_tasci.data.annotations import AnnotationRecord, write_jsonl  # noqa: E402
from banking_tasci.training.readiness import (  # noqa: E402
    BLOCKED_MESSAGE,
    ReadinessResult,
    assert_ready,
    check_readiness,
)

_MANIFESTS = ("train_manifest.csv", "validation_manifest.csv", "test_manifest.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed_record(intent: str = "complaint") -> AnnotationRecord:
    """A record that satisfies the completed+labelled condition."""
    return AnnotationRecord(
        record_id="rec_completed",
        source="bank_reviews",
        region="local",
        text="The fees are too high.",
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=[],
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="annotator_a",
        annotation_status="completed",
        notes="",
    )


def _unlabelled_record() -> AnnotationRecord:
    """A record that does NOT satisfy the completed+labelled condition
    (mirrors the current unannotated pilot: not_started, null intent)."""
    return AnnotationRecord(
        record_id="rec_not_started",
        source="bank_reviews",
        region="local",
        text="The fees are too high.",
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=[],
        intent=None,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="",
        annotation_status="not_started",
        notes="",
    )


def _build_state(
    base: Path,
    *,
    gold_present: bool,
    manifests_present: tuple[bool, bool, bool],
    has_completed: bool,
) -> tuple[Path, Path]:
    """Construct a synthetic readiness state under `base`.

    Returns (annotations_path, split_dir). Only the requested files are
    created; the adjudicated gold file, when present, contains a completed
    labelled record iff `has_completed` (plus always an unlabelled record so
    that "present but not labelled" is genuinely exercised).
    """
    ann_dir = base / "annotations"
    split_dir = base / "processed"
    ann_dir.mkdir(parents=True, exist_ok=True)
    split_dir.mkdir(parents=True, exist_ok=True)

    annotations_path = ann_dir / "pilot_adjudicated.jsonl"
    if gold_present:
        records = [_unlabelled_record()]
        if has_completed:
            records.append(_completed_record())
        write_jsonl(records, annotations_path)

    for present, name in zip(manifests_present, _MANIFESTS):
        if present:
            (split_dir / name).write_text("record_id\n", encoding="utf-8")

    return annotations_path, split_dir


# ---------------------------------------------------------------------------
# Property 1: Not-ready always yields the exact blocked message
# ---------------------------------------------------------------------------
# Feature: banking-tasci-phase-3a, Property 1: Not-ready always yields the
# exact blocked message
#
# Validates: Requirements 30.1, 30.2, 30.4
@settings(max_examples=150)
@given(
    gold_present=st.booleans(),
    manifests_present=st.tuples(st.booleans(), st.booleans(), st.booleans()),
    has_completed=st.booleans(),
)
def test_property_not_ready_yields_exact_blocked_message(
    gold_present: bool,
    manifests_present: tuple[bool, bool, bool],
    has_completed: bool,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        annotations_path, split_dir = _build_state(
            base,
            gold_present=gold_present,
            manifests_present=manifests_present,
            has_completed=has_completed,
        )

        expected_ready = gold_present and all(manifests_present) and has_completed

        result = check_readiness(annotations_path, split_dir)
        assert isinstance(result, ReadinessResult)
        assert result.ready is expected_ready

        if expected_ready:
            assert result.reasons == []
            # assert_ready must not raise when ready.
            assert assert_ready(annotations_path, split_dir) is None
        else:
            assert result.reasons  # at least one human-readable reason
            with pytest.raises(RuntimeError) as exc_info:
                assert_ready(annotations_path, split_dir)
            assert str(exc_info.value) == BLOCKED_MESSAGE


# ---------------------------------------------------------------------------
# Example: current repository state (no adjudicated file, no manifests)
# ---------------------------------------------------------------------------
# Supports Req 30.5.
def test_current_repo_state_is_not_ready_with_exact_message() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Mirror the current repo: no adjudicated file, an empty split dir,
        # no manifests.
        annotations_path = base / "annotations" / "pilot_adjudicated.jsonl"
        split_dir = base / "processed"
        split_dir.mkdir(parents=True, exist_ok=True)

        result = check_readiness(annotations_path, split_dir)
        assert result.ready is False
        assert result.reasons

        with pytest.raises(RuntimeError) as exc_info:
            assert_ready(annotations_path, split_dir)
        assert str(exc_info.value) == BLOCKED_MESSAGE


def test_ready_when_gold_and_all_manifests_and_completed_record_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        annotations_path, split_dir = _build_state(
            base,
            gold_present=True,
            manifests_present=(True, True, True),
            has_completed=True,
        )
        result = check_readiness(annotations_path, split_dir)
        assert result.ready is True
        assert result.reasons == []
        assert assert_ready(annotations_path, split_dir) is None


def test_gold_present_but_no_labelled_record_is_not_ready() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        annotations_path, split_dir = _build_state(
            base,
            gold_present=True,
            manifests_present=(True, True, True),
            has_completed=False,
        )
        result = check_readiness(annotations_path, split_dir)
        assert result.ready is False
        with pytest.raises(RuntimeError) as exc_info:
            assert_ready(annotations_path, split_dir)
        assert str(exc_info.value) == BLOCKED_MESSAGE
