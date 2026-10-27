"""Workflow validation for immutable ``new_pipeline_v1`` annotation records.

The schema validator checks an individual record.  This module adds the
annotation-workflow checks that require the original label-hidden package:
status semantics, immutable source fields, approved batch membership and
privacy.  Aggregate reports deliberately contain IDs and rule codes only.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import new_pipeline_schema as schema

IMMUTABLE_FIELDS = (
    "record_id", "source_record_id", "source", "region", "bank", "review_id",
    "thread_id", "conversation_id", "publish_year", "text", "previous_text",
    "context_available", "duplicate_group", "leakage_group",
)
VALID_STATUSES = {"label_hidden", "not_started", "in_progress", "completed", "validation_failed", "validated", "frozen"}


def _sha_ids(ids: list[str]) -> str:
    return hashlib.sha256("".join(f"{rid}\n" for rid in sorted(ids)).encode()).hexdigest()


def _issue(record_id: str, rule_id: str, message: str, guidance: str) -> dict[str, Any]:
    return {"record_id": record_id, "rule_id": rule_id, "severity": "error", "message": message,
            "fix_guidance": guidance}


def _group_linkage_issues(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Require every evidenced duplicate/review/thread link to share a leakage group."""
    group_fields = ("duplicate_group", "review_id", "thread_id", "conversation_id")
    linked: dict[tuple[str, str], list[tuple[str, str | None]]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    for record in records:
        rid = str(record.get("record_id", "<unknown>"))
        leakage = record.get("leakage_group")
        leakage_key = str(leakage).strip() if leakage is not None and str(leakage).strip() else None
        for field in group_fields:
            value = record.get(field)
            if value is None or not str(value).strip():
                continue
            if leakage_key is None:
                issues.append(_issue(
                    rid,
                    "group_link_missing_leakage_group",
                    f"Record has a {field} link but no leakage_group.",
                    "Assign linked records to a stable leakage_group so the relation cannot cross data partitions.",
                ))
            linked[(field, str(value))].append((rid, leakage_key))

    for (field, _value), members in linked.items():
        leakage_groups = {group for _, group in members}
        if len(members) > 1 and len(leakage_groups) > 1:
            for rid, _ in members:
                issues.append(_issue(
                    rid,
                    "linked_records_leakage_group_mismatch",
                    f"Records sharing {field} are assigned to different leakage groups.",
                    "Use one shared leakage_group for every record linked by the same duplicate, review, thread, or conversation identifier.",
                ))
    return issues


def validate_records(
    submitted: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    batch_membership: dict[str, set[str]] | None = None,
    *,
    completed_gold: bool = False,
) -> dict[str, Any]:
    """Validate submitted records without modifying them.

    ``source_records`` is the immutable, label-hidden package.  A completed
    gold submission may contain labels, while a label-hidden/not-started file
    remains valid annotation input but is not valid completed gold data.
    """
    source_by_id = {str(r.get("record_id")): r for r in source_records}
    expected_batch = {rid: name for name, ids in (batch_membership or {}).items() for rid in ids}
    # Check linkage over the complete approved package, not just the submitted
    # batch: linked records may otherwise be split across separate submissions.
    issues: list[dict[str, Any]] = _group_linkage_issues(source_records)
    warnings: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    valid = 0
    for raw in submitted:
        rid = str(raw.get("record_id", "<unknown>"))
        seen[rid] += 1
        local: list[dict[str, Any]] = []
        status = raw.get("annotation_status")
        if status not in VALID_STATUSES:
            local.append(_issue(rid, "status_not_allowed", "annotation_status is not a workflow status.", "Use an approved status."))
        if raw.get("annotation_version") != schema.PIPELINE_VERSION:
            local.append(_issue(rid, "annotation_version_unsupported", "annotation_version is not new_pipeline_v1.", "Use the current pipeline version."))
        original = source_by_id.get(rid)
        if original is None:
            local.append(_issue(rid, "source_record_unknown", "record_id is absent from the approved source package.", "Submit only approved batch records."))
        else:
            for field in IMMUTABLE_FIELDS:
                if raw.get(field) != original.get(field):
                    local.append(_issue(rid, "immutable_source_field_changed", f"Immutable field '{field}' differs from source package.", "Restore the source value; labels may be edited but provenance may not."))
            if raw.get("privacy_status") not in {"anonymised", "not_required"}:
                local.append(_issue(rid, "privacy_requirement_failed", "Record is not cleared for annotation privacy handling.", "Use the approved anonymised/not_required privacy status."))
        if expected_batch and rid not in expected_batch:
            local.append(_issue(rid, "batch_membership_missing", "record_id is absent from approved batch membership.", "Use the assigned batch only."))
        # schema validation covers span offsets, taxonomy, labels, zero/multi opinions.
        rec = schema.record_from_dict(raw)
        for issue in schema.validate_record(rec):
            if issue.severity == "error":
                local.append(issue.to_dict())
            elif issue.severity == "warning":
                warnings.append(issue.to_dict())
        hidden = (raw.get("primary_intent") is None and raw.get("public_warning") is None and raw.get("opinions") == [])
        if completed_gold and (status != "completed" or hidden):
            local.append(_issue(rid, "completed_gold_required", "A completed-gold validation requires completed records with labels.", "Complete labels before submitting as gold data."))
        if status == "completed" and raw.get("public_warning") is None:
            local.append(_issue(rid, "completed_without_public_warning", "Completed record has null public_warning.", "Set public_warning to true or false."))
        issues.extend(local)
        valid += not local
    for rid, count in seen.items():
        if count > 1:
            issues.append(_issue(rid, "duplicate_record_id", f"record_id occurs {count} times.", "Keep exactly one record per immutable record_id."))
            valid -= count
    if completed_gold:
        submitted_ids = set(seen)
        for rid in sorted(set(source_by_id) - submitted_ids):
            issues.append(_issue(
                rid,
                "completed_gold_record_missing",
                "Approved source record is missing from the completed-gold submission.",
                "Include every approved source record exactly once in completed gold data.",
            ))
            valid -= 1
    affected: dict[str, list[str]] = defaultdict(list)
    for item in issues:
        if item["record_id"] not in affected[item["rule_id"]]:
            affected[item["rule_id"]].append(item["record_id"])
    affected_warnings: dict[str, list[str]] = defaultdict(list)
    for item in warnings:
        if item["record_id"] not in affected_warnings[item["rule_id"]]:
            affected_warnings[item["rule_id"]].append(item["record_id"])
    return {
        "pipeline_version": schema.PIPELINE_VERSION,
        "submitted_count": len(submitted), "valid_count": max(valid, 0), "invalid_count": len({x["record_id"] for x in issues}),
        "error_count": len(issues), "warning_count": len(warnings),
        "completed_gold_required": completed_gold, "submitted_id_set_checksum": _sha_ids([str(x.get("record_id")) for x in submitted]),
        "errors_by_code": dict(Counter(x["rule_id"] for x in issues)),
        "warnings_by_code": dict(Counter(x["rule_id"] for x in warnings)),
        "affected_record_ids": dict(affected), "affected_warning_record_ids": dict(affected_warnings),
        "issues": issues, "warnings": warnings,
        "result": "PASS" if not issues else "FAIL",
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = ["# New-pipeline annotation validation report", "", f"Result: **{report['result']}**", "",
             f"Submitted: {report['submitted_count']}", f"Valid: {report['valid_count']}", f"Invalid: {report['invalid_count']}",
             f"Errors: {report.get('error_count', len(report.get('issues', [])))}",
             f"Warnings: {report.get('warning_count', len(report.get('warnings', [])))}", "",
             "## Error codes", "", "| Code | Count |", "| --- | ---: |"]
    lines += [f"| {code} | {count} |" for code, count in sorted(report["errors_by_code"].items())]
    lines += ["", "## Warning codes", "", "| Code | Count |", "| --- | ---: |"]
    lines += [f"| {code} | {count} |" for code, count in sorted(report.get("warnings_by_code", {}).items())]
    lines += ["", "Reports contain record IDs and correction guidance only; they do not contain customer text."]
    return "\n".join(lines) + "\n"


def read_raw_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
