#!/usr/bin/env python3
"""Current user-facing, read-only inspector and opener for uniform annotation batches."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from banking_tasci.data.annotation_batches import annotation_batch_display_name  # noqa: E402
from banking_tasci.data.calibration_workspace import create_annotation_workspace  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("technical_batch_id", help="Approved technical ID; physical filename is unchanged")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--guide-version", required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--write", action="store_true", help="Create the isolated working copy; default is dry-run")
    args = parser.parse_args(argv)
    batch_id = args.technical_batch_id
    if not args.write:
        print(json.dumps({
            "result": "DRY_RUN",
            "technical_batch_id": batch_id,
            "display_name": annotation_batch_display_name(batch_id),
            "writes": 0,
        }, indent=2))
        return 0
    result = create_annotation_workspace(
        ROOT,
        batch_id,
        actor=args.actor,
        reason=args.reason,
        guide_version=args.guide_version,
        workspace=ROOT / args.workspace if args.workspace else None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
