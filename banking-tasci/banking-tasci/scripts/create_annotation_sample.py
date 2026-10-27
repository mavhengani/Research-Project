"""Annotation_Sampler: draws a deterministic, diversity-preserving pilot
annotation sample from `data/interim/prepared.csv` (Requirement 17).

Usage:
    python scripts/create_annotation_sample.py \\
        --input data/interim/prepared.csv \\
        --output data/annotations/pilot_unannotated.jsonl \\
        --size 600 \\
        --seed 42

Wires `banking_tasci.data.context` to expand each `prepared.csv` row into
one or more annotatable units (one per sentence for `bank_reviews` rows,
one per row for `international_bank_tweets` rows), draws a seeded
stratified sample that preserves source/region/rating/text-length/
context-availability proportions where the data supports it, converts the
sample into unannotated `Annotation_Record`s, and writes both the JSONL
output and a JSON sample-composition report.

No gold aspect/sentiment/intent label is ever read or used while
selecting the sample (Req 17.4) -- none exists at this stage, since these
records come straight from Phase 1's canonical schema, which has no such
fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data import context  # noqa: E402
from banking_tasci.data.annotations import AnnotationRecord, write_jsonl  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "base.yaml"
_DEFAULT_REPORT_PATH = PROJECT_ROOT / "outputs" / "annotation_sample_report.json"


def build_arg_parser() -> argparse.ArgumentParser:
    """Defines --input, --output, --size, --seed (Req 17.1), plus optional
    --config and --report for wiring configuration and the report path."""
    parser = argparse.ArgumentParser(
        prog="create_annotation_sample.py",
        description=(
            "Draw a deterministic, diversity-preserving pilot annotation "
            "sample from a canonical prepared.csv and write it as "
            "unannotated Annotation_Records plus a sample composition "
            "report."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the canonical prepared.csv (Phase 1 output).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the unannotated Annotation_Record JSONL file.",
    )
    parser.add_argument(
        "--size",
        required=True,
        type=int,
        help="Number of annotatable units to sample.",
    )
    parser.add_argument(
        "--seed",
        required=True,
        type=int,
        help="Random seed for deterministic, reproducible sampling.",
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="Path to the YAML configuration file (default: configs/base.yaml).",
    )
    parser.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT_PATH),
        help="Path to write the JSON sample report (default: outputs/annotation_sample_report.json).",
    )
    return parser


def build_annotatable_pool(prepared_df: "pd.DataFrame", cfg) -> list[dict]:
    """Expand every `prepared_df` row into one or more annotatable dicts.

    `bank_reviews`-sourced rows are split by `context.build_review_sentence_
    records` into one dict per sentence; `international_bank_tweets`-sourced
    rows become a single dict via `context.build_tweet_record` (with
    `thread_map=None`, since no thread data exists for this source). Rows
    with any other `source` value are skipped defensively.

    Because `context.build_review_sentence_records` deliberately leaves
    `record_id` as the ORIGINAL review's id on every sentence it emits (so
    later split logic can group them via `source_record_id`), sentence-level
    dicts here are given a fresh, deterministic, unique `record_id` of the
    form `"{original_record_id}::s{sentence_index}"` before entering the
    pool -- otherwise multiple sampled sentences from the same review would
    collide on `record_id` once converted to Annotation_Records.
    """
    reviews_source = cfg.data.reviews_source_name
    tweets_source = cfg.data.tweets_source_name

    pool: list[dict] = []
    for row in prepared_df.to_dict(orient="records"):
        source = row.get("source")
        if source == reviews_source:
            original_record_id = row.get("record_id")
            sentence_records = context.build_review_sentence_records(row)
            for sentence_index, sentence_record in enumerate(sentence_records):
                sentence_record["record_id"] = f"{original_record_id}::s{sentence_index}"
                pool.append(sentence_record)
        elif source == tweets_source:
            pool.append(context.build_tweet_record(row, thread_map=None))
    return pool


def _stratum_key(item: dict) -> tuple:
    """(source, context_available) -- the bucket used for proportional
    stratified sampling (Req 17.3)."""
    return (item.get("source"), bool(item.get("context_available")))


def stratified_sample(pool: list[dict], size: int, seed: int) -> list[dict]:
    """Deterministic stratified draw of `size` items from `pool`.

    Stratifies by `(source, context_available)` and allocates the sample
    proportionally to each stratum's share of the pool (largest-remainder
    rounding, with graceful fallback -- and redistribution of any shortfall
    to other strata -- when a stratum is smaller than its proportional
    allocation), then draws without replacement within each stratum using a
    `numpy.random.Generator(numpy.random.PCG64(seed))` seeded ONLY from
    `seed`, never from global RNG state. This makes the same `pool`/`size`/
    `seed` always produce the same sampled set (Req 17.2).

    Never reads or reasons about any gold-label field (Req 17.4) -- only
    `source` and `context_available` (both present on every Phase-1
    canonical record, well before any annotation happens) drive selection.
    """
    n = len(pool)
    if size <= 0 or n == 0:
        return []

    rng = np.random.Generator(np.random.PCG64(seed))

    if size >= n:
        order = rng.permutation(n)
        return [pool[int(i)] for i in order]

    strata: dict[tuple, list[int]] = {}
    for idx, item in enumerate(pool):
        strata.setdefault(_stratum_key(item), []).append(idx)

    # Deterministic stratum ordering, independent of dict iteration order.
    keys = sorted(strata.keys(), key=lambda k: (str(k[0]), bool(k[1])))

    raw_allocations = {key: size * len(strata[key]) / n for key in keys}
    allocations = {key: int(np.floor(raw_allocations[key])) for key in keys}
    remainder = size - sum(allocations.values())

    # Largest-remainder method: give the leftover units to the strata with
    # the biggest fractional part first, deterministic tie-break by key.
    by_fraction = sorted(
        keys,
        key=lambda k: (-(raw_allocations[k] - allocations[k]), str(k[0]), bool(k[1])),
    )
    i = 0
    while remainder > 0:
        key = by_fraction[i % len(by_fraction)]
        allocations[key] += 1
        remainder -= 1
        i += 1

    # A stratum cannot be allocated more than it actually contains; push any
    # such overflow onto strata that still have spare capacity (Req 17.3's
    # "graceful fallback" for under-sized strata).
    overflow = 0
    for key in keys:
        capacity = len(strata[key])
        if allocations[key] > capacity:
            overflow += allocations[key] - capacity
            allocations[key] = capacity

    while overflow > 0:
        capacity_remaining = {key: len(strata[key]) - allocations[key] for key in keys}
        available = [key for key in keys if capacity_remaining[key] > 0]
        if not available:
            break  # entire pool exhausted; size >= n already handled above
        for key in available:
            if overflow <= 0:
                break
            allocations[key] += 1
            overflow -= 1

    selected_indices: list[int] = []
    for key in keys:
        stratum_indices = strata[key]
        take = allocations[key]
        if take <= 0:
            continue
        if take >= len(stratum_indices):
            selected_indices.extend(stratum_indices)
        else:
            chosen = rng.choice(np.array(stratum_indices), size=take, replace=False)
            selected_indices.extend(int(c) for c in chosen)

    selected_indices = sorted(set(selected_indices))
    return [pool[i] for i in selected_indices]


def to_unannotated_records(sample: list[dict]) -> list[AnnotationRecord]:
    """Map each sampled annotatable dict to an unannotated `AnnotationRecord`
    (Req 17.5): `aspects=[]`, `intent=None`, `intent_ambiguous=False`,
    `alternative_intent=None`, `annotator_id=""`,
    `annotation_status="not_started"`, `notes=""`, carrying over
    `record_id`/`source`/`region`/`text`/`previous_text`/`context_available`
    as produced by `build_annotatable_pool`."""
    return [
        AnnotationRecord(
            record_id=item.get("record_id"),
            source=item.get("source"),
            region=item.get("region"),
            text=item.get("text"),
            previous_text=item.get("previous_text"),
            context_available=item.get("context_available"),
            aspects=[],
            intent=None,
            intent_ambiguous=False,
            alternative_intent=None,
            annotator_id="",
            annotation_status="not_started",
            notes="",
        )
        for item in sample
    ]


def _to_native(value):
    """Best-effort conversion of a numpy/pandas scalar to a plain Python
    value, so `json.dumps` never chokes on `numpy.float64`/`numpy.int64`
    and NaN is normalised to `None`."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write_sample_report(sample: list[dict], seed: int, path: "str | Path") -> None:
    """Write the JSON sample-composition report required by Req 17.6:
    counts by source, counts by region, context-availability counts, a
    text-length distribution summary (min/max/mean/quartiles), a rating
    distribution where available, the count of multi-sentence reviews
    represented in the sample, and the seed used."""
    source_counts = Counter(item.get("source") for item in sample)
    region_counts = Counter(item.get("region") for item in sample)
    context_true = sum(1 for item in sample if item.get("context_available") is True)
    context_false = sum(1 for item in sample if item.get("context_available") is False)

    lengths = [len(item.get("text") or "") for item in sample]
    if lengths:
        arr = np.asarray(lengths, dtype=float)
        text_length_distribution = {
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
            "q1": float(np.percentile(arr, 25)),
            "median": float(np.percentile(arr, 50)),
            "q3": float(np.percentile(arr, 75)),
        }
    else:
        text_length_distribution = {"min": None, "max": None, "mean": None, "q1": None, "median": None, "q3": None}

    rating_counts: Counter = Counter()
    for item in sample:
        rating = _to_native(item.get("rating"))
        if rating is not None:
            rating_counts[rating] += 1

    # A review is "multi-sentence [and] represented" when more than one of
    # its sentence-records made it into the sample. Only review-derived
    # dicts carry `source_record_id` (tweets do not).
    per_review_counts = Counter(
        item.get("source_record_id") for item in sample if item.get("source_record_id") is not None
    )
    multi_sentence_review_count = sum(1 for count in per_review_counts.values() if count > 1)

    report = {
        "seed": seed,
        "sample_size": len(sample),
        "counts_by_source": dict(source_counts),
        "counts_by_region": dict(region_counts),
        "context_available_true_count": context_true,
        "context_available_false_count": context_false,
        "text_length_distribution": text_length_distribution,
        "rating_distribution": {str(k): v for k, v in rating_counts.items()},
        "multi_sentence_review_count": multi_sentence_review_count,
    }

    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Parse args -> load_config -> read --input as a DataFrame ->
    build_annotatable_pool -> stratified_sample -> to_unannotated_records ->
    write_jsonl to --output -> write_sample_report to --report -> return 0."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    cfg = load_config(args.config)

    prepared_df = pd.read_csv(args.input)

    pool = build_annotatable_pool(prepared_df, cfg)
    sample = stratified_sample(pool, args.size, args.seed)
    records = to_unannotated_records(sample)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(records, output_path)

    write_sample_report(sample, args.seed, args.report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
