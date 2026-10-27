#!/usr/bin/env python3
"""Deprecated compatibility wrapper for opening technical batch calibration_001.

The physical technical ID is retained, but the operation is the standard
Annotation Batch 1 workflow shared by all eleven batches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import warnings
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from banking_tasci.data.annotation_batches import (  # noqa: E402
    BatchMetadata,
    annotation_records_checksum,
    operational_batch_metadata,
)
from banking_tasci.data.calibration_workspace import create_annotation_workspace  # noqa: E402
from banking_tasci.data.new_pipeline_annotation_validator import (  # noqa: E402
    IMMUTABLE_FIELDS,
    validate_records,
)

APPROVED_SHA256 = "7665366000c4b95b6c57fac91a2bd786098f16848001bf59a5c2c5a0b8700e66"
ACTOR = "Rotondwa Mavhengani"
REASON = "Authorised 50-record calibration"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: Path, value: dict) -> None:
    _atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def precheck(root: Path) -> tuple[list[dict], BatchMetadata, dict]:
    warnings.warn(
        "activate_calibration_workspace is deprecated; use scripts/annotation_workspace.py with calibration_001",
        DeprecationWarning,
        stacklevel=2,
    )
    batch_path = root / "data/annotations/new_pipeline_v1_candidate_2/batches/calibration_001.jsonl"
    records_path = root / "data/annotations/new_pipeline_v1_candidate_2/annotation_records.jsonl"
    manifest_path = root / "artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json"
    approval_path = root / "artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json"
    frozen_path = root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_record_ids.jsonl"
    membership_path = root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/approved_batch_membership.jsonl"
    if _sha256(batch_path) != APPROVED_SHA256:
        raise ValueError("approved annotation batch checksum mismatch")
    records = _read_jsonl(batch_path)
    ids = [str(row.get("record_id", "")) for row in records]
    if len(records) != 50 or len(set(ids)) != 50 or any(not rid for rid in ids):
        raise ValueError("Annotation Batch 1 must contain 50 unique canonical IDs")
    if any(row.get("annotation_version") != "new_pipeline_v1" for row in records):
        raise ValueError("annotation version mismatch")
    if any(row.get("annotation_status") != "not_started" for row in records):
        raise ValueError("approved source batch has unexpected annotation statuses")
    if any(row.get("primary_intent") is not None or row.get("public_warning") is not None or row.get("opinions") != [] for row in records):
        raise ValueError("approved calibration source contains labels")
    if any(row.get("privacy_status") not in {"anonymised", "not_required"} for row in records):
        raise ValueError("approved batch privacy validation failed")

    frozen_ids = {row["record_id"] for row in _read_jsonl(frozen_path)}
    approved_membership = {row["record_id"] for row in _read_jsonl(membership_path) if row["batch_id"] == "calibration_001"}
    if set(ids) - frozen_ids or set(ids) != approved_membership:
        raise ValueError("frozen identity or approved batch membership mismatch")

    all_records = {row["record_id"]: row for row in _read_jsonl(records_path)}
    for row in records:
        original = all_records.get(row["record_id"])
        if original is None or any(row.get(field) != original.get(field) for field in IMMUTABLE_FIELDS):
            raise ValueError(f"source/provenance mismatch for {row['record_id']}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest["batches"]["calibration_001"]
    if item.get("batch_status") != "generated" or manifest.get("checksums", {}).get("calibration_001") != APPROVED_SHA256:
        raise ValueError("Annotation Batch 1 manifest is not the approved generated batch")
    if annotation_records_checksum(records) != APPROVED_SHA256:
        raise ValueError("canonical Annotation Batch 1 checksum mismatch")
    validation = validate_records(records, records, {"calibration_001": set(ids)}, completed_gold=False)
    if validation["result"] != "PASS":
        raise ValueError("label-hidden batch validation failed")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    frozen_manifest = json.loads((root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_sample_manifest.json").read_text(encoding="utf-8"))
    metadata = operational_batch_metadata(
        "calibration_001", record_count=50, source_checksum=APPROVED_SHA256,
        candidate_number=2, pipeline_version="new_pipeline_v1",
        approved_membership_checksum=frozen_manifest["approved_batch_manifest"]["membership_checksum"],
        current_status=item["batch_status"],
    )
    return records, metadata, approval


def activate(root: Path, workspace: Path) -> dict:
    warnings.warn(
        "activate_calibration_workspace is deprecated; it now opens Annotation Batch 1 under the uniform workflow",
        DeprecationWarning,
        stacklevel=2,
    )
    precheck(root)
    return create_annotation_workspace(
        root, "calibration_001", actor=ACTOR, reason=REASON,
        guide_version="new_pipeline_v1-guide-1", workspace=workspace,
    )


def main(argv: list[str] | None = None) -> int:
    print(
        "DEPRECATED: use scripts/annotation_workspace.py; calibration_001 is Annotation Batch 1.",
        file=sys.stderr,
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="data/annotations/new_pipeline_v1_candidate_2/calibration_workspace/calibration_001")
    parser.add_argument("--actor", default=ACTOR)
    parser.add_argument("--reason", default=REASON)
    parser.add_argument("--guide-version", default="new_pipeline_v1-guide-1")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    workspace = ROOT / args.workspace
    if args.verify_only:
        records, _, _ = precheck(ROOT)
        print(json.dumps({"result": "PASS", "records": len(records), "writes": 0}))
        return 0
    print(json.dumps(activate(ROOT, workspace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
