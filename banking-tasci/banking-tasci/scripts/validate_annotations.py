"""Annotation_Validator: validates a JSONL Annotation_Record file against
the schema and label rules in Requirement 19, and writes a JSON validation
report (Req 19.14).

Usage:
    python scripts/validate_annotations.py \\
        --input data/annotations/pilot_annotator_a.jsonl \\
        --output outputs/annotation_validation_report.json

Reads the input JSONL via `banking_tasci.data.annotations.read_jsonl`,
partitions the records into valid/invalid via `annotations.validate_all`
(which reuses the pure validation rules in that module rather than
re-implementing them here), and writes a JSON report summarising counts,
errors grouped by type with the affected record IDs, label distributions
over the VALID records only, aspect counts, zero-aspect count, and the
ambiguous-intent count.

A file full of invalid records is a SUCCESSFUL validation run: `main`
returns 0 and the invalid records are simply reported in the report's
`invalid_count`/`errors_by_type`/`affected_record_ids`. Only a genuinely
unreadable or unparsable `--input` (missing file, or a line that is not
valid JSON) is a CLI failure: `main` prints a descriptive error to stderr
and returns a non-zero exit code (Req 19.1, design.md Annotation_Validator).

The validator never modifies or auto-corrects any record (Req 19.13); it
only reads records and classifies them.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data import annotations  # noqa: E402
from banking_tasci.data.annotations import AnnotationRecord, AspectSpan  # noqa: E402
from banking_tasci.logging_utils import get_logger  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_arg_parser() -> argparse.ArgumentParser:
    """Defines the `--input` and `--output` command-line arguments
    (Req 19.1): the JSONL Annotation_Record file to validate and the path
    to write the JSON validation report to.

    Additional flags:
    --completed-only   Validate only records with annotation_status="completed";
                       records with "not_started" or "in_progress" are silently
                       skipped. Useful during partial annotation to check
                       quality of completed records without treating unfinished
                       records as errors.
    --require-complete Fail (exit 1) when any record has annotation_status
                       that is not "completed". Used for final validation to
                       enforce that annotation is fully done.
    """
    parser = argparse.ArgumentParser(
        prog="validate_annotations.py",
        description=(
            "Validate a JSONL Annotation_Record file against the schema and "
            "label rules in Requirement 19 and write a JSON validation "
            "report."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the JSONL Annotation_Record file to validate.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the JSON validation report to.",
    )
    parser.add_argument(
        "--completed-only",
        action="store_true",
        default=False,
        help=(
            "Validate only records with annotation_status='completed'; "
            "skip not_started and in_progress records. "
            "Useful during partial annotation."
        ),
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        default=False,
        help=(
            "Fail with exit code 1 when any record has annotation_status "
            "that is not 'completed'. Use for final validation."
        ),
    )
    return parser


def _valid_aspects(record: AnnotationRecord) -> list[AspectSpan]:
    """The record's aspect spans as a list (empty when `aspects` is not a
    list), for label-distribution/aspect-count aggregation over records
    already known to be valid."""
    aspects = getattr(record, "aspects", None)
    if not isinstance(aspects, list):
        return []
    return [a for a in aspects if isinstance(a, AspectSpan)]


def build_report(
    valid_records: list[AnnotationRecord],
    invalid: "dict[str, list]",
) -> dict:
    """Build the JSON validation report dict required by Req 19.14 from the
    `(valid_records, invalid)` output of `annotations.validate_all`.

    - `valid_count` / `invalid_count`: sizes of the two partitions.
    - `errors_by_type`: `{error_type: count}` over every ValidationError in
      the invalid dict's per-record lists.
    - `affected_record_ids`: `{error_type: [record_id, ...]}` (de-duplicated,
      order-preserving) over the same ValidationErrors.
    - `label_distributions`: `aspect_category`/`sentiment`/`intent` counts,
      computed over the VALID records only.
    - `aspect_count`: total aspect spans across valid records.
    - `zero_aspect_count`: valid records with an empty aspects list.
    - `ambiguous_intent_count`: valid records with `intent_ambiguous=true`.
    """
    errors_by_type: "Counter[str]" = Counter()
    affected_record_ids: "dict[str, list[str]]" = defaultdict(list)
    seen: "dict[str, set[str]]" = defaultdict(set)

    for error_list in invalid.values():
        for error in error_list:
            errors_by_type[error.error_type] += 1
            if error.record_id not in seen[error.error_type]:
                seen[error.error_type].add(error.record_id)
                affected_record_ids[error.error_type].append(error.record_id)

    category_counts: "Counter[str]" = Counter()
    sentiment_counts: "Counter[str]" = Counter()
    intent_counts: "Counter[str]" = Counter()
    aspect_count = 0
    zero_aspect_count = 0
    ambiguous_intent_count = 0

    for record in valid_records:
        aspects = _valid_aspects(record)
        aspect_count += len(aspects)
        if len(aspects) == 0:
            zero_aspect_count += 1
        for aspect in aspects:
            category_counts[aspect.category] += 1
            sentiment_counts[aspect.sentiment] += 1

        intent = getattr(record, "intent", None)
        if intent is not None:
            intent_counts[intent] += 1

        if getattr(record, "intent_ambiguous", None) is True:
            ambiguous_intent_count += 1

    return {
        "valid_count": len(valid_records),
        "invalid_count": len(invalid),
        "errors_by_type": dict(errors_by_type),
        "affected_record_ids": {k: list(v) for k, v in affected_record_ids.items()},
        "label_distributions": {
            "aspect_category": dict(category_counts),
            "sentiment": dict(sentiment_counts),
            "intent": dict(intent_counts),
        },
        "aspect_count": aspect_count,
        "zero_aspect_count": zero_aspect_count,
        "ambiguous_intent_count": ambiguous_intent_count,
    }


def main(argv: "list[str] | None" = None) -> int:
    """Parse args -> `read_jsonl(--input)` -> optional filtering ->
    `validate_all(records)` -> `build_report` -> write JSON to `--output`
    -> return 0 for a successful validation RUN (even when the file
    contains invalid records).

    With --completed-only: only records whose annotation_status is
    "completed" are validated; others are silently skipped.

    With --require-complete: exits 1 when any record is not "completed",
    printing the count of incomplete records to stderr.

    If `--input` cannot be read or parsed as JSONL, print a descriptive
    error to stderr and return a non-zero exit code WITHOUT writing a
    report.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logger = get_logger("validate_annotations")

    try:
        records = annotations.read_jsonl(args.input)
    except FileNotFoundError:
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print(f"error: could not read/parse --input as JSONL ({args.input}): {exc}", file=sys.stderr)
        return 1

    # --require-complete: fail early if any record is incomplete.
    if args.require_complete:
        incomplete = [
            getattr(r, "record_id", "<unknown>")
            for r in records
            if getattr(r, "annotation_status", None) != "completed"
        ]
        if incomplete:
            print(
                f"error: --require-complete failed: {len(incomplete)} record(s) are not "
                f"'completed' (e.g. {incomplete[:5]})",
                file=sys.stderr,
            )
            return 1

    # --completed-only: drop non-completed records before validating.
    if args.completed_only:
        records = [r for r in records if getattr(r, "annotation_status", None) == "completed"]

    valid_records, invalid = annotations.validate_all(records)
    report = build_report(valid_records, invalid)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info(
        "Validated %d records from %s: %d valid, %d invalid; report written to %s",
        len(records),
        args.input,
        report["valid_count"],
        report["invalid_count"],
        output_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
