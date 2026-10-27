#!/usr/bin/env python3
"""Build the calibration + main + final annotation batches for `new_pipeline_v1`.

Requirements Section 13: partitions the immutable 1,000-record label-hidden
annotation package into 11 batches - ``calibration_001`` (50), ``main_001``
through ``main_009`` (100 each), and ``final_001`` (50) - with group-aware
leakage-safety (Requirements Section 13 grouping fields never split across
batches).

**Defaults to dry-run.** Prints a summary and writes nothing. ``--write``
persists the batch files and manifests under
``data/annotations/new_pipeline_v1/batches/``. Existing batch files are never
overwritten without ``--overwrite``.

Usage::

    python scripts/build_annotation_batches.py
    python scripts/build_annotation_batches.py --write
    python scripts/build_annotation_batches.py --write --overwrite

Exit codes: ``0`` success, ``1`` IO/usage error, ``2`` refused write,
``3`` batching failed (e.g. an oversized annotation group).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotation_batches import (  # noqa: E402
    BATCH_SPECS,
    DEFAULT_SEED,
    TOTAL_RECORDS,
    assign_batches,
    build_batch_metadata,
    build_combined_batch_manifest,
    write_batches,
)
from banking_tasci.data.manifest import sha256_file  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "annotations" / "new_pipeline_v1" / "annotation_records.jsonl"
)
DEFAULT_SAMPLE_MANIFEST = (
    PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1" / "gold_sample_plan_manifest.json"
)
DEFAULT_BATCH_DIR = PROJECT_ROOT / "data" / "annotations" / "new_pipeline_v1" / "batches"
DEFAULT_MANIFEST_OUTPUT = (
    PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1" / "annotation_batch_manifest.json"
)
DEFAULT_REPORT = PROJECT_ROOT / "artifacts" / "reports" / "new_pipeline_v1" / "annotation_batches.md"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_annotation_batches.py",
        description=(
            "Partition the label-hidden annotation package into calibration, "
            "main, and final batches (50 + 9x100 + 50 = 1,000). Dry-run by "
            "default."
        ),
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--sample-manifest", default=str(DEFAULT_SAMPLE_MANIFEST))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--manifest-output", default=None)
    parser.add_argument("--report", default=None)
    return parser


def _load_records(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_sample_manifest_checksum(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("plan_output_sha256", ""))


def _print_summary(assignment, metadatas) -> None:
    print("\n=== annotation batches ===")
    print(f"  total groups:      {assignment.total_groups}")
    print(f"  unresolved warnings: {assignment.unresolved_balancing_warnings or 'none'}")
    for metadata in metadatas:
        print(
            f"  {metadata.display_name:20} technical_id={metadata.batch_id:16} "
            f"records={metadata.record_count:4} "
            f"sources={metadata.source_distribution} "
                f"target={metadata.source_target_distribution} "
                f"deviation={metadata.source_deviation} "
                f"regions={metadata.region_distribution} "
                f"groups={metadata.group_count} "
                f"warnings={metadata.constraint_warnings or 'none'}"
        )


def _write_report_md(metadatas, assignment, path: Path) -> None:
    lines = [
        "# Uniform annotation batches report (`new_pipeline_v1`)",
        "",
        f"- total batches: **{len(metadatas)}**",
        f"- total records: **{sum(m.record_count for m in metadatas)}**",
        f"- total annotation groups: {assignment.total_groups}",
        f"- unresolved balancing warnings: {assignment.unresolved_balancing_warnings or 'none'}",
        "",
        "| display name | technical batch ID | workflow role | size | source target | observed source | source deviation | regions | groups | warnings / explanation |",
        "|---|---|---|---:|---|---|---|---|---:|---|",
    ]
    for metadata in metadatas:
        lines.append(
            f"| {metadata.display_name} | {metadata.technical_batch_id} | standard_manual_annotation_batch | {metadata.record_count} "
            f"| {metadata.source_target_distribution} | {metadata.source_distribution} "
            f"| {metadata.source_deviation} | {metadata.region_distribution} "
            f"| {metadata.group_count} | {metadata.constraint_warnings or metadata.balancing_explanation or 'none'} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not input_path.is_file():
        print(
            f"Error: annotation package not found: {input_path}\n"
            f"Run scripts/build_gold_sample_plan.py --write --write-annotation-package first.",
            file=sys.stderr,
        )
        return 1

    records = _load_records(input_path)
    if len(records) != TOTAL_RECORDS:
        print(
            f"Error: expected exactly {TOTAL_RECORDS} records in {input_path}, "
            f"found {len(records)}.",
            file=sys.stderr,
        )
        return 1

    sample_manifest_checksum = _load_sample_manifest_checksum(Path(args.sample_manifest))

    try:
        assignment = assign_batches(records, seed=args.seed)
    except ValueError as exc:
        print(f"Batching failed: {exc}", file=sys.stderr)
        return 3

    metadatas = [
        build_batch_metadata(
            name,
            batch_type,
            [records[i] for i in assignment.batches[name]],
            source_sample_manifest_checksum=sample_manifest_checksum,
            group_count=assignment.group_counts.get(name, 0),
            source_target_distribution=assignment.source_targets.get(name, {}),
            source_deviation=assignment.source_deviations.get(name, {}),
            region_target_distribution=assignment.region_targets.get(name, {}),
            region_deviation=assignment.region_deviations.get(name, {}),
            constraint_warnings=[warning for warning in assignment.unresolved_balancing_warnings if name in warning],
            balancing_explanation=assignment.grouping_balance_explanations.get(name),
        )
        for name, batch_type, _size in BATCH_SPECS
    ]

    _print_summary(assignment, metadatas)

    if not args.write:
        print("\nDry run only - nothing was written. Re-run with --write to persist.")
        return 0

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_BATCH_DIR
    try:
        batches = {
            name: [records[i] for i in assignment.batches[name]] for name, _t, _s in BATCH_SPECS
        }
        paths = write_batches(batches, output_dir, overwrite=args.overwrite)
    except FileExistsError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2

    for metadata in metadatas:
        metadata.output_path = str(paths[metadata.batch_id])
        metadata.checksum = sha256_file(paths[metadata.batch_id])
        metadata.checksum_algorithm = "jsonl_sha256"

    manifest_output = Path(args.manifest_output) if args.manifest_output else DEFAULT_MANIFEST_OUTPUT
    combined_manifest = build_combined_batch_manifest(
        metadatas, assignment, creation_command=" ".join(sys.argv), seed=args.seed
    )
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(combined_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    report_path = Path(args.report) if args.report else DEFAULT_REPORT
    _write_report_md(metadatas, assignment, report_path)

    print(f"\n  batches written to: {output_dir}")
    print(f"  combined manifest:  {manifest_output}")
    print(f"  report:             {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
