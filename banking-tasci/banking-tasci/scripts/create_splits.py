"""Split_Manager: partitions a validated, adjudicated Annotation_Record
JSONL file into leakage-safe train/validation/test manifests (Requirement 23).

Usage:
    python scripts/create_splits.py \\
        --input data/annotations/pilot_adjudicated.jsonl \\
        --output-dir data/processed \\
        --train-ratio 0.70 \\
        --validation-ratio 0.15 \\
        --test-ratio 0.15 \\
        --seed 42

Behavior (Req 23):
- 23.1: accepts --input, --output-dir, --train-ratio, --validation-ratio,
  --test-ratio, --seed.
- 23.2: refuses to run (non-zero exit, NO manifest written) when any record
  in --input fails `annotations.validate_all` -- it names the invalid record
  IDs on stderr and returns non-zero before writing anything.
- 23.3-23.5: every record sharing a leakage group (its originating
  review/thread/duplicate group) is assigned to a single split. The group
  key is the record's `source_record_id` when present (sentence-level review
  records from the same review share one), otherwise the record's own
  `record_id` (e.g. tweets, which have no originating parent).
- 23.6: assignment is stratified by `intent` where feasible.
- 23.7: region/source distributions are preserved across splits where
  feasible (a by-product of proportional per-stratum assignment).
- 23.8: writes train_manifest.csv/validation_manifest.csv/test_manifest.csv
  to --output-dir, each with at least a `record_id` column.
- 23.9: writes split_report.json summarizing sizes and distributions by
  source, region, intent, sentiment, and context availability.

`assign_groups_to_splits` is a pure, deterministic, seeded function so the
same groups/ratios/seed always produce the same assignment (used directly by
the determinism test). No global RNG state is touched.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data import annotations  # noqa: E402
from banking_tasci.data.annotations import AnnotationRecord  # noqa: E402

# Sentinel used by annotations.py for absent fields; treated as "no value".
_MISSING = annotations._MISSING

_SPLIT_NAMES = ("train", "validation", "test")
_RATIO_TOLERANCE = 1e-6

DEFAULT_TRAIN_RATIO = 0.70
DEFAULT_VALIDATION_RATIO = 0.15
DEFAULT_TEST_RATIO = 0.15


def build_arg_parser() -> argparse.ArgumentParser:
    """Defines --input, --output-dir, --train-ratio, --validation-ratio,
    --test-ratio, --seed (Req 23.1)."""
    parser = argparse.ArgumentParser(
        prog="create_splits.py",
        description=(
            "Partition a validated Annotation_Record JSONL file into "
            "leakage-safe train/validation/test manifests plus a "
            "split-distribution report."
        ),
    )
    parser.add_argument("--input", required=True, help="Path to the validated Annotation_Record JSONL file.")
    parser.add_argument("--output-dir", required=True, help="Directory to write the manifest CSVs and report.")
    parser.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO, help="Train split proportion.")
    parser.add_argument(
        "--validation-ratio", type=float, default=DEFAULT_VALIDATION_RATIO, help="Validation split proportion."
    )
    parser.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO, help="Test split proportion.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic assignment.")
    parser.add_argument(
        "--near-dup-csv",
        default=None,
        help=(
            "Optional path to the prepared canonical CSV (e.g. data/interim/prepared.csv). "
            "When supplied, near-duplicate group IDs (near_dup_group_id column) are read "
            "from this file and used as an additional leakage-prevention constraint: "
            "records sharing a near-dup group are placed in the same split."
        ),
    )
    return parser


def _clean(value):
    """Normalise the annotations `_MISSING` sentinel to None; leave other
    values untouched."""
    return None if value is _MISSING else value


def _read_source_record_ids(path: "str | Path") -> dict[str, str]:
    """Read `{record_id: source_record_id}` from the raw JSONL for every line
    that carries a truthy `source_record_id`.

    `source_record_id` is an extra leakage-grouping field (not part of the
    core Annotation_Record schema deserialised by `annotations.read_jsonl`),
    so it is read directly from the JSONL objects here."""
    mapping: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            record_id = obj.get("record_id")
            source_record_id = obj.get("source_record_id")
            if record_id is not None and source_record_id:
                mapping[str(record_id)] = str(source_record_id)
    return mapping


def group_key(record: AnnotationRecord) -> str:
    """Return the leakage-grouping key for `record` (Req 23.3-23.5).

    Uses the record's `source_record_id` attribute when present and truthy
    (sentence-level review records derived by `context.py` carry the
    originating review's id here, so all sentences of one review share a
    group). Falls back to the record's own `record_id` when
    `source_record_id` is absent (e.g. tweets, which have no parent).
    """
    source_record_id = _clean(getattr(record, "source_record_id", None))
    if source_record_id:
        return str(source_record_id)
    return str(_clean(getattr(record, "record_id", None)))


def _dominant_intent(records: list[AnnotationRecord]) -> str | None:
    """Most common non-null `intent` among a group's records, deterministic
    tie-break by label name. None when no record carries an intent."""
    counts: Counter = Counter()
    for record in records:
        intent = _clean(getattr(record, "intent", None))
        if intent:
            counts[intent] += 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]


def _dominant_source(records: list[AnnotationRecord]) -> str | None:
    for record in records:
        source = _clean(getattr(record, "source", None))
        if source:
            return str(source)
    return None


def assign_groups_to_splits(groups, ratios, seed, strata_key="intent") -> dict[str, str]:
    """Pure, deterministic, seeded assignment of whole groups to splits.

    Args:
        groups: mapping of `group_id -> attributes dict`. Each attributes
            dict may carry `intent`, `source`, `region`, etc. The value at
            `strata_key` (falling back to `source`, then a single shared
            bucket) determines the stratum a group is assigned within.
        ratios: `(train, validation, test)` proportions summing to ~1.0.
        seed: integer seed; a fresh `random.Random(seed)` drives all
            shuffling, so no global RNG state is read or mutated.
        strata_key: attribute name to stratify by (default `"intent"`,
            Req 23.6).

    Returns:
        `group_id -> split name` for every group id in `groups`.

    Determinism: group ids are processed in sorted order, strata in sorted
    order, and each stratum is shuffled by the same seeded RNG, so identical
    inputs always yield identical output.
    """
    train_ratio, validation_ratio, test_ratio = ratios
    rng = random.Random(seed)

    # Bucket group ids by stratum, deterministically.
    strata: dict[str, list[str]] = defaultdict(list)
    for group_id in sorted(groups.keys(), key=str):
        attributes = groups[group_id]
        stratum = None
        if isinstance(attributes, dict):
            stratum = attributes.get(strata_key)
            if stratum is None:
                stratum = attributes.get("source")
        if stratum is None:
            stratum = "__nostrata__"
        strata[str(stratum)].append(group_id)

    assignment: dict[str, str] = {}
    for stratum in sorted(strata.keys()):
        group_ids = sorted(strata[stratum], key=str)
        rng.shuffle(group_ids)
        n = len(group_ids)

        raw = {
            "train": n * train_ratio,
            "validation": n * validation_ratio,
            "test": n * test_ratio,
        }
        allocation = {name: int(math.floor(raw[name])) for name in _SPLIT_NAMES}
        remainder = n - sum(allocation.values())

        # Largest-remainder method: hand leftover groups to the splits with
        # the biggest fractional parts first, deterministic tie-break by the
        # fixed split order (train, validation, test).
        order = sorted(
            _SPLIT_NAMES,
            key=lambda name: (-(raw[name] - allocation[name]), _SPLIT_NAMES.index(name)),
        )
        i = 0
        while remainder > 0:
            allocation[order[i % len(order)]] += 1
            remainder -= 1
            i += 1

        idx = 0
        for name in _SPLIT_NAMES:
            for _ in range(allocation[name]):
                assignment[group_ids[idx]] = name
                idx += 1

    return assignment


def _read_near_dup_groups(csv_path: "str | Path") -> dict[str, str]:
    """Read {record_id: near_dup_group_id} from a prepared canonical CSV.

    Returns an empty dict when the file is absent, the column is missing,
    or any row lacks a near_dup_group_id value (those rows are simply
    omitted rather than raising).
    """
    import csv as _csv

    path = Path(csv_path)
    if not path.is_file():
        return {}
    mapping: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = _csv.DictReader(fh)
            if reader.fieldnames is None or "near_dup_group_id" not in reader.fieldnames:
                return {}
            for row in reader:
                rid = row.get("record_id")
                group = row.get("near_dup_group_id")
                if rid and group:
                    mapping[str(rid)] = str(group)
    except (OSError, Exception):
        return {}
    return mapping


def _write_manifest(record_ids: list[str], path: "str | Path") -> None:
    """Write a manifest CSV containing a `record_id` column (Req 23.8)."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id"])
        for record_id in record_ids:
            writer.writerow([record_id])


