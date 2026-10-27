"""Tests for calibration approval gates and safe annotation resumption (NOT_RUN)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from banking_tasci.data.annotation_batches import (  # noqa: E402
    BatchMetadata,
    annotation_records_checksum,
    assert_main_annotation_allowed,
    freeze_calibration_guide,
    next_incomplete_record,
    save_annotation_checkpoint,
    transition_batch_status,
    validate_submission,
)


def _record(index: int, *, status: str = "not_started") -> dict:
    return {
        "record_id": f"south_africa_tweet::r{index:04d}",
        "source_record_id": f"r{index:04d}",
        "source": "south_africa_tweet",
        "region": "south_africa",
        "text": "Privacy-safe text",
        "previous_text": None,
        "context_available": False,
        "privacy_status": "anonymised",
        "primary_intent": None,
        "public_warning": None,
        "opinions": [],
        "annotation_status": status,
        "annotation_version": "new_pipeline_v1",
    }


def _metadata(batch_id: str, batch_type: str, records: list[dict], **kwargs) -> BatchMetadata:
    return BatchMetadata(
        batch_id=batch_id,
        batch_type=batch_type,
        record_count=len(records),
        record_ids=[r["record_id"] for r in records],
        checksum=annotation_records_checksum(records),
        checksum_algorithm="jsonl_sha256",
        **kwargs,
    )


def test_any_batch_cannot_start_without_approval():
    records = [_record(i) for i in range(100)]
    main = _metadata("main_001", "main", records)
    with pytest.raises(ValueError, match="APPROVED"):
        transition_batch_status(main, "in_progress")


def test_any_batch_starts_after_candidate_approval_without_first_batch_gate():
    batch = _metadata("main_001", "main", [_record(i) for i in range(100)])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    started = transition_batch_status(batch, "in_progress", approval=approval)
    assert started.batch_status == "in_progress"


def test_guide_version_does_not_change_batch_status_or_require_first_batch_completion():
    records = [_record(i) for i in range(50)]
    metadata = _metadata("main_001", "main", [_record(i) for i in range(100)])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    with pytest.warns(DeprecationWarning):
        updated = freeze_calibration_guide(metadata, guide_version="guide-v1", approval=approval)
    assert updated.batch_status == "generated"
    assert updated.annotation_guide_version == "guide-v1"


def test_each_batch_can_start_independently_after_approval():
    calibration_records = [_record(i, status="completed") for i in range(50)]
    calibration = _metadata(
        "calibration_001", "calibration", calibration_records,
        batch_status="validated", completed_record_count=50,
    )
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    with pytest.warns(DeprecationWarning):
        freeze_calibration_guide(calibration, guide_version="guide-v1", approval=approval)
    main = _metadata("main_001", "main", [_record(i + 100) for i in range(100)])
    started = transition_batch_status(main, "in_progress", approval=approval)
    assert started.batch_status == "in_progress"
    assert started.annotation_guide_version is None


def test_submission_requires_all_records_in_same_batch_and_pipeline():
    records = [_record(i) for i in range(3)]
    metadata = _metadata("calibration_001", "calibration", records)
    assert validate_submission(metadata, records) == []
    foreign = [_record(100), records[1], records[2]]
    assert validate_submission(metadata, foreign)
    wrong_version = [dict(r) for r in records]
    wrong_version[0]["annotation_version"] = "other"
    assert any("annotation_version" in e for e in validate_submission(metadata, wrong_version))


def test_submission_detects_batch_checksum_mismatch():
    records = [_record(1)]
    metadata = _metadata("calibration_001", "calibration", records)
    changed = [dict(records[0], text="changed")]
    assert any("checksum" in issue for issue in validate_submission(metadata, changed))


def test_next_incomplete_record_is_deterministic():
    records = [_record(2), _record(1, status="completed")]
    assert next_incomplete_record(records)["record_id"].endswith("::r0002")


def test_checkpoint_write_requires_checksum_to_replace_and_can_backup(tmp_path):
    records = [_record(i) for i in range(2)]
    metadata = _metadata("calibration_001", "calibration", records)
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    path = tmp_path / "checkpoint.jsonl"
    first_checksum = save_annotation_checkpoint(metadata, records, path)
    with pytest.raises(FileExistsError):
        save_annotation_checkpoint(metadata, records, path)
    backup = tmp_path / "checkpoint.backup.jsonl"
    second_checksum = save_annotation_checkpoint(
        metadata,
        records,
        path,
        expected_existing_checksum=first_checksum,
        backup_path=backup,
    )
    assert first_checksum == second_checksum
    assert backup.is_file()


def test_checkpoint_refuses_changed_current_checksum(tmp_path):
    records = [_record(i) for i in range(2)]
    metadata = _metadata("calibration_001", "calibration", records)
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    path = tmp_path / "checkpoint.jsonl"
    save_annotation_checkpoint(metadata, records, path)
    with pytest.raises(ValueError, match="checksum changed"):
        save_annotation_checkpoint(
            metadata, records, path, expected_existing_checksum="stale"
        )
