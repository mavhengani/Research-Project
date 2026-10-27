"""Deterministic South African gold sampler for `new_pipeline_v1`.

Implements the South African half of Requirements Section 7.1: **500 records**,
initially allocated **100 per bank** across FNB, Absa, Nedbank, Standard Bank,
and Capitec, drawn from the VERIFIED 100,768-record materialised v2 candidate
corpus.

Mirrors the design properties already established and tested for
``international_sampler`` so both sources behave identically:

- *Deterministic.* All randomness flows through one ``numpy`` ``PCG64``
  generator seeded only from the caller's seed (default 42); global RNG state is
  never read or mutated.
- *No replacement.* Selection is by unique index; a record cannot appear twice.
- *Source-specific length bands.* Short/medium/long boundaries come from this
  corpus's own quantiles, never shared with the international sources
  (Requirements 7.4).
- *Group integrity.* At most one record per duplicate/leakage group is selected,
  so no group is ever partially sampled.
- *Label-hidden output.* Emitted records carry empty ``opinions`` and null
  ``primary_intent``. No target, category, sentiment, or intent is inferred.
- *Candidate rules are not labels.* The v2 rule that caused a record to be a
  candidate is used for **coverage reporting only** and never written to the
  annotation view (Requirements 6.5).
- *Shortages reported.* A bank or stratum with insufficient records produces an
  explicit shortage entry rather than silent under-delivery.

Bank distribution in the materialised corpus is uneven (FNB ~32.9k, Absa
~12.9k), but every bank holds far more than 100 candidates, so the 100-per-bank
allocation is satisfiable. The sampler still reports per-bank shortages rather
than assuming this.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from banking_tasci.data.sa_candidates_v2 import RULE_PRECEDENCE

__all__ = [
    "DEFAULT_SEED",
    "SOUTH_AFRICA_SOURCE",
    "TARGET_TOTAL",
    "PER_BANK_TARGET",
    "CANONICAL_BANKS",
    "BANK_ALIASES",
    "LENGTH_QUANTILES",
    "SouthAfricaSamplerReport",
    "normalise_bank",
    "compute_length_bands",
    "assign_length_band",
    "dry_run",
    "sample_south_africa",
    "to_label_hidden_records",
    "build_selection_manifest",
]

DEFAULT_SEED = 42

SOUTH_AFRICA_SOURCE = "south_african_bank_tweets"

TARGET_TOTAL = 500
PER_BANK_TARGET = 100

# Requirements Section 5.1 / 7.1 canonical bank names.
CANONICAL_BANKS = ("FNB", "Absa", "Nedbank", "Standard Bank", "Capitec")

# The corpus stores banks lower-cased with underscores; map to canonical form
# so reporting uses the requirement's vocabulary without mutating source data.
BANK_ALIASES = {
    "fnb": "FNB",
    "absa": "Absa",
    "nedbank": "Nedbank",
    "standard_bank": "Standard Bank",
    "standardbank": "Standard Bank",
    "capitec": "Capitec",
}

LENGTH_QUANTILES = (0.33, 0.66)
BAND_NAMES = ("short", "medium", "long")

_NO_CONTEXT = "[NO_CONTEXT]"


@dataclass
class SouthAfricaSamplerReport:
    """Everything the sampler observed and decided (Requirements 7.5)."""

    pipeline_version: str = "new_pipeline_v1"
    seed: int = DEFAULT_SEED
    dry_run: bool = False
    source_file: str = ""
    source_sha256: str = ""
    generated_at: str = ""
    available_total: int = 0
    available_by_bank: dict[str, int] = field(default_factory=dict)
    requested_by_bank: dict[str, int] = field(default_factory=dict)
    selected_by_bank: dict[str, int] = field(default_factory=dict)
    requested_total: int = TARGET_TOTAL
    selected_total: int = 0
    length_bands: dict[str, Any] = field(default_factory=dict)
    available_by_stratum: dict[str, int] = field(default_factory=dict)
    selected_by_stratum: dict[str, int] = field(default_factory=dict)
    year_distribution_available: dict[str, int] = field(default_factory=dict)
    year_distribution_selected: dict[str, int] = field(default_factory=dict)
    rule_distribution_available: dict[str, int] = field(default_factory=dict)
    rule_distribution_selected: dict[str, int] = field(default_factory=dict)
    duplicate_group_coverage: dict[str, Any] = field(default_factory=dict)
    duplicate_group_conflicts: int = 0
    context_availability: dict[str, int] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    shortages: list[dict] = field(default_factory=list)
    unsatisfied_strata: list[dict] = field(default_factory=list)
    can_select_full_total: bool = False
    can_select_full_per_bank: bool = False
    selection_reasons: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise_bank(value: Any) -> str:
    """Map a stored bank value onto its canonical requirement name."""
    if value is None:
        return "unknown"
    text = str(value).strip().lower().replace(" ", "_")
    return BANK_ALIASES.get(text, str(value))


def compute_length_bands(
    frame: pd.DataFrame,
    text_column: str = "text",
    quantiles: tuple[float, float] = LENGTH_QUANTILES,
) -> dict:
    """Boundaries from THIS corpus's own quantiles (Requirements 7.4)."""
    lengths = frame[text_column].fillna("").astype(str).str.len()
    if lengths.empty:
        return {
            "source": SOUTH_AFRICA_SOURCE,
            "q_low": 0.0,
            "q_high": 0.0,
            "quantiles": list(quantiles),
            "n": 0,
        }
    return {
        "source": SOUTH_AFRICA_SOURCE,
        "q_low": float(lengths.quantile(quantiles[0])),
        "q_high": float(lengths.quantile(quantiles[1])),
        "quantiles": list(quantiles),
        "n": int(len(lengths)),
    }


