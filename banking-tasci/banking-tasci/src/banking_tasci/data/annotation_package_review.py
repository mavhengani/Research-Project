"""Static candidate-package review model for `new_pipeline_v1`.

This module represents review evidence without approving or freezing a package.
It reads the existing sample plan, annotation JSONL, manifests, and batch files;
it never writes beneath ``data/annotations/new_pipeline_v1``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from banking_tasci.data.annotation_batches import BATCH_SPECS, GROUP_FIELDS
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
from banking_tasci.data.new_pipeline_schema import PRIVACY_STATUSES

__all__ = [
    "RECOMMENDATIONS",
    "AnnotationPackageReview",
    "PackageIntegrityError",
    "load_jsonl_dicts",
    "build_package_review",
    "write_review_json",
    "render_review_markdown",
    "write_review_markdown",
    "validate_review_for_approval",
]

RECOMMENDATIONS = (
    "READY_FOR_RESEARCHER_APPROVAL",
    "NOT_READY_FOR_RESEARCHER_APPROVAL",
)


class PackageIntegrityError(ValueError):
    """Raised when candidate artifacts cannot be consistently inspected."""


def load_jsonl_dicts(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PackageIntegrityError(
                    f"invalid JSONL at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise PackageIntegrityError(
                    f"expected JSON object at {path}:{line_number}"
                )
            records.append(value)
    return records


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageIntegrityError(f"cannot read JSON manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PackageIntegrityError(f"manifest {path} must contain a JSON object")
    return value


def _distribution(records: list[dict], field_name: str) -> dict[str, int]:
    return dict(sorted(Counter(str(r.get(field_name)) for r in records).items()))


def _selection_reason_band(reason: Any) -> str:
    match = re.search(r"(?:^|;)\s*length_band=([^;]+)", str(reason or ""))
    return match.group(1).strip() if match else "not_recorded"


def _selection_reason_rule(reason: Any) -> str:
    match = re.search(r"(?:^|;)\s*v2_rule=([^;]+)", str(reason or ""))
    return match.group(1).strip() if match else "not_recorded"


def _is_present(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "nan", "None"}


def _group_integrity(
    records: list[dict], field_name: str, record_to_batch: dict[str, str]
) -> dict[str, Any]:
    members: dict[str, list[str]] = defaultdict(list)
    for record in records:
        value = record.get(field_name)
        if _is_present(value):
            members[str(value)].append(str(record.get("record_id")))
    cross_batch = 0
    for record_ids in members.values():
        if len({record_to_batch.get(rid) for rid in record_ids}) > 1:
            cross_batch += 1
    populated = sum(len(ids) for ids in members.values())
    return {
        "field": field_name,
        "records_with_value": populated,
        "distinct_groups": len(members),
        "multi_record_groups": sum(len(ids) > 1 for ids in members.values()),
        "cross_batch_violations": cross_batch,
        "verified": cross_batch == 0 and populated > 0,
        "coverage": "present" if populated else "unavailable",
    }


@dataclass
class AnnotationPackageReview:
    pipeline_version: str = PIPELINE_VERSION
    candidate_number: int = 1
    candidate1_checksum: str | None = None
    candidate1_preserved: bool | None = None
    candidate1_artifact_integrity: dict[str, Any] = field(default_factory=dict)
    sample_plan_path: str = ""
    sample_plan_checksum: str = ""
    annotation_manifest_path: str = ""
    annotation_manifest_checksum: str = ""
    batch_manifest_path: str = ""
    batch_manifest_checksum: str = ""
    total_records: int = 0
    unique_record_ids: int = 0
    duplicate_record_ids: list[str] = field(default_factory=list)
    source_distribution: dict[str, int] = field(default_factory=dict)
    region_distribution: dict[str, int] = field(default_factory=dict)
    bank_distribution: dict[str, int] = field(default_factory=dict)
    year_distribution: dict[str, int] = field(default_factory=dict)
    length_band_distribution: dict[str, int] = field(default_factory=dict)
    context_availability: dict[str, int] = field(default_factory=dict)
    context_experiment_status: str = ""
    review_id_integrity: dict[str, Any] = field(default_factory=dict)
    v2_rule_distribution: dict[str, int] = field(default_factory=dict)
    duplicate_group_integrity: dict[str, Any] = field(default_factory=dict)
    leakage_group_integrity: dict[str, Any] = field(default_factory=dict)
    review_group_integrity: dict[str, Any] = field(default_factory=dict)
    thread_group_integrity: dict[str, Any] = field(default_factory=dict)
    conversation_group_integrity: dict[str, Any] = field(default_factory=dict)
    missing_text_count: int = 0
    invalid_privacy_status_count: int = 0
    prefilled_primary_intent_count: int = 0
    prefilled_public_warning_count: int = 0
    non_empty_opinions_count: int = 0
    non_not_started_status_count: int = 0
    batch_distribution: dict[str, Any] = field(default_factory=dict)
    calibration_diversity: dict[str, Any] = field(default_factory=dict)
    review_issues: list[str] = field(default_factory=list)
    recommendation: str = "NOT_READY_FOR_RESEARCHER_APPROVAL"
    reviewed_at: str = ""
    reviewer: str | None = None
    git_commit: str = NO_COMMIT_MARKER

    def __post_init__(self) -> None:
        if self.recommendation not in RECOMMENDATIONS:
            raise ValueError(
                "review recommendation must be one of " + ", ".join(RECOMMENDATIONS)
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnnotationPackageReview":
        if not isinstance(data, dict):
            raise PackageIntegrityError("review report must be a JSON object")
        known = cls.__dataclass_fields__
        return cls(**{name: data[name] for name in known if name in data})


def build_package_review(
    *,
    sample_plan_path: str | Path,
    annotation_records_path: str | Path,
    sample_plan_manifest_path: str | Path,
    annotation_manifest_path: str | Path,
    batch_manifest_path: str | Path,
    batch_directory: str | Path,
    reviewer: str | None = None,
    candidate_number: int = 1,
    candidate1_path: str | Path | None = None,
    expected_candidate1_checksum: str | None = None,
) -> AnnotationPackageReview:
    """Inspect current candidate files and return review evidence only."""
    sample_path = Path(sample_plan_path)
    annotation_path = Path(annotation_records_path)
    plan_manifest = _read_json(sample_plan_manifest_path)
    annotation_manifest = _read_json(annotation_manifest_path)
    batch_path = Path(batch_manifest_path)
    batch_manifest = _read_json(batch_path)
    plan = load_jsonl_dicts(sample_path)
    records = load_jsonl_dicts(annotation_path)

    review = AnnotationPackageReview(
        candidate_number=candidate_number,
        sample_plan_path=str(sample_path),
        sample_plan_checksum=sha256_file(sample_path),
        annotation_manifest_path=str(annotation_manifest_path),
        annotation_manifest_checksum=sha256_file(annotation_manifest_path),
        batch_manifest_path=str(batch_path),
        batch_manifest_checksum=sha256_file(batch_path),
        total_records=len(records),
        reviewer=reviewer,
        reviewed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=git_commit(),
    )

    ids = [str(r.get("record_id")) for r in records]
    counts = Counter(ids)
    review.unique_record_ids = len(counts)
    review.duplicate_record_ids = sorted(rid for rid, count in counts.items() if count > 1)
    review.source_distribution = _distribution(records, "source")
    review.region_distribution = _distribution(records, "region")
    review.bank_distribution = _distribution(records, "bank")
    review.year_distribution = _distribution(records, "publish_year")
    review.context_availability = _distribution(records, "context_available")
    review.context_experiment_status = (
        "AVAILABLE" if any(record.get("context_available") is True for record in records)
        else "BLOCKED_NO_VERIFIED_CONTEXT_DATA; package remains eligible for no-context annotation"
    )
    review.missing_text_count = sum(
        not isinstance(r.get("text"), str) or not r["text"].strip() for r in records
    )
    review.invalid_privacy_status_count = sum(
        r.get("privacy_status") not in PRIVACY_STATUSES for r in records
    )
    review.prefilled_primary_intent_count = sum(
        r.get("primary_intent") is not None for r in records
    )
    review.prefilled_public_warning_count = sum(
        r.get("public_warning") is not None for r in records
    )
    review.non_empty_opinions_count = sum(bool(r.get("opinions")) for r in records)
    review.non_not_started_status_count = sum(
        r.get("annotation_status") != "not_started" for r in records
    )

    plan_by_id = {str(r.get("record_id")): r for r in plan}
    review.length_band_distribution = dict(sorted(Counter(
        _selection_reason_band(r.get("selection_reason")) for r in plan
    ).items()))
    review.v2_rule_distribution = dict(sorted(Counter(
        f"{r.get('source')}:{_selection_reason_rule(r.get('selection_reason'))}"
        for r in plan
    ).items()))

    batch_files = batch_manifest.get("output_paths", {})
    issues: list[str] = []
    record_to_batch: dict[str, str] = {}
    batch_record_ids: list[str] = []
    batch_distribution: dict[str, Any] = {}
    directory = Path(batch_directory)
    expected_batch_ids = set(batch_manifest.get("batch_ids", []))
    for batch_id, _batch_type, expected_size in BATCH_SPECS:
        path_from_manifest = batch_files.get(batch_id)
        batch_file = Path(path_from_manifest) if path_from_manifest else directory / f"{batch_id}.jsonl"
        batch_records = load_jsonl_dicts(batch_file) if batch_file.is_file() else []
        for record in batch_records:
            record_id = str(record.get("record_id"))
            batch_record_ids.append(record_id)
            record_to_batch[record_id] = batch_id
        batch_distribution[batch_id] = {
            "batch_type": dict((name, kind) for name, kind, _size in BATCH_SPECS)[batch_id],
            "record_count": len(batch_records),
            "expected_record_count": expected_size,
            "source_distribution": _distribution(batch_records, "source"),
            "region_distribution": _distribution(batch_records, "region"),
            "context_availability": _distribution(batch_records, "context_available"),
            "sha256": sha256_file(batch_file) if batch_file.is_file() else None,
            "manifest_checksum_matches": (
                sha256_file(batch_file) == batch_manifest.get("checksums", {}).get(batch_id)
                if batch_file.is_file() else False
            ),
        }
    review.batch_distribution = batch_distribution
    package_ids = {str(record.get("record_id")) for record in records}
    if len(batch_record_ids) != len(set(batch_record_ids)):
        issues.append("one or more canonical IDs occur in multiple batch files")
    if set(batch_record_ids) != package_ids or len(batch_record_ids) != len(records):
        issues.append("batch files do not contain every package record exactly once")

    group_result = {
        field_name: _group_integrity(records, field_name, record_to_batch)
        for field_name in GROUP_FIELDS
    }
    if candidate_number == 2:
        duplicate_summary = plan_manifest.get("duplicate_group_summary", {})
        observed_duplicate_members = sum(_is_present(record.get("duplicate_group")) for record in records)
        if (
            duplicate_summary.get("records_with_group") == observed_duplicate_members
            and duplicate_summary.get("records_with_group") == 0
            and duplicate_summary.get("source_near_duplicate_groups_observed") == 0
            and duplicate_summary.get("exact_normalized_text_duplicate_groups") == 0
        ):
            group_result["duplicate_group"].update(
                {"verified": True, "coverage": "verified_none", "evidence": "candidate-2 source join verified no selected duplicate groups"}
            )
    review.duplicate_group_integrity = group_result["duplicate_group"]
    review.leakage_group_integrity = group_result["leakage_group"]
    review.review_group_integrity = group_result["review_id"]
    review.review_id_integrity = dict(group_result["review_id"])
    review.review_id_integrity["review_records"] = sum(
        record.get("source") == INTERNATIONAL_REVIEW for record in records
    )
    review.review_id_integrity["review_records_with_id"] = sum(
        record.get("source") == INTERNATIONAL_REVIEW and _is_present(record.get("review_id"))
        for record in records
    )
    review.thread_group_integrity = group_result["thread_id"]
    review.conversation_group_integrity = group_result["conversation_id"]

    calibration_ids = {
        str(r.get("record_id"))
        for r in load_jsonl_dicts(directory / "calibration_001.jsonl")
    } if (directory / "calibration_001.jsonl").is_file() else set()
    calibration_plan = [plan_by_id[rid] for rid in calibration_ids if rid in plan_by_id]
    review.calibration_diversity = {
        "record_count": len(calibration_plan),
        "source_distribution": dict(sorted(Counter(str(r.get("source")) for r in calibration_plan).items())),
        "region_distribution": dict(sorted(Counter(str(r.get("region")) for r in calibration_plan).items())),
        "length_band_distribution": dict(sorted(Counter(_selection_reason_band(r.get("selection_reason")) for r in calibration_plan).items())),
        "context_availability": dict(sorted(Counter(str(r.get("context_available")) for r in calibration_plan).items())),
        "bank_distribution": dict(sorted(Counter(str(r.get("bank")) for r in calibration_plan).items())),
        "v2_rule_distribution": dict(sorted(Counter(_selection_reason_rule(r.get("selection_reason")) for r in calibration_plan).items())),
    }

    if review.total_records != TOTAL_TARGET:
        issues.append(f"annotation record count is {review.total_records}, expected {TOTAL_TARGET}")
    if review.unique_record_ids != review.total_records or review.duplicate_record_ids:
        issues.append("canonical record IDs are duplicated or not unique")
    if review.source_distribution != dict(sorted(SOURCE_TARGETS.items())):
        issues.append("source allocation does not match 500/250/250")
    if review.region_distribution != dict(sorted(REGION_TARGETS.items())):
        issues.append("regional allocation does not match 500/500")
    if review.missing_text_count:
        issues.append(f"{review.missing_text_count} records have missing or blank text")
    if review.invalid_privacy_status_count:
        issues.append(f"{review.invalid_privacy_status_count} records have invalid privacy status")
    if review.prefilled_primary_intent_count or review.prefilled_public_warning_count or review.non_empty_opinions_count:
        issues.append("one or more annotation task-label fields are prefilled")
    if review.non_not_started_status_count:
        issues.append("one or more records have annotation_status other than not_started")
    if annotation_manifest.get("pipeline_version") != PIPELINE_VERSION:
        issues.append("annotation manifest pipeline_version mismatch")
    if annotation_manifest.get("output_checksum") != sha256_file(annotation_path):
        issues.append("annotation manifest output checksum does not match current records")
    if annotation_manifest.get("input_sample_plan_checksum") != sha256_file(sample_path):
        issues.append("annotation manifest sample-plan checksum does not match current plan")
    if plan_manifest.get("plan_output_sha256") != sha256_file(sample_path):
        issues.append("sample-plan manifest checksum does not match current sample plan")
    if batch_manifest.get("pipeline_version") != PIPELINE_VERSION:
        issues.append("batch manifest pipeline_version mismatch")
    if batch_manifest.get("total_records") != TOTAL_TARGET or batch_manifest.get("total_batches") != len(BATCH_SPECS):
        issues.append("batch manifest totals do not match the canonical 11-batch plan")
    if batch_distribution.get("calibration_001", {}).get("record_count") != 50:
        issues.append("calibration batch does not contain exactly 50 records")
    if len(review.calibration_diversity.get("source_distribution", {})) < 2:
        issues.append("calibration batch does not demonstrate multi-source diversity")
    for batch_id in expected_batch_ids:
        info = batch_distribution.get(batch_id)
        if not info or info["record_count"] != info["expected_record_count"] or not info["manifest_checksum_matches"]:
            issues.append(f"batch {batch_id} missing, wrong-sized, or checksum-mismatched")
    if not group_result["duplicate_group"]["verified"] or not group_result["leakage_group"]["verified"]:
        issues.append("duplicate/leakage group integrity is unverified or violated")
    south_africa_rules = {
        _selection_reason_rule(r.get("selection_reason"))
        for r in plan
        if r.get("source") == SOUTH_AFRICA_TWEET
    }
    available_rules = south_africa_rules.intersection({"A", "B", "C", "D", "E", "F"})
    review.v2_rule_distribution = dict(sorted(Counter(
        _selection_reason_rule(r.get("selection_reason"))
        for r in plan if r.get("source") == SOUTH_AFRICA_TWEET
    ).items()))
    if available_rules != {"A", "B", "C", "D", "E", "F"}:
        issues.append("South African v2-rule coverage does not include all six rules")
    missing_review_ids = [
        str(r.get("record_id")) for r in records
        if r.get("source") == INTERNATIONAL_REVIEW and not _is_present(r.get("review_id"))
    ]
    if missing_review_ids:
        issues.append(f"{len(missing_review_ids)} international reviews lack deterministic review_id values")
    invalid_bank_values = {"review", "unknown", "all_banks", "all banks", "none", "null", "n/a", "na"}
    invalid_banks_present = {
        str(record.get("bank")).strip()
        for record in records
        if isinstance(record.get("bank"), str)
        and record.get("bank").strip().lower() in invalid_bank_values
    }
    if invalid_banks_present:
        issues.append("bank metadata contains invalid placeholder value(s): " + ", ".join(sorted(invalid_banks_present)))
    homogeneous_main = [
        batch_id
        for batch_id, data in batch_distribution.items()
        if data["batch_type"] in {"main", "final"}
        and len(data["source_distribution"]) <= 1
    ]
    if homogeneous_main:
        issues.append(
            "source-homogeneous main/final batches require review: "
            + ", ".join(homogeneous_main)
        )
    if any(_canonical_id_mismatch(r) for r in records):
        issues.append("one or more canonical record IDs do not match source::<source_record_id>")
    if candidate_number == 2:
        source_targets = batch_manifest.get("source_targets", {})
        source_observed = batch_manifest.get("source_observed", {})
        explanations = batch_manifest.get("grouping_balance_explanations", {})
        deviations = batch_manifest.get("source_deviations", {})
        if not source_targets or not source_observed:
            issues.append("candidate-2 batch manifest omits source targets or observed distributions")
        for batch_id, targets in source_targets.items():
            observed = source_observed.get(batch_id, {})
            actual = batch_distribution.get(batch_id, {}).get("source_distribution", {})
            normalized_actual = {source: actual.get(source, 0) for source in targets}
            normalized_observed = {source: observed.get(source, 0) for source in targets}
            if normalized_actual != normalized_observed:
                issues.append(f"candidate-2 batch {batch_id} source counts disagree with manifest")
        for batch_id, delta in deviations.items():
            if delta and not explanations.get(batch_id):
                issues.append(f"candidate-2 batch {batch_id} has unexplained source deviation")
        if candidate1_path is not None:
            first_candidate_path = Path(candidate1_path)
            if not first_candidate_path.is_file():
                issues.append("candidate-1 comparison package is unavailable")
            else:
                review.candidate1_checksum = sha256_file(first_candidate_path)
                review.candidate1_preserved = (
                    expected_candidate1_checksum is None
                    or review.candidate1_checksum == expected_candidate1_checksum
                )
                if not review.candidate1_preserved:
                    issues.append("candidate-1 checksum does not match expected preserved checksum")
                protected_checksums = plan_manifest.get("candidate1_artifact_checksums", {})
                checked_artifacts: dict[str, Any] = {}
                for artifact_path, expected_checksum in protected_checksums.items():
                    artifact = Path(artifact_path)
                    exists = artifact.is_file()
                    observed_checksum = sha256_file(artifact) if exists else None
                    checked_artifacts[artifact_path] = {
                        "exists": exists,
                        "expected_checksum": expected_checksum,
                        "observed_checksum": observed_checksum,
                        "matches": exists and observed_checksum == expected_checksum,
                    }
                review.candidate1_artifact_integrity = checked_artifacts
                all_preserved = bool(checked_artifacts) and all(item["matches"] for item in checked_artifacts.values())
                review.candidate1_preserved = bool(review.candidate1_preserved and all_preserved)
                if not all_preserved:
                    issues.append("one or more protected candidate-1 artifacts are missing or checksum-changed")

    review.review_issues = issues
    review.recommendation = (
        "READY_FOR_RESEARCHER_APPROVAL" if not issues else "NOT_READY_FOR_RESEARCHER_APPROVAL"
    )
    return review


def _canonical_id_mismatch(record: dict[str, Any]) -> bool:
    source = record.get("source")
    source_record_id = record.get("source_record_id")
    return not isinstance(source, str) or not isinstance(source_record_id, str) or record.get("record_id") != f"{source}::{source_record_id}"


def validate_review_for_approval(review: AnnotationPackageReview) -> list[str]:
    issues = list(review.review_issues)
    if review.pipeline_version != PIPELINE_VERSION:
        issues.append("review report pipeline_version mismatch")
    if review.recommendation != "READY_FOR_RESEARCHER_APPROVAL":
        issues.append("review recommendation is not READY_FOR_RESEARCHER_APPROVAL")
    if review.total_records != TOTAL_TARGET or review.unique_record_ids != TOTAL_TARGET:
        issues.append("review report does not establish exactly 1,000 unique records")
    if review.duplicate_record_ids:
        issues.append("review report records duplicate canonical IDs")
    if review.source_distribution != dict(sorted(SOURCE_TARGETS.items())):
        issues.append("review report source allocation mismatch")
    if review.region_distribution != dict(sorted(REGION_TARGETS.items())):
        issues.append("review report regional allocation mismatch")
    if any((review.prefilled_primary_intent_count, review.prefilled_public_warning_count, review.non_empty_opinions_count, review.non_not_started_status_count, review.invalid_privacy_status_count, review.missing_text_count)):
        issues.append("review report records package integrity or label-hiding failures")
    if not review.duplicate_group_integrity.get("verified") or not review.leakage_group_integrity.get("verified"):
        issues.append("duplicate/leakage group integrity is not verified")
    return sorted(set(issues))


def write_review_json(review: AnnotationPackageReview, path: str | Path, *, overwrite: bool = False) -> Path:
    """Write a machine-readable review record atomically; never approve/freeze."""
    import os
    import tempfile

    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite review report without permission: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(review.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if Path(temp_name).exists():
            Path(temp_name).unlink()
    return target


def render_review_markdown(review: AnnotationPackageReview) -> str:
    """Render human-readable evidence without implying researcher approval."""
    protected = review.candidate1_artifact_integrity
    preserved_count = sum(bool(item.get("matches")) for item in protected.values())
    group_rows = [
        ("duplicate_group", review.duplicate_group_integrity),
        ("leakage_group", review.leakage_group_integrity),
        ("review_id", review.review_id_integrity),
        ("thread_id", review.thread_group_integrity),
        ("conversation_id", review.conversation_group_integrity),
    ]
    lines = [
        f"# Candidate {review.candidate_number} annotation-package review",
        "",
        f"- Recommendation: **{review.recommendation}**",
        f"- Pipeline version: `{review.pipeline_version}`",
        f"- Records / unique IDs: {review.total_records} / {review.unique_record_ids}",
        f"- Source distribution: `{review.source_distribution}`",
        f"- Region distribution: `{review.region_distribution}`",
        f"- Context experiment status: {review.context_experiment_status}",
        f"- Context-available records: {review.context_availability.get('True', 0)}",
        f"- Candidate-1 preserved: **{review.candidate1_preserved}** "
        f"({preserved_count}/{len(protected)} artifact checksums match)",
        "",
        "## Checksums",
        "",
        f"- Sample plan: `{review.sample_plan_checksum}`",
        f"- Annotation package manifest: `{review.annotation_manifest_checksum}`",
        f"- Batch manifest: `{review.batch_manifest_checksum}`",
        "",
        "## Source, group, and batch evidence",
        "",
        f"- Bank distribution: `{review.bank_distribution}`",
        f"- Invalid privacy status records: {review.invalid_privacy_status_count}",
        f"- Missing/blank text records: {review.missing_text_count}",
        f"- Prefilled labels: intent={review.prefilled_primary_intent_count}, "
        f"public_warning={review.prefilled_public_warning_count}, "
        f"non-empty opinions={review.non_empty_opinions_count}",
        f"- Records not `not_started`: {review.non_not_started_status_count}",
        f"- v2 rule distribution (sampling provenance only): `{review.v2_rule_distribution}`",
        "",
        "| Linkage field | Coverage | Records with value | Groups | Cross-batch violations | Verified |",
        "|---|---|---:|---:|---:|---|",
    ]
    for field_name, evidence in group_rows:
        lines.append(
            f"| {field_name} | {evidence.get('coverage', 'unavailable')} "
            f"| {evidence.get('records_with_value', 0)} | {evidence.get('distinct_groups', 0)} "
            f"| {evidence.get('cross_batch_violations', 0)} | {evidence.get('verified', False)} |"
        )
    lines.extend([
        "",
        f"- International reviews with deterministic review IDs: "
        f"{review.review_id_integrity.get('review_records_with_id', 0)}/"
        f"{review.review_id_integrity.get('review_records', 0)}",
        "- Calibration diversity: "
        f"`{review.calibration_diversity.get('source_distribution', {})}`; "
        f"context `{review.calibration_diversity.get('context_availability', {})}`",
        "",
        "| Batch | Type | Records | Source distribution | Region distribution | SHA-256 matches |",
        "|---|---|---:|---|---|---|",
    ])
    for batch_id, evidence in review.batch_distribution.items():
        lines.append(
            f"| {batch_id} | {evidence.get('batch_type')} | {evidence.get('record_count')} "
            f"| `{evidence.get('source_distribution', {})}` "
            f"| `{evidence.get('region_distribution', {})}` "
            f"| {evidence.get('manifest_checksum_matches', False)} |"
        )
    lines.extend([
        "## Issues requiring resolution or researcher consideration",
        "",
    ])
    if not review.review_issues:
        lines.append("- None reported by automated static checks.")
    lines.extend([
        "",
        "This report is evidence only. A READY recommendation is not approval; "
        "approval and identity freeze require separate explicit researcher actions.",
        "",
    ])
    return "\n".join(lines)


def write_review_markdown(review: AnnotationPackageReview, path: str | Path, *, overwrite: bool = False) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite review Markdown without permission: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = render_review_markdown(review).encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        if Path(temporary_name).exists():
            Path(temporary_name).unlink()
    return target
