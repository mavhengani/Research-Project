#!/usr/bin/env python3
"""Explicitly approve a reviewed `new_pipeline_v1` candidate package.

Dry-run is the default. Writing requires ``--approve``, an explicit reviewer,
review report, and expected sample/batch checksums. The approval record is a
separate artifact; candidate annotation files are read-only inputs.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotation_approval import (  # noqa: E402
    DEFAULT_APPROVAL_PATH,
    create_approval_record,
    write_approval_record,
)

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / "data/annotations/new_pipeline_v1"
MANIFESTS = ROOT / "artifacts/manifests/new_pipeline_v1"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", action="store_true", help="Explicit approval action; otherwise dry-run only.")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--review-report", required=True)
    parser.add_argument("--expected-sample-checksum", required=True)
    parser.add_argument("--expected-batch-manifest-checksum", required=True)
    parser.add_argument("--sample-plan")
    parser.add_argument("--annotation-records")
    parser.add_argument("--annotation-manifest")
    parser.add_argument("--batch-manifest")
    parser.add_argument("--output")
    parser.add_argument("--command")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        review_data = json.loads(Path(args.review_report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        review_data = {}
    candidate_number = review_data.get("candidate_number", 1) if isinstance(review_data, dict) else 1
    if candidate_number == 2:
        candidate_annotations = ROOT / "data/annotations/new_pipeline_v1_candidate_2"
        candidate_manifests = ROOT / "artifacts/manifests/new_pipeline_v1/candidate_2"
        default_output = ROOT / "artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json"
    else:
        candidate_annotations = ANNOTATIONS
        candidate_manifests = MANIFESTS
        default_output = ROOT / DEFAULT_APPROVAL_PATH
    command = args.command or shlex.join(
        ["python3", "scripts/approve_annotation_package.py", *(argv if argv is not None else sys.argv[1:])]
    )
    approval = create_approval_record(
        reviewer=args.reviewer,
        review_report_path=args.review_report,
        sample_plan_path=args.sample_plan or candidate_annotations / "gold_sample_plan.jsonl",
        annotation_records_path=args.annotation_records or candidate_annotations / "annotation_records.jsonl",
        annotation_manifest_path=args.annotation_manifest or candidate_manifests / "annotation_package_manifest.json",
        batch_manifest_path=args.batch_manifest or candidate_manifests / "annotation_batch_manifest.json",
        expected_sample_checksum=args.expected_sample_checksum,
        expected_batch_manifest_checksum=args.expected_batch_manifest_checksum,
        command=command,
        approve=args.approve,
    )
    if not args.approve:
        print(json.dumps(approval.to_dict(), indent=2, sort_keys=True))
        print("dry-run: approval artifact not written; pass --approve to create it")
        return 0
    path = write_approval_record(approval, args.output or default_output)
    print(f"approval record written: {path}")
    print(f"approval_id: {approval.approval_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
