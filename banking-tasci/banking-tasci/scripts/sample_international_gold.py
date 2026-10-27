#!/usr/bin/env python3
"""Dry-run / sample the international `new_pipeline_v1` gold records.

Phase 3 tooling, international sources ONLY: 250 international banking tweets
and 250 international bank reviews drawn from the VERIFIED 10,847-record
prepared international corpus.

**Scope guard.** This script never samples South African records. The
500-record South African sample requires the 100,768-record corpus to exist as
a materialised, checksummed artifact first (gap-analysis finding R3).

**Defaults to dry-run.** Writing annotation output requires an explicit
``--write``, so the authoritative gold corpus is never produced by accident
while the South African side is unverified.

Usage::

    # Report what would be sampled; writes nothing.
    python scripts/sample_international_gold.py

    # Write the label-hidden international partial sample + manifest.
    python scripts/sample_international_gold.py --write \\
        --output data/annotations/new_pipeline_v1/international_unannotated.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.international_sampler import (  # noqa: E402
    DEFAULT_SEED,
    REVIEW_SOURCE,
    TWEET_SOURCE,
    build_selection_manifest,
    dry_run,
    sample_international,
    to_label_hidden_records,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "new_pipeline_v1.yaml"
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "interim" / "prepared.csv"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sample_international_gold.py",
        description=(
            "Deterministically sample the international gold records "
            "(250 tweets + 250 reviews). Dry-run by default; international "
            "sources only."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input", default=str(DEFAULT_SOURCE))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--tweet-target", type=int, default=None)
    parser.add_argument("--review-target", type=int, default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the label-hidden JSONL and manifest (default: dry-run only).",
    )
    parser.add_argument("--output", default=None, help="Label-hidden JSONL output path.")
    parser.add_argument("--manifest", default=None, help="Selection-manifest output path.")
    return parser


def _print_report(report) -> None:
    print("\n=== international gold sampling ===")
    print(f"  mode:            {'DRY RUN' if report.dry_run else 'SELECTION'}")
    print(f"  source:          {report.source_file}")
    print(f"  source sha256:   {report.source_sha256}")
    print(f"  seed:            {report.seed}")

    print("\n  available by source:")
    for name, count in sorted(report.available_counts.items()):
        print(f"    {name}: {count:,}")

    print("\n  source-specific length bands (quantile-derived):")
    for name, bands in sorted(report.length_bands.items()):
        print(
            f"    {name}: q{bands['quantiles'][0]}={bands['q_low']:.1f} "
            f"q{bands['quantiles'][1]}={bands['q_high']:.1f} (n={bands['n']:,})"
        )

    print("\n  requested by source:")
    for name, count in sorted(report.requested_by_source.items()):
        print(f"    {name}: {count}")

    if report.selected_by_source:
        print("\n  selected by source:")
        for name, count in sorted(report.selected_by_source.items()):
            print(f"    {name}: {count}")

    print("\n  available by stratum:")
    for source_name, strata in sorted(report.available_by_stratum.items()):
        print(f"    {source_name}: {len(strata)} strata")
        for stratum, count in list(sorted(strata.items()))[:8]:
            print(f"      {stratum}: {count}")
        if len(strata) > 8:
            print(f"      ... and {len(strata) - 8} more")

    if report.context_availability:
        print(f"\n  context availability: {report.context_availability}")
    if report.rating_band_counts:
        print(f"  rating bands (sampling metadata only): {report.rating_band_counts}")
    if report.sentence_band_counts:
        print(f"  sentence bands: {report.sentence_band_counts}")

    print(f"\n  duplicate-group conflicts avoided: {report.duplicate_group_conflicts}")
    print(f"  review-group conflicts avoided:    {report.review_group_conflicts}")

    if report.shortages:
        print("\n  SHORTAGES:")
        for entry in report.shortages:
            print(
                f"    {entry['source']}: requested {entry['requested']}, "
                f"selected {entry['selected']}, shortfall {entry['shortfall']}"
            )
    else:
        print("\n  shortages: none")

    if report.unsatisfied_strata:
        print(f"  unsatisfied strata: {len(report.unsatisfied_strata)}")

    for note in report.notes:
        print(f"  NOTE: {note}")


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)

    cfg = load_config(args.config)
    annotation = cfg.annotation
    tweet_target = (
        args.tweet_target
        if args.tweet_target is not None
        else annotation.international_tweets
    )
    review_target = (
        args.review_target
        if args.review_target is not None
        else annotation.international_reviews
    )

    source_path = Path(args.input)
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    if not source_path.is_file():
        print(f"Error: source not found: {source_path}", file=sys.stderr)
        return 1

    if not args.write:
        report = dry_run(
            source_path,
            tweet_target=tweet_target,
            review_target=review_target,
            seed=args.seed,
        )
        _print_report(report)
        print(
            "\nDry run only - nothing was written. Re-run with --write to emit the "
            "label-hidden international sample."
        )
        print(
            "NOTE: the South African 500-record sample is NOT produced by this "
            "script. It requires the 100,768-record corpus to exist as a "
            "materialised, checksummed artifact first (gap-analysis R3)."
        )
        return 0

    selected, report = sample_international(
        source_path,
        tweet_target=tweet_target,
        review_target=review_target,
        seed=args.seed,
    )
    _print_report(report)

    records = to_label_hidden_records(selected)

    output = Path(args.output) if args.output else (
        PROJECT_ROOT
        / "data"
        / "annotations"
        / "new_pipeline_v1"
        / "international_unannotated.jsonl"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest_path = Path(args.manifest) if args.manifest else (
        PROJECT_ROOT
        / "artifacts"
        / "manifests"
        / "new_pipeline_v1"
        / "international_sample_manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(build_selection_manifest(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"\n  label-hidden output: {output} ({len(records)} records)")
    print(f"  selection manifest:  {manifest_path}")
    print(
        "\nThis is the INTERNATIONAL PARTIAL sample only - not the authoritative "
        "1,000-record gold corpus."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
