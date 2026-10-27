"""create_combined_gold.py — Phase 3B Step 1.

Combines pilot_adjudicated.jsonl and south_african_adjudicated.jsonl into a
single combined_adjudicated_v2.jsonl for Phase 3B baseline training.

Behaviour:
- Reads both gold files from data/annotations/.
- Checks for duplicate record_ids across files.
  If any exist, writes outputs/combined_gold_conflicts.json and stops (exit 1).
- Writes data/annotations/combined_adjudicated_v2.jsonl (no extra fields).
- Writes outputs/combined_gold_provenance.json: {record_id -> source_file}.

The combined JSONL is written without injecting any extra fields so the
existing annotation schema validator accepts it unchanged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import read_jsonl  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GOLD_FILES = [
    ("pilot_adjudicated.jsonl", PROJECT_ROOT / "data" / "annotations" / "pilot_adjudicated.jsonl"),
    ("south_african_adjudicated_v2.jsonl", PROJECT_ROOT / "data" / "annotations" / "south_african_adjudicated_v2.jsonl"),
]
OUTPUT_JSONL = PROJECT_ROOT / "data" / "annotations" / "combined_adjudicated_v2.jsonl"
CONFLICT_REPORT = PROJECT_ROOT / "outputs" / "combined_gold_conflicts.json"
PROVENANCE_FILE = PROJECT_ROOT / "outputs" / "combined_gold_provenance.json"


def _raw_lines(path: Path) -> list[str]:
    """Return non-blank raw JSONL lines from path."""
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    print("Step 1: Creating combined gold dataset...")

    # --- 1. Read records from both gold files. ---
    all_ids: dict[str, str] = {}          # record_id -> source filename
    file_lines: list[tuple[str, str]] = []  # (source_filename, raw_line)

    for source_name, path in GOLD_FILES:
        if not path.is_file():
            print(f"ERROR: Gold file not found: {path}", file=sys.stderr)
            return 1
        lines = _raw_lines(path)
        print(f"  {source_name}: {len(lines)} records")
        for line in lines:
            file_lines.append((source_name, line))

    # --- 2. Check for duplicate record_ids. ---
    seen: dict[str, str] = {}   # record_id -> first source
    duplicates: list[dict] = []

    for source_name, line in file_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Invalid JSON in {source_name}: {exc}", file=sys.stderr)
            return 1
        rid = obj.get("record_id")
        if rid is None:
            print(f"WARNING: record missing record_id in {source_name}", file=sys.stderr)
            continue
        rid = str(rid)
        if rid in seen:
            duplicates.append({"record_id": rid, "first_seen_in": seen[rid], "also_in": source_name})
        else:
            seen[rid] = source_name

    if duplicates:
        CONFLICT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        CONFLICT_REPORT.write_text(json.dumps({"duplicate_count": len(duplicates), "duplicates": duplicates}, indent=2), encoding="utf-8")
        print(
            f"ERROR: {len(duplicates)} duplicate record_id(s) found across gold files. "
            f"Conflict report written to {CONFLICT_REPORT}. Stopping.",
            file=sys.stderr,
        )
        return 1

    print(f"  No duplicate record_ids found across files.")

    # --- 3. Build provenance mapping. ---
    provenance: dict[str, str] = {}
    for source_name, line in file_lines:
        obj = json.loads(line)
        rid = str(obj["record_id"])
        provenance[rid] = source_name

    # --- 4. Write combined JSONL (no extra fields). ---
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSONL.open("w", encoding="utf-8") as fh:
        for _source_name, line in file_lines:
            fh.write(line.rstrip() + "\n")

    # --- 5. Write provenance file. ---
    PROVENANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE_FILE.write_text(
        json.dumps({"description": "record_id -> source gold file", "provenance": provenance}, indent=2),
        encoding="utf-8",
    )

    total = len(provenance)
    print(f"  Combined JSONL written to: {OUTPUT_JSONL} ({total} records)")
    print(f"  Provenance written to:     {PROVENANCE_FILE}")

    # Verify read-back.
    try:
        check = read_jsonl(OUTPUT_JSONL)
        print(f"  Read-back verification: {len(check)} records parsed OK.")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Read-back failed: {exc}", file=sys.stderr)
        return 1

    print("Step 1 COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
