#!/usr/bin/env python3
"""Read-only final Candidate 2 gold validator. Never creates a split or trains models."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from banking_tasci.data.final_gold_validation import (  # noqa: E402
    FinalGoldValidationError,
    validate_final_gold_files,
    _render_markdown,
)


def _new_path(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite validation report: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Researcher-supplied completed Candidate 2 JSONL")
    parser.add_argument("--batch-manifest", default="artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json")
    parser.add_argument("--membership", default="artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/approved_batch_membership.jsonl")
    parser.add_argument("--frozen-ids", default="artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_record_ids.jsonl")
    parser.add_argument("--freeze-manifest", default="artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_sample_manifest.json")
    parser.add_argument("--json-report")
    parser.add_argument("--markdown-report")
    parser.add_argument("--write-reports", action="store_true", help="Write new reports; default prints summary only")
    args = parser.parse_args(argv)
    try:
        report = validate_final_gold_files(
            input_path=args.input,
            project_root=ROOT,
            batch_manifest_path=ROOT / args.batch_manifest,
            membership_path=ROOT / args.membership,
            frozen_ids_path=ROOT / args.frozen_ids,
            freeze_manifest_path=ROOT / args.freeze_manifest,
        )
    except FinalGoldValidationError as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc), "split_created": False, "training_started": False}, indent=2))
        return 2
    if args.write_reports:
        if not args.json_report or not args.markdown_report:
            raise SystemExit("--json-report and --markdown-report are both required with --write-reports")
        json_path = ROOT / args.json_report
        markdown_path = ROOT / args.markdown_report
        _new_path(json_path)
        _new_path(markdown_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "record_count": report["record_count"],
        "completed_count": report["completed_count"],
        "error_count": report["error_count"],
        "warning_count": report["warning_count"],
        "split_created": False,
        "training_started": False,
        "reports_written": bool(args.write_reports),
    }, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
