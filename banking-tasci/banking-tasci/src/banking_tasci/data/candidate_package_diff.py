"""Canonical-ID comparison and lineage reporting for annotation candidates."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

__all__ = ["CandidatePackageDiffError", "compare_candidate_packages", "candidate_file_sha256"]


class CandidatePackageDiffError(ValueError):
    """Raised when candidate identity evidence is incomplete or ambiguous."""


def candidate_file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _by_id(records: list[dict[str, Any]], candidate_name: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise CandidatePackageDiffError(f"{candidate_name} has a missing canonical record_id")
        if record_id in output:
            raise CandidatePackageDiffError(f"{candidate_name} has duplicate record_id {record_id}")
        output[record_id] = record
    return output


def _distribution(records: dict[str, dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(record.get(field)) for record in records.values())
    return dict(sorted(counts.items()))


def _batch_map(batches: dict[str, list[dict[str, Any]]] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for batch_id, records in (batches or {}).items():
        for record in records:
            record_id = str(record.get("record_id", ""))
            if not record_id:
                raise CandidatePackageDiffError(f"batch {batch_id} contains a missing record_id")
            if record_id in mapping:
                raise CandidatePackageDiffError(f"record {record_id} occurs in multiple batches")
            mapping[record_id] = batch_id
    return mapping


def _batch_distributions(batches: dict[str, list[dict[str, Any]]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for batch_id, records in sorted((batches or {}).items()):
        source = Counter(str(record.get("source")) for record in records)
        region = Counter(str(record.get("region")) for record in records)
        result[batch_id] = {
            "record_count": len(records),
            "source_distribution": dict(sorted(source.items())),
            "region_distribution": dict(sorted(region.items())),
        }
    return result


def compare_candidate_packages(
    candidate1_records: list[dict[str, Any]],
    candidate2_records: list[dict[str, Any]],
    *,
    candidate1_checksum: str,
    candidate2_checksum: str,
    candidate1_batches: dict[str, list[dict[str, Any]]] | None = None,
    candidate2_batches: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Compare package records by canonical ID, never by row position."""
    first = _by_id(candidate1_records, "candidate 1")
    second = _by_id(candidate2_records, "candidate 2")
    first_ids, second_ids = set(first), set(second)
    retained = sorted(first_ids & second_ids)
    added = sorted(second_ids - first_ids)
    removed = sorted(first_ids - second_ids)
    changes: dict[str, dict[str, dict[str, Any]]] = {}
    for record_id in retained:
        fields = sorted(set(first[record_id]) | set(second[record_id]))
        field_changes = {
            field: {"candidate_1": first[record_id].get(field), "candidate_2": second[record_id].get(field)}
            for field in fields
            if first[record_id].get(field) != second[record_id].get(field)
        }
        if field_changes:
            changes[record_id] = field_changes

    changed_ids = sorted(changes)
    bank_changes = {
        record_id: change["bank"]
        for record_id, fields in changes.items()
        if "bank" in fields
        for change in [fields]
    }
    review_id_changes = {
        record_id: fields["review_id"]
        for record_id, fields in changes.items()
        if "review_id" in fields
    }
    field_sets = {
        field: sorted(record_id for record_id, fields in changes.items() if field in fields)
        for field in sorted({field for fields in changes.values() for field in fields})
    }
    first_batches = _batch_map(candidate1_batches)
    second_batches = _batch_map(candidate2_batches)
    common_batch_ids = sorted(set(first_batches) & set(second_batches))
    batch_membership_changes = {
        record_id: {"candidate_1": first_batches[record_id], "candidate_2": second_batches[record_id]}
        for record_id in common_batch_ids
        if first_batches[record_id] != second_batches[record_id]
    }

    return {
        "candidate_1_checksum": candidate1_checksum,
        "candidate_2_checksum": candidate2_checksum,
        "comparison_key": "record_id",
        "records_retained": len(retained),
        "records_added": len(added),
        "records_removed": len(removed),
        "retained_record_ids": retained,
        "added_record_ids": added,
        "removed_record_ids": removed,
        "changed_canonical_ids": changed_ids,
        "changed_metadata_fields": field_sets,
        "record_field_changes": changes,
        "bank_corrections": bank_changes,
        "review_id_changes": review_id_changes,
        "rule_provenance_additions": field_sets.get("selection_reason", []),
        "duplicate_group_changes": field_sets.get("duplicate_group", []),
        "leakage_group_changes": field_sets.get("leakage_group", []),
        "context_changes": {
            field: field_sets.get(field, []) for field in ("previous_text", "context_available")
        },
        "batch_membership_changes": batch_membership_changes,
        "candidate_1_source_distribution": _distribution(first, "source"),
        "candidate_2_source_distribution": _distribution(second, "source"),
        "candidate_1_region_distribution": _distribution(first, "region"),
        "candidate_2_region_distribution": _distribution(second, "region"),
        "candidate_1_batch_distribution": _batch_distributions(candidate1_batches),
        "candidate_2_batch_distribution": _batch_distributions(candidate2_batches),
    }