def _distribution_by(records: list[AnnotationRecord], attribute: str) -> dict[str, int]:
    counts: Counter = Counter()
    for record in records:
        value = _clean(getattr(record, attribute, None))
        counts[str(value)] += 1
    return dict(counts)


def _sentiment_distribution(records: list[AnnotationRecord]) -> dict[str, int]:
    counts: Counter = Counter()
    for record in records:
        aspects = getattr(record, "aspects", None)
        if isinstance(aspects, list):
            for aspect in aspects:
                sentiment = _clean(getattr(aspect, "sentiment", None))
                counts[str(sentiment)] += 1
    return dict(counts)


def _context_distribution(records: list[AnnotationRecord]) -> dict[str, int]:
    counts: Counter = Counter()
    for record in records:
        counts[str(bool(_clean(getattr(record, "context_available", None))))] += 1
    return dict(counts)


def _build_report(splits: dict[str, list[AnnotationRecord]], seed: int, ratios) -> dict:
    train_ratio, validation_ratio, test_ratio = ratios
    return {
        "seed": seed,
        "ratios": {"train": train_ratio, "validation": validation_ratio, "test": test_ratio},
        "sizes": {name: len(splits[name]) for name in _SPLIT_NAMES},
        "by_source": {name: _distribution_by(splits[name], "source") for name in _SPLIT_NAMES},
        "by_region": {name: _distribution_by(splits[name], "region") for name in _SPLIT_NAMES},
        "by_intent": {name: _distribution_by(splits[name], "intent") for name in _SPLIT_NAMES},
        "by_sentiment": {name: _sentiment_distribution(splits[name]) for name in _SPLIT_NAMES},
        "by_context_availability": {name: _context_distribution(splits[name]) for name in _SPLIT_NAMES},
    }