def assign_length_band(length: int, bands: dict) -> str:
    if length <= bands["q_low"]:
        return "short"
    if length <= bands["q_high"]:
        return "medium"
    return "long"


def _group_key(row: pd.Series) -> str | None:
    """Duplicate/leakage group membership for leakage-safe selection."""
    for column in ("near_dup_group_id", "thread_id"):
        value = row.get(column)
        if value is not None and not (isinstance(value, float) and value != value):
            text = str(value).strip()
            if text and text.lower() not in {"nan", "none"}:
                return f"{column}:{text}"
    return None


def _is_missing_group(value: Any) -> bool:
    """True when ``value`` represents "no group" (``None`` or float NaN).

    ``DataFrame.apply(..., axis=1)`` can coerce a mostly-``None`` result column
    into the single shared ``float('nan')`` object, which is not ``None`` by
    identity. Treating only ``None`` as "no group" then makes every ungrouped
    record after the first look like it collides with an already-used group
    (same NaN object), catastrophically under-selecting. Both representations
    must be treated as "no group" everywhere a group value is compared.
    """
    return value is None or (isinstance(value, float) and value != value)


def _prepare(frame: pd.DataFrame, rule_labels: "pd.Series | None") -> pd.DataFrame:
    out = frame.copy()
    out["_bank"] = out["bank"].apply(normalise_bank) if "bank" in out.columns else "unknown"
    out["_text_length"] = out["text"].fillna("").astype(str).str.len()
    out["_year"] = (
        out["created_at"].fillna("").astype(str).str[:4]
        if "created_at" in out.columns
        else "unknown"
    )
    # Normalise explicitly to Python None so no group ever collapses onto the
    # shared NaN singleton (see _is_missing_group).
    out["_group"] = out.apply(_group_key, axis=1).apply(
        lambda v: None if _is_missing_group(v) else v
    )
    # v2 rule attribution is COVERAGE METADATA ONLY (Requirements 6.5).
    #
    # `rule_labels` is keyed by record_id (not by positional index), because the
    # labels are computed against the PARENT corpus whose row positions differ
    # from this materialised subset. Mapping by record_id is therefore the only
    # correct join; reindexing on the frame's own index would silently produce
    # all-missing labels.
    if rule_labels is not None:
        out["_v2_rule"] = (
            out["record_id"].astype(str).map(rule_labels).fillna("unknown")
        )
    else:
        out["_v2_rule"] = "unavailable"
    return out


def _counts(series) -> dict[str, int]:
    return {str(k): int(v) for k, v in sorted(series.value_counts().to_dict().items())}


