#!/usr/bin/env python3
"""Materialise the verified v2 South African candidate corpus.

Writes the **100,768-record** v2 evidence-based candidate selection to its own
immutable, checksummed artifact, so Requirements Section 4.1's South African
starting corpus stops being "reproducible in principle" and becomes a concrete
dataset with provenance.

**One canonical filter.** Selection is delegated entirely to
``banking_tasci.data.sa_candidates_v2.select_v2_candidates`` - the extracted,
authoritative implementation of the vectorised keyword path that produced the
historical count. The rules are NOT reimplemented here.

Note that ``sa_candidate_filter.classify_candidate`` is deliberately *not* used:
that module carries duplicate definitions (the live ``classify_candidate`` is
the regex variant at line 757), and it disagrees with the authoritative
vectorised selection on roughly 1.9% of rows, so it would not reproduce 100,768.

**Verification before writing.** Every assertion below runs *before* any output
file is created. The script fails loudly rather than coercing: it never
truncates, samples, pads, appends, or re-filters to reach a target count.

Usage::

    # Verify and write (refuses if the output already exists)
    python scripts/materialize_south_africa_candidates_v2.py

    # Verify only; write nothing
    python scripts/materialize_south_africa_candidates_v2.py --dry-run

    # Replace an existing output deliberately
    python scripts/materialize_south_africa_candidates_v2.py --overwrite

Exit codes: ``0`` success, ``1`` usage/IO error, ``2`` verification failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd  # noqa: E402

from banking_tasci.data.sa_candidates_v2 import (  # noqa: E402
    EXPECTED_RULE_COUNTS,
    EXPECTED_TOTAL,
    SELECTION_VERSION,
    select_v2_candidates,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SOURCE = PROJECT_ROOT / "data" / "interim" / "south_africa_prepared.parquet"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "new_pipeline_v1"
    / "south_africa_candidates_v2.parquet"
)
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "artifacts"
    / "manifests"
    / "new_pipeline_v1"
    / "south_africa_candidates_v2_materialisation.json"
)

PIPELINE_VERSION = "new_pipeline_v1"
NO_COMMIT_MARKER = "UNKNOWN_NO_COMMIT"

# Columns carried into the materialised corpus. Provenance, privacy-safe text,
# and duplicate/leakage grouping are preserved; nothing is invented.
#
# Deliberately EXCLUDED: `candidate_strata` and `filter_reason`. Those are
# candidate-rule metadata, and Requirements Section 6.5 forbids data-preparation
# rules becoming task labels. The attributed rule is recorded in the REPORT for
# auditability, not attached to records where an annotator could see it.
CARRY_COLUMNS = (
    "record_id",
    "source",
    "region",
    "bank",
    "text",
    "previous_text",
    "context_available",
    "created_at",
    "near_dup_group_id",
    "near_dup_flag",
    "thread_id",
    "rating",
    "title",
)

# Columns that must never appear in the output (task labels / predictive
# shortcuts / sampling metadata).
FORBIDDEN_OUTPUT_COLUMNS = (
    "target",
    "target_start",
    "target_end",
    "category",
    "entity",
    "attribute",
    "sentiment",
    "intent",
    "primary_intent",
    "opinions",
    "aspects",
    "annotation_status",
    "annotation_notes",
    "split",
    "candidate_strata",
    "filter_reason",
    "customer_feedback_candidate",
)


class VerificationError(RuntimeError):
    """Raised when a pre-write assertion fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def logical_checksum(frame: pd.DataFrame) -> str:
    """Order-independent checksum of the selected identifier set.

    Parquet bytes can vary between writes (compression, metadata, library
    version), so byte checksums are unsuitable for asserting that two
    materialisations are logically identical. Hashing the sorted identifier set
    gives a stable, reproducible fingerprint of *which records* were selected.
    """
    joined = "\n".join(sorted(frame["record_id"].astype(str)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,
        )
    except Exception:
        return NO_COMMIT_MARKER
    if result.returncode != 0:
        return NO_COMMIT_MARKER
    return result.stdout.strip() or NO_COMMIT_MARKER


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="materialize_south_africa_candidates_v2.py",
        description=(
            "Materialise the verified 100,768-record v2 South African candidate "
            "corpus. Verifies before writing and never coerces counts."
        ),
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument(
        "--expected-total",
        type=int,
        default=EXPECTED_TOTAL,
        help=f"Expected selected row count (default {EXPECTED_TOTAL}).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file (refused by default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify and report; write nothing.",
    )
    parser.add_argument(
        "--allow-count-change",
        action="store_true",
        help=(
            "Permit a selected count differing from --expected-total. Requires a "
            "documented source-version change; use only deliberately."
        ),
    )
    return parser


def verify_selection(
    parent: pd.DataFrame,
    selected: pd.DataFrame,
    result,
    expected_total: int,
    allow_count_change: bool,
) -> dict:
    """Run every pre-write assertion. Raises :class:`VerificationError`."""
    checks: dict[str, object] = {}

    # (3) exact row count
    checks["row_count"] = int(len(selected))
    if len(selected) != expected_total and not allow_count_change:
        raise VerificationError(
            f"selected {len(selected)} rows but expected {expected_total}. "
            f"Refusing to write. No truncation, sampling, or padding is applied "
            f"to reach an expected count. Re-run with --allow-count-change only "
            f"alongside a documented source-version change."
        )

    # (4)(5) unique identifiers, zero duplicates
    ids = selected["record_id"].astype(str)
    unique_count = int(ids.nunique())
    duplicate_count = int(len(ids) - unique_count)
    checks["unique_record_count"] = unique_count
    checks["duplicate_record_count"] = duplicate_count
    if duplicate_count != 0:
        raise VerificationError(
            f"{duplicate_count} duplicate record_id value(s) in the selection; "
            f"identifiers must be unique."
        )
    if unique_count != expected_total and not allow_count_change:
        raise VerificationError(
            f"{unique_count} unique identifiers but expected {expected_total}."
        )

    # (6)(7) every selected ID exists in the parent, and is a STRICT subset
    parent_ids = set(parent["record_id"].astype(str))
    selected_ids = set(ids)
    missing = selected_ids - parent_ids
    checks["ids_present_in_parent"] = len(missing) == 0
    if missing:
        raise VerificationError(
            f"{len(missing)} selected identifier(s) absent from the parent source; "
            f"selection must derive entirely from the parent."
        )
    strict_subset = selected_ids < parent_ids
    checks["strict_subset_verified"] = bool(strict_subset)
    checks["parent_unique_ids"] = len(parent_ids)
    if not strict_subset:
        raise VerificationError(
            "selected identifiers are not a STRICT subset of the parent set "
            f"(selected {len(selected_ids)}, parent {len(parent_ids)})."
        )

    # rule counts must sum to the total and match expectations
    rule_counts = result.rule_counts
    checks["rule_counts"] = rule_counts
    rule_sum = sum(rule_counts.values())
    checks["rule_counts_sum"] = rule_sum
    if rule_sum != len(selected):
        raise VerificationError(
            f"rule counts sum to {rule_sum} but {len(selected)} rows were selected."
        )
    expected_rules = dict(sorted(EXPECTED_RULE_COUNTS.items()))
    checks["expected_rule_counts"] = expected_rules
    checks["rule_counts_match_expected"] = rule_counts == expected_rules
    if rule_counts != expected_rules and not allow_count_change:
        raise VerificationError(
            f"rule-level counts {rule_counts} differ from the documented "
            f"{expected_rules}. Refusing to write without --allow-count-change "
            f"and a documented source-version change."
        )

    # (9) privacy-safe text and (no task labels)
    leaked = [c for c in FORBIDDEN_OUTPUT_COLUMNS if c in selected.columns]
    checks["forbidden_columns_present"] = leaked
    if leaked:
        raise VerificationError(
            "output would contain forbidden column(s): " + ", ".join(leaked)
        )
    identifier_columns = [
        c
        for c in ("username", "user_name", "screen_name", "author", "tweet_id")
        if c in selected.columns
    ]
    checks["raw_identifier_columns_present"] = identifier_columns
    if identifier_columns:
        raise VerificationError(
            "output would contain raw identifier column(s): "
            + ", ".join(identifier_columns)
        )
    checks["privacy_status"] = "anonymised_upstream_no_raw_identifier_columns"

    return checks


def write_atomic(frame: pd.DataFrame, output: Path) -> None:
    """Write parquet atomically: temp file in the same directory, then rename.

    A partial file is never observable at ``output``, and a failure mid-write
    leaves no temporary file behind.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + f".tmp.{os.getpid()}")
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, output)  # atomic within a filesystem
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)

    source = Path(args.source)
    output = Path(args.output)
    report_path = Path(args.report)

    if not source.is_file():
        print(f"Error: source not found: {source}", file=sys.stderr)
        return 1

    if output.exists() and not args.overwrite and not args.dry_run:
        print(
            f"Error: output already exists: {output}\n"
            f"Refusing to overwrite a materialised corpus. Pass --overwrite to "
            f"replace it deliberately.",
            file=sys.stderr,
        )
        return 1

    print("=== materialise South African v2 candidates ===")
    print(f"  selection version: {SELECTION_VERSION}")
    print(f"  source:            {source}")
    print("  hashing source (large file, please wait)...")
    source_sha = sha256_file(source)
    print(f"  source sha256:     {source_sha}")

    print("  loading parent source...")
    parent = pd.read_parquet(source)
    print(f"  parent rows:       {len(parent):,}")

    print("  applying canonical v2 selection...")
    result = select_v2_candidates(parent)
    print(f"  selected rows:     {result.total:,}")
    print(f"  rule counts:       {result.rule_counts}")

    selected_full = parent.loc[result.mask]
    carry = [c for c in CARRY_COLUMNS if c in selected_full.columns]
    selected = selected_full[carry].copy()

    try:
        checks = verify_selection(
            parent, selected, result, args.expected_total, args.allow_count_change
        )
    except VerificationError as exc:
        print(f"\nVERIFICATION FAILED: {exc}", file=sys.stderr)
        print("No output was written.", file=sys.stderr)
        return 2

    print("\n  verification:")
    print(f"    row count:            {checks['row_count']:,}")
    print(f"    unique identifiers:   {checks['unique_record_count']:,}")
    print(f"    duplicate identifiers:{checks['duplicate_record_count']}")
    print(f"    all IDs in parent:    {checks['ids_present_in_parent']}")
    print(f"    strict subset:        {checks['strict_subset_verified']}")
    print(f"    rule counts match:    {checks['rule_counts_match_expected']}")
    print(f"    forbidden columns:    {checks['forbidden_columns_present'] or 'none'}")

    logical = logical_checksum(selected)
    print(f"    logical checksum:     {logical}")

    if args.dry_run:
        print("\nDRY RUN - verification passed; nothing was written.")
        return 0

    print(f"\n  writing atomically to {output} ...")
    write_atomic(selected, output)
    output_sha = sha256_file(output)
    print(f"  output sha256:     {output_sha}")

    report = {
        "pipeline_version": PIPELINE_VERSION,
        "selection_version": SELECTION_VERSION,
        "source_path": str(source),
        "source_sha256": source_sha,
        "source_row_count": int(len(parent)),
        "output_path": str(output),
        "output_sha256": output_sha,
        "output_row_count": int(len(selected)),
        "output_logical_checksum": logical,
        "unique_record_count": checks["unique_record_count"],
        "duplicate_record_count": checks["duplicate_record_count"],
        "strict_subset_verified": checks["strict_subset_verified"],
        "ids_present_in_parent": checks["ids_present_in_parent"],
        "parent_unique_ids": checks["parent_unique_ids"],
        "privacy_status": checks["privacy_status"],
        "rule_counts": checks["rule_counts"],
        "expected_rule_counts": checks["expected_rule_counts"],
        "rule_counts_match_expected": checks["rule_counts_match_expected"],
        "rule_counts_sum": checks["rule_counts_sum"],
        "columns_written": carry,
        "columns_excluded_as_candidate_metadata": [
            c for c in ("candidate_strata", "filter_reason", "customer_feedback_candidate")
            if c in parent.columns
        ],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generation_command": "python scripts/materialize_south_africa_candidates_v2.py "
        + " ".join(argv if argv is not None else sys.argv[1:]),
        "git_commit": git_commit(),
        "notes": [
            "Selection delegated to banking_tasci.data.sa_candidates_v2."
            "select_v2_candidates - the single canonical v2 implementation.",
            "sa_candidate_filter.classify_candidate was NOT used: that module has "
            "duplicate definitions (live variant at line 757) and disagrees with "
            "the authoritative vectorised selection on ~1.9% of rows, so it would "
            "not reproduce 100,768.",
            "Candidate-rule columns (candidate_strata, filter_reason) are excluded "
            "from the output per Requirements 6.5; the attributed rule is recorded "
            "in this report for audit only.",
            "All verification ran BEFORE writing; no truncation, sampling, padding, "
            "or re-filtering was applied to reach the expected count.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  report:            {report_path}")

    print("\nMaterialisation complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
