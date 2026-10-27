"""Tests for candidate-package review and explicit approval (not executed in implementation session)."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from banking_tasci.data.annotation_approval import (  # noqa: E402
    APPROVAL_APPROVED,
    ApprovalError,
    create_approval_record,
    write_approval_record,
)
from banking_tasci.data.annotation_package_review import (  # noqa: E402
    AnnotationPackageReview,
    build_package_review,
    render_review_markdown,
    validate_review_for_approval,
    write_review_markdown,
    write_review_json,
)
from banking_tasci.data.gold_sample_plan import (  # noqa: E402
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    SOUTH_AFRICA_TWEET,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records() -> tuple[list[dict], list[dict]]:
    plan, annotation = [], []
    sources = [SOUTH_AFRICA_TWEET] * 25 + [INTERNATIONAL_TWEET] * 13 + [INTERNATIONAL_REVIEW] * 12
    for _ in range(9):
        sources.extend([SOUTH_AFRICA_TWEET] * 50)
        sources.extend([INTERNATIONAL_TWEET] * 25)
        sources.extend([INTERNATIONAL_REVIEW] * 25)
    sources.extend([SOUTH_AFRICA_TWEET] * 25)
    sources.extend([INTERNATIONAL_TWEET] * 12)
    sources.extend([INTERNATIONAL_REVIEW] * 13)
    for i, source in enumerate(sources):
        source_id = f"source-{i:04d}"
        region = "south_africa" if source == SOUTH_AFRICA_TWEET else "international"
        record = {
            "record_id": f"{source}::{source_id}",
            "source_record_id": source_id,
            "source": source,
            "region": region,
            "bank": None,
            "review_id": f"review::bank_reviews::{source_id}" if source == INTERNATIONAL_REVIEW else None,
            "thread_id": None,
            "conversation_id": None,
            "publish_year": None,
            "text": "Privacy-safe banking feedback.",
            "previous_text": "Genuine preceding sentence." if i % 2 == 0 else None,
            "context_available": i % 2 == 0,
            "duplicate_group": f"dup-{i}",
            "leakage_group": f"leak-{i}",
            "privacy_status": "anonymised",
            "selection_reason": f"length_band=short; v2_rule={'ABCDEF'[i % 6]}",
        }
        plan.append(record)
        annotation.append({
            **{k: v for k, v in record.items() if k != "selection_reason"},
            "primary_intent": None,
            "public_warning": None,
            "opinions": [],
            "annotation_status": "not_started",
            "annotation_version": "new_pipeline_v1",
            "annotation_notes": None,
        })
    return plan, annotation


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _package(tmp_path: Path):
    plan, annotation = _records()
    data_dir = tmp_path / "data/annotations/new_pipeline_v1"
    manifest_dir = tmp_path / "artifacts/manifests/new_pipeline_v1"
    sample = data_dir / "gold_sample_plan.jsonl"
    records = data_dir / "annotation_records.jsonl"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("".join(json.dumps(r) + "\n" for r in plan), encoding="utf-8")
    records.write_text("".join(json.dumps(r) + "\n" for r in annotation), encoding="utf-8")
    sample_manifest = manifest_dir / "gold_sample_plan_manifest.json"
    annotation_manifest = manifest_dir / "annotation_package_manifest.json"
    batch_manifest = manifest_dir / "annotation_batch_manifest.json"
    _write_json(sample_manifest, {
        "plan_output_sha256": _sha(sample),
        "candidate1_artifact_checksums": {str(sample): _sha(sample)},
    })
    _write_json(annotation_manifest, {
        "pipeline_version": "new_pipeline_v1",
        "output_checksum": _sha(records),
        "input_sample_plan_checksum": _sha(sample),
    })
    batch_ids = ["calibration_001"] + [f"main_{i:03d}" for i in range(1, 10)] + ["final_001"]
    sizes = {"calibration_001": 50, **{f"main_{i:03d}": 100 for i in range(1, 10)}, "final_001": 50}
    batch_dir = data_dir / "batches"
    batch_dir.mkdir()
    batch_ranges = {"calibration_001": (0, 50), **{f"main_{i:03d}": (50 + (i - 1) * 100, 50 + i * 100) for i in range(1, 10)}, "final_001": (950, 1000)}
    output_paths, checksums = {}, {}
    for name, (start, end) in batch_ranges.items():
        batch_file = batch_dir / f"{name}.jsonl"
        batch_file.write_text("".join(json.dumps(r) + "\n" for r in annotation[start:end]), encoding="utf-8")
        output_paths[name] = str(batch_file)
        checksums[name] = _sha(batch_file)
    batch_manifest_data = {
        "pipeline_version": "new_pipeline_v1",
        "batch_ids": batch_ids,
        "batch_sizes": sizes,
        "batch_types": {name: ("calibration" if name.startswith("calibration") else "final" if name.startswith("final") else "main") for name in batch_ids},
        "total_batches": 11,
        "total_records": 1000,
        "unresolved_balancing_warnings": [],
        "output_paths": output_paths,
        "checksums": checksums,
    }
    _write_json(batch_manifest, batch_manifest_data)
    review_path = tmp_path / "review.json"
    review = AnnotationPackageReview(
        sample_plan_path=str(sample),
        sample_plan_checksum=_sha(sample),
        annotation_manifest_path=str(annotation_manifest),
        annotation_manifest_checksum=_sha(annotation_manifest),
        batch_manifest_path=str(batch_manifest),
        batch_manifest_checksum=_sha(batch_manifest),
        total_records=1000,
        unique_record_ids=1000,
        source_distribution=dict(Counter(sources for sources in [r["source"] for r in annotation])),
        region_distribution=dict(Counter(r["region"] for r in annotation)),
        duplicate_group_integrity={"coverage": "present", "verified": True},
        leakage_group_integrity={"coverage": "present", "verified": True},
        recommendation="READY_FOR_RESEARCHER_APPROVAL",
        review_issues=[],
    )
    write_review_json(review, review_path)
    return sample, records, sample_manifest, annotation_manifest, batch_manifest, review_path


def test_review_model_rejects_approval_or_freeze_recommendations():
    with pytest.raises(ValueError):
        AnnotationPackageReview(recommendation="APPROVED")
    with pytest.raises(ValueError):
        AnnotationPackageReview(recommendation="FROZEN")


def test_review_build_accepts_complete_static_evidence(tmp_path):
    sample, records, sample_manifest, annotation_manifest, batch_manifest, _ = _package(tmp_path)
    batch_dir = tmp_path / "data/annotations/new_pipeline_v1/batches"
    review = build_package_review(
        sample_plan_path=sample,
        annotation_records_path=records,
        sample_plan_manifest_path=sample_manifest,
        annotation_manifest_path=annotation_manifest,
        batch_manifest_path=batch_manifest,
        batch_directory=batch_dir,
    )
    assert review.review_issues == []
    assert review.recommendation == "READY_FOR_RESEARCHER_APPROVAL"


def test_candidate2_review_records_candidate1_checksum_and_context_limit(tmp_path):
    sample, records, sample_manifest, annotation_manifest, batch_manifest, _ = _package(tmp_path)
    review = build_package_review(
        sample_plan_path=sample,
        annotation_records_path=records,
        sample_plan_manifest_path=sample_manifest,
        annotation_manifest_path=annotation_manifest,
        batch_manifest_path=batch_manifest,
        batch_directory=tmp_path / "data/annotations/new_pipeline_v1/batches",
        candidate_number=2,
        candidate1_path=sample,
        expected_candidate1_checksum=_sha(sample),
    )
    assert review.candidate_number == 2
    assert review.candidate1_preserved is True
    assert review.candidate1_checksum == _sha(sample)
    rendered = render_review_markdown(review)
    assert "READY recommendation is not approval" in rendered


def test_candidate1_checksum_mismatch_is_reported(tmp_path):
    sample, records, sample_manifest, annotation_manifest, batch_manifest, _ = _package(tmp_path)
    review = build_package_review(
        sample_plan_path=sample,
        annotation_records_path=records,
        sample_plan_manifest_path=sample_manifest,
        annotation_manifest_path=annotation_manifest,
        batch_manifest_path=batch_manifest,
        batch_directory=tmp_path / "data/annotations/new_pipeline_v1/batches",
        candidate_number=2,
        candidate1_path=sample,
        expected_candidate1_checksum="not-the-current-checksum",
    )
    assert review.candidate1_preserved is False
    assert any("candidate-1 checksum" in issue for issue in review.review_issues)


def test_review_markdown_writer_is_atomic_and_refuses_overwrite(tmp_path):
    review = AnnotationPackageReview(candidate_number=2)
    target = tmp_path / "candidate_2_review.md"
    written = write_review_markdown(review, target)
    assert written == target
    assert "Candidate 2 annotation-package review" in target.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_review_markdown(review, target)


def test_approval_requires_machine_readable_ready_review(tmp_path):
    sample, records, _sample_manifest, annotation_manifest, batch_manifest, review_path = _package(tmp_path)
    review = json.loads(review_path.read_text())
    review["recommendation"] = "NOT_READY_FOR_RESEARCHER_APPROVAL"
    review_path.write_text(json.dumps(review))
    with pytest.raises(ApprovalError):
        create_approval_record(
            reviewer="Researcher",
            review_report_path=review_path,
            sample_plan_path=sample,
            annotation_records_path=records,
            annotation_manifest_path=annotation_manifest,
            batch_manifest_path=batch_manifest,
            expected_sample_checksum=_sha(sample),
            expected_batch_manifest_checksum=_sha(batch_manifest),
            command="approve",
        )


def test_approval_requires_explicit_matching_checksums(tmp_path):
    sample, records, _sample_manifest, annotation_manifest, batch_manifest, review_path = _package(tmp_path)
    with pytest.raises(ApprovalError):
        create_approval_record(
            reviewer="Researcher",
            review_report_path=review_path,
            sample_plan_path=sample,
            annotation_records_path=records,
            annotation_manifest_path=annotation_manifest,
            batch_manifest_path=batch_manifest,
            expected_sample_checksum="wrong",
            expected_batch_manifest_checksum=_sha(batch_manifest),
            command="approve",
        )


def test_explicit_approval_creates_separate_approved_record(tmp_path):
    sample, records, _sample_manifest, annotation_manifest, batch_manifest, review_path = _package(tmp_path)
    before = _sha(records)
    approval = create_approval_record(
        reviewer="Researcher",
        review_report_path=review_path,
        sample_plan_path=sample,
        annotation_records_path=records,
        annotation_manifest_path=annotation_manifest,
        batch_manifest_path=batch_manifest,
        expected_sample_checksum=_sha(sample),
        expected_batch_manifest_checksum=_sha(batch_manifest),
        command="approve --approve",
        approve=True,
    )
    assert approval.approval_status == APPROVAL_APPROVED
    target = tmp_path / "approval.json"
    write_approval_record(approval, target)
    assert json.loads(target.read_text())["approval_status"] == APPROVAL_APPROVED
    assert _sha(records) == before


def test_candidate2_approval_captures_candidate_checksums_and_context_limit(tmp_path):
    sample, records, _sample_manifest, annotation_manifest, batch_manifest, review_path = _package(tmp_path)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["candidate_number"] = 2
    review["context_experiment_status"] = (
        "BLOCKED_NO_VERIFIED_CONTEXT_DATA; package remains eligible for no-context annotation"
    )
    review_path.write_text(json.dumps(review), encoding="utf-8")

    approval = create_approval_record(
        reviewer="Rotondwa Mavhengani",
        review_report_path=review_path,
        sample_plan_path=sample,
        annotation_records_path=records,
        annotation_manifest_path=annotation_manifest,
        batch_manifest_path=batch_manifest,
        expected_sample_checksum=_sha(sample),
        expected_batch_manifest_checksum=_sha(batch_manifest),
        command="python3 scripts/approve_annotation_package.py --approve",
        approve=True,
    )

    assert approval.candidate_number == 2
    assert approval.annotation_records_checksum == _sha(records)
    assert approval.context_limitation == review["context_experiment_status"]
    assert any("Accepted context limitation" in note for note in approval.notes)
    assert approval.command.startswith("python3 scripts/approve_annotation_package.py")


def test_approval_write_refuses_overwrite(tmp_path):
    from banking_tasci.data.annotation_approval import AnnotationPackageApproval

    approval = AnnotationPackageApproval(
        approval_id="id", pipeline_version="new_pipeline_v1", reviewer="R",
        approved_at="2026-10-12T00:00:00Z", sample_plan_checksum="a",
        annotation_manifest_checksum="b", batch_manifest_checksum="c",
        review_report_checksum="d", reviewed_record_count=1000,
        recommendation="READY_FOR_RESEARCHER_APPROVAL", approval_status=APPROVAL_APPROVED,
        git_commit="UNKNOWN_NO_COMMIT", command="approve", notes=[],
    )
    target = tmp_path / "approval.json"
    write_approval_record(approval, target)
    with pytest.raises(FileExistsError):
        write_approval_record(approval, target)
