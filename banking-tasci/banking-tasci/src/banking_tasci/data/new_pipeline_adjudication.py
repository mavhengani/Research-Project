"""Pure, label-neutral adjudication scaffolding for ``new_pipeline_v1``.

The module compares independently completed submissions and applies only
explicit human decisions. It never infers a label. Record output and the audit
trail are returned separately so adjudication metadata cannot pollute the
canonical annotation schema.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from . import new_pipeline_schema as schema
from .new_pipeline_annotation_validator import IMMUTABLE_FIELDS

ADJUDICABLE_FIELDS = ("primary_intent", "public_warning", "opinions", "annotation_notes")
CHOICES = {"a", "b", "new"}


class AdjudicationError(ValueError):
    """Raised when paired submissions or explicit decisions are inconsistent."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(records: list[dict[str, Any]]) -> str:
    payload = "".join(_canonical(record) + "\n" for record in sorted(records, key=lambda r: str(r.get("record_id", ""))))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _index(records: list[dict[str, Any]], annotator: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise AdjudicationError(f"annotator {annotator} has a missing/invalid record_id")
        if record_id in index:
            raise AdjudicationError(f"annotator {annotator} has duplicate record_id {record_id}")
        if record.get("annotation_status") != "completed":
            raise AdjudicationError(f"annotator {annotator} record {record_id} is not completed")
        if record.get("annotation_version") != schema.PIPELINE_VERSION:
            raise AdjudicationError(f"annotator {annotator} record {record_id} has the wrong annotation_version")
        parsed = schema.record_from_dict(record)
        errors = [item.rule_id for item in schema.validate_record(parsed) if item.severity == "error"]
        if errors:
            raise AdjudicationError(f"annotator {annotator} record {record_id} is invalid: {', '.join(errors)}")
        index[record_id] = record
    return index


def compare_submissions(
    annotator_a: list[dict[str, Any]], annotator_b: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return immutable-field failures, disagreements and stable input hashes."""
    a = _index(annotator_a, "A")
    b = _index(annotator_b, "B")
    if set(a) != set(b):
        missing_a = sorted(set(b) - set(a))
        missing_b = sorted(set(a) - set(b))
        raise AdjudicationError(f"annotator record IDs differ (missing from A={missing_a[:10]}, missing from B={missing_b[:10]})")

    disagreements: list[dict[str, Any]] = []
    immutable_mismatches: list[dict[str, str]] = []
    for record_id in sorted(a):
        left, right = a[record_id], b[record_id]
        for field in IMMUTABLE_FIELDS:
            if left.get(field) != right.get(field):
                immutable_mismatches.append({"record_id": record_id, "field": field})
        fields = {
            field: {"annotator_a": left.get(field), "annotator_b": right.get(field)}
            for field in ADJUDICABLE_FIELDS
            if left.get(field) != right.get(field)
        }
        if fields:
            disagreements.append({"record_id": record_id, "fields": fields})
    return {
        "pipeline_version": schema.PIPELINE_VERSION,
        "annotator_a_checksum": _checksum(annotator_a),
        "annotator_b_checksum": _checksum(annotator_b),
        "record_count": len(a),
        "disagreement_count": sum(len(row["fields"]) for row in disagreements),
        "records_with_disagreements": len(disagreements),
        "immutable_mismatches": immutable_mismatches,
        "disagreements": disagreements,
    }


def apply_adjudication(
    annotator_a: list[dict[str, Any]],
    annotator_b: list[dict[str, Any]],
    decisions: dict[str, dict[str, dict[str, Any]]],
    *,
    adjudicator: str,
) -> dict[str, Any]:
    """Apply explicit A/B/new decisions; unresolved items remain pending.

    ``decisions`` is keyed by record ID then disputed field. Each decision has
    ``choice`` and, for ``choice='new'``, ``value``. Every resolved field also
    requires a non-empty human rationale. No majority vote or model inference
    is used.
    """
    if not isinstance(adjudicator, str) or not adjudicator.strip():
        raise AdjudicationError("an explicit adjudicator identity is required")
    comparison = compare_submissions(annotator_a, annotator_b)
    if comparison["immutable_mismatches"]:
        raise AdjudicationError("immutable source fields differ between annotators")
    a = _index(annotator_a, "A")
    b = _index(annotator_b, "B")
    disagreement_fields = {
        row["record_id"]: set(row["fields"])
        for row in comparison["disagreements"]
    }
    extra_ids = set(decisions) - set(disagreement_fields)
    if extra_ids:
        raise AdjudicationError(f"decisions include records without disagreements: {sorted(extra_ids)[:10]}")

    outputs: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []
    for record_id in sorted(a):
        record = dict(a[record_id])
        fields = disagreement_fields.get(record_id, set())
        supplied = decisions.get(record_id, {})
        extra_fields = set(supplied) - fields
        if extra_fields:
            raise AdjudicationError(f"decisions for {record_id} include undisputed fields: {sorted(extra_fields)}")
        record_audit: dict[str, Any] = {"record_id": record_id, "fields": {}}
        for field in sorted(fields):
            decision = supplied.get(field)
            if decision is None:
                pending.append({"record_id": record_id, "field": field})
                continue
            choice = decision.get("choice")
            rationale = decision.get("rationale")
            if choice not in CHOICES:
                raise AdjudicationError(f"decision for {record_id}.{field} must choose a, b, or new")
            if not isinstance(rationale, str) or not rationale.strip():
                raise AdjudicationError(f"decision for {record_id}.{field} requires a human rationale")
            if choice == "a":
                final_value = a[record_id].get(field)
            elif choice == "b":
                final_value = b[record_id].get(field)
            else:
                if "value" not in decision:
                    raise AdjudicationError(f"decision for {record_id}.{field} chose new without a value")
                final_value = decision["value"]
            record[field] = final_value
            record_audit["fields"][field] = {
                "annotator_a": a[record_id].get(field),
                "annotator_b": b[record_id].get(field),
                "choice": choice,
                "final_value": final_value,
                "rationale": rationale.strip(),
                "adjudicator": adjudicator.strip(),
            }
        if fields and record_audit["fields"]:
            audit.append(record_audit)
        parsed = schema.record_from_dict(record)
        errors = [item.rule_id for item in schema.validate_record(parsed) if item.severity == "error"]
        if errors:
            raise AdjudicationError(f"adjudicated record {record_id} is invalid: {', '.join(errors)}")
        outputs.append(record)

    return {
        "pipeline_version": schema.PIPELINE_VERSION,
        "adjudicator": adjudicator.strip(),
        "input_comparison": comparison,
        "resolved_disagreement_fields": sum(len(item["fields"]) for item in audit),
        "pending_review": pending,
        "complete": not pending,
        "records": outputs if not pending else [],
        "audit_records": audit,
        "output_checksum": _checksum(outputs) if not pending else None,
    }
