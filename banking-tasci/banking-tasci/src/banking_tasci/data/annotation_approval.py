"""Explicit researcher approval for a reviewed candidate annotation package.

Approval is a separate, immutable audit artifact. This module never mutates
annotation records and never treats ``READY_FOR_RESEARCHER_APPROVAL`` as an
approval by itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from banking_tasci.data.annotation_package_review import (
    AnnotationPackageReview,
    PackageIntegrityError,
    load_jsonl_dicts,
    validate_review_for_approval,
)
from banking_tasci.data.annotation_batches import BATCH_SPECS
from banking_tasci.config import load_config
from banking_tasci.data.gold_sample_plan import (
    ANNOTATION_RECORD_FIELDS,
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    PIPELINE_VERSION,
    REGION_TARGETS,
    SOURCE_TARGETS,
    SOUTH_AFRICA_TWEET,
    TOTAL_TARGET,
)
from banking_tasci.data.manifest import NO_COMMIT_MARKER, git_commit, sha256_file
from banking_tasci.data.anonymise import EMAIL_PATTERN, MENTION_PATTERN, URL_PATTERN
from banking_tasci.data.new_pipeline_schema import PRIVACY_STATUSES, RECORD_FIELDS

__all__ = [
    "APPROVAL_NOT_APPROVED",
    "APPROVAL_APPROVED",
    "DEFAULT_APPROVAL_PATH",
    "ApprovalError",
    "AnnotationPackageApproval",
    "validate_package_for_approval",
    "create_approval_record",
    "write_approval_record",
    "load_approval_record",
    "validate_approval_record",
]

APPROVAL_NOT_APPROVED = "NOT_APPROVED"
APPROVAL_APPROVED = "APPROVED"
DEFAULT_APPROVAL_PATH = Path("artifacts/approvals/new_pipeline_v1/annotation_package_approval.json")


class ApprovalError(ValueError):
    """Raised when explicit researcher approval preconditions are not met."""


@dataclass(frozen=True)
class AnnotationPackageApproval:
    approval_id: str
    pipeline_version: str
    reviewer: str
    approved_at: str
    sample_plan_checksum: str
    annotation_manifest_checksum: str
    batch_manifest_checksum: str
    review_report_checksum: str
    reviewed_record_count: int
    recommendation: str
    approval_status: str
    git_commit: str
    command: str
    notes: list[str]
    candidate_number: int = 1
    annotation_records_checksum: str = ""
    context_limitation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_report(path: str | Path) -> AnnotationPackageReview:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovalError(
            "review report must be an existing machine-readable JSON report; "
            "Markdown prose is not an approval input"
        ) from exc
    if not isinstance(data, dict):
        raise ApprovalError("review report must contain a JSON object")
    try:
        return AnnotationPackageReview.from_dict(data)
    except (TypeError, ValueError) as exc:
        raise ApprovalError(f"review report does not match the review schema: {exc}") from exc


def _verify_group_integrity(report: AnnotationPackageReview) -> list[str]:
    issues: list[str] = []
    for attr in ("duplicate_group_integrity", "leakage_group_integrity"):
        value = getattr(report, attr)
        if value.get("coverage") not in {"present", "verified_none"} or not value.get("verified"):
            issues.append(f"{attr} is not verified")
    return issues


def validate_package_for_approval(
    *,
    review_report_path: str | Path,
    sample_plan_path: str | Path,
    annotation_records_path: str | Path,
    annotation_manifest_path: str | Path,
    batch_manifest_path: str | Path,
    expected_sample_checksum: str,
    expected_batch_manifest_checksum: str,
) -> tuple[AnnotationPackageReview, dict[str, Any], list[dict[str, Any]]]:
    """Check all machine-verifiable approval preconditions without writing."""
    paths = [
        Path(review_report_path),
        Path(sample_plan_path),
        Path(annotation_records_path),
        Path(annotation_manifest_path),
        Path(batch_manifest_path),
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ApprovalError("required approval input(s) missing: " + ", ".join(missing))

    review = _load_report(review_report_path)
    issues = validate_review_for_approval(review)
    actual_sample_checksum = sha256_file(sample_plan_path)
    actual_batch_checksum = sha256_file(batch_manifest_path)
    actual_annotation_manifest_checksum = sha256_file(annotation_manifest_path)
    if actual_sample_checksum != expected_sample_checksum:
        issues.append("sample-plan checksum does not match --expected-sample-checksum")
    if actual_batch_checksum != expected_batch_manifest_checksum:
        issues.append("batch-manifest checksum does not match --expected-batch-manifest-checksum")
    if review.sample_plan_checksum != actual_sample_checksum:
        issues.append("review report sample-plan checksum does not match current sample plan")
    if review.batch_manifest_checksum != actual_batch_checksum:
        issues.append("review report batch-manifest checksum does not match current batch manifest")
    if review.annotation_manifest_checksum != actual_annotation_manifest_checksum:
        issues.append("review report annotation-manifest checksum does not match current annotation manifest")

    records = load_jsonl_dicts(annotation_records_path)
    sample_plan = load_jsonl_dicts(sample_plan_path)
    batch_manifest = json.loads(Path(batch_manifest_path).read_text(encoding="utf-8"))
    expected_batch_ids = [name for name, _kind, _size in BATCH_SPECS]
    expected_batch_sizes = {name: size for name, _kind, size in BATCH_SPECS}
    if batch_manifest.get("batch_ids") != expected_batch_ids:
        issues.append("batch manifest IDs do not match the canonical 11-batch order")
    if batch_manifest.get("batch_sizes") != expected_batch_sizes:
        issues.append("batch manifest sizes do not match 50 + 9x100 + 50")
    if batch_manifest.get("total_batches") != len(BATCH_SPECS) or batch_manifest.get("total_records") != TOTAL_TARGET:
        issues.append("batch manifest totals are not 11 batches / 1,000 records")
    if batch_manifest.get("unresolved_balancing_warnings"):
        issues.append("batch manifest has unresolved placement/balancing warnings")
    if len(records) != TOTAL_TARGET:
        issues.append(f"expected exactly {TOTAL_TARGET} annotation records, found {len(records)}")
    ids = [str(r.get("record_id")) for r in records]
    if len(set(ids)) != TOTAL_TARGET:
        issues.append("annotation record IDs are not exactly 1,000 unique canonical IDs")
    if len({str(r.get("record_id")) for r in sample_plan}) != TOTAL_TARGET:
        issues.append("sample-plan IDs are not exactly 1,000 unique canonical IDs")
    if set(ids) != {str(r.get("record_id")) for r in sample_plan}:
        issues.append("annotation record IDs do not match the sample-plan IDs")

    source_counts: dict[str, int] = {}
    region_counts: dict[str, int] = {}
    for field_name, destination in (("source", source_counts), ("region", region_counts)):
        for record in records:
            value = str(record.get(field_name))
            destination[value] = destination.get(value, 0) + 1
    if source_counts != SOURCE_TARGETS:
        issues.append(f"source allocation mismatch: {source_counts}")
    if region_counts != REGION_TARGETS:
        issues.append(f"regional allocation mismatch: {region_counts}")

    allowed_sources = {SOUTH_AFRICA_TWEET, INTERNATIONAL_TWEET, INTERNATIONAL_REVIEW}
    config_path = Path(__file__).resolve().parents[3] / "configs" / "new_pipeline_v1.yaml"
    cfg = load_config(config_path)
    privacy_patterns = (
        EMAIL_PATTERN,
        URL_PATTERN,
        MENTION_PATTERN,
        re.compile(cfg.anonymise.account_reference_pattern),
        re.compile(cfg.anonymise.phone_pattern),
    )
    for record in records:
        rid = str(record.get("record_id"))
        if set(record) != set(ANNOTATION_RECORD_FIELDS):
            issues.append(f"record {rid} has missing or non-canonical annotation-package fields")
        missing_keys = sorted(set(RECORD_FIELDS) - set(record))
        if missing_keys:
            issues.append(f"record {rid} is missing required key(s): {missing_keys}")
        if record.get("source") not in allowed_sources:
            issues.append(f"record {rid} has invalid source")
        if record.get("annotation_status") != "not_started":
            issues.append(f"record {rid} has annotation_status other than not_started")
        if record.get("annotation_version") != PIPELINE_VERSION:
            issues.append(f"record {rid} has annotation_version other than {PIPELINE_VERSION}")
        if record.get("primary_intent") is not None:
            issues.append(f"record {rid} has prefilled primary_intent")
        if record.get("public_warning") is not None:
            issues.append(f"record {rid} has prefilled public_warning")
        if record.get("opinions") != []:
            issues.append(f"record {rid} has non-empty or malformed opinions")
        if record.get("privacy_status") not in PRIVACY_STATUSES:
            issues.append(f"record {rid} has invalid privacy_status")
        if not isinstance(record.get("text"), str) or not record["text"].strip():
            issues.append(f"record {rid} has missing or blank text")
        elif any(pattern.search(record["text"]) for pattern in privacy_patterns):
            issues.append(f"record {rid} text appears to contain a raw identifier")
        source_record_id = record.get("source_record_id")
        if record.get("record_id") != f"{record.get('source')}::{source_record_id}":
            issues.append(f"record {rid} does not have the canonical namespaced ID")
        expected_region = "south_africa" if record.get("source") == SOUTH_AFRICA_TWEET else "international"
        if record.get("region") != expected_region:
            issues.append(f"record {rid} source/region mapping is inconsistent")

    source_id_sources: dict[str, set[str]] = {}
    for record in records:
        source_id_sources.setdefault(str(record.get("source_record_id")), set()).add(
            str(record.get("source"))
        )
    if any(len(sources) > 1 for sources in source_id_sources.values()):
        issues.append("source_record_id collision exists across canonical sources")

    batch_manifest_ids: list[str] = []
    output_paths = batch_manifest.get("output_paths", {})
    batch_checksums = batch_manifest.get("checksums", {})
    batch_sizes = batch_manifest.get("batch_sizes", {})
    for batch_id, _batch_type, expected_size in BATCH_SPECS:
        batch_path_value = output_paths.get(batch_id)
        batch_path = Path(batch_path_value) if batch_path_value else None
        if batch_path is None or not batch_path.is_file():
            issues.append(f"batch output file is missing for {batch_id}")
            continue
        if batch_sizes.get(batch_id) != expected_size:
            issues.append(f"batch manifest size mismatch for {batch_id}")
        if sha256_file(batch_path) != batch_checksums.get(batch_id):
            issues.append(f"batch file checksum mismatch for {batch_id}")
        batch_records = load_jsonl_dicts(batch_path)
        if len(batch_records) != expected_size:
            issues.append(f"batch file {batch_id} has {len(batch_records)} records, expected {expected_size}")
        batch_manifest_ids.extend(str(record.get("record_id")) for record in batch_records)
    if len(batch_manifest_ids) != TOTAL_TARGET or set(batch_manifest_ids) != set(ids):
        issues.append("batch files do not contain every annotation record exactly once")
    if len(set(batch_manifest_ids)) != len(batch_manifest_ids):
        issues.append("record ID is duplicated across batch files")

    issues.extend(_verify_group_integrity(review))
    annotation_manifest = json.loads(Path(annotation_manifest_path).read_text(encoding="utf-8"))
    if annotation_manifest.get("pipeline_version") != PIPELINE_VERSION:
        issues.append("annotation manifest pipeline_version mismatch")
    if annotation_manifest.get("output_checksum") != sha256_file(annotation_records_path):
        issues.append("annotation manifest checksum does not match annotation records")
    if annotation_manifest.get("input_sample_plan_checksum") != actual_sample_checksum:
        issues.append("annotation manifest input checksum does not match sample plan")

    unique_issues = sorted(set(issues))
    if unique_issues:
        raise ApprovalError("package is not eligible for approval:\n- " + "\n- ".join(unique_issues))
    return review, annotation_manifest, records


def create_approval_record(
    *,
    reviewer: str,
    review_report_path: str | Path,
    sample_plan_path: str | Path,
    annotation_records_path: str | Path,
    annotation_manifest_path: str | Path,
    batch_manifest_path: str | Path,
    expected_sample_checksum: str,
    expected_batch_manifest_checksum: str,
    command: str,
    approve: bool = False,
) -> AnnotationPackageApproval:
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ApprovalError("reviewer must be explicitly supplied and non-empty")
    review, _annotation_manifest, records = validate_package_for_approval(
        review_report_path=review_report_path,
        sample_plan_path=sample_plan_path,
        annotation_records_path=annotation_records_path,
        annotation_manifest_path=annotation_manifest_path,
        batch_manifest_path=batch_manifest_path,
        expected_sample_checksum=expected_sample_checksum,
        expected_batch_manifest_checksum=expected_batch_manifest_checksum,
    )
    if review.recommendation != "READY_FOR_RESEARCHER_APPROVAL":
        raise ApprovalError("review recommendation is not READY_FOR_RESEARCHER_APPROVAL")

    checksums = {
        "sample": sha256_file(sample_plan_path),
        "annotation_manifest": sha256_file(annotation_manifest_path),
        "annotation_records": sha256_file(annotation_records_path),
        "batch": sha256_file(batch_manifest_path),
        "review": sha256_file(review_report_path),
    }
    approval_id = hashlib.sha256(
        json.dumps(
            {"candidate_number": review.candidate_number, **checksums},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:24]
    context_limitation = review.context_experiment_status or "No context limitation recorded in review."
    return AnnotationPackageApproval(
        approval_id=approval_id,
        pipeline_version=PIPELINE_VERSION,
        reviewer=reviewer.strip(),
        approved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sample_plan_checksum=checksums["sample"],
        annotation_manifest_checksum=checksums["annotation_manifest"],
        batch_manifest_checksum=checksums["batch"],
        review_report_checksum=checksums["review"],
        reviewed_record_count=len(records),
        recommendation=review.recommendation,
        approval_status=APPROVAL_APPROVED if approve else APPROVAL_NOT_APPROVED,
        git_commit=git_commit(),
        command=command,
        notes=[
            "Approval is a separate artifact; annotation records were not modified.",
            "This approval authorizes a later identity-freeze decision only; it does not freeze IDs or start annotation or training.",
            f"Accepted context limitation: {context_limitation}",
        ],
        candidate_number=review.candidate_number,
        annotation_records_checksum=checksums["annotation_records"],
        context_limitation=context_limitation,
    )


def write_approval_record(
    approval: AnnotationPackageApproval, path: str | Path
) -> Path:
    """Atomically create an approval artifact without ever replacing one."""
    if approval.approval_status != APPROVAL_APPROVED:
        raise ApprovalError("only an explicitly approved record may be written")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = load_approval_record(target)
        existing_checksums = (
            existing.sample_plan_checksum,
            existing.annotation_manifest_checksum,
            existing.batch_manifest_checksum,
        )
        new_checksums = (
            approval.sample_plan_checksum,
            approval.annotation_manifest_checksum,
            approval.batch_manifest_checksum,
        )
        if existing.approval_status == APPROVAL_APPROVED and existing_checksums != new_checksums:
            raise FileExistsError("a different package is already approved at this path")
        raise FileExistsError(f"approval record already exists; refusing overwrite: {target}")

    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(approval.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, target)
        except FileExistsError as exc:
            raise FileExistsError(f"approval record already exists; refusing overwrite: {target}") from exc
    finally:
        if Path(temp_name).exists():
            Path(temp_name).unlink()
    return target


def load_approval_record(path: str | Path) -> AnnotationPackageApproval:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AnnotationPackageApproval(**data)


def validate_approval_record(
    approval: AnnotationPackageApproval,
    *,
    sample_plan_checksum: str,
    annotation_manifest_checksum: str,
    batch_manifest_checksum: str,
) -> list[str]:
    issues: list[str] = []
    if approval.approval_status != APPROVAL_APPROVED:
        issues.append("approval_status is not APPROVED")
    if approval.pipeline_version != PIPELINE_VERSION:
        issues.append("approval pipeline_version mismatch")
    if approval.recommendation != "READY_FOR_RESEARCHER_APPROVAL":
        issues.append("approval recommendation is not ready")
    if approval.sample_plan_checksum != sample_plan_checksum:
        issues.append("approval sample-plan checksum mismatch")
    if approval.annotation_manifest_checksum != annotation_manifest_checksum:
        issues.append("approval annotation-manifest checksum mismatch")
    if approval.batch_manifest_checksum != batch_manifest_checksum:
        issues.append("approval batch-manifest checksum mismatch")
    if approval.reviewed_record_count != TOTAL_TARGET:
        issues.append("approval record count is not 1,000")
    if not approval.reviewer.strip():
        issues.append("approval reviewer is missing")
    return issues
