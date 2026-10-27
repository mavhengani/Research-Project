"""Tests for explicit package approval and immutable gold-identity freeze (NOT_RUN)."""
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

from banking_tasci.data.annotation_approval import AnnotationPackageApproval, write_approval_record  # noqa: E402
from banking_tasci.data.annotation_batches import BATCH_SPECS  # noqa: E402
from banking_tasci.data.gold_sample_freeze import (  # noqa: E402
    FREEZE_CHECKSUM_FILENAME,
    FREEZE_ID_FILENAME,
    FREEZE_RECEIPT_FILENAME,
    FREEZE_RECORDS_FILENAME,
    FreezeError,
    prepare_freeze_artifacts,
    resolve_candidate_paths,
    write_freeze_artifacts,
)
from banking_tasci.data.gold_sample_plan import (  # noqa: E402
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    SOUTH_AFRICA_TWEET,
)
from banking_tasci.data.unlabelled_corpus import load_gold_ids  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    root = tmp_path
    annotations = root / "data/annotations/new_pipeline_v1"
    manifests = root / "artifacts/manifests/new_pipeline_v1"
    approvals = root / "artifacts/approvals/new_pipeline_v1"
    annotations.mkdir(parents=True)
    manifests.mkdir(parents=True)
    approvals.mkdir(parents=True)
    sources = [SOUTH_AFRICA_TWEET] * 500 + [INTERNATIONAL_TWEET] * 250 + [INTERNATIONAL_REVIEW] * 250
    plans, records = [], []
    for i, source in enumerate(sources):
        sid = f"sid-{i:04d}"
        region = "south_africa" if source == SOUTH_AFRICA_TWEET else "international"
        base = {
            "record_id": f"{source}::{sid}", "source_record_id": sid,
            "source": source, "region": region, "bank": None,
            "review_id": None, "thread_id": None, "conversation_id": None,
            "publish_year": None, "text": "Privacy-safe feedback.",
            "previous_text": None, "context_available": False,
            "duplicate_group": f"duplicate-{i}", "leakage_group": f"leak-{i}",
            "privacy_status": "anonymised",
        }
        plans.append({**base, "selection_reason": "length_band=short; v2_rule=A"})
        records.append({**base, "primary_intent": None, "public_warning": None,
                        "opinions": [], "annotation_status": "not_started",
                        "annotation_version": "new_pipeline_v1", "annotation_notes": None})
    sample = annotations / "gold_sample_plan.jsonl"
    annotation = annotations / "annotation_records.jsonl"
    sample.write_text("".join(json.dumps(r) + "\n" for r in plans), encoding="utf-8")
    annotation.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    sample_manifest = manifests / "gold_sample_plan_manifest.json"
    sample_manifest.write_text(json.dumps({
        "plan_output_sha256": _sha(sample),
        "south_africa_source_sha256": "sa-source-checksum",
        "international_source_sha256": "intl-source-checksum",
    }), encoding="utf-8")
    annotation_manifest = manifests / "annotation_package_manifest.json"
    annotation_manifest.write_text(json.dumps({
        "pipeline_version": "new_pipeline_v1",
        "output_checksum": _sha(annotation),
        "input_sample_plan_checksum": _sha(sample),
        "output_record_count": 1000,
        "label_hidden": True,
    }), encoding="utf-8")
    batch_manifest = manifests / "annotation_batch_manifest.json"
    batch_dir = annotations / "batches"
    batch_dir.mkdir()
    ids, sizes, types, output_paths, checksums = [], {}, {}, {}, {}
    offset = 0
    for name, batch_type, size in BATCH_SPECS:
        batch_file = batch_dir / f"{name}.jsonl"
        batch_file.write_text("".join(json.dumps(r) + "\n" for r in records[offset:offset + size]), encoding="utf-8")
        offset += size
        ids.append(name)
        sizes[name] = size
        types[name] = batch_type
        output_paths[name] = str(batch_file)
        checksums[name] = _sha(batch_file)
    batch_manifest.write_text(json.dumps({
        "batch_ids": ids, "batch_sizes": sizes, "batch_types": types,
        "total_batches": 11, "total_records": 1000,
        "output_paths": output_paths, "checksums": checksums,
    }), encoding="utf-8")
    approval = AnnotationPackageApproval(
        approval_id="approval-1", pipeline_version="new_pipeline_v1", reviewer="Reviewer",
        approved_at="2026-10-12T00:00:00Z", sample_plan_checksum=_sha(sample),
        annotation_manifest_checksum=_sha(annotation_manifest),
        batch_manifest_checksum=_sha(batch_manifest), review_report_checksum="review-hash",
        reviewed_record_count=1000, recommendation="READY_FOR_RESEARCHER_APPROVAL",
        approval_status="APPROVED", git_commit="UNKNOWN_NO_COMMIT", command="approve", notes=[],
        annotation_records_checksum=_sha(annotation),
    )
    approval_path = approvals / "annotation_package_approval.json"
    write_approval_record(approval, approval_path)
    return sample, annotation, annotation_manifest, batch_manifest, approval_path, sample_manifest


