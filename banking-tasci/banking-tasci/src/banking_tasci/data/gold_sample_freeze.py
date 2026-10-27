"""Explicit immutable identity freeze for an approved `new_pipeline_v1` sample.

A freeze creates identity/provenance artifacts only. It never copies human
annotation fields, changes candidate package records, or starts a split/corpus
workflow.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from banking_tasci.data.annotation_approval import (
    APPROVAL_APPROVED,
    AnnotationPackageApproval,
    load_approval_record,
    validate_approval_record,
)
from banking_tasci.data.annotation_package_review import load_jsonl_dicts
from banking_tasci.data.gold_sample_plan import (
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    PIPELINE_VERSION,
    REGION_TARGETS,
    SOURCE_TARGETS,
    SOUTH_AFRICA_TWEET,
    TOTAL_TARGET,
)
from banking_tasci.data.manifest import NO_COMMIT_MARKER, git_commit, sha256_file

__all__ = [
    "FREEZE_ID_FILENAME",
    "FREEZE_RECORDS_FILENAME",
    "FREEZE_CHECKSUM_FILENAME",
    "FREEZE_RECEIPT_FILENAME",
    "FreezeError",
    "build_gold_identity_records",
    "resolve_candidate_paths",
    "prepare_superseding_revision",
    "write_superseding_revision",
    "prepare_freeze_artifacts",
    "write_freeze_artifacts",
]

FREEZE_ID_FILENAME = "gold_sample_manifest.json"
FREEZE_RECORDS_FILENAME = "gold_record_ids.jsonl"
FREEZE_CHECKSUM_FILENAME = "gold_record_ids.sha256"
FREEZE_RECEIPT_FILENAME = "freeze_receipt.json"
FREEZE_SUPERSESSION_FILENAME = "supersession_manifest.json"
FREEZE_BATCH_MEMBERSHIP_FILENAME = "approved_batch_membership.jsonl"


class FreezeError(ValueError):
    """Raised when approval or immutable-freeze preconditions fail."""


def resolve_candidate_paths(project_root: str | Path, candidate_number: int) -> dict[str, Path]:
    """Return the only permitted artifact set for an explicitly selected candidate."""
    root = Path(project_root)
    if candidate_number not in {1, 2}:
        raise FreezeError("unsupported candidate number; expected 1 or 2")
    if candidate_number == 1:
        suffix = ""
        candidate_manifest = root / "artifacts/manifests" / PIPELINE_VERSION / "gold_sample_plan_manifest.json"
    else:
        suffix = "_candidate_2"
        candidate_manifest = root / "artifacts/manifests" / PIPELINE_VERSION / "candidate_2/candidate_2_manifest.json"
    annotations = root / f"data/annotations/{PIPELINE_VERSION}{suffix}"
    manifests = root / "artifacts/manifests" / PIPELINE_VERSION
    if candidate_number == 2:
        manifests = manifests / "candidate_2"
    approvals = root / "artifacts/approvals" / PIPELINE_VERSION
    if candidate_number == 2:
        approvals = approvals / "candidate_2"
    return {
        "sample_plan": annotations / "gold_sample_plan.jsonl",
        "annotation_records": annotations / "annotation_records.jsonl",
        "annotation_manifest": manifests / "annotation_package_manifest.json",
        "batch_manifest": manifests / "annotation_batch_manifest.json",
        "candidate_manifest": candidate_manifest,
        "review_report": root / "artifacts/reports" / PIPELINE_VERSION / ("candidate_2/annotation_package_review.json" if candidate_number == 2 else "annotation_package_review.json"),
        "approval": approvals / "annotation_package_approval.json",
        "output_dir": root / "artifacts/frozen" / PIPELINE_VERSION / ("candidate_2" if candidate_number == 2 else "candidate_1"),
    }


def build_gold_identity_records(
    sample_plan: list[dict[str, Any]],
    source_checksums: dict[str, str],
) -> list[dict[str, Any]]:
    """Project plan to identifiers and provenance only; labels are excluded."""
    identities: list[dict[str, Any]] = []
    for record in sample_plan:
        source = record.get("source")
        if source == SOUTH_AFRICA_TWEET:
            source_checksum = source_checksums.get("south_africa", "")
        elif source in {INTERNATIONAL_TWEET, INTERNATIONAL_REVIEW}:
            source_checksum = source_checksums.get("international", "")
        else:
            raise FreezeError(f"unsupported canonical source '{source}'")
        source_record_id = record.get("source_record_id")
        canonical_id = record.get("record_id")
        if not source_record_id or canonical_id != f"{source}::{source_record_id}":
            raise FreezeError(f"invalid canonical/source ID pair for {canonical_id}")
        identities.append(
            {
                "record_id": canonical_id,
                "source_record_id": source_record_id,
                "source": source,
                "region": record.get("region"),
                "source_checksum": source_checksum,
            }
        )
    ids = [r["record_id"] for r in identities]
    if len(identities) != TOTAL_TARGET or len(set(ids)) != TOTAL_TARGET:
        raise FreezeError("freeze requires exactly 1,000 unique canonical record IDs")
    if any(not r["source_checksum"] for r in identities):
        raise FreezeError("every identity record requires a verified source checksum")
    if set(Counter(r["source"] for r in identities).items()) != set(SOURCE_TARGETS.items()):
        raise FreezeError("gold identity source allocation does not match requirements")
    if set(Counter(r["region"] for r in identities).items()) != set(REGION_TARGETS.items()):
        raise FreezeError("gold identity regional allocation does not match requirements")
    return identities


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    ).encode("utf-8")


def prepare_freeze_artifacts(
    *,
    sample_plan_path: str | Path,
    annotation_records_path: str | Path,
    annotation_manifest_path: str | Path,
    batch_manifest_path: str | Path,
    approval_path: str | Path,
    authority: str,
    command: str,
    candidate_number: int = 1,
    candidate_manifest_path: str | Path | None = None,
    review_report_path: str | Path | None = None,
    expected_checksums: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Prepare all immutable freeze payloads without writing them."""
    if candidate_number not in {1, 2}:
        raise FreezeError("unsupported candidate number; expected 1 or 2")
    if not isinstance(authority, str) or not authority.strip():
        raise FreezeError("freeze authority must be explicitly supplied")
    for name, value in (
        ("sample plan", sample_plan_path),
        ("annotation records", annotation_records_path),
        ("annotation manifest", annotation_manifest_path),
        ("batch manifest", batch_manifest_path),
        ("approval", approval_path),
    ):
        if not Path(value).is_file():
            raise FreezeError(f"{name} does not exist: {value}")

    if candidate_number == 2 and (candidate_manifest_path is None or review_report_path is None):
        raise FreezeError("Candidate 2 requires explicit candidate manifest and review report paths")
    sample_checksum = sha256_file(sample_plan_path)
    annotation_checksum = sha256_file(annotation_records_path)
    annotation_manifest_checksum = sha256_file(annotation_manifest_path)
    batch_checksum = sha256_file(batch_manifest_path)
    approval_checksum = sha256_file(approval_path)
    current_checksums = {
        "sample": sample_checksum, "annotation": annotation_checksum,
        "batch": batch_checksum, "review": sha256_file(review_report_path) if review_report_path else "",
        "approval": approval_checksum,
    }
    for name, expected in (expected_checksums or {}).items():
        if expected is not None and current_checksums.get(name) != expected:
            raise FreezeError(f"{name} checksum does not match its explicit expected checksum")
    approval: AnnotationPackageApproval = load_approval_record(approval_path)
    problems = validate_approval_record(
        approval,
        sample_plan_checksum=sample_checksum,
        annotation_manifest_checksum=annotation_manifest_checksum,
        batch_manifest_checksum=batch_checksum,
    )
    if problems:
        raise FreezeError("approval does not match current package: " + "; ".join(problems))
    if approval.approval_status != APPROVAL_APPROVED:
        raise FreezeError("package does not have an APPROVED approval record")
    if approval.candidate_number != candidate_number:
        raise FreezeError("approval candidate number does not match requested candidate")
    if not approval.approval_id or not approval.reviewer:
        raise FreezeError("approval must include an approval ID and researcher")
    if approval.annotation_records_checksum != annotation_checksum:
        raise FreezeError("approval annotation-record checksum does not match current annotation records")
    if review_report_path and approval.review_report_checksum != current_checksums["review"]:
        raise FreezeError("approval review-report checksum does not match current review report")

    sample_plan = load_jsonl_dicts(sample_plan_path)
    annotation_records = load_jsonl_dicts(annotation_records_path)
    if len(sample_plan) != TOTAL_TARGET or len(annotation_records) != TOTAL_TARGET:
        raise FreezeError("freeze requires exactly 1,000 sample-plan and annotation records")
    if {r.get("record_id") for r in sample_plan} != {r.get("record_id") for r in annotation_records}:
        raise FreezeError("annotation records do not have the same immutable IDs as sample plan")

    annotation_manifest = json.loads(Path(annotation_manifest_path).read_text(encoding="utf-8"))
    if annotation_manifest.get("output_checksum") != annotation_checksum:
        raise FreezeError("annotation manifest does not match current annotation records")
    if annotation_manifest.get("label_hidden") is not True:
        raise FreezeError("annotation manifest does not attest a label-hidden package")
    if annotation_manifest.get("output_record_count") != TOTAL_TARGET:
        raise FreezeError("annotation manifest record count is not 1,000")
    if annotation_manifest.get("input_sample_plan_checksum") != sample_checksum:
        raise FreezeError("annotation manifest does not match current sample plan")
    batch_manifest = json.loads(Path(batch_manifest_path).read_text(encoding="utf-8"))
    if batch_manifest.get("total_batches") != 11 or batch_manifest.get("total_records") != TOTAL_TARGET:
        raise FreezeError("batch manifest totals do not match the 11-batch/1,000-record plan")
    batch_paths = batch_manifest.get("output_paths", {})
    for batch_id, expected_checksum in batch_manifest.get("checksums", {}).items():
        file_path = Path(batch_paths.get(batch_id, ""))
        if not file_path.is_file() or sha256_file(file_path) != expected_checksum:
            raise FreezeError(f"batch file missing or checksum mismatch: {batch_id}")
    plan_manifest_path = Path(candidate_manifest_path) if candidate_manifest_path else Path(sample_plan_path).parents[3] / "artifacts" / "manifests" / PIPELINE_VERSION / "gold_sample_plan_manifest.json"
    if not plan_manifest_path.is_file():
        raise FreezeError("sample-plan manifest is missing")
    plan_manifest = json.loads(plan_manifest_path.read_text(encoding="utf-8"))
    if plan_manifest.get("plan_output_sha256") != sample_checksum:
        raise FreezeError("sample-plan manifest checksum mismatch")
    if candidate_number == 2 and plan_manifest.get("candidate_number") != 2:
        raise FreezeError("Candidate 2 manifest does not identify Candidate 2")
    for artifact, data in (("annotation manifest", annotation_manifest), ("batch manifest", batch_manifest)):
        if candidate_number == 2 and data.get("candidate_number") != 2:
            raise FreezeError(f"{artifact} does not identify Candidate 2")
    candidate1_preserved = True
    if candidate_number == 2:
        baseline = plan_manifest.get("candidate1_artifact_checksums")
        if not isinstance(baseline, dict) or not baseline:
            raise FreezeError("Candidate 2 manifest lacks Candidate 1 preservation evidence")
        for path_text, expected_checksum in baseline.items():
            path = Path(path_text)
            if not path.is_file() or sha256_file(path) != expected_checksum:
                candidate1_preserved = False
                raise FreezeError(f"Candidate 1 preservation checksum mismatch: {path}")

    label_fields = ("primary_intent", "public_warning", "opinions", "target_labels", "category_labels", "sentiment_labels", "annotation_notes")
    for record in annotation_records:
        if record.get("annotation_status") != "not_started":
            raise FreezeError("annotation records must all remain not_started")
        for field in label_fields:
            value = record.get(field)
            if value not in (None, [], {}, ""):
                raise FreezeError(f"annotation records contain task-label contamination: {field}")

    source_checksums = {
        "south_africa": str(
            plan_manifest.get("south_africa_source_sha256")
            or plan_manifest.get("source_checksums", {}).get("south_africa_candidates_v2", "")
        ),
        "international": str(
            plan_manifest.get("international_source_sha256")
            or plan_manifest.get("source_checksums", {}).get("international_prepared", "")
        ),
    }
    identities = build_gold_identity_records(sample_plan, source_checksums)
    identity_bytes = _jsonl_bytes(identities)
    identity_checksum = hashlib.sha256(identity_bytes).hexdigest()
    freeze_id = hashlib.sha256(
        f"{sample_checksum}:{annotation_manifest_checksum}:{batch_checksum}:{approval_checksum}".encode("utf-8")
    ).hexdigest()[:24]
    source_distribution = dict(sorted(Counter(r["source"] for r in identities).items()))
    region_distribution = dict(sorted(Counter(r["region"] for r in identities).items()))
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "freeze_id": freeze_id,
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frozen_by": authority.strip(),
        "record_count": len(identities),
        "unique_record_count": len({r["record_id"] for r in identities}),
        "source_distribution": source_distribution,
        "region_distribution": region_distribution,
        "sample_plan_checksum": sample_checksum,
        "annotation_records_checksum": annotation_checksum,
        "annotation_manifest_checksum": annotation_manifest_checksum,
        "batch_manifest_checksum": batch_checksum,
        "approval_checksum": approval_checksum,
        "review_report_checksum": current_checksums["review"] or approval.review_report_checksum,
        "candidate_number": candidate_number,
        "candidate1_preserved": candidate1_preserved,
        "gold_id_file": FREEZE_RECORDS_FILENAME,
        "gold_id_checksum": identity_checksum,
        "git_commit": git_commit(),
        "immutable_status": "PENDING_FREEZE",
        "command": command,
        "notes": ["Identity and provenance only; no annotation labels are included."],
    }
    receipt = {
        "pipeline_version": PIPELINE_VERSION,
        "freeze_id": freeze_id,
        "freeze_manifest_checksum": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "gold_id_checksum": identity_checksum,
        "frozen_by": authority.strip(),
        "frozen_at": manifest["frozen_at"],
        "immutable_status": "PENDING_FREEZE",
        "git_commit": git_commit(),
    }
    return {
        "manifest": manifest,
        "identity_records": identities,
        "identity_bytes": identity_bytes,
        "identity_checksum": identity_checksum,
        "receipt": receipt,
    }


