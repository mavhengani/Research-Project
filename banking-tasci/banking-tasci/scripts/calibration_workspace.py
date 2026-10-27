#!/usr/bin/env python3
"""Deprecated compatibility CLI for uniform annotation batch workspaces.

Mutating commands are dry-run by default and require ``--apply``, an observed
current checksum, an observed workspace/guide version, explicit changed record
IDs, researcher acknowledgements, an actor, and a reason. It never creates
labels. Use ``scripts/manage_annotation_workspace.py`` for current naming.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from banking_tasci.data.calibration_workspace import (  # noqa: E402
    restore_checkpoint,
    save_checkpoint,
    verify_audit_chain,
    workspace_status,
    create_annotation_workspace,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "open", "save", "restore", "verify-audit"))
    parser.add_argument(
        "--workspace",
        default="data/annotations/new_pipeline_v1_candidate_2/calibration_workspace/calibration_001",
    )
    parser.add_argument("--candidate", help="Human-edited JSONL input to validate and checkpoint")
    parser.add_argument("--backup", help="Registered in-workspace backup JSONL to restore")
    parser.add_argument("--expected-current-sha256")
    parser.add_argument("--expected-workspace-version", type=int)
    parser.add_argument("--expected-guide-version")
    parser.add_argument("--explicit-record-id", action="append", default=[])
    parser.add_argument("--acknowledgement-record-id", action="append", default=[])
    parser.add_argument("--decision-actor-record-id", action="append", default=[])
    parser.add_argument("--candidate-number", type=int, choices=(2,), default=2)
    parser.add_argument("--guide-version", default="")
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--apply", action="store_true", help="Perform the save/restore; default is validation-only")
    return parser


def main(argv: list[str] | None = None) -> int:
    warnings.warn(
        "scripts/calibration_workspace.py is deprecated; use scripts/manage_annotation_workspace.py",
        DeprecationWarning,
        stacklevel=2,
    )
    args = _parser().parse_args(argv)
    workspace = ROOT / args.workspace
    if args.action == "open":
        batch_id = args.workspace.rsplit("/", 1)[-1]
        result = create_annotation_workspace(
            ROOT, batch_id, actor=args.actor, reason=args.reason,
            guide_version=args.guide_version, workspace=workspace,
        )
    elif args.action == "status":
        result = workspace_status(workspace, project_root=ROOT)
    elif args.action == "verify-audit":
        result = verify_audit_chain(workspace)
    else:
        if not args.expected_current_sha256:
            raise SystemExit("--expected-current-sha256 is required for save/restore")
        if args.expected_workspace_version is None or not args.expected_guide_version:
            raise SystemExit("--expected-workspace-version and --expected-guide-version are required for save/restore")
        if not args.actor.strip() or not args.reason.strip():
            raise SystemExit("--actor and --reason are required for save/restore")
        if args.action == "save":
            if not args.candidate:
                raise SystemExit("--candidate is required for save")
            result = save_checkpoint(
                workspace,
                ROOT / args.candidate,
                project_root=ROOT,
                expected_current_sha256=args.expected_current_sha256,
                actor=args.actor,
                reason=args.reason,
                expected_workspace_version=args.expected_workspace_version,
                expected_guide_version=args.expected_guide_version,
                explicit_record_ids=args.explicit_record_id,
                researcher_acknowledgements={rid: "I confirm these are my own human annotation decisions." for rid in args.acknowledgement_record_id},
                decision_actors={rid: args.actor for rid in args.decision_actor_record_id},
                apply=args.apply,
            )
        else:
            if not args.backup:
                raise SystemExit("--backup is required for restore")
            result = restore_checkpoint(
                workspace,
                args.backup,
                project_root=ROOT,
                expected_current_sha256=args.expected_current_sha256,
                actor=args.actor,
                reason=args.reason,
                expected_workspace_version=args.expected_workspace_version,
                expected_guide_version=args.expected_guide_version,
                apply=args.apply,
            )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
