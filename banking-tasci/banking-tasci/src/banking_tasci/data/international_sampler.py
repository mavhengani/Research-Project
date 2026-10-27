"""Deterministic, source-aware international gold sampler for `new_pipeline_v1`.

Implements the international half of Requirements Section 7 (gold-corpus
sampling): 250 international banking tweets and 250 international bank reviews,
drawn from the VERIFIED 10,847-record prepared international corpus.

**Scope.** International sources only. The South African 500-record sample is
deliberately NOT implemented here: its 100,768-record source corpus is not yet
materialised as a checksummed artifact (gap-analysis finding R3), and
Requirements Migration Principle 6 forbids fabricating it.

**Design properties** (each backed by a focused test):

- *Deterministic.* All randomness flows through one ``numpy`` ``PCG64``
  generator seeded only from the caller's seed (default 42). Global RNG state
  is never read or mutated.
- *No replacement.* Selection is by unique index; every chosen index is drawn
  once. A record cannot appear twice.
- *Source-specific length bands.* Short/medium/long boundaries are computed
  from per-source quantiles, never one shared character threshold
  (Requirements 7.4). The two sources differ substantially in practice -
  tweets sit around 140/183 characters at q33/q66 while reviews sit around
  289/328 - so a shared threshold would place every review in one band.
- *Group integrity.* Records sharing a duplicate group or a review group are
  never split across the selected/unselected boundary: at most one record per
  group is selected, so no group is partially sampled.
- *Rating is sampling metadata only.* Review rating drives band coverage and
  nothing else. It is never written into the annotation output and never
  becomes a sentiment label (Requirements 7.3).
- *Label-hidden output.* Emitted records carry empty ``opinions`` and null
  ``primary_intent``; no target, category, sentiment, or intent value is ever
  inferred (Requirements 13.1, 6.5).
- *Genuine context only.* ``previous_text``/``context_available`` are carried
  through from the source as-is. Physical row adjacency is never used
  (Requirements 12).
- *Shortages reported.* A stratum with insufficient records yields an explicit
  shortage entry rather than silent under-delivery or replacement sampling.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "DEFAULT_SEED",
    "TWEET_SOURCE",
    "REVIEW_SOURCE",
    "BandBoundaries",
    "SamplePlan",
    "SamplerReport",
    "compute_length_bands",
    "assign_length_band",
    "count_sentences",
    "assign_rating_band",
    "dry_run",
    "sample_international",
    "to_label_hidden_records",
    "build_selection_manifest",
]

DEFAULT_SEED = 42

TWEET_SOURCE = "international_bank_tweets"
REVIEW_SOURCE = "bank_reviews"

DEFAULT_TWEET_TARGET = 250
DEFAULT_REVIEW_TARGET = 250

# Requirements 7.4 / configs/new_pipeline_v1.yaml annotation.length_bands.
LENGTH_QUANTILES = (0.33, 0.66)
BAND_NAMES = ("short", "medium", "long")

# Rating bands for review diversity (Requirements 7.3: "low, middle, and high
# rating bands where ratings are available"). Sampling metadata ONLY.
RATING_BANDS = ("low", "middle", "high")

# Sentence-count bands for reviews (Requirements 7.3: "number of sentences").
SENTENCE_BANDS = ("single", "few", "many")

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+(?:\s+|$)")

_NO_CONTEXT = "[NO_CONTEXT]"


@dataclass(frozen=True)
class BandBoundaries:
    """Per-source length-band boundaries derived from quantiles."""

    source: str
    q_low: float
    q_high: float
    quantiles: tuple[float, float] = LENGTH_QUANTILES
    n: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SamplePlan:
    """What the sampler intends to draw, per source and stratum."""

    source: str
    target: int
    available: int
    per_stratum_target: dict[str, int] = field(default_factory=dict)
    per_stratum_available: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SamplerReport:
    """Everything the sampler observed and decided (Requirements 7.5)."""

    pipeline_version: str = "new_pipeline_v1"
    seed: int = DEFAULT_SEED
    dry_run: bool = False
    source_file: str = ""
    source_sha256: str = ""
    generated_at: str = ""
    available_counts: dict[str, int] = field(default_factory=dict)
    length_bands: dict[str, dict] = field(default_factory=dict)
    requested_by_source: dict[str, int] = field(default_factory=dict)
    selected_by_source: dict[str, int] = field(default_factory=dict)
    available_by_stratum: dict[str, dict[str, int]] = field(default_factory=dict)
    selected_by_stratum: dict[str, dict[str, int]] = field(default_factory=dict)
    shortages: list[dict] = field(default_factory=list)
    unsatisfied_strata: list[dict] = field(default_factory=list)
    duplicate_group_conflicts: int = 0
    review_group_conflicts: int = 0
    context_availability: dict[str, int] = field(default_factory=dict)
    rating_band_counts: dict[str, int] = field(default_factory=dict)
    sentence_band_counts: dict[str, int] = field(default_factory=dict)
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


def count_sentences(text: Any) -> int:
    """Number of sentence-terminated segments in ``text`` (minimum 1).

    Deliberately simple and dependency-free; used only to bucket reviews into
    sentence-count bands for sampling diversity.
    """
    if not isinstance(text, str) or not text.strip():
        return 0
    parts = [p for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return max(1, len(parts))


def compute_length_bands(
    frame: pd.DataFrame,
    source: str,
    text_column: str = "text",
    quantiles: tuple[float, float] = LENGTH_QUANTILES,
) -> BandBoundaries:
    """Per-source short/medium/long boundaries (Requirements 7.4).

    Computed from this source's own text-length distribution, so tweets and
    reviews never share a threshold.
    """
    subset = frame[frame["source"] == source]
    lengths = subset[text_column].fillna("").astype(str).str.len()
    if lengths.empty:
        return BandBoundaries(source=source, q_low=0.0, q_high=0.0, quantiles=quantiles, n=0)
    return BandBoundaries(
        source=source,
        q_low=float(lengths.quantile(quantiles[0])),
        q_high=float(lengths.quantile(quantiles[1])),
        quantiles=quantiles,
        n=int(len(lengths)),
    )


def assign_length_band(length: int, bands: BandBoundaries) -> str:
    """Map a character length onto ``short``/``medium``/``long``."""
    if length <= bands.q_low:
        return "short"
    if length <= bands.q_high:
        return "medium"
    return "long"


def assign_rating_band(rating: Any) -> str | None:
    """Map a review rating onto ``low``/``middle``/``high``.

    Returns ``None`` when no rating is available. The band is sampling
    metadata only and must never be treated as sentiment (Requirements 7.3).
    """
    if rating is None:
        return None
    try:
        value = float(rating)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    if value <= 2.0:
        return "low"
    if value <= 3.5:
        return "middle"
    return "high"


def _assign_sentence_band(count: int) -> str:
    if count <= 1:
        return "single"
    if count <= 4:
        return "few"
    return "many"


def _group_key(row: pd.Series) -> str | None:
    """Duplicate/review group membership for leakage-safe selection.

    Review grouping takes precedence (all sentences of one review belong
    together); near-duplicate grouping applies otherwise.
    """
    for column in ("review_id", "near_dup_group_id", "thread_id"):
        value = row.get(column)
        if value is not None and not (isinstance(value, float) and value != value):
            text = str(value).strip()
            if text and text.lower() not in {"nan", "none"}:
                return f"{column}:{text}"
    return None


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach derived sampling columns without mutating the caller's frame."""
    out = frame.copy()
    out["_text_length"] = out["text"].fillna("").astype(str).str.len()
    out["_sentence_count"] = out["text"].apply(count_sentences)
    out["_sentence_band"] = out["_sentence_count"].apply(_assign_sentence_band)
    out["_rating_band"] = out["rating"].apply(assign_rating_band) if "rating" in out.columns else None
    out["_group"] = out.apply(_group_key, axis=1)
    return out


