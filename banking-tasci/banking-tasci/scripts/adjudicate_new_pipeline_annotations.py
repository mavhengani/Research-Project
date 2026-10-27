#!/usr/bin/env python3
"""Compare and adjudicate new_pipeline_v1 submissions using explicit human decisions.

No command creates labels. ``template`` emits record IDs and disputed field
names only. ``apply`` requires a decision JSONL and ``--write``; it refuses to
write while any disagreement remains unresolved or either output exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from banking_tasci.data.new_pipeline_adjudication import (  # noqa: E402
    AdjudicationError,
    apply_adjudication,
    compare_submissions,
)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"JSONL row {number} must be an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise AdjudicationError(f"cannot read JSONL input: {path}") from exc
    return rows


def _atomic_new_file(path: str | Path, payload: bytes) -> Path:
    target = Path(path)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing adjudication output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link creation is atomic and fails if another writer created the
        # destination after the initial existence check.
        os.link(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def _jsonl_payload(rows: list[dict[str, Any]]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows)


def _load_decisions(path: str | Path) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _read_jsonl(path):
        record_id, field = row.get("record_id"), row.get("field")
        if not isinstance(record_id, str) or not isinstance(field, str):
            raise AdjudicationError("decision rows require string record_id and field")
        if field in result.setdefault(record_id, {}):
            raise AdjudicationError(f"duplicate decision for {record_id}.{field}")
        result[record_id][field] = {
            "choice": row.get("choice"),
            "value": row.get("value"),
            "rationale": row.get("rationale"),
        }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("compare", "template", "apply"):
        command = commands.add_parser(action)
        command.add_argument("--annotator-a", required=True)
        command.add_argument("--annotator-b", required=True)
    commands.choices["compare"].add_argument("--report")
    commands.choices["compare"].add_argument("--write", action="store_true")
    commands.choices["template"].add_argument("--output", required=True)
    commands.choices["template"].add_argument("--write", action="store_true")
    apply_parser = commands.choices["apply"]
    apply_parser.add_argument("--decisions", required=True)
    apply_parser.add_argument("--adjudicator", required=True)
    apply_parser.add_argument("--output", required=True)
    apply_parser.add_argument("--audit-output", required=True)
    apply_parser.add_argument("--write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    left, right = _read_jsonl(args.annotator_a), _read_jsonl(args.annotator_b)
    comparison = compare_submissions(left, right)
    if args.action == "compare":
        rendered = json.dumps(comparison, indent=2, sort_keys=True) + "\n"
        if args.report:
            if Path(args.report).exists():
                raise FileExistsError(f"refusing to overwrite report: {args.report}")
            if not getattr(args, "write", False):
                print(rendered, end="")
                print("dry-run: report not written; rerun through a separately reviewed output step")
                return 0
            _atomic_new_file(args.report, rendered.encode("utf-8"))
        else:
            print(rendered, end="")
        return 0

    if args.action == "template":
        rows = [
            {"record_id": item["record_id"], "field": field}
            for item in comparison["disagreements"]
            for field in sorted(item["fields"])
        ]
        if not args.write:
            print(json.dumps({"result": "DRY_RUN", "decision_items": len(rows), "output": args.output, "writes": 0}, indent=2))
            return 0
        _atomic_new_file(args.output, _jsonl_payload(rows))
        print(json.dumps({"result": "DECISION_TEMPLATE_CREATED", "decision_items": len(rows), "output": args.output}, indent=2))
        return 0

    decisions = _load_decisions(args.decisions)
    result = apply_adjudication(left, right, decisions, adjudicator=args.adjudicator)
    if not result["complete"]:
        print(json.dumps({"result": "PENDING_REVIEW", "pending_review": result["pending_review"], "writes": 0}, indent=2))
        return 3
    if not args.write:
        print(json.dumps({
            "result": "DRY_RUN_PASS", "records": len(result["records"]),
            "resolved_fields": result["resolved_disagreement_fields"],
            "output_checksum": result["output_checksum"], "writes": 0,
        }, indent=2))
        return 0
    output = Path(args.output)
    audit = Path(args.audit_output)
    if output.resolve() == audit.resolve():
        raise AdjudicationError("adjudicated records and audit trail require separate output paths")
    if output.exists() or audit.exists():
        raise FileExistsError("refusing to overwrite adjudicated records or audit output")
    _atomic_new_file(output, _jsonl_payload(result["records"]))
    try:
        _atomic_new_file(audit, (json.dumps({key: value for key, value in result.items() if key not in {"records"}}, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    except Exception:
        # Do not remove the records file; preserve evidence of any partial
        # write and fail loudly for manual reconciliation.
        raise AdjudicationError(f"records were written to {output}, but audit output failed; preserve and reconcile both files")
    print(json.dumps({"result": "ADJUDICATED", "records": str(output), "audit": str(audit), "output_checksum": result["output_checksum"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
