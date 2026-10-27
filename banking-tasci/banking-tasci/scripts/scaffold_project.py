"""CLI entry point that scaffolds the banking-tasci project structure.

Usage:
    python scripts/scaffold_project.py

Idempotent: safe to re-run against an existing project (Req 1.4). Aborts and
reports the failing path if any step fails (Req 1.5).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.scaffold import ScaffoldError, scaffold_project  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# The two source CSVs live one directory above banking-tasci/ (the workspace
# root), per design.md.
WORKSPACE_ROOT = PROJECT_ROOT.parent


def main() -> int:
    try:
        scaffold_project(root=PROJECT_ROOT, source_csv_dir=WORKSPACE_ROOT)
    except ScaffoldError as exc:
        print(f"Scaffolding aborted: failed to create {exc.path}: {exc.reason}", file=sys.stderr)
        return 1
    print(f"banking-tasci project scaffolded at {PROJECT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