def main(argv: list[str] | None = None) -> int:
    """Read --input, refuse to run if any record is invalid (Req 23.2),
    group records by leakage group, assign whole groups to splits, and write
    the manifests plus split_report.json to --output-dir."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    ratios = (args.train_ratio, args.validation_ratio, args.test_ratio)
    if abs(sum(ratios) - 1.0) > _RATIO_TOLERANCE:
        print(
            f"Error: --train-ratio + --validation-ratio + --test-ratio must sum to 1.0 "
            f"(got {sum(ratios)}).",
            file=sys.stderr,
        )
        return 1

    try:
        records = annotations.read_jsonl(args.input)
        source_record_ids = _read_source_record_ids(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read --input '{args.input}': {exc}", file=sys.stderr)
        return 1

    # `annotations.read_jsonl` only materialises the core Annotation_Record
    # schema; `source_record_id` is an extra leakage-grouping field carried by
    # sentence-level review records (added by context.py). Re-attach it from
    # the raw JSONL so `group_key` can group review sentences correctly.
    for record in records:
        rid = _clean(getattr(record, "record_id", None))
        if rid is not None and str(rid) in source_record_ids:
            record.source_record_id = source_record_ids[str(rid)]

    # Near-duplicate leakage prevention: when a prepared CSV is supplied,
    # read near_dup_group_id and use it to further merge leakage groups so
    # near-duplicate records never cross split boundaries (Req 14).
    near_dup_groups: dict[str, str] = {}
    if args.near_dup_csv:
        near_dup_groups = _read_near_dup_groups(args.near_dup_csv)

    # Hard precondition (Req 23.2): refuse to run on unvalidated input,
    # writing NO manifest, when any record fails validation.
    valid_records, invalid = annotations.validate_all(records)
    if invalid:
        invalid_ids = ", ".join(sorted(invalid.keys()))
        print(
            f"Error: refusing to create splits -- {len(invalid)} record(s) failed validation: {invalid_ids}",
            file=sys.stderr,
        )
        return 1

    # Group records by leakage group (Req 23.3-23.5).
    groups_records: dict[str, list[AnnotationRecord]] = defaultdict(list)
    for record in valid_records:
        rid = str(_clean(getattr(record, "record_id", None)))
        # Use near-dup group ID when available (overrides individual record_id
        # leakage key so near-duplicate records stay together across splits).
        nd_group = near_dup_groups.get(rid)
        if nd_group:
            # Merge near-dup group into leakage group: use the near-dup group
            # ID directly (it already represents the canonical group key).
            effective_key = f"nd:{nd_group}"
        else:
            effective_key = group_key(record)
        groups_records[effective_key].append(record)

    # Per-group attributes used for stratification (Req 23.6) and reporting.
    group_attributes: dict[str, dict] = {}
    for gid, recs in groups_records.items():
        group_attributes[gid] = {
            "intent": _dominant_intent(recs),
            "source": _dominant_source(recs),
        }

    group_to_split = assign_groups_to_splits(group_attributes, ratios, args.seed, strata_key="intent")

    splits: dict[str, list[AnnotationRecord]] = {name: [] for name in _SPLIT_NAMES}
    for gid, recs in groups_records.items():
        split_name = group_to_split[gid]
        splits[split_name].extend(recs)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name in _SPLIT_NAMES:
        record_ids = [str(_clean(getattr(r, "record_id", None))) for r in splits[name]]
        _write_manifest(record_ids, output_dir / f"{name}_manifest.csv")

    report = _build_report(splits, args.seed, ratios)
    (output_dir / "split_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
