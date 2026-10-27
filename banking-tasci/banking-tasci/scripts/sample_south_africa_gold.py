#!/usr/bin/env python3
"""Dry-run / sample the South African `new_pipeline_v1` gold records.

Phase 3 tooling, South African source ONLY: **500 records**, initially
allocated **100 per bank** across FNB, Absa, Nedbank, Standard Bank, and
Capitec, drawn from the VERIFIED materialised 100,768-record v2 candidate
corpus.

**Defaults to dry-run.** Writing annotation output requires both ``--write``
and ``--authorise-final-write``, so the authoritative gold corpus cannot be
produced by accident or by a single mistyped flag.

**Candidate rules are not labels.** The ``--with-rule-coverage`` flag recomputes
the v2 rule attribution from the parent source purely so the dry-run can report
rule coverage. The rule never reaches the annotation output (Requirements 6.5).

Usage::

    python scripts/sample_south_africa_gold.py
    python scripts/sample_south_africa_gold.py --with-rule-coverage

Exit codes: ``0`` success, ``1`` IO/usage error, ``2`` refused write.
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
from banking_tasci.data.south_africa_sampler import (  # noqa: E402
    CANONICAL_BANKS,
    DEFAULT_SEED,
    build_selection_manifest,
    dry_run,
    sample_south_africa,
    to_label_hidden_records,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "new_pipeline_v1.yaml"
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "new_pipeline_v1"
    / "south_africa_candidates_v2.parquet"
)
PARENT_SOURCE = PROJECT_ROOT / "data" / "interim" / "south_africa_prepared.parquet"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sample_south_africa_gold.py",
        description=(
            "Deterministically sample the South African gold records (500 total, "
            "100 per bank). Dry-run by default."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input", default=str(DEFAULT_SOURCE))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--target-total", type=int, default=None)
    parser.add_argument("--per-bank", type=int, default=None)
    parser.add_argument(
        "--with-rule-coverage",
        action="store_true",
        help=(
            "Recompute v2 rule attribution from the parent source for coverage "
            "reporting only. Slower; the rule never reaches the output."
        ),
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--authorise-final-write",
        action="store_true",
        help="Second, explicit authorisation required alongside --write.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--manifest", default=None)
    return parser


def _rule_labels_from_parent():
    """Recompute v2 rule attribution, for coverage reporting only."""
    import pandas as pd

    from banking_tasci.data.sa_candidates_v2 import select_v2_candidates

    cols = ["record_id", "text", "created_at", "possible_official_account"]
    parent = pd.read_parquet(PARENT_SOURCE, columns=cols)
    result = select_v2_candidates(parent)
    # Index rule labels by record_id so they align with the materialised corpus.
    labels = result.rule_labels[result.mask]
    ids = parent.loc[result.mask, "record_id"].astype(str)
    return pd.Series(labels.values, index=ids.values)


def _print_report(report) -> None:
    print("\n=== South African gold sampling ===")
    print(f"  mode:              {'DRY RUN' if report.dry_run else 'SELECTION'}")
    print(f"  source:            {report.source_file}")
    print(f"  source sha256:     {report.source_sha256}")
    print(f"  seed:              {report.seed}")
    print(f"  available records: {report.available_total:,}")

    print("\n  available by bank:")
    for bank in CANONICAL_BANKS:
        print(f"    {bank:15} {report.available_by_bank.get(bank, 0):,}")

    print("\n  requested by bank:")
    for bank, count in report.requested_by_bank.items():
        print(f"    {bank:15} {count}")

    if report.selected_by_bank:
        print("\n  selected by bank:")
        for bank, count in report.selected_by_bank.items():
            print(f"    {bank:15} {count}")

    bands = report.length_bands
    print(
        f"\n  length bands (source-specific quantiles): "
        f"q{bands['quantiles'][0]}={bands['q_low']:.1f} "
        f"q{bands['quantiles'][1]}={bands['q_high']:.1f} (n={bands['n']:,})"
    )
    print(f"  available by band: {report.available_by_stratum}")
    if report.selected_by_stratum:
        print(f"  selected by band:  {report.selected_by_stratum}")

    print(f"\n  year distribution (available): {report.year_distribution_available}")
    if report.year_distribution_selected:
        print(f"  year distribution (selected):  {report.year_distribution_selected}")

    print(f"\n  v2 rule distribution (available): {report.rule_distribution_available}")
    if report.rule_distribution_selected:
        print(f"  v2 rule distribution (selected):  {report.rule_distribution_selected}")

    print(f"\n  duplicate-group coverage: {report.duplicate_group_coverage}")
    print(f"  duplicate-group conflicts avoided: {report.duplicate_group_conflicts}")
    if report.context_availability:
        print(f"  context availability: {report.context_availability}")

    print(f"\n  missing fields: {report.missing_fields or 'none'}")
    print(f"  can select {report.requested_total} without replacement: {report.can_select_full_total}")
    print(f"  can select 100 per bank:                 {report.can_select_full_per_bank}")

    if report.shortages:
        print("\n  SHORTAGES:")
        for entry in report.shortages:
            scope = entry.get("bank") or entry.get("scope")
            print(
                f"    {scope}: requested {entry['requested']}, "
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
    target_total = (
        args.target_total if args.target_total is not None else annotation.south_africa_tweets
    )
    per_bank = args.per_bank if args.per_bank is not None else annotation.per_bank_allocation

    source = Path(args.input)
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    if not source.is_file():
        print(
            f"Error: source not found: {source}\n"
            f"Run scripts/materialize_south_africa_candidates_v2.py first.",
            file=sys.stderr,
        )
        return 1

    rule_labels = None
    if args.with_rule_coverage:
        print("  recomputing v2 rule attribution for coverage (reads parent)...")
        rule_labels = _rule_labels_from_parent()

    if not args.write:
        report = dry_run(
            source,
            target_total=target_total,
            per_bank_target=per_bank,
            seed=args.seed,
            rule_labels=rule_labels,
        )
        _print_report(report)
        print(
            "\nDry run only - nothing was written. A real selection additionally "
            "requires BOTH --write and --authorise-final-write."
        )
        return 0

    if not args.authorise_final_write:
        print(
            "\nRefused: --write also requires --authorise-final-write.\n"
            "The authoritative gold annotation input must not be produced by a "
            "single flag.",
            file=sys.stderr,
        )
        return 2

    selected, report = sample_south_africa(
        source,
        target_total=target_total,
        per_bank_target=per_bank,
        seed=args.seed,
        rule_labels=rule_labels,
    )
    _print_report(report)

    records = to_label_hidden_records(selected)
    output = Path(args.output) if args.output else (
        PROJECT_ROOT / "data" / "annotations" / "new_pipeline_v1"
        / "south_africa_unannotated.jsonl"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest_path = Path(args.manifest) if args.manifest else (
        PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1"
        / "south_africa_sample_manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(build_selection_manifest(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"\n  label-hidden output: {output} ({len(records)} records)")
    print(f"  selection manifest:  {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
