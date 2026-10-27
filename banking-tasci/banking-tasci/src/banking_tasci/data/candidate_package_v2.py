"""Corrected candidate-package enrichment and lineage for `new_pipeline_v1`.

Candidate 2 reuses candidate 1's selected canonical IDs; it does not resample,
add, or remove records. It restores auditable metadata from the verified source
artifacts, computes only evidence-backed grouping, and keeps all sampling-rule
information outside the annotator-facing records.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Any

from banking_tasci.data.gold_sample_plan import (
    ANNOTATION_RECORD_FIELDS,
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    PIPELINE_VERSION,
    SOUTH_AFRICA_TWEET,
    to_annotation_records,
)
from banking_tasci.data.ingest import make_record_id

__all__ = [
    "CandidatePackageBuildError",
    "build_v2_rule_map",
    "build_review_metadata_map",
    "build_candidate2_package",
]

_INVALID_BANK_SENTINELS = {"review", "unknown", "all_banks", "all banks", "none", "null", "n/a", "na", ""}


class CandidatePackageBuildError(ValueError):
    """Raised when source evidence is missing, conflicting, or ambiguous."""


def _source_id(record: dict[str, Any]) -> str:
    value = record.get("source_record_id")
    if not isinstance(value, str) or not value:
        raise CandidatePackageBuildError("candidate plan record is missing source_record_id")
    return value


def _stable_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalised_text(text: Any) -> str:
    if text is None or (isinstance(text, float) and text != text):
        return ""
    from banking_tasci.data.clean import normalise_text

    return normalise_text(str(text))


def build_v2_rule_map(parent_frame, selected_source_ids: list[str]) -> dict[str, str]:
    """Select rules with the canonical vectorised algorithm and join by ID.

    Fails on missing/duplicate IDs and on any selected source ID without
    exactly one authoritative rule mapping.
    """
    from banking_tasci.data.sa_candidates_v2 import select_v2_candidates

    if "record_id" not in parent_frame.columns:
        raise CandidatePackageBuildError("SA parent data lacks record_id")
    ids = parent_frame["record_id"].astype(str)
    duplicated = ids[ids.duplicated(keep=False)]
    if not duplicated.empty:
        raise CandidatePackageBuildError(
            f"SA parent has duplicate record_id values: {sorted(set(duplicated))[:5]}"
        )
    selected_set = set(str(value) for value in selected_source_ids)
    if len(selected_set) != len(selected_source_ids):
        raise CandidatePackageBuildError("selected SA source IDs contain duplicates")
    missing_parent = selected_set - set(ids)
    if missing_parent:
        raise CandidatePackageBuildError(
            f"selected SA IDs absent from source parent: {sorted(missing_parent)[:5]}"
        )
    result = select_v2_candidates(parent_frame)
    mapping = {
        str(record_id): str(rule)
        for record_id, rule in zip(ids[result.mask], result.rule_labels[result.mask])
    }
    missing_rules = selected_set - set(mapping)
    if missing_rules:
        raise CandidatePackageBuildError(
            "selected SA records have no v2 rule mapping by record_id: "
            + ", ".join(sorted(missing_rules)[:10])
        )
    return {record_id: mapping[record_id] for record_id in selected_source_ids}


def build_review_metadata_map(
    raw_reviews,
    prepared_reviews,
    *,
    record_id_factory=make_record_id,
    source_checksum: str | None = None,
    raw_source_checksum: str | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Map prepared complete-review IDs to verified raw source metadata.

    Raw `bank` values are direct source evidence. The sentinel `review` is
    invalid as a bank; the generic `ALL_BANKS` logo does not identify a bank,
    so such records receive null rather than an inferred bank.
    """
    required_raw = {"review", "bank"}
    if not required_raw.issubset(raw_reviews.columns):
        raise CandidatePackageBuildError(
            f"raw reviews missing source field(s): {sorted(required_raw - set(raw_reviews.columns))}"
        )
    if not {"record_id", "source", "bank"}.issubset(prepared_reviews.columns):
        raise CandidatePackageBuildError("prepared review data lacks record_id/source/bank")

    raw_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_reviews.to_dict(orient="records"):
        normalized = _normalised_text(row.get("review"))
        if not normalized:
            continue
        # This is the ingestion contract: make_record_id(source, normalized)
        # hashes f"{source}:{normalized}" with SHA-256 and keeps 16 hex chars.
        source_id = record_id_factory("bank_reviews", normalized)
        raw_by_id[str(source_id)].append(row)

    prepared_reviews = prepared_reviews[
        prepared_reviews["source"] == "bank_reviews"
    ]
    mapping: dict[str, dict[str, Any]] = {}
    invalid_values: Counter[str] = Counter()
    corrected_using_source = 0
    set_null = 0
    ambiguous = 0
    affected: list[str] = []
    correction_ids: list[str] = []
    original_invalid_values_by_id: dict[str, list[str]] = {}
    original_bank_by_id: dict[str, Any] = {}
    per_prepared_id_duplicates = 0

    for prepared in prepared_reviews.to_dict(orient="records"):
        source_id = str(prepared["record_id"])
        source_rows = raw_by_id.get(source_id, [])
        if not source_rows:
            raise CandidatePackageBuildError(
                f"prepared review ID {source_id} has no matching raw review by deterministic source ID"
            )
        if len(source_rows) > 1:
            per_prepared_id_duplicates += 1
        raw_banks = {
            str(row.get("bank")).strip()
            for row in source_rows
            if row.get("bank") is not None and str(row.get("bank")).strip()
        }
        prepared_bank = prepared.get("bank")
        if not _present(prepared_bank):
            prepared_bank = None
        original_bank_by_id[source_id] = prepared_bank
        invalid_values.update(value for value in raw_banks if value.strip().lower() in _INVALID_BANK_SENTINELS)
        valid_raw_banks = {value for value in raw_banks if value.strip().lower() not in _INVALID_BANK_SENTINELS}
        bank: str | None
        if len(valid_raw_banks) == 1:
            bank = next(iter(valid_raw_banks))
            if prepared_bank != bank:
                corrected_using_source += 1
                correction_ids.append(source_id)
                affected.append(source_id)
                original_invalid_values_by_id[source_id] = (
                    sorted(value for value in raw_banks if value.strip().lower() in _INVALID_BANK_SENTINELS)
                    or ([str(prepared_bank)] if prepared_bank is not None else [])
                )
        elif len(valid_raw_banks) > 1:
            bank = None
            ambiguous += 1
            affected.append(source_id)
            original_invalid_values_by_id[source_id] = sorted(raw_banks)
        else:
            bank = None
            set_null += 1
            affected.append(source_id)
            original_invalid_values_by_id[source_id] = sorted(raw_banks) or (
                [str(prepared_bank)] if prepared_bank is not None else []
            )
        # Complete source reviews are represented as one record; no sentence
        # order or preceding review is inferred here.
        mapping[source_id] = {
            "bank": bank,
            "review_id": f"review::bank_reviews::{source_id}",
            "review_source_record_id": source_id,
            "review_identity_method": "review::bank_reviews::<make_record_id output>; make_record_id('bank_reviews', clean.normalise_text(full review)) computes sha256(f'{source}:{normalized_text}')[:16]; clean.normalise_text preserves case",
            "original_prepared_bank": prepared_bank,
            "original_invalid_bank_values": original_invalid_values_by_id.get(source_id, []),
            "bank_correction_reason": (
                "replaced prepared bank metadata with a unique valid raw source bank field"
                if bank is not None and prepared_bank != bank
                else "bank unavailable, invalid sentinel, or ambiguous raw-source values; set null"
                if bank is None
                else None
            ),
            "source_checksum": source_checksum,
            "thread_id": prepared.get("thread_id") if _present(prepared.get("thread_id")) else None,
            "conversation_id": prepared.get("conversation_id") if _present(prepared.get("conversation_id")) else None,

        }

    report = {
        "source": "bank_reviews3.csv",
        "raw_source_sha256": raw_source_checksum,
        "prepared_source_manifest_sha256": source_checksum,
        "source_id_algorithm": "make_record_id('bank_reviews', clean.normalise_text(review))",
        "source_evidence_fields": ["bank", "bank_image", "review", "date", "review_title_by_user"],
        "raw_invalid_bank_values": dict(sorted(invalid_values.items())),
        "corrected_using_verified_source_evidence": corrected_using_source,
        "corrected_source_record_ids": sorted(correction_ids),
        "set_null_because_bank_unavailable_or_invalid": set_null,
        "ambiguous_multiple_verified_banks": ambiguous,
        "prepared_ids_matching_multiple_raw_rows": per_prepared_id_duplicates,
        "affected_source_record_ids": sorted(affected),
        "original_invalid_values_by_source_record_id": dict(sorted(original_invalid_values_by_id.items())),
        "original_prepared_bank_values": {key: original_bank_by_id[key] for key in sorted(original_bank_by_id)},
        "affected_canonical_record_ids": sorted(f"{INTERNATIONAL_REVIEW}::{rid}" for rid in affected),
        "context_policy": "prepared records are complete reviews; no sentence segmentation or previous_text is fabricated at package-build time",
    }
    return mapping, report


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            first, second = sorted((root_left, root_right))
            self.parent[second] = first


