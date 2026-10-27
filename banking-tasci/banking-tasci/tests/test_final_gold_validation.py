from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from banking_tasci.data.annotation_batches import BATCH_SPECS, annotation_batch_display_name  # noqa: E402
from banking_tasci.data.final_gold_validation import (  # noqa: E402
    FinalGoldValidationError,
    validate_final_gold,
    validate_final_gold_files,
)
from banking_tasci.data.manifest import sha256_file  # noqa: E402

SOURCES = ("south_africa_tweet", "international_tweet", "international_review")


def _jsonl_bytes(rows):
    return "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode()


def _rows():
    result = []
    totals = {"south_africa_tweet": 500, "international_tweet": 250, "international_review": 250}
    for source in SOURCES:
        for index in range(totals[source]):
            rid = f"{source}::r{index:04d}"
            result.append({
                "record_id": rid, "source_record_id": f"r{index:04d}", "source": source,
                "region": "south_africa" if source == "south_africa_tweet" else "international",
                "bank": "FNB" if source == "south_africa_tweet" else None,
                "review_id": f"review-{index}" if source == "international_review" else None,
                "thread_id": None, "conversation_id": None, "publish_year": 2020,
                "text": "Privacy-safe synthetic record.", "previous_text": "[NO_CONTEXT]",
                "context_available": False, "duplicate_group": None,
                "leakage_group": f"{source}-group-{index}", "privacy_status": "anonymised",
                "primary_intent": "complaint", "public_warning": False, "opinions": [],
                "annotation_status": "completed", "annotation_version": "new_pipeline_v1",
                "annotation_notes": None,
            })
    return result


def _fixture(tmp_path: Path):
    records = _rows()
    approved = []
    for row in records:
        hidden = dict(row)
        hidden.update(primary_intent=None, public_warning=None, opinions=[], annotation_status="not_started")
        approved.append(hidden)
    batch_rows = {name: [] for name, _kind, _size in BATCH_SPECS}
    ordered = sorted(records, key=lambda row: row["record_id"])
    offset = 0
    membership = []
    for name, _kind, size in BATCH_SPECS:
        batch_rows[name] = ordered[offset:offset + size]
        offset += size
        membership.extend({"record_id": row["record_id"], "batch_id": name} for row in batch_rows[name])
    return records, approved, batch_rows, membership


def test_final_gold_passes_all_uniform_batch_and_freeze_checks(tmp_path):
    records, approved, batch_rows, membership = _fixture(tmp_path)
    frozen = [{"record_id": row["record_id"]} for row in records]
    freeze = {"immutable_status": "FROZEN", "candidate_number": 2, "pipeline_version": "new_pipeline_v1", "source_distribution": dict(Counter(row["source"] for row in records))}
    report = validate_final_gold(
        records=records, approved_package=approved,
        batch_manifest={"pipeline_version": "new_pipeline_v1"},
        approved_membership=membership, frozen_ids=frozen, freeze_manifest=freeze,
        source_checksums={},
    )
    assert report["result"] == "PASS"
    assert report["record_count"] == report["completed_count"] == 1000
    assert report["batch_counts"] == {name: size for name, _kind, size in BATCH_SPECS}
    assert report["split_created"] is False
    assert report["training_started"] is False


def test_final_gold_rejects_missing_or_duplicate_frozen_records():
    records, approved, _batch_rows, membership = _fixture(Path("."))
    frozen = [{"record_id": row["record_id"]} for row in records]
    freeze = {"immutable_status": "FROZEN", "candidate_number": 2, "pipeline_version": "new_pipeline_v1", "source_distribution": dict(Counter(row["source"] for row in records))}
    report = validate_final_gold(
        records=records[:-1], approved_package=approved,
        batch_manifest={}, approved_membership=membership, frozen_ids=frozen,
        freeze_manifest=freeze, source_checksums={},
    )
    assert report["result"] == "FAIL"
    assert "gold_record_count_or_duplicate_id" in report["errors_by_code"]
    duplicate = records + [records[0]]
    duplicate_report = validate_final_gold(
        records=duplicate, approved_package=approved,
        batch_manifest={}, approved_membership=membership, frozen_ids=frozen,
        freeze_manifest=freeze, source_checksums={},
    )
    assert duplicate_report["result"] == "FAIL"


def test_uniform_batch_display_name_numbering():
    assert [annotation_batch_display_name(name) for name, _kind, _size in BATCH_SPECS] == [
        f"Annotation Batch {number}" for number in range(1, 12)
    ]


def test_file_validator_refuses_mutated_protected_checksums(tmp_path):
    project = tmp_path
    records, approved, batches, membership = _fixture(tmp_path)
    def write(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path
    input_path = write(project / "gold.jsonl", _jsonl_bytes(records))
    approved_path = write(project / "data/annotations/new_pipeline_v1_candidate_2/annotation_records.jsonl", _jsonl_bytes(approved))
    batch_dir = project / "data/annotations/new_pipeline_v1_candidate_2/batches"
    output_paths, checksums = {}, {}
    for name, rows in batches.items():
        path = write(batch_dir / f"{name}.jsonl", _jsonl_bytes(rows))
        output_paths[name] = str(path)
        checksums[name] = sha256_file(path)
    batch_manifest = {"pipeline_version": "new_pipeline_v1", "output_paths": output_paths, "checksums": checksums}
    batch_path = write(project / "artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json", json.dumps(batch_manifest).encode())
    membership_path = write(project / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/approved_batch_membership.jsonl", _jsonl_bytes(membership))
    frozen_rows = [{"record_id": row["record_id"]} for row in records]
    frozen_path = write(project / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_record_ids.jsonl", _jsonl_bytes(frozen_rows))
    freeze = {
        "immutable_status": "FROZEN", "candidate_number": 2, "pipeline_version": "new_pipeline_v1",
        "source_distribution": dict(Counter(row["source"] for row in records)),
        "batch_manifest_checksum": sha256_file(batch_path),
        "approved_batch_manifest": {"membership_checksum": sha256_file(membership_path)},
        "gold_id_checksum": sha256_file(frozen_path),
    }
    freeze_path = write(project / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_sample_manifest.json", json.dumps(freeze).encode())
    report = validate_final_gold_files(
        input_path=input_path, project_root=project,
        batch_manifest_path=batch_path, membership_path=membership_path,
        frozen_ids_path=frozen_path, freeze_manifest_path=freeze_path,
    )
    assert report["result"] == "PASS"
    with pytest.raises(FinalGoldValidationError, match="batch manifest checksum"):
        validate_final_gold_files(
            input_path=input_path, project_root=project,
            batch_manifest_path=batch_path, membership_path=membership_path,
            frozen_ids_path=frozen_path, freeze_manifest_path=write(project / "bad-freeze.json", b"{}"),
        )
