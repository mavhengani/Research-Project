"""check_training_readiness.py — supervised-training readiness gate CLI (Part 6).

Usage:
    python scripts/check_training_readiness.py \\
        --annotations data/annotations/pilot_adjudicated.jsonl \\
        --split-dir data/processed

Runs the full set of Part-6 readiness checks (see
``banking_tasci.training.supervised_gate``) and prints a per-check report.
Exits non-zero and prints the exact blocked message when training is not ready.

At the current project stage the pilot is still UNANNOTATED, so this command
is expected to fail safely with:

    Supervised training is blocked: adjudicated gold annotations and
    leakage-safe split manifests are missing.

It never fabricates or infers any label — it only reads and inspects files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.training.supervised_gate import (  # noqa: E402
    SUPERVISED_BLOCKED_MESSAGE,
    check_supervised_readiness,
)

DEFAULT_ANNOTATIONS = "data/annotations/pilot_adjudicated.jsonl"
DEFAULT_SPLIT_DIR = "data/processed"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_training_readiness.py",
        description=(
            "Verify that adjudicated gold annotations and leakage-safe split "
            "manifests exist and are valid before any supervised baseline "
            "training is attempted."
        ),
    )
    parser.add_argument(
        "--annotations",
        default=DEFAULT_ANNOTATIONS,
        help=f"Path to the adjudicated gold JSONL (default: {DEFAULT_ANNOTATIONS}).",
    )
    parser.add_argument(
        "--split-dir",
        default=DEFAULT_SPLIT_DIR,
        help=f"Directory holding the split manifests (default: {DEFAULT_SPLIT_DIR}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full report as JSON on stdout.",
    )
    return parser


def main(argv: "list[str] | None" = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    report = check_supervised_readiness(args.annotations, args.split_dir)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("Supervised-training readiness report")
        print("=" * 40)
        for check in report.checks:
            mark = "PASS" if check.passed else "FAIL"
            line = f"[{mark}] {check.name}"
            if check.detail:
                line += f" — {check.detail}"
            print(line)
        print("=" * 40)

    if not report.ready:
        print(SUPERVISED_BLOCKED_MESSAGE, file=sys.stderr)
        return 1

    print("READY: adjudicated gold + leakage-safe splits verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

