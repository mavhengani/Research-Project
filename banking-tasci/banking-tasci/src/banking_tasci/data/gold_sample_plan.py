"""Canonical combined gold sample-plan builder for `new_pipeline_v1`.

Implements Requirements Sections 7 and 13 at the combination layer: the
**single, canonical 1,000-record combined sample plan** formed from the two
already-VERIFIED dry-run samplers:

- ``banking_tasci.data.south_africa_sampler`` (500 South African tweets)
- ``banking_tasci.data.international_sampler`` (250 international tweets +
  250 international reviews)

This module does not re-implement sampling. It invokes both samplers'
deterministic selection functions, assigns a canonical, namespaced
``record_id`` to every selected record, preserves the original identifier as
``source_record_id``, and asserts the exact counts the requirements document
specifies. No new record is created and no record is dropped: the combined
plan is exactly the union of what the two samplers already selected.

Two distinct views are produced:

``plan records`` (written to ``gold_sample_plan.jsonl``)
    Carry ``selection_reason`` and every preserved provenance field
    (Requirements Section 10, points 10-14). This file is sampling/selection
    provenance, not the annotator-facing file.

``annotation records`` (written to ``annotation_records.jsonl`` by a later,
explicitly-flagged step)
    Exactly the Section 11 field set. ``selection_reason`` and every other
    sampling-only field are absent - candidate rule, rating, stratum, and
    selection reasons may appear in the separate selection manifest, never as
    prefilled gold task labels.

Scope guard: this module never selects records itself. It is a combination
and validation layer over the two already-tested samplers.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from banking_tasci.data.international_sampler import (
    DEFAULT_SEED,
    REVIEW_SOURCE,
    TWEET_SOURCE,
)
from banking_tasci.data.international_sampler import (
    build_selection_manifest as _build_international_manifest,
)
from banking_tasci.data.international_sampler import sample_international
from banking_tasci.data.international_sampler import (
    to_label_hidden_records as _international_label_hidden_records,
)
from banking_tasci.data.manifest import NO_COMMIT_MARKER, git_commit
from banking_tasci.data.south_africa_sampler import SOUTH_AFRICA_SOURCE
from banking_tasci.data.south_africa_sampler import (
    build_selection_manifest as _build_south_africa_manifest,
)
from banking_tasci.data.south_africa_sampler import sample_south_africa
from banking_tasci.data.south_africa_sampler import (
    to_label_hidden_records as _south_africa_label_hidden_records,
)

__all__ = [
    "PIPELINE_VERSION",
    "DEFAULT_SEED",
    "SOUTH_AFRICA_TWEET",
    "INTERNATIONAL_TWEET",
    "INTERNATIONAL_REVIEW",
    "SOURCE_TARGETS",
    "REGION_TARGETS",
    "TOTAL_TARGET",
    "PLAN_RECORD_FIELDS",
    "ANNOTATION_RECORD_FIELDS",
    "GoldSamplePlanReport",
    "build_combined_sample_plan",
    "to_annotation_records",
    "build_gold_sample_plan_manifest",
    "write_jsonl",
]

PIPELINE_VERSION = "new_pipeline_v1"

# Requirements Section 10: canonical, configuration-driven source values.
SOUTH_AFRICA_TWEET = "south_africa_tweet"
INTERNATIONAL_TWEET = "international_tweet"
INTERNATIONAL_REVIEW = "international_review"

SOURCE_TARGETS: dict[str, int] = {
    SOUTH_AFRICA_TWEET: 500,
    INTERNATIONAL_TWEET: 250,
    INTERNATIONAL_REVIEW: 250,
}
REGION_TARGETS: dict[str, int] = {
    "south_africa": 500,
    "international": 500,
}
TOTAL_TARGET = sum(SOURCE_TARGETS.values())

_ORIGINAL_TO_CANONICAL_SOURCE: dict[str, str] = {
    SOUTH_AFRICA_SOURCE: SOUTH_AFRICA_TWEET,
    TWEET_SOURCE: INTERNATIONAL_TWEET,
    REVIEW_SOURCE: INTERNATIONAL_REVIEW,
}

_CANONICAL_TO_REGION: dict[str, str] = {
    SOUTH_AFRICA_TWEET: "south_africa",
    INTERNATIONAL_TWEET: "international",
    INTERNATIONAL_REVIEW: "international",
}

# Selection-provenance fields (gold_sample_plan.jsonl). Deliberately excludes
# every task-label field; this file carries no opinions/intent either, since
# it is a selection record, not an annotation record.
PLAN_RECORD_FIELDS: tuple[str, ...] = (
    "record_id",
    "source_record_id",
    "source",
    "region",
    "bank",
    "review_id",
    "thread_id",
    "conversation_id",
    "publish_year",
    "text",
    "previous_text",
    "context_available",
    "duplicate_group",
    "leakage_group",
    "privacy_status",
    "selection_reason",
)

# Annotator-facing fields (annotation_records.jsonl): Requirements Section 11
# record structure, plus the explicitly-listed `source_record_id`.
# `selection_reason` is NOT present here - it may live in the selection
# manifest only, never as a prefilled gold task label.
ANNOTATION_RECORD_FIELDS: tuple[str, ...] = (
    "record_id",
    "source_record_id",
    "source",
    "region",
    "bank",
    "review_id",
    "thread_id",
    "conversation_id",
    "publish_year",
    "text",
    "previous_text",
    "context_available",
    "duplicate_group",
    "leakage_group",
    "privacy_status",
    "primary_intent",
    "public_warning",
    "opinions",
    "annotation_status",
    "annotation_version",
    "annotation_notes",
)


@dataclass
class GoldSamplePlanReport:
    """The combined gold sample-plan manifest (Requirements Section 17)."""

    pipeline_version: str = PIPELINE_VERSION
    seed: int = DEFAULT_SEED
    generated_at: str = ""
    git_commit: str = NO_COMMIT_MARKER
    total: int = 0
    unique_record_count: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_region: dict[str, int] = field(default_factory=dict)
    cross_source_collision_count: int = 0
    grouping_coverage: dict[str, Any] = field(default_factory=dict)
    privacy_status_distribution: dict[str, int] = field(default_factory=dict)
    south_africa_source_file: str = ""
    south_africa_source_sha256: str = ""
    international_source_file: str = ""
    international_source_sha256: str = ""
    south_africa_selection_manifest: dict[str, Any] = field(default_factory=dict)
    international_selection_manifest: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _canonical_source_for(original_source: Any) -> str:
    try:
        return _ORIGINAL_TO_CANONICAL_SOURCE[original_source]
    except KeyError as exc:
        raise ValueError(
            f"unrecognised original source value '{original_source}'; expected one "
            f"of {sorted(_ORIGINAL_TO_CANONICAL_SOURCE)}"
        ) from exc


def _to_plan_records(
    label_hidden_records: list[dict], selection_reasons: dict[str, str]
) -> list[dict]:
    out: list[dict] = []
    for record in label_hidden_records:
        source_record_id = record["record_id"]
        canonical_source = _canonical_source_for(record["source"])
        namespaced_id = f"{canonical_source}::{source_record_id}"
        plan = dict(record)
        plan["source_record_id"] = source_record_id
        plan["source"] = canonical_source
        plan["record_id"] = namespaced_id
        plan["region"] = _CANONICAL_TO_REGION[canonical_source]
        plan["selection_reason"] = selection_reasons.get(str(source_record_id))
        out.append({name: plan.get(name) for name in PLAN_RECORD_FIELDS})
    return out


def _assert_plan_integrity(records: list[dict]) -> dict[str, Any]:
    """Enforce Requirements Section 10, points 3-7. Raises on any mismatch."""
    total = len(records)
    if total != TOTAL_TARGET:
        raise ValueError(
            f"combined sample plan must contain exactly {TOTAL_TARGET} records, "
            f"found {total}"
        )

    ids = [r["record_id"] for r in records]
    unique_ids = set(ids)
    if len(unique_ids) != total:
        raise ValueError(
            f"combined sample plan must have {total} unique canonical record_id "
            f"values, found {len(unique_ids)}"
        )

    by_source = Counter(r["source"] for r in records)
    for source, expected in SOURCE_TARGETS.items():
        observed = by_source.get(source, 0)
        if observed != expected:
            raise ValueError(
                f"expected exactly {expected} '{source}' records, found {observed}"
            )

    by_region = Counter(r["region"] for r in records)
    for region, expected in REGION_TARGETS.items():
        observed = by_region.get(region, 0)
        if observed != expected:
            raise ValueError(
                f"expected exactly {expected} '{region}' records, found {observed}"
            )

    source_id_sources: dict[str, set[str]] = {}
    for r in records:
        source_id_sources.setdefault(str(r["source_record_id"]), set()).add(r["source"])
    collisions = {
        sid: sorted(sources)
        for sid, sources in source_id_sources.items()
        if len(sources) > 1
    }
    if collisions:
        raise ValueError(
            f"{len(collisions)} source_record_id value(s) appear under more than "
            f"one canonical source; records must not be duplicated across source "
            f"groups: {collisions}"
        )

    return {
        "total": total,
        "unique_record_count": len(unique_ids),
        "by_source": dict(sorted(by_source.items())),
        "by_region": dict(sorted(by_region.items())),
        "cross_source_collision_count": len(collisions),
    }


def build_combined_sample_plan(
    south_africa_source: "str | Path",
    international_source: "str | Path",
    *,
    seed: int = DEFAULT_SEED,
    sa_rule_labels: "Any | None" = None,
) -> "tuple[list[dict], GoldSamplePlanReport]":
    """Build the canonical 1,000-record combined gold sample plan.

    Invokes both verified samplers (South African: 500/100-per-bank;
    international: 250 tweets + 250 reviews), both under the same ``seed``,
    combines their selections into one list of plan records, and asserts
    every Section 10 integrity requirement before returning. Raises
    ``ValueError`` on any mismatch rather than silently coercing the result.

    Source files are only ever read.
    """
    sa_selected, sa_report = sample_south_africa(
        south_africa_source, seed=seed, rule_labels=sa_rule_labels
    )
    intl_selected, intl_report = sample_international(international_source, seed=seed)

    sa_label_hidden = _south_africa_label_hidden_records(sa_selected)
    intl_label_hidden = _international_label_hidden_records(intl_selected)

    plan_records = _to_plan_records(sa_label_hidden, sa_report.selection_reasons)
    plan_records += _to_plan_records(intl_label_hidden, intl_report.selection_reasons)

    integrity = _assert_plan_integrity(plan_records)

    grouped = [r for r in plan_records if r.get("duplicate_group") or r.get("leakage_group")]
    distinct_groups = {
        r.get("duplicate_group") or r.get("leakage_group") for r in grouped
    }
    privacy_distribution = Counter(str(r.get("privacy_status")) for r in plan_records)

    report = GoldSamplePlanReport(
        seed=seed,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=git_commit(),
        total=integrity["total"],
        unique_record_count=integrity["unique_record_count"],
        by_source=integrity["by_source"],
        by_region=integrity["by_region"],
        cross_source_collision_count=integrity["cross_source_collision_count"],
        grouping_coverage={
            "records_with_group": len(grouped),
            "distinct_groups": len(distinct_groups),
        },
        privacy_status_distribution=dict(sorted(privacy_distribution.items())),
        south_africa_source_file=sa_report.source_file,
        south_africa_source_sha256=sa_report.source_sha256,
        international_source_file=intl_report.source_file,
        international_source_sha256=intl_report.source_sha256,
        south_africa_selection_manifest=_build_south_africa_manifest(sa_report),
        international_selection_manifest=_build_international_manifest(intl_report),
        notes=[
            "Plan records carry selection_reason for audit; the annotation-facing "
            "view (to_annotation_records) strips it per Requirements Section 11.",
            "No record was created or dropped: this is exactly the union of the "
            "two already-verified samplers' selections.",
        ],
    )
    return plan_records, report


def to_annotation_records(plan_records: list[dict]) -> list[dict]:
    """Project plan records to the Section 11 label-hidden annotation view.

    Strips ``selection_reason`` and any other sampling-only field, and adds
    the structurally-required, always-empty task-label fields. No target,
    category, sentiment, or intent is ever inferred.
    """
    out: list[dict] = []
    for record in plan_records:
        view = {name: record.get(name) for name in ANNOTATION_RECORD_FIELDS}
        view["primary_intent"] = None
        view["public_warning"] = None
        view["opinions"] = []
        view["annotation_status"] = "not_started"
        view["annotation_version"] = PIPELINE_VERSION
        view["annotation_notes"] = None
        out.append(view)
    return out


def build_gold_sample_plan_manifest(report: GoldSamplePlanReport) -> dict:
    """The immutable selection manifest required by Requirements Section 17."""
    manifest = report.to_dict()
    manifest["source_allocation"] = dict(SOURCE_TARGETS)
    manifest["region_allocation"] = dict(REGION_TARGETS)
    manifest["requirements_reference"] = {
        "section_10": "combined gold-sample plan",
        "section_13": "calibration and batching (downstream)",
        "section_17": "gold sample-plan manifest",
    }
    return manifest


def _logical_checksum(records: list[dict]) -> str:
    joined = "\n".join(sorted(str(r["record_id"]) for r in records))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def write_jsonl(records: list[dict], path: "str | Path") -> None:
    """Atomic JSONL write: temp file in the same directory, then replace."""
    import os

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
