#!/usr/bin/env python3
"""Generate `new_pipeline_v1` source manifests (Requirements Sections 4, 25).

Phase 2 tooling. Records row count, checksum, schema, source/region, bank and
year distributions, duplicate-group coverage, privacy status, candidate-status
field, generation command, and pipeline version for each configured source.

**This script never fabricates a count.** When a source's observed row count
does not match the expected count in ``configs/new_pipeline_v1.yaml``, the
manifest records ``REQUIRES_DATA_CONFIRMATION`` with both numbers and their
difference, and the script exits non-zero. It does not sample, truncate, or
filter to reach an expected number (Requirements Migration Principle 6: "Do not
fabricate annotations, identifiers, context, or metrics").

Usage::

    # Both configured sources, writing to artifacts/manifests/new_pipeline_v1/
    python scripts/generate_source_manifest.py

    # One source
    python scripts/generate_source_manifest.py --source international

    # Custom file, no expected count (pure description, always VERIFIED)
    python scripts/generate_source_manifest.py \\
        --input data/interim/prepared.csv \\
        --output artifacts/manifests/new_pipeline_v1/ad_hoc.json \\
        --no-expected

Exit codes:

- ``0`` every requested manifest is VERIFIED
- ``2`` at least one manifest is REQUIRES_DATA_CONFIRMATION or FILE_MISSING
- ``1`` usage or configuration error
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.manifest import (  # noqa: E402
    STATUS_VERIFIED,
    build_manifest,
    write_manifest,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "new_pipeline_v1.yaml"

# Known sources, mapped to their file, the config key holding the expected
# count, and their source/region labels.
SOURCES: dict[str, dict] = {
    "south_africa": {
        "input": "data/interim/south_africa_prepared.parquet",
        "expected_count_key": "south_africa_candidates",
        "source": "south_african_bank_tweets",
        "region": "south_africa",
        "output": "south_africa_source_manifest.json",
        # The expected 100,768 count is NOT this file's raw row count
        # (2,250,776). It is the output of the v2 evidence-based candidate
        # filter, reproducibly derived from this immutable source. Recording
        # the derivation here makes the mismatch explained rather than
        # unexplained, without ever coercing the observed count.
        "derived_selection": {
            "method": "v2_evidence_based_candidate_filter",
            "generator": "scripts/resample_south_africa_v2.py",
            "generator_function": "build_reservoir",
            "filter_module": "src/banking_tasci/data/sa_candidate_filter.py",
            "expected_selected_count": 100768,
            "selection_rules": [
                "A: banking aspect + problem expression",
                "B: banking aspect + request expression",
                "C: first-person + banking aspect",
                "D: positive sentiment + positive service context",
                "E: suggestion/warning/churn + banking reference",
                "F: specific banking issue phrase",
            ],
            "additional_constraints": [
                "excludes unrelated-bank matches",
                "excludes text shorter than MIN_TEXT_LENGTH",
                "excludes promotional unless first-person/problem/specific",
                "restricted to created_at years 2018-2022 inclusive",
                "excludes possible_official_account records",
            ],
            "documented_rule_breakdown": {
                "C": 38185, "A": 33360, "B": 18428,
                "D": 6380, "E": 2880, "F": 1535,
            },
            "provenance_log": "outputs/logs/run_20260905_191954_887494.log",
            "provenance_docs": [
                "docs/south_africa_filter_history.md",
                "docs/south_africa_resampling_report.md",
            ],
            "status_note": (
                "Count reproduced exactly (100768, 0 duplicate identifiers) by "
                "read-only re-execution of the filter against this source. The "
                "selection is not yet materialised as its own checksummed "
                "artifact, which is the remaining Phase 2 step."
            ),
        },
    },
    "international": {
        "input": "data/interim/prepared.csv",
        "expected_count_key": "international_prepared",
        "source": "international_bank_tweets+bank_reviews",
        "region": "international",
        "output": "international_source_manifest.json",
    },
    # The MATERIALISED v2 candidate corpus. Unlike the parent parquet above,
    # this file's own row count IS the authoritative 100,768, so it is expected
    # to report VERIFIED with no derived_selection caveat.
    "south_africa_candidates_v2": {
        "input": "data/processed/new_pipeline_v1/south_africa_candidates_v2.parquet",
        "expected_count_key": "south_africa_candidates",
        "source": "south_african_bank_tweets",
        "region": "south_africa",
        "output": "south_africa_candidates_v2_source_manifest.json",
        "required_columns": ("record_id", "source", "region", "bank", "text"),
    },
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_source_manifest.py",
        description=(
            "Generate checksummed new_pipeline_v1 source manifests and verify "
            "observed row counts against configured expectations. Never "
            "fabricates or coerces counts."
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to new_pipeline_v1.yaml (default: configs/new_pipeline_v1.yaml).",
    )
    parser.add_argument(
        "--source",
        choices=sorted(SOURCES) + ["all"],
        default="all",
        help="Which configured source to describe (default: all).",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Describe an arbitrary file instead of a configured source.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Manifest output path (required with --input).",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="Override the expected row count for --input.",
    )
    parser.add_argument(
        "--no-expected",
        action="store_true",
        help="Describe without verifying any expected count.",
    )
    parser.add_argument(
        "--manifests-dir",
        default=None,
        help="Override the manifest output directory from config paths.manifests_dir.",
    )
    return parser


def _report(result) -> None:
    print(f"\n=== {result.source_file} ===")
    print(f"  status:          {result.status}")
    print(f"  exists:          {result.exists}")
    if result.row_count is not None:
        print(f"  rows observed:   {result.row_count:,}")
    if result.expected_row_count is not None:
        print(f"  rows expected:   {result.expected_row_count:,}")
    if result.row_count_difference not in (None, 0):
        print(f"  difference:      {result.row_count_difference:+,}")
    if result.sha256:
        print(f"  sha256:          {result.sha256}")
    if result.candidate_status:
        print(
            f"  candidate flag:  {result.candidate_status['column']} true for "
            f"{result.candidate_status['true_count']:,}"
        )
    if result.duplicate_group_coverage:
        coverage = result.duplicate_group_coverage
        print(
            f"  dup groups:      {coverage['distinct_groups']:,} distinct, "
            f"coverage {coverage['coverage_fraction']:.4f}"
        )
    for note in result.notes:
        print(f"  NOTE: {note}")


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)

    cfg = load_config(args.config)
    pipeline_version = cfg.pipeline_version
    counts = cfg.counts.to_dict() if "counts" in cfg else {}

    if args.manifests_dir:
        manifests_dir = Path(args.manifests_dir)
    else:
        configured = cfg.paths.manifests_dir if "paths" in cfg else "artifacts/manifests"
        manifests_dir = PROJECT_ROOT / configured

    generation_command = " ".join(["python", "scripts/generate_source_manifest.py", *(argv or sys.argv[1:])])

    results = []

    if args.input:
        if not args.output:
            print("Error: --output is required with --input.", file=sys.stderr)
            return 1
        expected = None if args.no_expected else args.expected_count
        result = build_manifest(
            PROJECT_ROOT / args.input if not Path(args.input).is_absolute() else args.input,
            pipeline_version=pipeline_version,
            expected_row_count=expected,
            generation_command=generation_command,
        )
        written = write_manifest(result, args.output)
        _report(result)
        print(f"  manifest:        {written}")
        results.append(result)
    else:
        selected = sorted(SOURCES) if args.source == "all" else [args.source]
        for name in selected:
            spec = SOURCES[name]
            expected = None if args.no_expected else counts.get(spec["expected_count_key"])
            result = build_manifest(
                PROJECT_ROOT / spec["input"],
                pipeline_version=pipeline_version,
                expected_row_count=expected,
                source=spec["source"],
                region=spec["region"],
                generation_command=generation_command,
                derived_selection=spec.get("derived_selection"),
                required_columns=spec.get("required_columns"),
            )
            written = write_manifest(result, manifests_dir / spec["output"])
            _report(result)
            print(f"  manifest:        {written}")
            results.append(result)

    unverified = [r for r in results if r.status != STATUS_VERIFIED]

    print("\n=== summary ===")
    print(f"  manifests written: {len(results)}")
    print(f"  verified:          {len(results) - len(unverified)}")
    print(f"  needs attention:   {len(unverified)}")

    if unverified:
        print(
            "\nOne or more sources did not match their expected count.\n"
            "This is reported, not corrected. Per Requirements Migration Principle 6,\n"
            "no sampling or filtering was applied to reach an expected number.\n"
            "Resolve by either confirming a corrected expected count or supplying a\n"
            "genuine, reproducible selection that yields it."
        )
        for r in unverified:
            print(f"  - {r.source_file}: {r.status}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