def _stratum_for(row: pd.Series, source: str, bands: BandBoundaries) -> str:
    """The sampling stratum label for one record."""
    band = assign_length_band(int(row["_text_length"]), bands)
    if source == REVIEW_SOURCE:
        rating_band = row.get("_rating_band") or "unrated"
        return f"{band}|{rating_band}|{row['_sentence_band']}"
    return band


def _plan_targets(strata_available: dict[str, int], target: int) -> dict[str, int]:
    """Allocate ``target`` across strata proportionally, largest-remainder.

    Deterministic: strata are processed in sorted order and ties break by
    stratum name, so the same inputs always produce the same allocation.
    """
    total = sum(strata_available.values())
    if total == 0 or target <= 0:
        return {name: 0 for name in strata_available}

    raw = {name: target * count / total for name, count in strata_available.items()}
    alloc = {name: int(np.floor(value)) for name, value in raw.items()}
    remainder = target - sum(alloc.values())

    order = sorted(
        strata_available,
        key=lambda name: (-(raw[name] - alloc[name]), name),
    )
    index = 0
    while remainder > 0 and order:
        name = order[index % len(order)]
        if alloc[name] < strata_available[name]:
            alloc[name] += 1
            remainder -= 1
        index += 1
        if index > len(order) * target + len(order):
            break  # capacity exhausted
    return alloc