def build_candidate2_package(
    candidate1_plan: list[dict[str, Any]],
    *,
    sa_source_metadata: dict[str, dict[str, Any]],
    v2_rule_map: dict[str, str],
    review_metadata: dict[str, dict[str, Any]],
    international_tweet_metadata: dict[str, dict[str, Any]] | None = None,
    review_metadata_report: dict[str, Any] | None = None,
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Enrich candidate 1 IDs, preserving IDs and labels-hidden annotation state."""
    plan = [dict(record) for record in candidate1_plan]
    ids = [str(record.get("record_id")) for record in plan]
    if len(plan) != 1000 or len(set(ids)) != 1000:
        raise CandidatePackageBuildError("candidate 1 must contain 1,000 unique canonical IDs")

    expected_sa_ids = {
        _source_id(r) for r in plan if r.get("source") == SOUTH_AFRICA_TWEET
    }
    if expected_sa_ids != set(v2_rule_map):
        missing = expected_sa_ids - set(v2_rule_map)
        extra = set(v2_rule_map) - expected_sa_ids
        raise CandidatePackageBuildError(
            f"v2 rule map must cover selected SA IDs exactly; missing={sorted(missing)[:5]}, extra={sorted(extra)[:5]}"
        )
    if any(rule not in {"A", "B", "C", "D", "E", "F"} for rule in v2_rule_map.values()):
        raise CandidatePackageBuildError("v2 rule mapping contains an invalid or unavailable rule")
    if len(set(v2_rule_map.values())) != 6:
        raise CandidatePackageBuildError("the selected SA sample does not cover all six v2 rules")

    expected_review_ids = {
        _source_id(r) for r in plan if r.get("source") == INTERNATIONAL_REVIEW
    }
    missing_review_ids = expected_review_ids - set(review_metadata)
    if missing_review_ids:
        raise CandidatePackageBuildError(
            "review metadata map is missing selected review IDs: " + ", ".join(sorted(missing_review_ids)[:10])
        )
    expected_tweet_ids = {
        _source_id(r) for r in plan if r.get("source") == INTERNATIONAL_TWEET
    }
    if international_tweet_metadata is not None:
        missing_tweet_ids = expected_tweet_ids - set(international_tweet_metadata)
        if missing_tweet_ids:
            raise CandidatePackageBuildError(
                "international tweet metadata map is missing selected IDs: " + ", ".join(sorted(missing_tweet_ids)[:10])
            )

    metadata_report = {
        "pipeline_version": PIPELINE_VERSION,
        "candidate_number": 2,
        "lineage_from": "new_pipeline_v1 candidate 1",
        "record_count": len(plan),
        "rule_distribution": {},
        "bank_metadata": {},
        "review_identity": {
            "algorithm": "review::bank_reviews::<make_record_id('bank_reviews', clean.normalise_text(full_review))>",
            "unit": "one complete prepared review per row",
            "sentence_splitting": "not performed; prepared rows contain complete review texts, not sentence fragments",
        },
        "grouping_policy": {
            "duplicate_group": "verified SA near-duplicate IDs and exact normalized-text relationships among candidate-2 records; null when no duplicate relationship is evidenced",
            "leakage_group_priority": ["conversation", "thread", "review", "near_duplicate", "exact_duplicate", "source-namespaced singleton record_id"],
            "thread_and_conversation": "null; no verified source fields exist in the prepared inputs",
            "hash": "SHA-256; no builtin hash()",
        },
        "context_policy": "complete reviews remain no-context at sample-record level; previous_text is null and no synthetic context is created; context-aware experiments remain blocked until a separate provenance-preserving, genuinely linked context dataset exists",
        "source_manifest_checksums": {},
    }

    # Exact normalized-text duplicates link records across sources only when
    # the normalized full text itself is identical.
    text_members: dict[str, list[str]] = defaultdict(list)
    near_group_members: dict[str, list[str]] = defaultdict(list)
    duplicate_keys_by_id: dict[str, set[str]] = defaultdict(set)
    leakage_keys_by_id: dict[str, set[str]] = defaultdict(set)
    rule_counts: Counter[str] = Counter()
    bank_counts: Counter[str] = Counter()
    bank_counts_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    region_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    invalid_bank_ids: list[str] = []
    for record in plan:
        rid = str(record["record_id"])
        source = record.get("source")
        source_counts[str(source)] += 1
        region_counts[str(record.get("region"))] += 1
        sid = _source_id(record)
        if source == SOUTH_AFRICA_TWEET:
            source_meta = sa_source_metadata.get(sid)
            if source_meta is None:
                raise CandidatePackageBuildError(f"SA selected ID has no source metadata: {sid}")
            if record.get("text") != source_meta.get("text"):
                raise CandidatePackageBuildError(f"SA source text mismatch for {sid}")
            rule = v2_rule_map[sid]
            record["selection_reason"] = _replace_rule(record.get("selection_reason"), rule)
            record["bank"] = source_meta.get("bank") if _present(source_meta.get("bank")) else None
            record["thread_id"] = source_meta.get("thread_id") if _present(source_meta.get("thread_id")) else None
            record["conversation_id"] = source_meta.get("conversation_id") if _present(source_meta.get("conversation_id")) else None
            near_group = source_meta.get("near_dup_group_id")
            if _present(near_group):
                record["verified_near_dup_group_id"] = str(near_group)
                near_group_members[str(near_group)].append(rid)
                near_key = f"sa_near_dup:south_africa:{near_group}"
                duplicate_keys_by_id[rid].add(near_key)
                leakage_keys_by_id[rid].add(near_key)
            else:
                record["verified_near_dup_group_id"] = None
            rule_counts[rule] += 1
            bank_counts[str(record.get("bank"))] += 1
            bank_counts_by_source[str(source)][str(record.get("bank") if record.get("bank") is not None else "null")] += 1
        elif source in {INTERNATIONAL_TWEET, INTERNATIONAL_REVIEW}:
            if source == INTERNATIONAL_REVIEW:
                meta = review_metadata[sid]
                if meta.get("review_source_record_id") != sid or meta.get("review_id") != f"review::bank_reviews::{sid}":
                    raise CandidatePackageBuildError(
                        f"review identity is not derived from the immutable source record ID: {sid}"
                    )
                record["bank"] = meta.get("bank")
                record["review_id"] = meta["review_id"]
                record["previous_text"] = None
                record["context_available"] = False
                if meta.get("bank") is None:
                    invalid_bank_ids.append(sid)
                bank_counts[str(meta.get("bank") if meta.get("bank") is not None else "null")] += 1
                bank_counts_by_source[str(source)][str(meta.get("bank") if meta.get("bank") is not None else "null")] += 1
                record["bank_metadata_correction_reason"] = meta.get("bank_correction_reason")
                record["original_invalid_bank_values"] = list(meta.get("original_invalid_bank_values", []))
                if meta.get("review_identity_method") != "review::bank_reviews::<make_record_id output>; make_record_id('bank_reviews', clean.normalise_text(full review)) computes sha256(f'{source}:{normalized_text}')[:16]; clean.normalise_text preserves case":
                    raise CandidatePackageBuildError("unexpected review identity method")
            else:
                tweet_meta = (international_tweet_metadata or {}).get(sid, {})
                source_bank = tweet_meta.get("bank", record.get("bank"))
                record["bank"] = source_bank if _present(source_bank) else None
                bank_value = str(record["bank"] if record["bank"] is not None else "null")
                bank_counts[bank_value] += 1
                bank_counts_by_source[str(source)][bank_value] += 1
        else:
            raise CandidatePackageBuildError(f"unsupported candidate source: {source}")

        for field_name, namespace in (
            ("duplicate_group", "source_duplicate"),
            ("conversation_id", "conversation"),
            ("thread_id", "thread"),
            ("review_id", "review"),
            ("leakage_group", "source_leakage"),
        ):
            evidence_value = record.get(field_name)
            if _present(evidence_value):
                evidence_key = f"{namespace}:{evidence_value}"
                leakage_keys_by_id[rid].add(evidence_key)
                if field_name == "duplicate_group":
                    duplicate_keys_by_id[rid].add(evidence_key)

        normalized = _normalised_text(record.get("text"))
        if normalized:
            text_members[_stable_digest(normalized)].append(rid)

    exact_duplicate_group_count = 0
    for digest, members in text_members.items():
        if len(members) > 1:
            exact_duplicate_group_count += 1
            evidence_id = f"exact_text:{digest}"
            for rid in members:
                duplicate_keys_by_id[rid].add(evidence_id)
                leakage_keys_by_id[rid].add(evidence_id)

    duplicate_components = _components_from_keys(ids, duplicate_keys_by_id)
    duplicate_group_by_id: dict[str, str | None] = {}
    for component in duplicate_components:
        evidence_keys = sorted(set().union(*(duplicate_keys_by_id.get(rid, set()) for rid in component)))
        if not evidence_keys:
            continue
        if len(evidence_keys) == 1 and evidence_keys[0].startswith("sa_near_dup:"):
            group = "duplicate::new_pipeline_v1::" + evidence_keys[0]
        else:
            group = "duplicate::new_pipeline_v1::" + _stable_digest("\n".join(evidence_keys))
        for rid in component:
            duplicate_group_by_id[rid] = group
            leakage_keys_by_id[rid].update(duplicate_keys_by_id.get(rid, set()))

    for record in plan:
        rid = str(record["record_id"])
        record["duplicate_group"] = duplicate_group_by_id.get(rid)
        # Complete source reviews have one stable review identity. Thread and
        # conversation remain null because the verified sources expose none.
        record["thread_id"] = record.get("thread_id") or None
        record["conversation_id"] = record.get("conversation_id") or None

    leakage_components = _components_from_keys(ids, leakage_keys_by_id)
    leakage_by_id: dict[str, str] = {}
    for component in leakage_components:
        group_value = "leakage::new_pipeline_v1::" + _stable_digest("\n".join(sorted(component)))
        for rid in component:
            leakage_by_id[rid] = group_value
    for record in plan:
        record["leakage_group"] = leakage_by_id[str(record["record_id"])]

    annotation = to_annotation_records(plan)
    for record in annotation:
        if set(record) != set(ANNOTATION_RECORD_FIELDS):
            raise CandidatePackageBuildError("annotation projection has unexpected fields")
        if record["primary_intent"] is not None or record["public_warning"] is not None or record["opinions"]:
            raise CandidatePackageBuildError("candidate 2 projection is not label-hidden")
        record["annotation_version"] = PIPELINE_VERSION

    metadata_report["rule_distribution"] = dict(sorted(rule_counts.items()))
    sa_checksums = {str(meta["source_checksum"]) for meta in sa_source_metadata.values() if meta.get("source_checksum")}
    review_checksums = {str(meta["source_checksum"]) for meta in review_metadata.values() if meta.get("source_checksum")}
    if len(sa_checksums) > 1 or len(review_checksums) > 1:
        raise CandidatePackageBuildError("conflicting source checksums in metadata maps")
    metadata_report["source_manifest_checksums"] = {
        "south_africa_candidates_v2": next(iter(sa_checksums), None),
        "international_prepared": next(iter(review_checksums), None),
    }
    metadata_report["raw_source_checksums"] = {
        "bank_reviews3.csv": (review_metadata_report or {}).get("raw_source_sha256"),
    }
    metadata_report["source_distribution"] = dict(sorted(source_counts.items()))
    metadata_report["region_distribution"] = dict(sorted(region_counts.items()))
    metadata_report["bank_metadata"] = {
        "invalid_review_bank_sentinel": "review",
        "review_records_set_null": len(invalid_bank_ids),
        "review_record_ids_set_null": sorted(f"{INTERNATIONAL_REVIEW}::{rid}" for rid in invalid_bank_ids),
        "corrected_using_verified_evidence": sum(
            review_metadata.get(rid, {}).get("bank") is not None
            and review_metadata.get(rid, {}).get("bank_correction_reason") is not None
            for rid in expected_review_ids
        ),
        "corrected_source_record_ids": sorted(
            rid for rid in expected_review_ids
            if review_metadata.get(rid, {}).get("bank") is not None
            and review_metadata.get(rid, {}).get("bank_correction_reason") is not None
        ),
        "affected_record_ids": sorted(
            f"{INTERNATIONAL_REVIEW}::{rid}" for rid in expected_review_ids
            if review_metadata.get(rid, {}).get("bank_correction_reason") is not None
        ),
        "original_invalid_values_by_source_record_id": {
            rid: review_metadata[rid].get("original_invalid_bank_values", [])
            for rid in sorted(expected_review_ids)
            if review_metadata[rid].get("original_invalid_bank_values")
        },
        "source_mapping_report": review_metadata_report or {},
        "final_distribution": dict(sorted(bank_counts.items())),
        "distribution_by_source": {
            source: dict(sorted(counts.items())) for source, counts in sorted(bank_counts_by_source.items())
        },
    }
    metadata_report["duplicate_group_summary"] = {
        "records_with_group": sum(r.get("duplicate_group") is not None for r in plan),
        "distinct_groups": len({r["duplicate_group"] for r in plan if r.get("duplicate_group")}),
        "source_near_duplicate_groups_observed": len(near_group_members),
        "exact_normalized_text_duplicate_groups": exact_duplicate_group_count,
        "verified_source_near_duplicate_membership": {
            group: sorted(members) for group, members in sorted(near_group_members.items())
        },
    }
    metadata_report["leakage_group_summary"] = {
        "records_with_group": sum(bool(r.get("leakage_group")) for r in plan),
        "distinct_groups": len({r["leakage_group"] for r in plan}),
        "all_records_grouped": all(bool(r.get("leakage_group")) for r in plan),
    }
    metadata_report["sampling_diversity"] = {
        "year_distribution": dict(sorted(Counter(str(r.get("publish_year")) for r in plan).items())),
        "length_band_distribution": dict(sorted(Counter(
            re.search(r"length_band=([^;]+)", str(r.get("selection_reason", ""))).group(1).strip()
            if re.search(r"length_band=([^;]+)", str(r.get("selection_reason", "")))
            else "not_recorded"
            for r in plan
        ).items())),
        "v2_rule_distribution": dict(sorted(rule_counts.items())),
        "context_availability": dict(sorted(Counter(str(r.get("context_available")) for r in plan).items())),
    }
    expected_sources = {SOUTH_AFRICA_TWEET: 500, INTERNATIONAL_TWEET: 250, INTERNATIONAL_REVIEW: 250}
    expected_regions = {"south_africa": 500, "international": 500}
    if len(plan) != 1000 or len(set(ids)) != 1000 or dict(source_counts) != expected_sources:
        raise CandidatePackageBuildError(
            f"candidate package totals invalid: records={len(plan)}, sources={dict(source_counts)}"
        )
    if dict(region_counts) != expected_regions:
        raise CandidatePackageBuildError(f"candidate regional allocation invalid: {dict(region_counts)}")
    if set(rule_counts) != {"A", "B", "C", "D", "E", "F"}:
        raise CandidatePackageBuildError("candidate 2 must preserve all six selected SA v2 rules")
    if any(r.get("annotation_status") != "not_started" for r in annotation):
        raise CandidatePackageBuildError("candidate-2 annotation status must remain not_started")
    if any(r.get("context_available") is not False or r.get("previous_text") is not None for r in annotation if r.get("source") == INTERNATIONAL_REVIEW):
        raise CandidatePackageBuildError("review context must remain unavailable and previous_text null")
    return plan, annotation, metadata_report


def _present(value: Any) -> bool:
    return value is not None and str(value).strip().lower() not in {"", "nan", "none"}


def _replace_rule(reason: Any, rule: str) -> str:
    text = str(reason or "")
    text = re.sub(r"(?:^|;\s*)v2_rule=[^;]*", "", text).strip(" ;")
    return (text + "; " if text else "") + f"v2_rule={rule}"


def _components_from_keys(
    record_ids: list[str], keys_by_id: dict[str, set[str]]
) -> list[set[str]]:
    parent = {record_id: record_id for record_id in record_ids}

    def find(item: str) -> str:
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            first, second = sorted((ra, rb))
            parent[second] = first

    first_by_group: dict[str, str] = {}
    for rid, keys in keys_by_id.items():
        for key in sorted(keys):
            if key in first_by_group:
                union(rid, first_by_group[key])
            else:
                first_by_group[key] = rid
    components: dict[str, set[str]] = defaultdict(set)
    for rid in record_ids:
        components[find(rid)].add(rid)
    return list(components.values())