def sample_south_africa(
    source_path: "str | Path",
    *,
    target_total: int = TARGET_TOTAL,
    per_bank_target: int = PER_BANK_TARGET,
    seed: int = DEFAULT_SEED,
    rule_labels: "pd.Series | None" = None,
    _dry_run: bool = False,
) -> tuple[pd.DataFrame, SouthAfricaSamplerReport]:
    """Draw the South African gold sample deterministically.

    Returns ``(selected_frame, report)``. The source file is only ever read.
    """
    path = Path(source_path)
    frame = pd.read_parquet(path)
    prepared = _prepare(frame, rule_labels)

    report = SouthAfricaSamplerReport(
        seed=seed,
        dry_run=_dry_run,
        source_file=str(path),
        source_sha256=_sha256_file(path),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        requested_total=target_total,
        available_total=int(len(prepared)),
    )

    for column in ("bank", "created_at", "near_dup_group_id", "previous_text", "context_available"):
        if column not in frame.columns:
            report.missing_fields.append(column)

    bands = compute_length_bands(prepared)
    report.length_bands = bands
    report.notes.append(
        "Length bands are computed from this corpus's own quantiles and are not "
        "shared with the international sources (Requirements 7.4)."
    )
    report.notes.append(
        "The v2 candidate rule is reported for coverage only and is never written "
        "to the annotation output (Requirements 6.5)."
    )

    prepared["_band"] = prepared["_text_length"].apply(
        lambda n: assign_length_band(int(n), bands)
    )

    report.available_by_bank = _counts(prepared["_bank"])
    report.year_distribution_available = _counts(prepared["_year"])
    report.rule_distribution_available = _counts(prepared["_v2_rule"])
    report.available_by_stratum = _counts(prepared["_band"])

    grouped = prepared["_group"].notna()
    report.duplicate_group_coverage = {
        "records_with_group": int(grouped.sum()),
        "records_without_group": int((~grouped).sum()),
        "distinct_groups": int(prepared.loc[grouped, "_group"].nunique()),
    }

    # Per-bank targets, restricted to the represented canonical banks.
    report.requested_by_bank = {bank: per_bank_target for bank in CANONICAL_BANKS}

    report.can_select_full_per_bank = all(
        report.available_by_bank.get(bank, 0) >= per_bank_target
        for bank in CANONICAL_BANKS
    )
    report.can_select_full_total = int(len(prepared)) >= target_total

    rng = np.random.Generator(np.random.PCG64(seed))

    selected: list[int] = []
    used_groups: set[str] = set()
    conflicts = 0
    per_bank_selected: dict[str, int] = {}
    per_stratum_selected: dict[str, int] = {}

    for bank in CANONICAL_BANKS:
        subset = prepared[prepared["_bank"] == bank]
        available = int(len(subset))
        if available == 0:
            report.shortages.append(
                {
                    "bank": bank,
                    "requested": per_bank_target,
                    "available": 0,
                    "selected": 0,
                    "shortfall": per_bank_target,
                    "reason": "no records for this bank in the source corpus",
                }
            )
            per_bank_selected[bank] = 0
            continue

        # Spread each bank's allocation across its length bands so coverage is
        # not dominated by one band.
        bands_present = sorted(subset["_band"].unique())
        base = per_bank_target // max(1, len(bands_present))
        taken_for_bank = 0

        for band in bands_present:
            band_subset = subset[subset["_band"] == band]
            indices = sorted(band_subset.index)
            order = rng.permutation(len(indices))
            want = base
            got = 0
            for position in order:
                if got >= want or taken_for_bank >= per_bank_target:
                    break
                index = indices[int(position)]
                group = prepared.at[index, "_group"]
                if not _is_missing_group(group) and group in used_groups:
                    conflicts += 1
                    continue
                selected.append(index)
                if not _is_missing_group(group):
                    used_groups.add(group)
                report.selection_reasons[str(prepared.at[index, "record_id"])] = (
                    f"bank={bank}; length_band={band}; "
                    f"year={prepared.at[index, '_year']}; "
                    f"v2_rule={prepared.at[index, '_v2_rule']}"
                )
                per_stratum_selected[band] = per_stratum_selected.get(band, 0) + 1
                got += 1
                taken_for_bank += 1

        # Top up this bank to its target from any remaining records.
        if taken_for_bank < per_bank_target:
            remaining = [i for i in sorted(subset.index) if i not in set(selected)]
            order = rng.permutation(len(remaining))
            for position in order:
                if taken_for_bank >= per_bank_target:
                    break
                index = remaining[int(position)]
                group = prepared.at[index, "_group"]
                if not _is_missing_group(group) and group in used_groups:
                    conflicts += 1
                    continue
                selected.append(index)
                if not _is_missing_group(group):
                    used_groups.add(group)
                band = prepared.at[index, "_band"]
                report.selection_reasons[str(prepared.at[index, "record_id"])] = (
                    f"bank={bank}; length_band={band}; "
                    f"year={prepared.at[index, '_year']}; "
                    f"v2_rule={prepared.at[index, '_v2_rule']}; topped_up"
                )
                per_stratum_selected[band] = per_stratum_selected.get(band, 0) + 1
                taken_for_bank += 1

        per_bank_selected[bank] = taken_for_bank
        if taken_for_bank < per_bank_target:
            report.shortages.append(
                {
                    "bank": bank,
                    "requested": per_bank_target,
                    "available": available,
                    "selected": taken_for_bank,
                    "shortfall": per_bank_target - taken_for_bank,
                    "reason": (
                        "insufficient records after duplicate/leakage-group "
                        "constraints; replacement sampling is prohibited"
                    ),
                }
            )

    report.selected_by_bank = dict(sorted(per_bank_selected.items()))
    report.selected_by_stratum = dict(sorted(per_stratum_selected.items()))
    report.selected_total = len(selected)
    report.duplicate_group_conflicts = conflicts

    for band in BAND_NAMES:
        if band in report.available_by_stratum and band not in per_stratum_selected:
            report.unsatisfied_strata.append(
                {
                    "stratum": band,
                    "available": report.available_by_stratum[band],
                    "selected": 0,
                    "reason": "no records selected from this length band",
                }
            )

    if len(selected) < target_total:
        report.shortages.append(
            {
                "scope": "total",
                "requested": target_total,
                "selected": len(selected),
                "shortfall": target_total - len(selected),
                "reason": "per-bank shortfalls accumulated; no replacement sampling",
            }
        )

    if selected:
        chosen = prepared.loc[selected]
        report.year_distribution_selected = _counts(chosen["_year"])
        report.rule_distribution_selected = _counts(chosen["_v2_rule"])
        if "context_available" in chosen.columns:
            true_count = int(chosen["context_available"].fillna(False).astype(bool).sum())
            report.context_availability = {
                "context_available_true": true_count,
                "context_available_false": int(len(chosen) - true_count),
            }

    if _dry_run:
        return prepared.loc[[]], report

    return prepared.loc[selected], report


