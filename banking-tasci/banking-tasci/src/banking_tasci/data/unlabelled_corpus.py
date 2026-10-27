"""Strict unlabelled-corpus construction for `new_pipeline_v1`.

Implements Requirements Section 16: the **110,615-record** strict unlabelled
corpus for domain adaptation, formed by removing the 1,000 gold records from the
111,615-record combined relevant corpus.

    South African candidates   100,768  -  500 gold  =  100,268
    International prepared      10,847  -  500 gold  =   10,347
                               -------                 -------
    Combined                   111,615  - 1,000 gold  =  110,615

**Why two modes.** The 1,000 gold identifiers *do not exist yet* - the
annotation sample has not been drawn, and the South African half cannot be drawn
until Phase 3 completes. Building a 110,615-record file today would require
removing 1,000 arbitrary records, which Requirements Migration Principle 6
forbids ("do not fabricate annotations, identifiers, context, or metrics").

So:

``PREPARATION`` mode
    Validates manifests and arithmetic, inspects whether gold-ID manifests
    exist, and emits a readiness report. It **refuses** to claim the corpus has
    been built and writes no corpus.

``FINAL`` mode
    Requires frozen, verified gold identifiers (exactly 1,000: 500 South
    African, 250 international tweets, 250 international reviews) and excludes
    them by identifier. Unavailable until annotation completes.

**Field policy** (Requirements Section 16). The strict corpus excludes every
task label, annotation field, partition label, candidate/sampling-rule field,
and the predictive shortcuts (source, bank, region, rating). It retains only a
stable identifier, approved text, and - where approved - genuine previous
context. Provenance needed for traceability is kept in the *manifest*, not
supplied to the model as text.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "MODE_PREPARATION",
    "MODE_FINAL",
    "READINESS_READY",
    "READINESS_BLOCKED",
    "EXPECTED_COUNTS",
    "APPROVED_TEXT_FIELDS",
    "EXCLUDED_FIELDS",
    "GoldIdSet",
    "ReadinessReport",
    "assess_readiness",
    "load_gold_ids",
    "build_strict_corpus",
]

MODE_PREPARATION = "PREPARATION"
MODE_FINAL = "FINAL"

READINESS_READY = "READY_FOR_FINAL"
READINESS_BLOCKED = "BLOCKED_AWAITING_FROZEN_GOLD_IDS"

# Requirements Sections 4.4, 4.5.
EXPECTED_COUNTS = {
    "south_africa_candidates": 100_768,
    "south_africa_gold": 500,
    "south_africa_unlabelled": 100_268,
    "international_prepared": 10_847,
    "international_gold": 500,
    "international_tweet_gold": 250,
    "international_review_gold": 250,
    "international_unlabelled": 10_347,
    "combined_relevant": 111_615,
    "gold_total": 1_000,
    "strict_unlabelled": 110_615,
}

# Requirements Section 16: "Approved text fields must be specified in
# configuration." These are the only fields that may carry model-visible text.
APPROVED_TEXT_FIELDS = ("text",)

# Retained for traceability but NEVER supplied as model text.
IDENTIFIER_FIELDS = ("record_id",)

# Optional, only when the experiment approves genuine preceding context.
CONTEXT_FIELDS = ("previous_text", "context_available")

# Requirements Section 16 exclusion list. Grouped so the reason for each
# exclusion stays legible.
EXCLUDED_FIELDS = {
    "task_labels": (
        "target", "target_start", "target_end", "target_type",
        "entity", "attribute", "category",
        "opinion_phrase", "opinion_start", "opinion_end",
        "sentiment", "intent", "primary_intent", "public_warning",
        "opinions", "aspects",
    ),
    "annotation_metadata": (
        "annotation_notes", "annotation_status", "annotation_version",
        "annotator_id", "notes", "intent_ambiguous", "alternative_intent",
    ),
    "partition_labels": ("split", "partition", "fold"),
    "predictive_shortcuts": ("source", "bank", "region", "rating"),
    "candidate_and_sampling_rules": (
        "customer_feedback_candidate", "candidate_strata", "filter_reason",
        "likely_promotional", "possible_official_account", "sample_role",
        "rule_matched", "matched_strata", "is_zero_aspect",
    ),
}


def all_excluded_fields() -> tuple[str, ...]:
    out: list[str] = []
    for group in EXCLUDED_FIELDS.values():
        out.extend(group)
    return tuple(sorted(set(out)))


@dataclass
class GoldIdSet:
    """A frozen set of gold identifiers, by source."""

    south_africa: tuple[str, ...] = ()
    international_tweets: tuple[str, ...] = ()
    international_reviews: tuple[str, ...] = ()
    source_manifest: str | None = None

    @property
    def all_ids(self) -> set[str]:
        return set(self.south_africa) | set(
            self.international_tweets
        ) | set(self.international_reviews)

    @property
    def total(self) -> int:
        return (
            len(self.south_africa)
            + len(self.international_tweets)
            + len(self.international_reviews)
        )

    def validate(self) -> list[str]:
        """Return a list of problems; empty means the set is usable in FINAL."""
        problems: list[str] = []

        if len(self.south_africa) != EXPECTED_COUNTS["south_africa_gold"]:
            problems.append(
                f"expected {EXPECTED_COUNTS['south_africa_gold']} South African gold "
                f"IDs, found {len(self.south_africa)}"
            )
        if len(self.international_tweets) != EXPECTED_COUNTS["international_tweet_gold"]:
            problems.append(
                f"expected {EXPECTED_COUNTS['international_tweet_gold']} international "
                f"tweet gold IDs, found {len(self.international_tweets)}"
            )
        if len(self.international_reviews) != EXPECTED_COUNTS["international_review_gold"]:
            problems.append(
                f"expected {EXPECTED_COUNTS['international_review_gold']} international "
                f"review gold IDs, found {len(self.international_reviews)}"
            )
        if self.total != EXPECTED_COUNTS["gold_total"]:
            problems.append(
                f"expected {EXPECTED_COUNTS['gold_total']} gold IDs in total, found "
                f"{self.total}"
            )
        if len(self.all_ids) != self.total:
            problems.append(
                f"gold identifiers are not unique: {self.total} supplied but "
                f"{len(self.all_ids)} distinct"
            )
        return problems


@dataclass
class ReadinessReport:
    """Outcome of a PREPARATION-mode assessment."""

    mode: str = MODE_PREPARATION
    readiness: str = READINESS_BLOCKED
    pipeline_version: str = "new_pipeline_v1"
    corpus_built: bool = False
    expected_counts: dict[str, int] = field(default_factory=lambda: dict(EXPECTED_COUNTS))
    arithmetic_checks: dict[str, Any] = field(default_factory=dict)
    source_manifest_checks: dict[str, Any] = field(default_factory=dict)
    gold_id_manifests: dict[str, Any] = field(default_factory=dict)
    gold_exclusion_requirements: list[str] = field(default_factory=list)
    field_policy: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    generated_at: str = ""
    git_commit: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _check_arithmetic() -> dict:
    """Verify the Section 4.5 arithmetic is internally consistent."""
    c = EXPECTED_COUNTS
    checks = {
        "south_africa": {
            "candidates": c["south_africa_candidates"],
            "gold": c["south_africa_gold"],
            "unlabelled": c["south_africa_unlabelled"],
            "consistent": c["south_africa_candidates"] - c["south_africa_gold"]
            == c["south_africa_unlabelled"],
        },
        "international": {
            "prepared": c["international_prepared"],
            "gold": c["international_gold"],
            "unlabelled": c["international_unlabelled"],
            "consistent": c["international_prepared"] - c["international_gold"]
            == c["international_unlabelled"],
        },
        "international_gold_split": {
            "tweets": c["international_tweet_gold"],
            "reviews": c["international_review_gold"],
            "consistent": c["international_tweet_gold"] + c["international_review_gold"]
            == c["international_gold"],
        },
        "combined": {
            "relevant": c["combined_relevant"],
            "gold_total": c["gold_total"],
            "strict_unlabelled": c["strict_unlabelled"],
            "consistent": c["combined_relevant"] - c["gold_total"]
            == c["strict_unlabelled"],
        },
        "cross_check": {
            "sum_of_source_unlabelled": c["south_africa_unlabelled"]
            + c["international_unlabelled"],
            "strict_unlabelled": c["strict_unlabelled"],
            "consistent": c["south_africa_unlabelled"] + c["international_unlabelled"]
            == c["strict_unlabelled"],
        },
    }
    checks["all_consistent"] = all(
        v["consistent"] for k, v in checks.items() if isinstance(v, dict)
    )
    return checks


def load_gold_ids(manifest_path: "str | Path") -> GoldIdSet:
    """Load a frozen gold-identifier manifest.

    Expected shape::

        {
          "south_africa": [...],
          "international_tweets": [...],
          "international_reviews": [...]
        }
    """
    import json
    import hashlib

    path = Path(manifest_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("immutable_status") == "FROZEN":
        if data.get("pipeline_version") != "new_pipeline_v1":
            raise ValueError("frozen gold manifest pipeline_version mismatch")
        id_path = Path(data.get("gold_id_file", ""))
        if not id_path.is_absolute():
            id_path = path.parent / id_path
        if not id_path.is_file():
            raise FileNotFoundError(f"frozen gold ID file is missing: {id_path}")
        digest = hashlib.sha256(id_path.read_bytes()).hexdigest()
        if digest != data.get("gold_id_checksum"):
            raise ValueError("frozen gold ID file checksum does not match its freeze manifest")
        groups: dict[str, list[str]] = {
            "south_africa": [],
            "international_tweets": [],
            "international_reviews": [],
        }
        with id_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                source = record.get("source")
                source_id = record.get("source_record_id")
                if source == "south_africa_tweet":
                    key = "south_africa"
                elif source == "international_tweet":
                    key = "international_tweets"
                elif source == "international_review":
                    key = "international_reviews"
                else:
                    raise ValueError(
                        f"invalid canonical source in frozen gold IDs at line {line_number}"
                    )
                if not isinstance(source_id, str) or not source_id:
                    raise ValueError(f"missing source_record_id in frozen IDs at line {line_number}")
                groups[key].append(source_id)
        return GoldIdSet(
            south_africa=tuple(groups["south_africa"]),
            international_tweets=tuple(groups["international_tweets"]),
            international_reviews=tuple(groups["international_reviews"]),
            source_manifest=str(path),
        )

    return GoldIdSet(
        south_africa=tuple(str(x) for x in data.get("south_africa", [])),
        international_tweets=tuple(
            str(x) for x in data.get("international_tweets", [])
        ),
        international_reviews=tuple(
            str(x) for x in data.get("international_reviews", [])
        ),
        source_manifest=str(path),
    )


def assess_readiness(
    *,
    south_africa_manifest: "dict | None" = None,
    international_manifest: "dict | None" = None,
    combined_manifest: "dict | None" = None,
    gold_id_manifest_paths: "dict[str, Path] | None" = None,
    git_commit_value: str = "UNKNOWN_NO_COMMIT",
) -> ReadinessReport:
    """PREPARATION mode: report readiness without building anything.

    Never claims the strict corpus exists. Returns ``READINESS_BLOCKED`` while
    any gold-ID manifest is missing or invalid.
    """
    report = ReadinessReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=git_commit_value,
    )

    report.arithmetic_checks = _check_arithmetic()
    if not report.arithmetic_checks["all_consistent"]:
        report.blockers.append(
            "the configured counts are not internally consistent; resolve before "
            "building any corpus"
        )

    # --- source manifests ---------------------------------------------------
    manifest_checks: dict[str, Any] = {}
    for name, manifest in (
        ("south_africa", south_africa_manifest),
        ("international", international_manifest),
        ("combined", combined_manifest),
    ):
        if manifest is None:
            manifest_checks[name] = {"present": False, "status": None}
            report.blockers.append(f"{name} manifest was not supplied")
            continue
        status = manifest.get("status")
        manifest_checks[name] = {
            "present": True,
            "status": status,
            "verified": status == "VERIFIED",
            "row_count": manifest.get("row_count")
            or (manifest.get("counts") or {}).get("combined_relevant"),
            "sha256": manifest.get("sha256"),
        }
        if status != "VERIFIED":
            report.blockers.append(
                f"{name} manifest status is '{status}', not VERIFIED"
            )
    report.source_manifest_checks = manifest_checks

    # --- gold-ID manifests --------------------------------------------------
    gold_checks: dict[str, Any] = {}
    paths = gold_id_manifest_paths or {}
    if not paths:
        gold_checks["supplied"] = False
        report.blockers.append(
            "no gold-identifier manifest path was supplied; the 1,000 gold "
            "identifiers do not exist yet"
        )
    else:
        gold_checks["supplied"] = True
        for name, path in paths.items():
            exists = Path(path).is_file()
            entry: dict[str, Any] = {"path": str(path), "exists": exists}
            if exists:
                try:
                    loaded = load_gold_ids(path)
                    problems = loaded.validate()
                    entry.update(
                        {
                            "total_ids": loaded.total,
                            "south_africa": len(loaded.south_africa),
                            "international_tweets": len(loaded.international_tweets),
                            "international_reviews": len(loaded.international_reviews),
                            "problems": problems,
                            "usable": not problems,
                        }
                    )
                    if problems:
                        report.blockers.extend(
                            f"gold manifest '{name}': {p}" for p in problems
                        )
                except Exception as exc:  # pragma: no cover - defensive
                    entry["error"] = str(exc)
                    report.blockers.append(
                        f"gold manifest '{name}' could not be read: {exc}"
                    )
            else:
                report.blockers.append(
                    f"gold manifest '{name}' does not exist at {path}"
                )
            gold_checks[name] = entry
    report.gold_id_manifests = gold_checks

    # --- what FINAL mode will require --------------------------------------
    report.gold_exclusion_requirements = [
        "a frozen South African gold-ID set of exactly 500 identifiers",
        "a frozen international tweet gold-ID set of exactly 250 identifiers",
        "a frozen international review gold-ID set of exactly 250 identifiers",
        "a combined gold manifest totalling exactly 1,000 unique identifiers",
        "every gold identifier must exist in its corresponding source corpus",
        "zero overlap between the strict unlabelled corpus and the gold ID set",
        "exclusion performed by stable identifier, never by position or sampling",
    ]

    report.field_policy = {
        "approved_text_fields": list(APPROVED_TEXT_FIELDS),
        "identifier_fields_retained_for_traceability": list(IDENTIFIER_FIELDS),
        "context_fields_if_approved": list(CONTEXT_FIELDS),
        "excluded_fields_by_reason": {
            reason: list(fields) for reason, fields in EXCLUDED_FIELDS.items()
        },
        "note": (
            "Retained provenance lives in the manifest, never in model-visible "
            "text. Source, bank, region, and rating are excluded as predictive "
            "shortcuts (Requirements 16, 26)."
        ),
    }

    report.readiness = READINESS_READY if not report.blockers else READINESS_BLOCKED
    report.corpus_built = False
    report.notes = [
        "PREPARATION mode never builds a corpus and never claims one exists.",
        f"The strict corpus target is {EXPECTED_COUNTS['strict_unlabelled']:,} records, "
        "but it cannot be produced until the 1,000 gold identifiers are frozen. "
        "Removing 1,000 arbitrary records to hit the number is prohibited "
        "(Requirements Migration Principle 6).",
    ]
    return report


def build_strict_corpus(
    combined_frame,
    gold_ids: GoldIdSet,
    *,
    include_context: bool = False,
    expected_count: int = EXPECTED_COUNTS["strict_unlabelled"],
):
    """FINAL mode: build the strict unlabelled corpus by gold-ID exclusion.

    Args:
        combined_frame: the combined relevant corpus, carrying ``record_id``
            and the approved text field(s).
        gold_ids: a validated :class:`GoldIdSet`.
        include_context: retain genuine previous context when the experiment
            approves it.
        expected_count: the count to verify against (never to coerce toward).

    Returns:
        ``(strict_frame, report_dict)``.

    Raises:
        ValueError: if the gold set is invalid, a required column is absent, or
            the resulting count does not match ``expected_count``. The corpus is
            never trimmed or padded to fit.
    """
    problems = gold_ids.validate()
    if problems:
        raise ValueError(
            "refusing to build the strict corpus with an invalid gold ID set: "
            + "; ".join(problems)
        )

    if "record_id" not in combined_frame.columns:
        raise ValueError("combined frame must carry 'record_id'")
    missing_text = [f for f in APPROVED_TEXT_FIELDS if f not in combined_frame.columns]
    if missing_text:
        raise ValueError(
            "combined frame is missing approved text field(s): "
            + ", ".join(missing_text)
        )

    gold = gold_ids.all_ids
    ids = combined_frame["record_id"].astype(str)
    keep_mask = ~ids.isin(gold)
    strict = combined_frame.loc[keep_mask]

    # Verify the exclusion actually removed the full gold set.
    removed = int(len(combined_frame) - len(strict))
    if removed != gold_ids.total:
        raise ValueError(
            f"expected to remove {gold_ids.total} gold records but removed "
            f"{removed}; some gold identifiers were absent from the combined corpus"
        )

    if len(strict) != expected_count:
        raise ValueError(
            f"strict corpus has {len(strict)} records but expected {expected_count}. "
            f"Refusing to trim or pad to fit."
        )

    # Project to the approved field set only.
    columns = list(IDENTIFIER_FIELDS) + list(APPROVED_TEXT_FIELDS)
    if include_context:
        columns += [c for c in CONTEXT_FIELDS if c in strict.columns]
    columns = [c for c in columns if c in strict.columns]
    projected = strict[columns].copy()

    # Hard check: no excluded field survived.
    leaked = [c for c in all_excluded_fields() if c in projected.columns]
    if leaked:
        raise ValueError(
            "strict corpus would retain excluded field(s): " + ", ".join(leaked)
        )

    # Zero overlap with the gold set.
    overlap = set(projected["record_id"].astype(str)) & gold
    if overlap:
        raise ValueError(
            f"{len(overlap)} gold identifier(s) survived into the strict corpus"
        )

    joined = "\n".join(sorted(projected["record_id"].astype(str)))
    logical = hashlib.sha256(joined.encode("utf-8")).hexdigest()

    report = {
        "mode": MODE_FINAL,
        "corpus_built": True,
        "record_count": int(len(projected)),
        "expected_count": expected_count,
        "gold_records_excluded": removed,
        "gold_total": gold_ids.total,
        "gold_overlap_with_strict": 0,
        "columns_retained": columns,
        "excluded_fields_verified_absent": True,
        "include_context": include_context,
        "logical_checksum": logical,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return projected, report
