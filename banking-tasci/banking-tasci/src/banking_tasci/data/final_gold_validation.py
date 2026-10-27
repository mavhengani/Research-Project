"""Read-only integrity validation for completed uniform Candidate 2 gold batches."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .annotation_batches import BATCH_SPECS, PIPELINE_VERSION
from .manifest import sha256_file
from .new_pipeline_annotation_validator import report_markdown, validate_records


class FinalGoldValidationError(ValueError):
    """Raised when frozen package provenance cannot be established."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalGoldValidationError(f"cannot read governance JSON: {path}") from exc
    if not isinstance(data, dict):
        raise FinalGoldValidationError(f"governance JSON must be an object: {path}")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalGoldValidationError(f"cannot read JSONL: {path}") from exc
    if any(not isinstance(row, dict) for row in values):
        raise FinalGoldValidationError(f"JSONL must contain only objects: {path}")
    return values


def validate_final_gold(
    *,
    records: list[dict[str, Any]],
    approved_package: list[dict[str, Any]],
    batch_manifest: dict[str, Any],
    approved_membership: list[dict[str, Any]],
    frozen_ids: list[dict[str, Any]],
    freeze_manifest: dict[str, Any],
    source_checksums: dict[str, str],
) -> dict[str, Any]:
    """Validate the full 1,000 records without changing inputs or making a split."""
    issues: list[dict[str, Any]] = []
    expected_batch_ids = [name for name, _kind, _size in BATCH_SPECS]
    expected_sizes = {name: size for name, _kind, size in BATCH_SPECS}
    record_ids = [str(row.get("record_id", "")) for row in records]
    approved_ids = [str(row.get("record_id", "")) for row in approved_package]
    frozen_id_set = {str(row.get("record_id", "")) for row in frozen_ids}
    if freeze_manifest.get("immutable_status") != "FROZEN" or freeze_manifest.get("candidate_number") != 2:
        raise FinalGoldValidationError("Freeze Revision 2 Candidate 2 is not the active frozen identity authority")
    if freeze_manifest.get("pipeline_version") != PIPELINE_VERSION:
        raise FinalGoldValidationError("freeze pipeline_version mismatch")
    if len(frozen_id_set) != 1000 or len(frozen_ids) != 1000:
        raise FinalGoldValidationError("frozen ID file must contain exactly 1,000 unique IDs")
    if len(record_ids) != 1000 or len(set(record_ids)) != 1000:
        issues.append({"rule_id": "gold_record_count_or_duplicate_id", "severity": "error", "record_ids": sorted(set(record_ids))[:50]})
    if set(record_ids) != frozen_id_set:
        issues.append({"rule_id": "gold_ids_do_not_match_freeze", "severity": "error", "record_ids": sorted(set(record_ids) ^ frozen_id_set)[:100]})
    if set(approved_ids) != frozen_id_set or len(approved_ids) != 1000:
        raise FinalGoldValidationError("approved label-hidden package IDs do not match frozen identities")

    by_id = {str(row.get("record_id")): row for row in records}
    approved_by_id = {str(row.get("record_id")): row for row in approved_package}
    membership_by_batch: dict[str, set[str]] = {batch_id: set() for batch_id in expected_batch_ids}
    membership_owner: dict[str, list[str]] = {}
    for entry in approved_membership:
        rid, batch_id = str(entry.get("record_id", "")), entry.get("batch_id")
        if batch_id not in membership_by_batch:
            issues.append({"rule_id": "unknown_technical_batch_id", "severity": "error", "record_ids": [rid]})
            continue
        membership_by_batch[batch_id].add(rid)
        membership_owner.setdefault(rid, []).append(batch_id)
    for batch_id in expected_batch_ids:
        ids = membership_by_batch[batch_id]
        if len(ids) != expected_sizes[batch_id]:
            issues.append({"rule_id": "approved_batch_size_mismatch", "severity": "error", "batch_id": batch_id, "expected": expected_sizes[batch_id], "observed": len(ids)})
    repeated = sorted(rid for rid, owners in membership_owner.items() if len(owners) != 1)
    if repeated:
        issues.append({"rule_id": "approved_batch_membership_duplicate", "severity": "error", "record_ids": repeated[:100]})
    if set(membership_owner) != frozen_id_set:
        issues.append({"rule_id": "approved_membership_set_mismatch", "severity": "error", "record_ids": sorted(set(membership_owner) ^ frozen_id_set)[:100]})

    immutable_fields = (
        "record_id", "source_record_id", "source", "region", "bank", "review_id", "thread_id",
        "conversation_id", "publish_year", "text", "previous_text", "context_available",
        "duplicate_group", "leakage_group", "privacy_status",
    )
    changed_immutable: list[str] = []
    for rid in sorted(set(by_id) & set(approved_by_id)):
        if any(by_id[rid].get(field) != approved_by_id[rid].get(field) for field in immutable_fields):
            changed_immutable.append(rid)
    if changed_immutable:
        issues.append({"rule_id": "immutable_source_field_changed", "severity": "error", "record_ids": changed_immutable})

    schema_report = validate_records(
        records,
        approved_package,
        membership_by_batch,
        completed_gold=True,
    )
    if schema_report["result"] != "PASS":
        issues.extend({
            "rule_id": item["rule_id"], "severity": item["severity"],
            "record_ids": [item["record_id"]], "message": item["message"],
            "fix_guidance": item["fix_guidance"],
        } for item in schema_report["issues"])

    observed_sources = dict(sorted(Counter(str(row.get("source")) for row in records).items()))
    expected_sources = freeze_manifest.get("source_distribution", {})
    if observed_sources != expected_sources:
        issues.append({"rule_id": "gold_source_allocation_mismatch", "severity": "error", "record_ids": []})
    for row in records:
        if row.get("annotation_status") != "completed":
            issues.append({"rule_id": "record_not_completed", "severity": "error", "record_ids": [str(row.get("record_id"))]})

    group_summaries: dict[str, Any] = {}
    for key in ("duplicate_group", "review_id", "thread_id", "conversation_id", "leakage_group"):
        groups: dict[str, set[str]] = {}
        for row in records:
            value = row.get(key)
            if value is not None and str(value).strip():
                groups.setdefault(str(value), set()).add(str(row.get("record_id")))
        group_summaries[key] = {"observed_groups": len(groups), "linked_record_count": sum(map(len, groups.values()))}

    error_count = sum(issue["severity"] == "error" for issue in issues)
    return {
        "pipeline_version": PIPELINE_VERSION,
        "candidate_number": 2,
        "result": "PASS" if error_count == 0 else "FAIL",
        "record_count": len(records),
        "unique_record_count": len(set(record_ids)),
        "completed_count": sum(row.get("annotation_status") == "completed" for row in records),
        "validated_count": len(records) if error_count == 0 else 0,
        "error_count": error_count,
        "warning_count": schema_report.get("warning_count", 0),
        "errors_by_code": dict(Counter(issue["rule_id"] for issue in issues)),
        "affected_record_ids": {code: sorted({rid for issue in issues if issue["rule_id"] == code for rid in issue.get("record_ids", [])}) for code in sorted({issue["rule_id"] for issue in issues})},
        "warnings_by_code": schema_report.get("warnings_by_code", {}),
        "affected_warning_record_ids": schema_report.get("affected_warning_record_ids", {}),
        "source_distribution": observed_sources,
        "batch_counts": {name: len(membership_by_batch[name]) for name in expected_batch_ids},
        "group_summaries": group_summaries,
        "completed_gold_id_checksum": hashlib.sha256("".join(f"{rid}\n" for rid in sorted(record_ids)).encode()).hexdigest(),
        "records_checksum": hashlib.sha256("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in records).encode()).hexdigest(),
        "schema_validation": schema_report,
        "issues": issues,
        "split_created": False,
        "training_started": False,
    }


def validate_final_gold_files(
    *, input_path: str | Path, project_root: str | Path,
    batch_manifest_path: str | Path, membership_path: str | Path,
    frozen_ids_path: str | Path, freeze_manifest_path: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    input_file = Path(input_path)
    if not input_file.is_absolute():
        input_file = root / input_file
    batch_file, membership_file = Path(batch_manifest_path), Path(membership_path)
    ids_file, freeze_file = Path(frozen_ids_path), Path(freeze_manifest_path)
    paths = [input_file, batch_file, membership_file, ids_file, freeze_file]
    if not all(path.is_file() for path in paths):
        missing = [str(path) for path in paths if not path.is_file()]
        raise FinalGoldValidationError("required final-gold input missing: " + ", ".join(missing))
    freeze = _read_json(freeze_file)
    if freeze.get("batch_manifest_checksum") != sha256_file(batch_file):
        raise FinalGoldValidationError("batch manifest checksum differs from Freeze Revision 2")
    if freeze.get("approved_batch_manifest", {}).get("membership_checksum") != sha256_file(membership_file):
        raise FinalGoldValidationError("approved membership checksum differs from Freeze Revision 2")
    if freeze.get("gold_id_checksum") != sha256_file(ids_file):
        raise FinalGoldValidationError("frozen ID checksum differs from Freeze Revision 2")
    manifest = _read_json(batch_file)
    membership = _read_jsonl(membership_file)
    assigned: dict[str, set[str]] = {}
    for entry in membership:
        assigned.setdefault(str(entry.get("batch_id")), set()).add(str(entry.get("record_id")))
    for batch_id, _kind, expected_count in BATCH_SPECS:
        output_path = Path(manifest.get("output_paths", {}).get(batch_id, ""))
        if not output_path.is_absolute():
            output_path = root / output_path
        expected_sha = manifest.get("checksums", {}).get(batch_id)
        if not output_path.is_file() or not isinstance(expected_sha, str) or sha256_file(output_path) != expected_sha:
            raise FinalGoldValidationError(f"approved batch file checksum mismatch: {batch_id}")
        batch_rows = _read_jsonl(output_path)
        batch_ids = [str(row.get("record_id", "")) for row in batch_rows]
        if len(batch_rows) != expected_count or set(batch_ids) != assigned.get(batch_id, set()) or len(set(batch_ids)) != expected_count:
            raise FinalGoldValidationError(f"approved batch membership mismatch: {batch_id}")
    return validate_final_gold(
        records=_read_jsonl(input_file),
        approved_package=_read_jsonl(root / "data/annotations/new_pipeline_v1_candidate_2/annotation_records.jsonl"),
        batch_manifest=_read_json(batch_file),
        approved_membership=_read_jsonl(membership_file),
        frozen_ids=_read_jsonl(ids_file),
        freeze_manifest=freeze,
        source_checksums={"batch_manifest": sha256_file(batch_file), "membership": sha256_file(membership_file), "frozen_ids": sha256_file(ids_file)},
    )


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Final Gold Validation (read-only)", "",
        f"Result: **{report['result']}**", "",
        f"Records: {report['record_count']}",
        f"Completed: {report['completed_count']}",
        f"Errors: {report['error_count']}",
        f"Warnings: {report['warning_count']}",
        "", "## Batch counts", "", "| Technical ID | Records |", "|---|---:|",
    ]
    lines.extend(f"| {batch_id} | {count} |" for batch_id, count in report["batch_counts"].items())
    lines.extend(["", "No split was created and no model was trained."])
    return "\n".join(lines) + "\n"
