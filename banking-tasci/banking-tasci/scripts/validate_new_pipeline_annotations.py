#!/usr/bin/env python3
"""Validate new_pipeline_v1 records against source and batch governance."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from banking_tasci.data.new_pipeline_annotation_validator import read_raw_jsonl, report_markdown, validate_records

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True); p.add_argument("--source", required=True)
    p.add_argument("--batch-manifest"); p.add_argument("--json-report", required=True); p.add_argument("--markdown-report", required=True)
    p.add_argument("--completed-gold", action="store_true")
    a = p.parse_args(argv)
    membership = None
    if a.batch_manifest:
        body = json.loads(Path(a.batch_manifest).read_text(encoding="utf-8"))
        membership = {name: set(item["record_ids"]) for name, item in body["batches"].items()}
    report = validate_records(read_raw_jsonl(a.input), read_raw_jsonl(a.source), membership, completed_gold=a.completed_gold)
    for destination, content in ((Path(a.json_report), json.dumps(report, indent=2) + "\n"), (Path(a.markdown_report), report_markdown(report))):
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text(content, encoding="utf-8")
    print(json.dumps({"result": report["result"], "invalid_count": report["invalid_count"]}))
    return 0 if report["result"] == "PASS" else 1
if __name__ == "__main__": raise SystemExit(main())