def write_freeze_artifacts(
    payload: dict[str, Any],
    output_dir: str | Path,
    *,
    acknowledge_immutable_ids: bool,
) -> Path:
    """Atomically create an entirely new freeze directory; never replace it."""
    if not acknowledge_immutable_ids:
        raise FreezeError("--acknowledge-immutable-ids is required to write a freeze")
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"freeze output already exists; refusing overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        manifest = dict(payload["manifest"])
        manifest["immutable_status"] = "FROZEN"
        receipt = dict(payload["receipt"])
        receipt["immutable_status"] = "FROZEN"
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        receipt["freeze_manifest_checksum"] = hashlib.sha256(manifest_bytes).hexdigest()
        (staging / FREEZE_RECORDS_FILENAME).write_bytes(payload["identity_bytes"])
        (staging / FREEZE_CHECKSUM_FILENAME).write_text(
            payload["identity_checksum"] + "  " + FREEZE_RECORDS_FILENAME + "\n",
            encoding="utf-8",
        )
        (staging / FREEZE_ID_FILENAME).write_text(
            manifest_bytes.decode("utf-8"),
            encoding="utf-8",
        )
        (staging / FREEZE_RECEIPT_FILENAME).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def prepare_superseding_revision(
    *,
    original_dir: str | Path,
    approval_path: str | Path,
    batch_manifest_path: str | Path,
    source_manifest_paths: dict[str, str | Path],
    researcher: str,
    supersession_reason: str,
) -> dict[str, Any]:
    """Prepare a metadata-complete revision without changing frozen IDs."""
    original = Path(original_dir)
    required = [original / FREEZE_ID_FILENAME, original / FREEZE_RECORDS_FILENAME,
                original / FREEZE_CHECKSUM_FILENAME, original / FREEZE_RECEIPT_FILENAME]
    if not all(path.is_file() for path in required):
        raise FreezeError("original freeze package is incomplete")
    original_manifest = json.loads((original / FREEZE_ID_FILENAME).read_text(encoding="utf-8"))
    if original_manifest.get("immutable_status") != "FROZEN" or original_manifest.get("candidate_number") != 2:
        raise FreezeError("supersession requires the original frozen Candidate 2 package")
    identity_bytes = (original / FREEZE_RECORDS_FILENAME).read_bytes()
    identity_checksum = hashlib.sha256(identity_bytes).hexdigest()
    if identity_checksum != original_manifest.get("gold_id_checksum"):
        raise FreezeError("original frozen ID checksum mismatch")
    approval = load_approval_record(approval_path)
    approval_checksum = sha256_file(approval_path)
    if approval.approval_status != APPROVAL_APPROVED or approval.candidate_number != 2:
        raise FreezeError("supersession requires the approved Candidate 2 approval artifact")
    if approval.approval_id == "" or approval.reviewer != researcher:
        raise FreezeError("approval researcher or approval ID does not match supersession authority")
    batch_manifest = json.loads(Path(batch_manifest_path).read_text(encoding="utf-8"))
    if batch_manifest.get("candidate_number") != 2:
        raise FreezeError("batch manifest is not Candidate 2")
    memberships: list[dict[str, str]] = []
    for batch_id, batch_path in batch_manifest.get("output_paths", {}).items():
        for record in load_jsonl_dicts(batch_path):
            memberships.append({"record_id": record["record_id"], "batch_id": batch_id})
    original_ids = {json.loads(line)["record_id"] for line in identity_bytes.decode("utf-8").splitlines() if line}
    membership_ids = {item["record_id"] for item in memberships}
    if len(memberships) != 1000 or len(membership_ids) != 1000 or membership_ids != original_ids:
        raise FreezeError("approved batch membership does not cover exactly the frozen IDs")
    memberships.sort(key=lambda item: item["record_id"])
    membership_bytes = _jsonl_bytes(memberships)
    source_refs: dict[str, dict[str, str]] = {}
    for name, path_value in source_manifest_paths.items():
        path = Path(path_value)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "VERIFIED":
            raise FreezeError(f"source manifest is not VERIFIED: {name}")
        source_refs[name] = {"path": str(path), "file_checksum": sha256_file(path), "source_checksum": str(data.get("sha256", ""))}
    if set(source_refs) != {"south_africa", "international", "combined_relevant"}:
        raise FreezeError("all three verified source manifests are required")
    revision_id = hashlib.sha256((identity_checksum + approval_checksum + hashlib.sha256(membership_bytes).hexdigest()).encode()).hexdigest()[:24]
    manifest = {
        **original_manifest, "freeze_id": revision_id, "revision_number": 2,
        "supersedes_freeze": {"path": str(original), "freeze_id": original_manifest["freeze_id"], "frozen_at": original_manifest["frozen_at"], "gold_id_checksum": identity_checksum},
        "approval": {"approval_id": approval.approval_id, "artifact_path": str(approval_path), "artifact_checksum": approval_checksum},
        "approved_batch_manifest": {"path": str(batch_manifest_path), "checksum": sha256_file(batch_manifest_path), "membership_file": FREEZE_BATCH_MEMBERSHIP_FILENAME, "membership_checksum": hashlib.sha256(membership_bytes).hexdigest()},
        "verified_source_manifests": source_refs,
        "expected_counts": {"combined_relevant": 111615, "gold": 1000, "strict_unlabelled": 110615},
        "supersession_reason": supersession_reason,
        "frozen_by": researcher, "immutable_status": "FROZEN",
    }
    receipt = {"pipeline_version": PIPELINE_VERSION, "freeze_id": revision_id, "immutable_status": "FROZEN", "gold_id_checksum": identity_checksum, "supersedes_freeze_id": original_manifest["freeze_id"], "frozen_by": researcher, "git_commit": git_commit()}
    supersession = {"revision_number": 2, "supersedes": manifest["supersedes_freeze"], "reason": supersession_reason, "identity_projection_preserved": True, "original_gold_id_checksum": identity_checksum}
    return {"manifest": manifest, "receipt": receipt, "supersession": supersession, "identity_bytes": identity_bytes, "identity_checksum": identity_checksum, "membership_bytes": membership_bytes}


def write_superseding_revision(payload: dict[str, Any], output_dir: str | Path) -> Path:
    """Atomically write a new revision; never alter the original freeze."""
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"superseding revision already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        manifest_bytes = (json.dumps(payload["manifest"], indent=2, sort_keys=True) + "\n").encode()
        receipt = dict(payload["receipt"])
        receipt["freeze_manifest_checksum"] = hashlib.sha256(manifest_bytes).hexdigest()
        (staging / FREEZE_RECORDS_FILENAME).write_bytes(payload["identity_bytes"])
        (staging / FREEZE_CHECKSUM_FILENAME).write_text(payload["identity_checksum"] + "  " + FREEZE_RECORDS_FILENAME + "\n", encoding="utf-8")
        (staging / FREEZE_BATCH_MEMBERSHIP_FILENAME).write_bytes(payload["membership_bytes"])
        (staging / FREEZE_ID_FILENAME).write_bytes(manifest_bytes)
        (staging / FREEZE_RECEIPT_FILENAME).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (staging / FREEZE_SUPERSESSION_FILENAME).write_text(json.dumps(payload["supersession"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target
