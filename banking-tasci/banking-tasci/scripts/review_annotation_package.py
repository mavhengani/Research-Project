#!/usr/bin/env python3
"""Inspect existing candidate package artifacts and write a review record.

This command never writes beneath ``data/annotations/new_pipeline_v1`` and
never approves or freezes the package. It reads the current immutable
candidate files and writes only to ``artifacts/reports``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotation_package_review import (  # noqa: E402
    build_package_review,
    write_review_markdown,
    write_review_json,
)

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / "data/annotations/new_pipeline_v1"
MANIFESTS = ROOT / "artifacts/manifests/new_pipeline_v1"
ANNOTATIONS_CANDIDATE_2 = ROOT / "data/annotations/new_pipeline_v1_candidate_2"
MANIFESTS_CANDIDATE_2 = ROOT / "artifacts/manifests/new_pipeline_v1/candidate_2"
REPORTS_CANDIDATE_2 = ROOT / "artifacts/reports/new_pipeline_v1/candidate_2"
DEFAULT_OUTPUT = ROOT / "artifacts/reports/new_pipeline_v1/annotation_package_review.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-number", type=int, choices=(1, 2), default=1)
    parser.add_argument("--candidate1-checksum", default=None, help="expected checksum used to evidence candidate-1 preservation while reviewing candidate 2")
    parser.add_argument("--sample-plan", default=None)
    parser.add_argument("--annotation-records", default=None)
    parser.add_argument("--sample-plan-manifest", default=None)
    parser.add_argument("--annotation-manifest", default=None)
    parser.add_argument("--batch-manifest", default=None)
    parser.add_argument("--batch-directory", default=None)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print review JSON without writing (default).")
    parser.add_argument("--write", action="store_true", help="Write only the review JSON artifact.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.candidate_number == 1:
        annotation_root = ANNOTATIONS
        manifest_root = MANIFESTS
        default_output = DEFAULT_OUTPUT
    else:
        annotation_root = ANNOTATIONS_CANDIDATE_2
        manifest_root = MANIFESTS_CANDIDATE_2
        default_output = REPORTS_CANDIDATE_2 / "annotation_package_review.json"
    sample_plan = args.sample_plan or annotation_root / "gold_sample_plan.jsonl"
    annotation_records = args.annotation_records or annotation_root / "annotation_records.jsonl"
    plan_manifest = args.sample_plan_manifest or manifest_root / (
        "candidate_2_manifest.json" if args.candidate_number == 2 else "gold_sample_plan_manifest.json"
    )
    annotation_manifest = args.annotation_manifest or manifest_root / "annotation_package_manifest.json"
    batch_manifest = args.batch_manifest or manifest_root / "annotation_batch_manifest.json"
    batch_directory = args.batch_directory or annotation_root / "batches"
    output = args.output or str(default_output)
    candidate1_checksum = args.candidate1_checksum
    if args.candidate_number == 2 and candidate1_checksum is None:
        try:
            candidate2_manifest = json.loads(Path(plan_manifest).read_text(encoding="utf-8"))
            candidate1_checksum = candidate2_manifest.get("input_candidate1_plan_checksum")
        except (OSError, json.JSONDecodeError):
            candidate1_checksum = None
    review = build_package_review(
        sample_plan_path=sample_plan,
        annotation_records_path=annotation_records,
        sample_plan_manifest_path=plan_manifest,
        annotation_manifest_path=annotation_manifest,
        batch_manifest_path=batch_manifest,
        batch_directory=batch_directory,
        reviewer=args.reviewer,
        candidate_number=args.candidate_number,
        candidate1_path=(ANNOTATIONS / "gold_sample_plan.jsonl") if args.candidate_number == 2 else None,
        expected_candidate1_checksum=candidate1_checksum,
    )
    if args.write:
        path = write_review_json(review, output, overwrite=args.overwrite)
        print(f"review record written: {path}")
        if args.candidate_number == 2:
            markdown_path = Path(output).with_suffix(".md")
            write_review_markdown(review, markdown_path, overwrite=args.overwrite)
            print(f"review Markdown written: {markdown_path}")
    else:
        print(json.dumps(review.to_dict(), indent=2, sort_keys=True))
        print("dry-run: no files written")
    print(f"recommendation: {review.recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