def dry_run(
    source_path: "str | Path",
    *,
    target_total: int = TARGET_TOTAL,
    per_bank_target: int = PER_BANK_TARGET,
    seed: int = DEFAULT_SEED,
    rule_labels: "pd.Series | None" = None,
) -> SouthAfricaSamplerReport:
    """Report what sampling *would* do, selecting nothing and writing nothing."""
    _, report = sample_south_africa(
        source_path,
        target_total=target_total,
        per_bank_target=per_bank_target,
        seed=seed,
        rule_labels=rule_labels,
        _dry_run=True,
    )
    report.dry_run = True
    return report


def to_label_hidden_records(selected: pd.DataFrame) -> list[dict]:
    """Convert selected rows into label-hidden `new_pipeline_v1` records.

    No target, category, sentiment, or intent is inferred. The v2 candidate
    rule, length band, and every other sampling-only field are excluded so they
    cannot leak into human annotation (Requirements 6.5, 13.1).
    """
    records: list[dict] = []
    for _, row in selected.iterrows():
        def _clean(value):
            if value is None:
                return None
            if isinstance(value, float) and value != value:
                return None
            return value

        previous = row.get("previous_text")
        if previous is None or (isinstance(previous, float) and previous != previous):
            previous = _NO_CONTEXT

        year = str(row.get("created_at"))[:4]
        records.append(
            {
                "record_id": _clean(row.get("record_id")),
                "source": _clean(row.get("source")) or SOUTH_AFRICA_SOURCE,
                "region": _clean(row.get("region")) or "south_africa",
                "bank": _clean(row.get("bank")),
                "review_id": None,
                "thread_id": _clean(row.get("thread_id")),
                "conversation_id": None,
                "publish_year": int(year) if year.isdigit() else None,
                "text": _clean(row.get("text")),
                "previous_text": previous,
                "context_available": bool(row.get("context_available") is True),
                "duplicate_group": _clean(row.get("near_dup_group_id")),
                "leakage_group": _clean(row.get("_group")),
                "privacy_status": "anonymised",
                # Label-hidden: never inferred from candidate rules.
                "primary_intent": None,
                "public_warning": None,
                "opinions": [],
                "annotation_status": "not_started",
                "annotation_version": None,
                "annotation_notes": None,
            }
        )
    return records


def build_selection_manifest(report: SouthAfricaSamplerReport) -> dict:
    """The sample-selection manifest required by Requirements 7.5."""
    manifest = report.to_dict()
    manifest["requirements_reference"] = {
        "section_5_1": "represented banks",
        "section_7_1": "500 records, 100 per bank",
        "section_7_4": "source-specific quantile length bands",
        "section_7_5": "sampling outputs",
        "section_6_5": "candidate rules are not task labels",
    }
    manifest["replacement_sampling"] = False
    manifest["scope_note"] = (
        "South African sources only. Drawn from the VERIFIED materialised "
        "100,768-record v2 candidate corpus."
    )
    return manifest
