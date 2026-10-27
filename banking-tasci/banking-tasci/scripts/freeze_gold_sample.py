#!/usr/bin/env python3
"""Freeze approved gold sample identities without changing annotation data.

Dry-run is the default. A real freeze requires ``--freeze`` and
``--acknowledge-immutable-ids`` together, an explicit authority and output
directory, and a matching approved-package record.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.gold_sample_freeze import (  # noqa: E402
    prepare_freeze_artifacts,
    prepare_superseding_revision,
    resolve_candidate_paths,
    write_freeze_artifacts,
    write_superseding_revision,
)

ROOT = Path(__file__).resolve().parent.parent
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Explicitly execute the identity freeze.")
    parser.add_argument("--acknowledge-immutable-ids", action="store_true")
    parser.add_argument("--candidate-number", required=True, type=int, choices=(1, 2))
    parser.add_argument("--authority", "--researcher", dest="authority", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--approval", "--approval-artifact", dest="approval")
    parser.add_argument("--sample-plan")
    parser.add_argument("--annotation-records")
    parser.add_argument("--annotation-manifest")
    parser.add_argument("--batch-manifest")
    parser.add_argument("--candidate-manifest")
    parser.add_argument("--review-report")
    parser.add_argument("--expected-approval-checksum")
    parser.add_argument("--expected-sample-checksum")
    parser.add_argument("--expected-annotation-checksum")
    parser.add_argument("--expected-batch-manifest-checksum")
    parser.add_argument("--expected-review-checksum")
    parser.add_argument("--command", default="scripts/freeze_gold_sample.py")
    parser.add_argument("--supersede-original-freeze")
    parser.add_argument("--supersession-output-dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.supersede_original_freeze:
        if not args.supersession_output_dir:
            raise SystemExit("--supersession-output-dir is required for a superseding revision")
        payload = prepare_superseding_revision(
            original_dir=args.supersede_original_freeze, approval_path=args.approval or resolve_candidate_paths(ROOT, 2)["approval"],
            batch_manifest_path=args.batch_manifest or resolve_candidate_paths(ROOT, 2)["batch_manifest"], researcher=args.authority,
            source_manifest_paths={"south_africa": ROOT / "artifacts/manifests/new_pipeline_v1/south_africa_candidates_v2_source_manifest.json", "international": ROOT / "artifacts/manifests/new_pipeline_v1/international_source_manifest.json", "combined_relevant": ROOT / "artifacts/manifests/new_pipeline_v1/combined_relevant_manifest.json"},
            supersession_reason="Governance-complete revision: approval ID, approved batch membership, and verified source-manifest references.",
        )
        path = write_superseding_revision(payload, args.supersession_output_dir)
        print(f"superseding Candidate 2 freeze revision written: {path}")
        return 0
    defaults = resolve_candidate_paths(ROOT, args.candidate_number)
    if args.freeze and not args.output_dir:
        raise SystemExit("--output-dir is required with --freeze")
    payload = prepare_freeze_artifacts(
        sample_plan_path=args.sample_plan or defaults["sample_plan"],
        annotation_records_path=args.annotation_records or defaults["annotation_records"],
        annotation_manifest_path=args.annotation_manifest or defaults["annotation_manifest"],
        batch_manifest_path=args.batch_manifest or defaults["batch_manifest"],
        approval_path=args.approval or defaults["approval"],
        authority=args.authority,
        command=args.command,
        candidate_number=args.candidate_number,
        candidate_manifest_path=args.candidate_manifest or defaults["candidate_manifest"],
        review_report_path=args.review_report or defaults["review_report"],
        expected_checksums={"approval": args.expected_approval_checksum, "sample": args.expected_sample_checksum, "annotation": args.expected_annotation_checksum, "batch": args.expected_batch_manifest_checksum, "review": args.expected_review_checksum},
    )
    if not args.freeze:
        summary = dict(payload["manifest"])
        summary["identity_records_preview"] = payload["identity_records"][:3]
        print(json.dumps(summary, indent=2, sort_keys=True))
        print("dry-run: no freeze files written; pass --freeze --acknowledge-immutable-ids")
        return 0
    path = write_freeze_artifacts(
        payload,
        args.output_dir or defaults["output_dir"],
        acknowledge_immutable_ids=args.acknowledge_immutable_ids,
    )
    print(f"immutable gold identity package written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
