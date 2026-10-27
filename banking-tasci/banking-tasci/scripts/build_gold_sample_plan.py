#!/usr/bin/env python3
"""Build the canonical combined gold sample plan for `new_pipeline_v1`.

Requirements Section 10: combines the two already-VERIFIED dry-run samplers
(South African: 500/100-per-bank; international: 250 tweets + 250 reviews)
into one immutable, namespaced 1,000-record plan.

**Defaults to dry-run.** Prints a summary and writes nothing. ``--write``
writes the selection-provenance file (``gold_sample_plan.jsonl``) and its
manifest. ``--write-annotation-package`` additionally writes the Section 11
label-hidden ``annotation_records.jsonl`` and its manifest - it requires
``--write`` too, so the annotator-facing package is never produced by a
single flag while the underlying plan file does not exist.

Usage::

    python scripts/build_gold_sample_plan.py
    python scripts/build_gold_sample_plan.py --write
    python scripts/build_gold_sample_plan.py --write --write-annotation-package

Exit codes: ``0`` success, ``1`` IO/usage error, ``2`` refused write,
``3`` integrity assertion failed.
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
from banking_tasci.data.gold_sample_plan import (  # noqa: E402
    DEFAULT_SEED,
    REGION_TARGETS,
    SOURCE_TARGETS,
    TOTAL_TARGET,
    build_combined_sample_plan,
    build_gold_sample_plan_manifest,
    to_annotation_records,
    write_jsonl,
)
from banking_tasci.data.manifest import sha256_file  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "new_pipeline_v1.yaml"
DEFAULT_SA_SOURCE = (
    PROJECT_ROOT / "data" / "processed" / "new_pipeline_v1" / "south_africa_candidates_v2.parquet"
)
DEFAULT_INTL_SOURCE = PROJECT_ROOT / "data" / "interim" / "prepared.csv"
DEFAULT_PLAN_OUTPUT = (
    PROJECT_ROOT / "data" / "annotations" / "new_pipeline_v1" / "gold_sample_plan.jsonl"
)
DEFAULT_PLAN_MANIFEST = (
    PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1" / "gold_sample_plan_manifest.json"
)
DEFAULT_ANNOTATION_OUTPUT = (
    PROJECT_ROOT / "data" / "annotations" / "new_pipeline_v1" / "annotation_records.jsonl"
)
DEFAULT_ANNOTATION_MANIFEST = (
    PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1" / "annotation_package_manifest.json"
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "artifacts" / "reports" / "new_pipeline_v1" / "gold_sample_plan.md"
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_gold_sample_plan.py",
        description=(
            "Combine the verified South African and international dry-run "
            "samplers into the canonical 1,000-record gold sample plan. "
            "Dry-run by default."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--sa-input", default=str(DEFAULT_SA_SOURCE))
    parser.add_argument("--intl-input", default=str(DEFAULT_INTL_SOURCE))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--with-sa-rule-coverage",
        action="store_true",
        help="Recompute the SA v2 rule attribution for coverage reporting only.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--write-annotation-package",
        action="store_true",
        help="Also write the label-hidden annotation_records.jsonl (requires --write).",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--plan-output", default=None)
    parser.add_argument("--plan-manifest", default=None)
    parser.add_argument("--annotation-output", default=None)
    parser.add_argument("--annotation-manifest", default=None)
    parser.add_argument("--report", default=None)
    return parser


def _rule_labels_from_parent():
    import pandas as pd

    from banking_tasci.data.sa_candidates_v2 import select_v2_candidates

    parent_source = PROJECT_ROOT / "data" / "interim" / "south_africa_prepared.parquet"
    cols = ["record_id", "text", "created_at", "possible_official_account"]
    parent = pd.read_parquet(parent_source, columns=cols)
    result = select_v2_candidates(parent)
    labels = result.rule_labels[result.mask]
    ids = parent.loc[result.mask, "record_id"].astype(str)
    return pd.Series(labels.values, index=ids.values)


def _print_summary(report) -> None:
    print("\n=== combined gold sample plan ===")
    print(f"  pipeline_version:  {report.pipeline_version}")
    print(f"  seed:              {report.seed}")
    print(f"  git_commit:        {report.git_commit}")
    print(f"  total:             {report.total} (target {TOTAL_TARGET})")
    print(f"  unique ids:        {report.unique_record_count}")
    print(f"  by source:         {report.by_source}")
    print(f"  expected by source:{dict(sorted(SOURCE_TARGETS.items()))}")
    print(f"  by region:         {report.by_region}")
    print(f"  expected by region:{dict(sorted(REGION_TARGETS.items()))}")
    print(f"  cross-source collisions: {report.cross_source_collision_count}")
    print(f"  grouping coverage: {report.grouping_coverage}")
    print(f"  privacy status:    {report.privacy_status_distribution}")
    print(f"  SA source sha256:  {report.south_africa_source_sha256}")
    print(f"  Intl source sha256:{report.international_source_sha256}")
    for note in report.notes:
        print(f"  NOTE: {note}")


def _write_report_md(report, path: Path) -> None:
    lines = [
        "# Gold sample-plan report (`new_pipeline_v1`)",
        "",
        f"- pipeline_version: `{report.pipeline_version}`",
        f"- seed: `{report.seed}`",
        f"- git_commit: `{report.git_commit}`",
        f"- generated_at: `{report.generated_at}`",
        f"- total: **{report.total}** (target {TOTAL_TARGET})",
        f"- unique canonical ids: **{report.unique_record_count}**",
        f"- by source: `{report.by_source}`",
        f"- by region: `{report.by_region}`",
        f"- cross-source collisions: `{report.cross_source_collision_count}`",
        f"- grouping coverage: `{report.grouping_coverage}`",
        f"- South African source sha256: `{report.south_africa_source_sha256}`",
        f"- International source sha256: `{report.international_source_sha256}`",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)
    load_config(args.config)  # validated readable; seed/counts come from CLI defaults

    sa_source = Path(args.sa_input)
    if not sa_source.is_absolute():
        sa_source = PROJECT_ROOT / sa_source
    intl_source = Path(args.intl_input)
    if not intl_source.is_absolute():
        intl_source = PROJECT_ROOT / intl_source

    if not sa_source.is_file():
        print(f"Error: South African source not found: {sa_source}", file=sys.stderr)
        return 1
    if not intl_source.is_file():
        print(f"Error: international source not found: {intl_source}", file=sys.stderr)
        return 1

    if args.write_annotation_package and not args.write:
        print(
            "Refused: --write-annotation-package requires --write too. The "
            "annotator-facing package must not be produced without the "
            "underlying plan file.",
            file=sys.stderr,
        )
        return 2

    rule_labels = None
    if args.with_sa_rule_coverage:
        print("  recomputing SA v2 rule attribution for coverage (reads parent)...")
        rule_labels = _rule_labels_from_parent()

    try:
        records, report = build_combined_sample_plan(
            sa_source, intl_source, seed=args.seed, sa_rule_labels=rule_labels
        )
    except ValueError as exc:
        print(f"Integrity assertion failed: {exc}", file=sys.stderr)
        return 3

    _print_summary(report)

    if not args.write:
        print("\nDry run only - nothing was written. Re-run with --write to persist.")
        return 0

    plan_output = Path(args.plan_output) if args.plan_output else DEFAULT_PLAN_OUTPUT
    plan_manifest_path = Path(args.plan_manifest) if args.plan_manifest else DEFAULT_PLAN_MANIFEST
    report_path = Path(args.report) if args.report else DEFAULT_REPORT

    if plan_output.exists() and not args.overwrite:
        print(
            f"Refused: {plan_output} already exists. Pass --overwrite to replace it.",
            file=sys.stderr,
        )
        return 2

    write_jsonl(records, plan_output)
    manifest = build_gold_sample_plan_manifest(report)
    manifest["plan_output_sha256"] = sha256_file(plan_output)
    plan_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    plan_manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    _write_report_md(report, report_path)

    print(f"\n  gold sample plan: {plan_output} ({len(records)} records)")
    print(f"  plan manifest:    {plan_manifest_path}")
    print(f"  report:           {report_path}")

    if args.write_annotation_package:
        annotation_output = (
            Path(args.annotation_output) if args.annotation_output else DEFAULT_ANNOTATION_OUTPUT
        )
        annotation_manifest_path = (
            Path(args.annotation_manifest) if args.annotation_manifest else DEFAULT_ANNOTATION_MANIFEST
        )
        if annotation_output.exists() and not args.overwrite:
            print(
                f"Refused: {annotation_output} already exists. Pass --overwrite to replace it.",
                file=sys.stderr,
            )
            return 2

        annotation_records = to_annotation_records(records)
        write_jsonl(annotation_records, annotation_output)
        annotation_manifest = {
            "pipeline_version": report.pipeline_version,
            "git_commit": report.git_commit,
            "input_sample_plan_checksum": manifest["plan_output_sha256"],
            "output_record_count": len(annotation_records),
            "output_checksum": sha256_file(annotation_output),
            "schema_version": "new_pipeline_schema_v1",
            "label_hidden": True,
            "creation_command": " ".join(sys.argv),
        }
        annotation_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        annotation_manifest_path.write_text(
            json.dumps(annotation_manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"  annotation package: {annotation_output} ({len(annotation_records)} records)")
        print(f"  annotation manifest: {annotation_manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
