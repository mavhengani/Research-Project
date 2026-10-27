"""Group-aware annotation batching and uniform manual annotation workflow.

``calibration_001`` remains the immutable technical ID for checksum
compatibility. Operationally it is Annotation Batch 1 and follows the same
human annotation workflow as the other ten files.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from banking_tasci.data.gold_sample_plan import REGION_TARGETS, SOURCE_TARGETS
from banking_tasci.data.manifest import NO_COMMIT_MARKER, git_commit

PIPELINE_VERSION = "new_pipeline_v1"
DEFAULT_SEED = 42
CALIBRATION_SIZE = 50
MAIN_BATCH_SIZE = 100
MAIN_BATCH_COUNT = 9
FINAL_BATCH_SIZE = 50
TOTAL_RECORDS = 1000
BATCH_SPECS = (
    ("calibration_001", "calibration", CALIBRATION_SIZE),
    *((f"main_{index:03d}", "main", MAIN_BATCH_SIZE) for index in range(1, 10)),
    ("final_001", "final", FINAL_BATCH_SIZE),
)
BATCH_STATUSES = (
    "generated", "in_progress", "completed", "validation_failed", "validated", "frozen"
)
GROUP_FIELDS = ("duplicate_group", "leakage_group", "review_id", "thread_id", "conversation_id")

__all__ = [
    "PIPELINE_VERSION", "DEFAULT_SEED", "BATCH_SPECS", "BATCH_STATUSES", "GROUP_FIELDS",
    "CALIBRATION_SIZE", "MAIN_BATCH_SIZE", "MAIN_BATCH_COUNT", "FINAL_BATCH_SIZE", "TOTAL_RECORDS",
    "BatchMetadata", "BatchAssignment", "compute_annotation_group_key", "group_components",
    "assign_batches", "build_batch_metadata", "build_combined_batch_manifest", "write_batches",
    "validate_submission", "next_incomplete_record", "transition_batch_status",
    "freeze_calibration_guide", "assert_main_annotation_allowed", "annotation_records_checksum",
    "update_batch_progress", "save_annotation_checkpoint", "batch_source_targets",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _present(value: Any) -> bool:
    return value is not None and str(value).strip().lower() not in {"", "nan", "none"}


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def compute_annotation_group_key(record: dict) -> str | None:
    """Return the first evidenced grouping key, for display only."""
    for name in GROUP_FIELDS:
        value = record.get(name)
        if _present(value):
            return f"{name}:{value}"
    return None


def group_components(records: list[dict]) -> list[list[int]]:
    """Return transitive connected groups across every shared grouping field."""
    dsu = _DisjointSet(len(records))
    first: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        for field_name in GROUP_FIELDS:
            value = record.get(field_name)
            if not _present(value):
                continue
            key = (field_name, str(value).strip())
            if key in first:
                dsu.union(index, first[key])
            else:
                first[key] = index
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        groups[dsu.find(index)].append(index)
    return list(groups.values())


def _hamilton_targets(totals: dict[str, int], sizes: list[tuple[str, int]]) -> dict[str, dict[str, int]]:
    """Allocate each observed global source total over batch sizes exactly."""
    total_records = sum(size for _, size in sizes)
    result = {name: {source: 0 for source in totals} for name, _ in sizes}
    for source, total in totals.items():
        quotas = {name: total * size / total_records for name, size in sizes}
        assigned = {name: int(value) for name, value in quotas.items()}
        remainder = total - sum(assigned.values())
        order = sorted(quotas, key=lambda name: (-(quotas[name] - assigned[name]), name))
        for name in order[:remainder]:
            assigned[name] += 1
        for name, count in assigned.items():
            result[name][source] = count
    return result


def batch_source_targets(batch_specs=BATCH_SPECS) -> dict[str, dict[str, int]]:
    """Canonical source quotas; integer rounding reconciles to 500/250/250."""
    if tuple(batch_specs) == BATCH_SPECS:
        targets = {
            "calibration_001": {
                "south_africa_tweet": 25,
                "international_tweet": 13,
                "international_review": 12,
            },
            **{
                f"main_{index:03d}": {
                    "south_africa_tweet": 50,
                    "international_tweet": 25,
                    "international_review": 25,
                }
                for index in range(1, 10)
            },
            "final_001": {
                "south_africa_tweet": 25,
                "international_tweet": 12,
                "international_review": 13,
            },
        }
        if any(sum(row.values()) != size for (name, _, size) in batch_specs for row in [targets[name]]):
            raise ValueError("canonical batch source quotas do not match batch capacities")
        if {source: sum(row[source] for row in targets.values()) for source in SOURCE_TARGETS} != SOURCE_TARGETS:
            raise ValueError("canonical batch source targets do not reconcile to 500/250/250")
        return targets
    sizes = [(name, size) for name, _, size in batch_specs]
    targets = _hamilton_targets(SOURCE_TARGETS, sizes)
    if {source: sum(row[source] for row in targets.values()) for source in SOURCE_TARGETS} != SOURCE_TARGETS:
        raise ValueError("batch source targets do not reconcile to canonical source totals")
    return targets


@dataclass
class BatchAssignment:
    batches: dict[str, list[int]] = field(default_factory=dict)
    oversized_groups: list[dict[str, Any]] = field(default_factory=list)
    unresolved_balancing_warnings: list[str] = field(default_factory=list)
    source_targets: dict[str, dict[str, int]] = field(default_factory=dict)
    source_observed: dict[str, dict[str, int]] = field(default_factory=dict)
    source_deviations: dict[str, dict[str, int]] = field(default_factory=dict)
    region_targets: dict[str, dict[str, int]] = field(default_factory=dict)
    region_observed: dict[str, dict[str, int]] = field(default_factory=dict)
    region_deviations: dict[str, dict[str, int]] = field(default_factory=dict)
    group_counts: dict[str, int] = field(default_factory=dict)
    group_constraint_summary: dict[str, dict[str, Any]] = field(default_factory=dict)
    grouping_balance_explanations: dict[str, str] = field(default_factory=dict)
    total_groups: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _source_counts(records: list[dict], indices: list[int]) -> dict[str, int]:
    sources = tuple(SOURCE_TARGETS)
    counts = {source: 0 for source in sources}
    for index in indices:
        source = records[index].get("source")
        if source not in counts:
            raise ValueError(f"unknown source {source!r} for record {records[index].get('record_id')}")
        counts[source] += 1
    return counts


def _region_counts(records: list[dict], indices: list[int]) -> dict[str, int]:
    counts = {region: 0 for region in REGION_TARGETS}
    for index in indices:
        region = records[index].get("region")
        if region not in counts:
            raise ValueError(f"unknown region {region!r} for record {records[index].get('record_id')}")
        counts[region] += 1
    return counts


def _assign_group_set(
    records: list[dict], components: list[list[int]], names: list[str], capacities: dict[str, int],
    targets: dict[str, dict[str, int]], observed: dict[str, dict[str, int]], seed: int,
) -> tuple[dict[str, list[int]], list[str]]:
    """Greedy best-fit placement: group integrity is hard, source target soft."""
    assignment = {name: [] for name in names}
    rng = np.random.Generator(np.random.PCG64(seed))
    random_tie = {id(group): int(rng.integers(0, 2**31 - 1)) for group in components}
    ordered = sorted(
        components,
        key=lambda group: (-len(group), random_tie[id(group)], tuple(sorted(str(records[i]["record_id"]) for i in group))),
    )
    warnings: list[str] = []
    for group in ordered:
        group_counts = _source_counts(records, group)
        candidates = [name for name in names if capacities[name] >= len(group)]
        if not candidates:
            ids = sorted(str(records[i]["record_id"]) for i in group)
            warnings.append(f"unplaced connected group size={len(group)} record_ids={ids[:8]}")
            continue

        def score(name: str) -> tuple[float, int, str]:
            delta = sum(
                (observed[name][source] + group_counts[source] - targets[name][source]) ** 2
                - (observed[name][source] - targets[name][source]) ** 2
                for source in targets[name]
            )
            remaining = capacities[name] - len(group)
            return (delta + remaining * 0.01, remaining, name)

        chosen = min(candidates, key=score)
        assignment[chosen].extend(group)
        capacities[chosen] -= len(group)
        for source, count in group_counts.items():
            observed[chosen][source] += count
    return assignment, warnings


def assign_batches(records: list[dict], *, seed: int = DEFAULT_SEED) -> BatchAssignment:
    """Create 11 fixed-size, deterministic batches without splitting groups.

    Canonical 500/250/250 source targets are reported for the actual sample.
    For small noncanonical fixtures, targets are proportionally allocated from
    the fixture's observed global totals so the public API remains reusable.
    """
    if len(records) != TOTAL_RECORDS:
        raise ValueError(f"assign_batches requires exactly {TOTAL_RECORDS} records, got {len(records)}")
    ids = [str(record.get("record_id", "")) for record in records]
    if any(not record_id for record_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("batch input must have non-empty, unique canonical record_id values")
    global_counts = _source_counts(records, list(range(len(records))))
    components = group_components(records)
    oversized = [group for group in components if len(group) > MAIN_BATCH_SIZE]
    if oversized:
        detail = [{"size": len(group), "record_ids": sorted(ids[i] for i in group)} for group in oversized]
        raise ValueError(f"annotation groups exceed largest batch capacity 100: {detail}")

    specs = [(name, size) for name, _, size in BATCH_SPECS]
    targets = batch_source_targets() if global_counts == SOURCE_TARGETS else _hamilton_targets(global_counts, specs)
    capacities = {name: size for name, size in specs}
    observed = {name: {source: 0 for source in SOURCE_TARGETS} for name, _ in specs}

    # Batch 1 retains its original stratified composition as a sampling
    # property only; it has no separate annotation methodology or gate.
    calibration_name = "calibration_001"
    remaining = list(components)
    calibration: list[list[int]] = []
    cal_counts = {source: 0 for source in SOURCE_TARGETS}
    cal_target = targets[calibration_name]
    cal_capacity = CALIBRATION_SIZE
    rng = np.random.Generator(np.random.PCG64(seed))
    tie_break = {id(group): int(rng.integers(0, 2**31 - 1)) for group in remaining}

    def stratum(group: list[int]) -> tuple[str, str, str, str]:
        record = records[group[0]]
        text_len = len(str(record.get("text") or ""))
        return (
            str(record.get("source")),
            "short" if text_len < 120 else "medium" if text_len < 240 else "long",
            str(record.get("bank")),
            str(bool(record.get("context_available"))),
        )

    seen_strata: Counter[tuple[str, str, str, str]] = Counter()
    chosen_groups: set[int] = set()
    while cal_capacity > 0:
        candidates = [group for group in remaining if len(group) <= cal_capacity]
        if not candidates:
            break

        def calibration_score(group: list[int]) -> tuple[float, int, int, str]:
            counts = _source_counts(records, group)
            quota_penalty = sum(
                max(0, cal_counts[source] + counts[source] - cal_target[source]) * 1000
                for source in SOURCE_TARGETS
            )
            delta = sum(
                (cal_counts[source] + counts[source] - cal_target[source]) ** 2
                - (cal_counts[source] - cal_target[source]) ** 2
                for source in SOURCE_TARGETS
            )
            return (quota_penalty + delta, seen_strata[stratum(group)], tie_break[id(group)], min(ids[i] for i in group))

        selected = min(candidates, key=calibration_score)
        calibration.append(selected)
        chosen_groups.add(id(selected))
        cal_capacity -= len(selected)
        for source, count in _source_counts(records, selected).items():
            cal_counts[source] += count
        seen_strata[stratum(selected)] += 1
        remaining.remove(selected)

    assignment: dict[str, list[int]] = {name: [] for name, _, _ in BATCH_SPECS}
    assignment[calibration_name] = [index for group in calibration for index in group]
    capacities[calibration_name] = cal_capacity
    observed[calibration_name] = cal_counts
    warnings: list[str] = []
    if cal_capacity:
        warnings.append(
            f"{calibration_name} target/size constraint: remaining capacity={cal_capacity}; "
            f"observed source={cal_counts}, target={cal_target}; connected groups were not split"
        )

    other_names = [name for name, _, _ in BATCH_SPECS if name != calibration_name]
    placed, placement_warnings = _assign_group_set(
        records, remaining, other_names, capacities, targets, observed, seed + 1
    )
    warnings.extend(placement_warnings)
    for name in other_names:
        assignment[name] = placed[name]
    unplaced_ids = set(range(len(records))) - {index for values in assignment.values() for index in values}
    if unplaced_ids or any(capacities.values()):
        detail = {name: value for name, value in capacities.items() if value}
        raise ValueError(
            "group-aware placement cannot satisfy exact batch sizes without splitting connected groups; "
            f"remaining capacities={detail}; unplaced={sorted(ids[i] for i in unplaced_ids)[:20]}; "
            f"warnings={warnings}"
        )

    # Preserve deterministic ID order inside each technical batch.
    for name in assignment:
        assignment[name].sort(key=lambda index: ids[index])

    source_observed = {name: _source_counts(records, indices) for name, indices in assignment.items()}
    source_deviations: dict[str, dict[str, int]] = {}
    region_targets: dict[str, dict[str, int]] = {}
    region_observed = {name: _region_counts(records, indices) for name, indices in assignment.items()}
    region_deviations: dict[str, dict[str, int]] = {}
    group_counts: dict[str, int] = {}
    group_constraint_summary: dict[str, dict[str, Any]] = {}
    explanations: dict[str, str] = {}
    record_component = {index: component_index for component_index, group in enumerate(components) for index in group}
    for name, _, size in BATCH_SPECS:
        target_regions = {
            "south_africa": targets[name].get("south_africa_tweet", 0),
            "international": targets[name].get("international_tweet", 0) + targets[name].get("international_review", 0),
        }
        region_targets[name] = target_regions
        source_delta = {
            source: source_observed[name][source] - targets[name][source]
            for source in SOURCE_TARGETS
            if source_observed[name][source] != targets[name][source]
        }
        region_delta = {
            region: region_observed[name][region] - target_regions[region]
            for region in REGION_TARGETS
            if region_observed[name][region] != target_regions[region]
        }
        if source_delta:
            source_deviations[name] = source_delta
        if region_delta:
            region_deviations[name] = region_delta
        group_counts[name] = len({record_component[index] for index in assignment[name]})
        batch_components = [group for group in components if group and record_component[group[0]] in {
            record_component[index] for index in assignment[name]
        }]
        group_constraint_summary[name] = {
            "multi_record_group_count": sum(len(group) > 1 for group in batch_components),
            "largest_group_size": max((len(group) for group in batch_components), default=0),
            "mixed_source_group_count": sum(len({records[index].get("source") for index in group}) > 1 for group in batch_components),
        }
        if source_delta or region_delta:
            constraints = group_constraint_summary[name]
            explanation = (
                "Observed allocation differs from target; no connected group was split. "
                f"Batch has {group_counts[name]} groups, {constraints['multi_record_group_count']} multi-record groups "
                f"(largest={constraints['largest_group_size']}), and {constraints['mixed_source_group_count']} mixed-source groups. "
                f"Deviations source={source_delta}, region={region_delta}."
            )
            if constraints["multi_record_group_count"] == 0:
                explanation += " No multi-record grouping constraint explains this miss; the deterministic placement heuristic requires review."
            explanations[name] = explanation
            warnings.append(f"{name}: {explanation}")

    return BatchAssignment(
        batches=assignment,
        unresolved_balancing_warnings=warnings,
        source_targets=targets,
        source_observed=source_observed,
        source_deviations=source_deviations,
        region_targets=region_targets,
        region_observed=region_observed,
        region_deviations=region_deviations,
        group_counts=group_counts,
        group_constraint_summary=group_constraint_summary,
        grouping_balance_explanations=explanations,
        total_groups=len(components),
    )


@dataclass
class BatchMetadata:
    batch_id: str
    batch_type: str
    record_count: int
    record_ids: list[str] = field(default_factory=list)
    checksum: str = ""
    checksum_algorithm: str = "jsonl_sha256"
    pipeline_version: str = PIPELINE_VERSION
    batch_status: str = "generated"
    annotation_guide_version: str | None = None
    created_at: str = field(default_factory=_utc_now)
    opened_at: str | None = None
    completed_at: str | None = None
    validated_at: str | None = None
    source_sample_manifest_checksum: str = ""
    source_distribution: dict[str, int] = field(default_factory=dict)
    region_distribution: dict[str, int] = field(default_factory=dict)
    group_count: int = 0
    source_target_distribution: dict[str, int] = field(default_factory=dict)
    source_deviation: dict[str, int] = field(default_factory=dict)
    region_target_distribution: dict[str, int] = field(default_factory=dict)
    region_deviation: dict[str, int] = field(default_factory=dict)
    constraint_warnings: list[str] = field(default_factory=list)
    balancing_explanation: str | None = None
    completed_record_count: int = 0
    output_path: str | None = None
    validation_result: str | None = None
    technical_batch_id: str = ""
    display_name: str = ""
    workflow_role: str = "standard_manual_annotation_batch"
    candidate_number: int = 2
    approved_membership_checksum: str = ""
    source_checksum: str = ""
    validated_record_count: int = 0
    failed_validation_count: int = 0
    remaining_record_count: int = 0
    workspace_version: int = 1
    last_updated_at: str | None = None
    last_updated_by: str | None = None

    def __post_init__(self) -> None:
        self.technical_batch_id = self.technical_batch_id or self.batch_id
        self.display_name = self.display_name or annotation_batch_display_name(self.batch_id)
        # batch_type is retained as a legacy technical field only. It does not
        # control annotation permissions or workflow methodology.
        self.workflow_role = "standard_manual_annotation_batch"
        self.source_checksum = self.source_checksum or self.checksum
        if self.remaining_record_count == 0 and self.completed_record_count == 0:
            self.remaining_record_count = self.record_count
        self.last_updated_at = self.last_updated_at or self.created_at

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def current_status(self) -> str:
        return self.batch_status

    @property
    def completed_count(self) -> int:
        return self.completed_record_count

    @property
    def validated_count(self) -> int:
        return self.validated_record_count


_ORDERED_BATCH_IDS = tuple(name for name, _kind, _size in BATCH_SPECS)


def annotation_batch_display_name(batch_id: str) -> str:
    """Human-facing numbering while retaining all frozen technical IDs."""
    try:
        position = _ORDERED_BATCH_IDS.index(batch_id) + 1
    except ValueError as exc:
        raise ValueError(f"unknown technical annotation batch ID: {batch_id}") from exc
    return f"Annotation Batch {position}"


def operational_batch_metadata(
    batch_id: str,
    *,
    record_count: int,
    source_checksum: str,
    candidate_number: int,
    pipeline_version: str,
    approved_membership_checksum: str,
    current_status: str = "generated",
    completed_count: int = 0,
    validated_count: int = 0,
    failed_validation_count: int = 0,
    guide_version: str | None = None,
    last_updated_at: str | None = None,
    last_updated_by: str | None = None,
) -> BatchMetadata:
    """Build metadata for any approved batch under one standard workflow."""
    expected_size = dict((name, size) for name, _kind, size in BATCH_SPECS).get(batch_id)
    if expected_size is None or record_count != expected_size:
        raise ValueError(f"{batch_id} must have its approved record count ({expected_size})")
    if candidate_number != 2 or pipeline_version != PIPELINE_VERSION:
        raise ValueError("manual annotation is restricted to approved Candidate 2 new_pipeline_v1")
    if not source_checksum or not approved_membership_checksum:
        raise ValueError("source and approved-membership checksums are required")
    return BatchMetadata(
        batch_id=batch_id,
        technical_batch_id=batch_id,
        display_name=annotation_batch_display_name(batch_id),
        workflow_role="standard_manual_annotation_batch",
        batch_type="legacy_technical_type",
        record_count=record_count,
        checksum=source_checksum,
        source_checksum=source_checksum,
        candidate_number=candidate_number,
        pipeline_version=pipeline_version,
        approved_membership_checksum=approved_membership_checksum,
        batch_status=current_status,
        completed_record_count=completed_count,
        validated_record_count=validated_count,
        failed_validation_count=failed_validation_count,
        remaining_record_count=record_count - completed_count,
        annotation_guide_version=guide_version,
        last_updated_at=last_updated_at or _utc_now(),
        last_updated_by=last_updated_by,
    )


def _jsonl_bytes(records: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def annotation_records_checksum(records: list[dict]) -> str:
    return hashlib.sha256(_jsonl_bytes(records)).hexdigest()


def build_batch_metadata(
    batch_id: str,
    batch_type: str,
    records: list[dict],
    *,
    source_sample_manifest_checksum: str = "",
    group_count: int | None = None,
    source_target_distribution: dict[str, int] | None = None,
    source_deviation: dict[str, int] | None = None,
    region_target_distribution: dict[str, int] | None = None,
    region_deviation: dict[str, int] | None = None,
    constraint_warnings: list[str] | None = None,
    balancing_explanation: str | None = None,
) -> BatchMetadata:
    ids = [str(record.get("record_id", "")) for record in records]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"batch {batch_id} must contain unique, non-empty record IDs")
    groups = group_components(records)
    return BatchMetadata(
        batch_id=batch_id,
        batch_type=batch_type,
        record_count=len(records),
        record_ids=sorted(ids),
        checksum=annotation_records_checksum(records),
        source_sample_manifest_checksum=source_sample_manifest_checksum,
        source_distribution=dict(sorted(Counter(str(r.get("source")) for r in records).items())),
        region_distribution=dict(sorted(Counter(str(r.get("region")) for r in records).items())),
        group_count=len(groups) if group_count is None else group_count,
        source_target_distribution=dict(source_target_distribution or {}),
        source_deviation=dict(source_deviation or {}),
        region_target_distribution=dict(region_target_distribution or {}),
        region_deviation=dict(region_deviation or {}),
        constraint_warnings=list(constraint_warnings or []),
        balancing_explanation=balancing_explanation,
    )


def build_combined_batch_manifest(
    metadatas: list[BatchMetadata],
    assignment: BatchAssignment,
    *,
    creation_command: str = "",
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    by_id = {metadata.batch_id: metadata for metadata in metadatas}
    expected_ids = [name for name, _, _ in BATCH_SPECS]
    return {
        "pipeline_version": PIPELINE_VERSION,
        "git_commit": git_commit() or NO_COMMIT_MARKER,
        "seed": seed,
        "creation_command": creation_command,
        "generated_at": _utc_now(),
        "total_records": sum(item.record_count for item in metadatas),
        "total_batches": len(metadatas),
        "batch_ids": [name for name in expected_ids if name in by_id],
        "batch_sizes": {item.batch_id: item.record_count for item in metadatas},
        "output_paths": {item.batch_id: item.output_path for item in metadatas if item.output_path},
        "checksums": {item.batch_id: item.checksum for item in metadatas},
        "checksum_algorithms": {item.batch_id: item.checksum_algorithm for item in metadatas},
        "batches": {item.batch_id: item.to_dict() for item in metadatas},
        "source_targets": assignment.source_targets,
        "source_observed": assignment.source_observed,
        "source_deviations": assignment.source_deviations,
        "region_targets": assignment.region_targets,
        "region_observed": assignment.region_observed,
        "region_deviations": assignment.region_deviations,
        "group_counts": assignment.group_counts,
        "group_constraint_summary": assignment.group_constraint_summary,
        "total_groups": assignment.total_groups,
        "unresolved_balancing_warnings": assignment.unresolved_balancing_warnings,
        "grouping_balance_explanations": assignment.grouping_balance_explanations,
    }


def write_batches(
    batches: dict[str, list[dict]], output_dir: str | Path, *, overwrite: bool = False
) -> dict[str, Path]:
    """Atomically replace each JSONL batch; refuse existing outputs by default."""
    target_dir = Path(output_dir)
    expected_names = [name for name, _, _ in BATCH_SPECS]
    if set(batches) != set(expected_names):
        raise ValueError("write_batches requires exactly the canonical 11 batch IDs")
    expected_sizes = {name: size for name, _, size in BATCH_SPECS}
    for name, records in batches.items():
        if len(records) != expected_sizes[name]:
            raise ValueError(f"{name} has {len(records)} records; expected {expected_sizes[name]}")
        ids = [str(record.get("record_id", "")) for record in records]
        if any(not rid for rid in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"{name} contains missing or duplicate record IDs")
    existing = [target_dir / f"{name}.jsonl" for name in expected_names if (target_dir / f"{name}.jsonl").exists()]
    if existing and not overwrite:
        raise FileExistsError("refusing to overwrite existing batch file(s): " + ", ".join(map(str, existing)))
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name in expected_names:
        path = target_dir / f"{name}.jsonl"
        fd, temporary_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=target_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_jsonl_bytes(batches[name]))
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists() and not overwrite:
                raise FileExistsError(f"refusing to overwrite existing batch file: {path}")
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        paths[name] = path
    return paths


def _approval_is_valid(approval: dict | None) -> bool:
    return bool(
        approval
        and approval.get("approval_status") == "APPROVED"
        and approval.get("pipeline_version") == PIPELINE_VERSION
    )


def assert_main_annotation_allowed(*, approval: dict | None, calibration_metadata: BatchMetadata) -> None:
    """Deprecated compatibility check; approval applies uniformly to all batches."""
    warnings.warn(
        "assert_main_annotation_allowed is deprecated; use validate_annotation_start",
        DeprecationWarning,
        stacklevel=2,
    )
    validate_annotation_start(approval=approval)


def validate_annotation_start(*, approval: dict | None) -> None:
    """Apply the same approved-package gate to every annotation batch."""
    if not _approval_is_valid(approval):
        raise ValueError("an APPROVED Candidate 2 package is required before annotation can start")


def transition_batch_status(
    metadata: BatchMetadata,
    new_status: str,
    *,
    approval: dict | None = None,
    calibration_metadata: BatchMetadata | None = None,
    validation_passed: bool | None = None,
) -> BatchMetadata:
    if new_status not in BATCH_STATUSES:
        raise ValueError(f"unapproved batch status {new_status!r}")
    if new_status == "in_progress":
        # Legacy calibration_metadata is accepted for compatibility but never
        # controls today's uniform methodology.
        if calibration_metadata is not None:
            warnings.warn(
                "calibration_metadata is a deprecated technical argument and is ignored",
                DeprecationWarning,
                stacklevel=2,
            )
        validate_annotation_start(approval=approval)
        if metadata.batch_status not in {"generated", "validation_failed"}:
            raise ValueError(f"cannot transition {metadata.batch_status} to in_progress")
        metadata.batch_status = new_status
        metadata.opened_at = metadata.opened_at or _utc_now()
        metadata.last_updated_at = _utc_now()
        metadata.last_updated_by = metadata.last_updated_by or "researcher"
    elif new_status == "completed":
        if metadata.batch_status != "in_progress":
            raise ValueError("only an in-progress batch can be completed")
        if metadata.completed_record_count != metadata.record_count:
            raise ValueError("completed records are required for every batch record before batch completion")
        metadata.batch_status = new_status
        metadata.completed_at = _utc_now()
        metadata.last_updated_at = metadata.completed_at
    elif new_status == "validated":
        if metadata.batch_status != "completed":
            raise ValueError("only a completed batch can be validated")
        if validation_passed is not True:
            raise ValueError("validation_passed=True is required to mark a batch validated")
        metadata.batch_status = new_status
        metadata.validated_at = _utc_now()
        metadata.validation_result = "passed"
        metadata.validated_record_count = metadata.record_count
        metadata.last_updated_at = metadata.validated_at
    elif new_status == "validation_failed":
        if metadata.batch_status != "completed":
            raise ValueError("only a completed batch can fail validation")
        if validation_passed is True:
            raise ValueError("validation_passed=True cannot be used for validation_failed")
        metadata.batch_status = new_status
        metadata.validation_result = "failed"
        metadata.failed_validation_count += 1
        metadata.last_updated_at = _utc_now()
    elif new_status == "frozen":
        if metadata.batch_status != "validated":
            raise ValueError("only a validated annotation batch can be frozen")
        metadata.batch_status = "frozen"
        metadata.last_updated_at = _utc_now()
    else:
        raise ValueError(f"unsupported status transition {metadata.batch_status} -> {new_status}")
    return metadata


def freeze_calibration_guide(
    metadata: BatchMetadata, *, guide_version: str, approval: dict | None = None
) -> BatchMetadata:
    warnings.warn(
        "freeze_calibration_guide is deprecated; guide versions apply uniformly and batch status is unchanged",
        DeprecationWarning,
        stacklevel=2,
    )
    validate_annotation_start(approval=approval)
    if not isinstance(guide_version, str) or not guide_version.strip():
        raise ValueError("guide_version must be non-empty")
    metadata.annotation_guide_version = guide_version.strip()
    metadata.last_updated_at = _utc_now()
    metadata.last_updated_by = metadata.last_updated_by or "researcher"
    return metadata


def validate_submission(metadata: BatchMetadata, submitted_records: list[dict]) -> list[str]:
    issues: list[str] = []
    submitted_ids = [str(record.get("record_id", "")) for record in submitted_records]
    counts = Counter(submitted_ids)
    duplicates = sorted(record_id for record_id, count in counts.items() if count > 1)
    if duplicates:
        issues.append("duplicate record IDs in submission: " + ", ".join(duplicates[:10]))
    expected = set(metadata.record_ids)
    actual = set(submitted_ids)
    foreign = sorted(actual - expected)
    missing = sorted(expected - actual)
    if foreign:
        issues.append("records do not belong to this batch: " + ", ".join(foreign[:10]))
    if missing:
        issues.append("missing batch records: " + ", ".join(missing[:10]))
    if any(record.get("annotation_version") != metadata.pipeline_version for record in submitted_records):
        issues.append("annotation_version does not match the batch pipeline version")
    if metadata.checksum and annotation_records_checksum(submitted_records) != metadata.checksum:
        issues.append("submission checksum does not match original batch checksum")
    return issues


def update_batch_progress(metadata: BatchMetadata, submitted_records: list[dict]) -> BatchMetadata:
    issues = validate_submission(metadata, submitted_records)
    membership_or_version = [issue for issue in issues if "checksum" not in issue]
    if membership_or_version:
        raise ValueError("invalid batch progress submission: " + "; ".join(membership_or_version))
    metadata.completed_record_count = sum(
        record.get("annotation_status") == "completed" for record in submitted_records
    )
    metadata.remaining_record_count = metadata.record_count - metadata.completed_record_count
    metadata.last_updated_at = _utc_now()
    return metadata


def next_incomplete_record(records: list[dict]) -> dict | None:
    for record in records:
        if record.get("annotation_status") != "completed":
            return record
    return None


def save_annotation_checkpoint(
    metadata: BatchMetadata,
    records: list[dict],
    path: str | Path,
    *,
    expected_existing_checksum: str | None = None,
    backup_path: str | Path | None = None,
) -> str:
    if metadata.batch_status != "in_progress":
        raise ValueError("annotation checkpoint can be saved only for an in-progress batch")
    issues = validate_submission(metadata, records)
    blocking = [issue for issue in issues if "checksum" not in issue]
    if blocking:
        raise ValueError("invalid annotation checkpoint: " + "; ".join(blocking))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _jsonl_bytes(records)
    digest = hashlib.sha256(payload).hexdigest()
    if target.exists():
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_existing_checksum is None:
            raise FileExistsError(f"checkpoint exists; explicit observed checksum required: {target}")
        if current != expected_existing_checksum:
            raise ValueError("checkpoint checksum changed since it was observed")
        if backup_path is not None:
            backup = Path(backup_path)
            if backup.exists():
                raise FileExistsError(f"checkpoint backup already exists: {backup}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return digest