def test_freeze_payload_contains_only_identity_and_provenance(tmp_path):
    sample, records, annotation_manifest, batch_manifest, approval, _ = _fixture(tmp_path)
    payload = prepare_freeze_artifacts(
        sample_plan_path=sample, annotation_records_path=records,
        annotation_manifest_path=annotation_manifest, batch_manifest_path=batch_manifest,
        approval_path=approval, authority="Researcher", command="freeze",
    )
    ids = payload["identity_records"]
    assert len(ids) == 1000
    assert len({r["record_id"] for r in ids}) == 1000
    assert set(ids[0]) == {"record_id", "source_record_id", "source", "region", "source_checksum"}
    assert all("primary_intent" not in r and "opinions" not in r for r in ids)
    assert payload["manifest"]["immutable_status"] == "PENDING_FREEZE"
    assert payload["manifest"]["git_commit"] == "UNKNOWN_NO_COMMIT"


def test_freeze_requires_explicit_acknowledgement(tmp_path):
    sample, records, annotation_manifest, batch_manifest, approval, _ = _fixture(tmp_path)
    payload = prepare_freeze_artifacts(
        sample_plan_path=sample, annotation_records_path=records,
        annotation_manifest_path=annotation_manifest, batch_manifest_path=batch_manifest,
        approval_path=approval, authority="Researcher", command="freeze",
    )
    with pytest.raises(FreezeError):
        write_freeze_artifacts(payload, tmp_path / "frozen", acknowledge_immutable_ids=False)


def test_freeze_refuses_existing_output_directory(tmp_path):
    sample, records, annotation_manifest, batch_manifest, approval, _ = _fixture(tmp_path)
    payload = prepare_freeze_artifacts(
        sample_plan_path=sample, annotation_records_path=records,
        annotation_manifest_path=annotation_manifest, batch_manifest_path=batch_manifest,
        approval_path=approval, authority="Researcher", command="freeze",
    )
    target = tmp_path / "frozen"
    target.mkdir()
    with pytest.raises(FileExistsError):
        write_freeze_artifacts(payload, target, acknowledge_immutable_ids=True)


def test_freeze_writes_four_identity_artifacts_only_to_new_directory(tmp_path):
    sample, records, annotation_manifest, batch_manifest, approval, _ = _fixture(tmp_path)
    payload = prepare_freeze_artifacts(
        sample_plan_path=sample, annotation_records_path=records,
        annotation_manifest_path=annotation_manifest, batch_manifest_path=batch_manifest,
        approval_path=approval, authority="Researcher", command="freeze",
    )
    target = write_freeze_artifacts(
        payload, tmp_path / "frozen", acknowledge_immutable_ids=True
    )
    manifest = json.loads((target / FREEZE_ID_FILENAME).read_text())
    assert manifest["immutable_status"] == "FROZEN"
    assert {p.name for p in target.iterdir()} == {
        FREEZE_ID_FILENAME, FREEZE_RECORDS_FILENAME,
        FREEZE_CHECKSUM_FILENAME, FREEZE_RECEIPT_FILENAME,
    }
    frozen_records = [json.loads(line) for line in (target / FREEZE_RECORDS_FILENAME).read_text().splitlines()]
    assert len(frozen_records) == 1000
    assert Counter(r["source"] for r in frozen_records) == Counter({
        SOUTH_AFRICA_TWEET: 500, INTERNATIONAL_TWEET: 250, INTERNATIONAL_REVIEW: 250
    })
    assert _sha(target / FREEZE_RECORDS_FILENAME) == payload["identity_checksum"]
    assert records.is_file()
    frozen_ids = load_gold_ids(target / FREEZE_ID_FILENAME)
    assert frozen_ids.total == 1000
    assert len(frozen_ids.south_africa) == 500
    assert len(frozen_ids.international_tweets) == 250
    assert len(frozen_ids.international_reviews) == 250
    assert frozen_ids.validate() == []


def test_freeze_rejects_mismatched_approval_checksum(tmp_path):
    sample, records, annotation_manifest, batch_manifest, approval_path, _ = _fixture(tmp_path)
    approval = json.loads(approval_path.read_text())
    approval["sample_plan_checksum"] = "different"
    approval_path.write_text(json.dumps(approval))
    with pytest.raises(FreezeError):
        prepare_freeze_artifacts(
            sample_plan_path=sample, annotation_records_path=records,
            annotation_manifest_path=annotation_manifest, batch_manifest_path=batch_manifest,
            approval_path=approval_path, authority="Researcher", command="freeze",
        )


def test_candidate_two_paths_are_explicit_and_candidate_specific(tmp_path):
    paths = resolve_candidate_paths(tmp_path, 2)
    assert "new_pipeline_v1_candidate_2" in str(paths["sample_plan"])
    assert "candidate_2" in str(paths["approval"])
    assert paths["candidate_manifest"].name == "candidate_2_manifest.json"
    with pytest.raises(FreezeError, match="unsupported candidate"):
        resolve_candidate_paths(tmp_path, 3)


def test_freeze_rejects_candidate_one_approval_for_candidate_two(tmp_path):
    sample, records, annotation_manifest, batch_manifest, approval, plan_manifest = _fixture(tmp_path)
    review = tmp_path / "review.json"
    review.write_text("{}", encoding="utf-8")
    with pytest.raises(FreezeError, match="candidate number"):
        prepare_freeze_artifacts(
            sample_plan_path=sample, annotation_records_path=records,
            annotation_manifest_path=annotation_manifest, batch_manifest_path=batch_manifest,
            approval_path=approval, authority="Researcher", command="freeze",
            candidate_number=2, candidate_manifest_path=plan_manifest, review_report_path=review,
        )