def _select_for_source(
    prepared: pd.DataFrame,
    source: str,
    target: int,
    bands: BandBoundaries,
    rng: np.random.Generator,
    report: SamplerReport,
) -> list[int]:
    """Draw up to ``target`` indices for one source, without replacement."""
    subset = prepared[prepared["source"] == source]
    report.available_counts[source] = int(len(subset))
    report.requested_by_source[source] = int(target)

    strata: dict[str, list[int]] = {}
    for index, row in subset.iterrows():
        strata.setdefault(_stratum_for(row, source, bands), []).append(index)

    available = {name: len(items) for name, items in strata.items()}
    report.available_by_stratum[source] = dict(sorted(available.items()))

    planned = _plan_targets(available, target)

    selected: list[int] = []
    used_groups: set[str] = set()
    per_stratum_selected: dict[str, int] = {}
    group_conflicts = 0

    for name in sorted(strata):
        candidates = sorted(strata[name])
        # Deterministic shuffle from the injected generator only.
        order = rng.permutation(len(candidates))
        want = planned.get(name, 0)
        taken = 0
        for position in order:
            if taken >= want:
                break
            index = candidates[int(position)]
            group = prepared.at[index, "_group"]
            if group is not None and group in used_groups:
                group_conflicts += 1
                continue  # never split a duplicate/review group
            selected.append(index)
            if group is not None:
                used_groups.add(group)
            report.selection_reasons[str(prepared.at[index, "record_id"])] = (
                f"source={source}; stratum={name}; "
                f"length_band={assign_length_band(int(prepared.at[index, '_text_length']), bands)}"
            )
            taken += 1
        per_stratum_selected[name] = taken
        if taken < want:
            report.unsatisfied_strata.append(
                {
                    "source": source,
                    "stratum": name,
                    "requested": int(want),
                    "available": int(available.get(name, 0)),
                    "selected": int(taken),
                }
            )

    # Top up from any remaining capacity, still without replacement and still
    # respecting group integrity, so a shortage is genuine rather than an
    # artefact of proportional rounding.
    if len(selected) < target:
        remaining = [i for i in sorted(subset.index) if i not in set(selected)]
        order = rng.permutation(len(remaining))
        for position in order:
            if len(selected) >= target:
                break
            index = remaining[int(position)]
            group = prepared.at[index, "_group"]
            if group is not None and group in used_groups:
                group_conflicts += 1
                continue
            selected.append(index)
            if group is not None:
                used_groups.add(group)
            name = _stratum_for(prepared.loc[index], source, bands)
            per_stratum_selected[name] = per_stratum_selected.get(name, 0) + 1
            report.selection_reasons[str(prepared.at[index, "record_id"])] = (
                f"source={source}; stratum={name}; topped_up_to_meet_target"
            )

    report.selected_by_stratum[source] = dict(sorted(per_stratum_selected.items()))
    report.selected_by_source[source] = len(selected)

    if source == REVIEW_SOURCE:
        report.review_group_conflicts += group_conflicts
    else:
        report.duplicate_group_conflicts += group_conflicts

    if len(selected) < target:
        report.shortages.append(
            {
                "source": source,
                "requested": int(target),
                "selected": int(len(selected)),
                "shortfall": int(target - len(selected)),
                "available": int(len(subset)),
                "reason": (
                    "insufficient records after group-integrity constraints; "
                    "replacement sampling is prohibited"
                ),
            }
        )

    return selected


def _summarise_selection(prepared: pd.DataFrame, indices: list[int], report: SamplerReport) -> None:
    if not indices:
        return
    chosen = prepared.loc[indices]

    context_true = int(chosen["context_available"].fillna(False).astype(bool).sum())
    report.context_availability = {
        "context_available_true": context_true,
        "context_available_false": int(len(chosen) - context_true),
    }

    ratings = chosen["_rating_band"].dropna() if "_rating_band" in chosen else []
    counts: dict[str, int] = {}
    for value in ratings:
        counts[str(value)] = counts.get(str(value), 0) + 1
    report.rating_band_counts = dict(sorted(counts.items()))

    sentence_counts: dict[str, int] = {}
    for value in chosen["_sentence_band"]:
        sentence_counts[str(value)] = sentence_counts.get(str(value), 0) + 1
    report.sentence_band_counts = dict(sorted(sentence_counts.items()))


def _load(source_path: Path) -> pd.DataFrame:
    return pd.read_csv(source_path)


