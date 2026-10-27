#!/usr/bin/env python3
"""Review annotations for any approved uniform batch; report-only, never writes labels."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from banking_tasci.data.calibration_workspace import WorkspaceError, _load_json, _workspace_files, _load_approved_source, _load_source_package, _batch_policy, _workspace_metadata  # noqa: E402
from banking_tasci.data.new_pipeline_annotation_validator import read_raw_jsonl, report_markdown, validate_records  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--json-report", required=True)
    parser.add_argument("--markdown-report", required=True)
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = ROOT / workspace
    _root, working, progress_path, reference_path = _workspace_files(workspace)
    progress, reference = _load_json(progress_path), _load_json(reference_path)
    batch = _workspace_metadata(workspace, progress, reference, ROOT)
    source, _ = _load_approved_source(reference, ROOT)
    source_package = _load_source_package(reference, ROOT) or source
    records = read_raw_jsonl(working)
    report = validate_records(records, source_package, {batch["technical_batch_id"]: {r["record_id"] for r in source}})
    report.update({key: batch[key] for key in ("technical_batch_id", "display_name", "workflow_role", "record_count", "source_checksum", "candidate_number", "pipeline_version", "approved_membership_checksum")})
    report["completed_count"] = sum(r.get("annotation_status") == "completed" for r in records)
    report["remaining_count"] = batch["record_count"] - report["completed_count"]
    for destination, payload in ((Path(args.json_report), json.dumps(report, indent=2, sort_keys=True) + "\n"), (Path(args.markdown_report), report_markdown(report))):
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite review report: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
    print(json.dumps({"result": report["result"], "display_name": batch["display_name"], "completed_count": report["completed_count"], "remaining_count": report["remaining_count"], "error_count": report["error_count"], "warning_count": report["warning_count"]}))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
