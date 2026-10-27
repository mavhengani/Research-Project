#!/usr/bin/env python3
"""Manage any approved uniform new_pipeline_v1 annotation batch workspace."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from banking_tasci.data.calibration_workspace import (  # noqa: E402
    restore_checkpoint,
    save_checkpoint,
    verify_audit_chain,
    workspace_status,
)

ACK = "I confirm these are my own human annotation decisions."


def _pairs(items: list[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"{label} values must be RECORD_ID=VALUE")
        record_id, value = item.split("=", 1)
        if not record_id or record_id in result:
            raise SystemExit(f"duplicate or empty record ID in {label}")
        result[record_id] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "save", "restore", "verify-audit"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--backup")
    parser.add_argument("--expected-current-sha256")
    parser.add_argument("--expected-workspace-version", type=int)
    parser.add_argument("--expected-guide-version")
    parser.add_argument("--record-id", action="append", default=[])
    parser.add_argument("--acknowledge-record", action="append", default=[], metavar="RECORD_ID")
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--apply", action="store_true", help="Apply mutation; default is read-only dry-run")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    if not workspace.is_absolute():
        workspace = ROOT / workspace
    if args.action == "status":
        result = workspace_status(workspace, project_root=ROOT)
    elif args.action == "verify-audit":
        result = verify_audit_chain(workspace)
    else:
        if not args.expected_current_sha256 or args.expected_workspace_version is None or not args.expected_guide_version:
            raise SystemExit("save/restore require expected current checksum, workspace version, and guide version")
        if not args.actor.strip() or not args.reason.strip():
            raise SystemExit("save/restore require an actor and reason")
        if args.action == "save":
            if not args.candidate:
                raise SystemExit("save requires --candidate")
            candidate = Path(args.candidate)
            if not candidate.is_absolute():
                candidate = ROOT / candidate
            result = save_checkpoint(
                workspace, candidate, project_root=ROOT,
                expected_current_sha256=args.expected_current_sha256,
                expected_workspace_version=args.expected_workspace_version,
                expected_guide_version=args.expected_guide_version,
                explicit_record_ids=args.record_id,
                researcher_acknowledgements={rid: ACK for rid in args.acknowledge_record},
                decision_actors={rid: args.actor for rid in args.acknowledge_record},
                actor=args.actor, reason=args.reason, apply=args.apply,
            )
        else:
            if not args.backup:
                raise SystemExit("restore requires --backup")
            result = restore_checkpoint(
                workspace, args.backup, project_root=ROOT,
                expected_current_sha256=args.expected_current_sha256,
                expected_workspace_version=args.expected_workspace_version,
                expected_guide_version=args.expected_guide_version,
                actor=args.actor, reason=args.reason, apply=args.apply,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