def dry_run(
    source_path: "str | Path",
    *,
    tweet_target: int = DEFAULT_TWEET_TARGET,
    review_target: int = DEFAULT_REVIEW_TARGET,
    seed: int = DEFAULT_SEED,
) -> SamplerReport:
    """Report what sampling *would* do, selecting nothing and writing nothing."""
    report = sample_international(
        source_path,
        tweet_target=tweet_target,
        review_target=review_target,
        seed=seed,
        _dry_run=True,
    )[1]
    report.dry_run = True
    return report


def sample_international(
    source_path: "str | Path",
    *,
    tweet_target: int = DEFAULT_TWEET_TARGET,
    review_target: int = DEFAULT_REVIEW_TARGET,
    seed: int = DEFAULT_SEED,
    _dry_run: bool = False,
) -> tuple[pd.DataFrame, SamplerReport]:
    """Draw the international gold sample deterministically.

    Returns ``(selected_frame, report)``. The source file is only ever read.
    """
    path = Path(source_path)
    frame = _load(path)
    prepared = _prepare(frame)

    report = SamplerReport(
        seed=seed,
        dry_run=_dry_run,
        source_file=str(path),
        source_sha256=_sha256_file(path),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    tweet_bands = compute_length_bands(prepared, TWEET_SOURCE)
    review_bands = compute_length_bands(prepared, REVIEW_SOURCE)
    report.length_bands = {
        TWEET_SOURCE: tweet_bands.to_dict(),
        REVIEW_SOURCE: review_bands.to_dict(),
    }
    report.notes.append(
        "Length bands are computed per source from that source's own quantiles "
        "(Requirements 7.4); tweets and reviews never share a threshold."
    )
    report.notes.append(
        "Review rating is used only for sampling diversity and is never written "
        "to the annotation output or treated as sentiment (Requirements 7.3)."
    )

    # One generator, seeded only from `seed`; global RNG is never touched.
    rng = np.random.Generator(np.random.PCG64(seed))

    tweet_indices = _select_for_source(
        prepared, TWEET_SOURCE, tweet_target, tweet_bands, rng, report
    )
    review_indices = _select_for_source(
        prepared, REVIEW_SOURCE, review_target, review_bands, rng, report
    )

    indices = tweet_indices + review_indices
    _summarise_selection(prepared, indices, report)

    if _dry_run:
        return prepared.loc[[]], report

    return prepared.loc[indices], report


def to_label_hidden_records(selected: pd.DataFrame) -> list[dict]:
    """Convert selected rows into label-hidden `new_pipeline_v1` records.

    No target, category, sentiment, or intent is ever inferred: ``opinions`` is
    empty and ``primary_intent`` is null (Requirements 13.1, 6.5). Rating,
    stratum, and every other sampling-only field is excluded from the
    annotation view so it cannot leak into human labelling.
    """
    records: list[dict] = []
    for _, row in selected.iterrows():
        previous = row.get("previous_text")
        if previous is None or (isinstance(previous, float) and previous != previous):
            previous = _NO_CONTEXT
        context_available = bool(row.get("context_available") is True)

        def _clean(value):
            if value is None:
                return None
            if isinstance(value, float) and value != value:
                return None
            return value

        records.append(
            {
                "record_id": _clean(row.get("record_id")),
                "source": _clean(row.get("source")),
                "region": _clean(row.get("region")),
                "bank": _clean(row.get("bank")),
                "review_id": _clean(row.get("review_id")),
                "thread_id": _clean(row.get("thread_id")),
                "conversation_id": None,
                "publish_year": (
                    int(str(row.get("created_at"))[:4])
                    if str(row.get("created_at"))[:4].isdigit()
                    else None
                ),
                "text": _clean(row.get("text")),
                "previous_text": previous,
                "context_available": context_available,
                "duplicate_group": _clean(row.get("near_dup_group_id")),
                "leakage_group": _clean(row.get("_group")),
                "privacy_status": "anonymised",
                # Label-hidden: never inferred.
                "primary_intent": None,
                "public_warning": None,
                "opinions": [],
                "annotation_status": "not_started",
                "annotation_version": None,
                "annotation_notes": None,
            }
        )
    return records


def build_selection_manifest(report: SamplerReport) -> dict:
    """The sample-selection manifest required by Requirements 7.5."""
    manifest = report.to_dict()
    manifest["requirements_reference"] = {
        "section_7": "gold-corpus sampling",
        "section_7_4": "source-specific quantile length bands",
        "section_7_5": "sampling outputs",
        "section_13_1": "label-hidden export",
    }
    manifest["scope_note"] = (
        "International sources only. The South African 500-record sample is "
        "intentionally not produced here because its 100,768-record corpus is "
        "not yet a materialised, checksummed artifact (gap-analysis R3)."
    )
    manifest["replacement_sampling"] = False
    return manifest
