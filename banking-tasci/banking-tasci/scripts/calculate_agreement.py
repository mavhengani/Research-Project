"""Agreement_Calculator: computes inter-annotator agreement metrics between
two annotators' JSONL Annotation_Record files (Requirement 21).

Usage:
    python scripts/calculate_agreement.py \\
        --annotator-a data/annotations/pilot_alice.jsonl \\
        --annotator-b data/annotations/pilot_bob.jsonl \\
        --output outputs/inter_annotator_agreement.json

Reads both annotators' files via `banking_tasci.data.annotations.read_jsonl`,
restricts every metric to the records jointly annotated by BOTH annotators
(matched by `record_id`), and computes:

- Cohen's Kappa for `intent` (Req 21.2), aspect `category` (Req 21.3), and
  aspect `sentiment` (Req 21.4). Kappa uses `sklearn.metrics.cohen_kappa_score`
  when scikit-learn is installed, else a small pure-Python fallback that
  produces the same value.
- The exact aspect-span agreement rate (Req 21.5).
- Token-level aspect precision/recall/F1, treating annotator A's spans
  (expanded to whitespace-token indices) as reference and B's as
  hypothesis (Req 21.6).
- A disagreement count broken down by label type (Req 21.7).
- Which jointly annotated records have the most disagreement (Req 21.8).
- The number of jointly annotated records (Req 21.9).

It writes the main JSON report to `--output`
(conventionally `outputs/inter_annotator_agreement.json`) and per-record
disagreements to `outputs/annotation_disagreements.jsonl` (Req 21.10;
overridable via `--disagreements-output` so tests can redirect it).

This tool ONLY measures and reports; it NEVER auto-resolves, mutates, or
collapses any disagreement it detects (Req 21.11).

Aspect alignment for category/sentiment kappa: aspect spans from the two
annotators are aligned by identical (start, end) character offsets. Only
spans that BOTH annotators marked with the same (start, end) contribute a
paired (label_a, label_b) observation to the category/sentiment kappa;
spans that only one annotator marked (unmatched spans) are excluded from
the kappa paired-label lists (they cannot form a category/sentiment pair),
but they are still fully reflected in the exact-span-agreement rate, the
token-level P/R/F1, and the span disagreement count.

Undefined-kappa handling: when there are zero paired observations, or when
the expected-agreement denominator (1 - p_e) is zero (e.g. only a single
label class is present so agreement is trivial), Cohen's Kappa is
mathematically undefined; the report records `null` for that metric rather
than crashing or inventing a value.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data import annotations  # noqa: E402
from banking_tasci.data.annotations import AnnotationRecord, AspectSpan  # noqa: E402
from banking_tasci.logging_utils import get_logger  # noqa: E402

# Guarded import: use scikit-learn's implementation when available, else a
# pure-Python fallback (design.md: "sklearn.metrics.cohen_kappa_score if
# scikit-learn is available, else a small pure-Python fallback").
try:  # pragma: no cover - exercised by whichever branch is installed
    from sklearn.metrics import cohen_kappa_score as _sklearn_cohen_kappa

    _HAVE_SKLEARN = True
except Exception:  # pragma: no cover
    _sklearn_cohen_kappa = None
    _HAVE_SKLEARN = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "inter_annotator_agreement.json"
_DEFAULT_DISAGREEMENTS_PATH = PROJECT_ROOT / "outputs" / "annotation_disagreements.jsonl"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Defines the `--annotator-a`, `--annotator-b`, and `--output`
    command-line arguments (Req 21.1), plus an optional
    `--disagreements-output` for redirecting the per-record disagreements
    JSONL (defaults to `outputs/annotation_disagreements.jsonl`, Req 21.10)."""
    parser = argparse.ArgumentParser(
        prog="calculate_agreement.py",
        description=(
            "Compute inter-annotator agreement metrics (Cohen's Kappa for "
            "intent/category/sentiment, exact-span agreement, token-level "
            "P/R/F1, and disagreement breakdowns) between two annotators' "
            "JSONL Annotation_Record files."
        ),
    )
    parser.add_argument(
        "--annotator-a",
        required=True,
        help="Path to the first annotator's JSONL Annotation_Record file.",
    )
    parser.add_argument(
        "--annotator-b",
        required=True,
        help="Path to the second annotator's JSONL Annotation_Record file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the JSON inter-annotator agreement report to.",
    )
    parser.add_argument(
        "--disagreements-output",
        default=str(_DEFAULT_DISAGREEMENTS_PATH),
        help=(
            "Path to write the per-record disagreements JSONL to "
            "(default: outputs/annotation_disagreements.jsonl)."
        ),
    )
    parser.add_argument(
        "--disagreements",
        default=None,
        dest="disagreements",
        help=(
            "Alias for --disagreements-output. When both are provided, "
            "--disagreements takes precedence."
        ),
    )
    parser.add_argument(
        "--completed-only",
        action="store_true",
        default=False,
        help=(
            "Restrict agreement calculation to records where BOTH annotators "
            "have annotation_status='completed'. Records where either annotator "
            "has not finished are excluded. Use after partial annotation."
        ),
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        default=False,
        help=(
            "Fail (exit 1) when either annotator's file contains records that "
            "are not 'completed'. Use after full annotation to enforce completion."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index_by_record_id(records: list[AnnotationRecord]) -> dict[str, AnnotationRecord]:
    """Map `record_id -> record` for records carrying a usable string id.

    When the same `record_id` appears more than once in one annotator's
    file, the last occurrence wins; this is a degenerate input we do not
    otherwise try to reconcile here."""
    index: dict[str, AnnotationRecord] = {}
    for record in records:
        rid = getattr(record, "record_id", None)
        if isinstance(rid, str) and rid:
            index[rid] = record
    return index


def _valid_aspects(record: AnnotationRecord) -> list[AspectSpan]:
    """The record's aspect spans as a list of `AspectSpan` (empty when
    `aspects` is not a list)."""
    aspects = getattr(record, "aspects", None)
    if not isinstance(aspects, list):
        return []
    return [a for a in aspects if isinstance(a, AspectSpan)]


def _int_offsets(aspect: AspectSpan) -> "tuple[int, int] | None":
    """`(start, end)` for an aspect when both are plain ints, else None."""
    start, end = aspect.start, aspect.end
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if isinstance(start, int) and isinstance(end, int):
        return (start, end)
    return None


def _span_offset_set(record: AnnotationRecord) -> set[tuple[int, int]]:
    """The set of `(start, end)` character spans annotated on `record`."""
    spans: set[tuple[int, int]] = set()
    for aspect in _valid_aspects(record):
        offsets = _int_offsets(aspect)
        if offsets is not None:
            spans.add(offsets)
    return spans


def _offset_to_label(record: AnnotationRecord, field: str) -> dict[tuple[int, int], Any]:
    """Map `(start, end) -> aspect.<field>` for aligning aspects between the
    two annotators by identical character offsets."""
    mapping: dict[tuple[int, int], Any] = {}
    for aspect in _valid_aspects(record):
        offsets = _int_offsets(aspect)
        if offsets is not None:
            mapping[offsets] = getattr(aspect, field, None)
    return mapping


def _whitespace_tokens(text: str) -> list[tuple[int, int]]:
    """Whitespace-delimited tokens of `text` as `(start, end)` char spans."""
    tokens: list[tuple[int, int]] = []
    idx = 0
    length = len(text)
    while idx < length:
        if text[idx].isspace():
            idx += 1
            continue
        start = idx
        while idx < length and not text[idx].isspace():
            idx += 1
        tokens.append((start, idx))
    return tokens


def _token_indices_for_spans(record: AnnotationRecord) -> set[int]:
    """Set of whitespace-token indices covered by any aspect span on
    `record`. A token is covered when it overlaps an aspect's `[start, end)`
    character range."""
    text = getattr(record, "text", None)
    if not isinstance(text, str):
        return set()
    tokens = _whitespace_tokens(text)
    covered: set[int] = set()
    for aspect in _valid_aspects(record):
        offsets = _int_offsets(aspect)
        if offsets is None:
            continue
        span_start, span_end = offsets
        if span_start >= span_end:
            continue
        for tok_idx, (tok_start, tok_end) in enumerate(tokens):
            if tok_start < span_end and span_start < tok_end:
                covered.add(tok_idx)
    return covered


# ---------------------------------------------------------------------------
# Joint records (Req 21.9)
# ---------------------------------------------------------------------------


def joint_record_ids(
    records_a: list[AnnotationRecord], records_b: list[AnnotationRecord]
) -> set[str]:
    """The set of `record_id`s present in BOTH annotators' files."""
    ids_a = {
        rid
        for rid in (getattr(r, "record_id", None) for r in records_a)
        if isinstance(rid, str) and rid
    }
    ids_b = {
        rid
        for rid in (getattr(r, "record_id", None) for r in records_b)
        if isinstance(rid, str) and rid
    }
    return ids_a & ids_b


# ---------------------------------------------------------------------------
# Cohen's Kappa (Req 21.2-21.4)
# ---------------------------------------------------------------------------


def _cohens_kappa(labels_a: list[Any], labels_b: list[Any]) -> "float | None":
    """Cohen's Kappa over two equal-length aligned label lists.

    Uses scikit-learn when available, else a pure-Python fallback computing
    kappa = (p_o - p_e) / (1 - p_e). Returns None when kappa is undefined
    (no observations, or a zero (1 - p_e) denominator)."""
    if len(labels_a) != len(labels_b):
        raise ValueError("labels_a and labels_b must be the same length")
    n = len(labels_a)
    if n == 0:
        return None

    if _HAVE_SKLEARN:  # pragma: no cover - depends on install
        # Stringify labels so sklearn treats them as categorical and the
        # result matches the pure-Python fallback on identical inputs.
        str_a = [str(x) for x in labels_a]
        str_b = [str(x) for x in labels_b]
        value = float(_sklearn_cohen_kappa(str_a, str_b))
        if value != value:  # NaN -> undefined
            return None
        return value

    # Pure-Python fallback.
    observed_agree = sum(1 for x, y in zip(labels_a, labels_b) if x == y)
    p_o = observed_agree / n

    count_a: Counter = Counter(labels_a)
    count_b: Counter = Counter(labels_b)
    labels = set(count_a) | set(count_b)
    p_e = sum((count_a[l] / n) * (count_b[l] / n) for l in labels)

    denominator = 1.0 - p_e
    if denominator == 0:
        return None
    return (p_o - p_e) / denominator


def cohens_kappa_for_field(
    records_a: list[AnnotationRecord],
    records_b: list[AnnotationRecord],
    joint_ids: set[str],
    field_getter: Callable[[AnnotationRecord, AnnotationRecord], tuple[list[Any], list[Any]]],
) -> "float | None":
    """Cohen's Kappa for a categorical field over the joint records only.

    `field_getter(rec_a, rec_b)` returns a pair of positionally-aligned
    label lists for that one jointly-annotated record; the lists must be
    the same length. For a record-level field (e.g. intent) this is a
    single-element pair `([rec_a.intent], [rec_b.intent])`; for an
    aspect-level field (category/sentiment) it is the labels of the aspect
    spans the two annotators aligned by identical (start, end) offsets. The
    per-record pairs are concatenated and passed to `_cohens_kappa`.

    Returns None when kappa is undefined (see `_cohens_kappa`)."""
    index_a = _index_by_record_id(records_a)
    index_b = _index_by_record_id(records_b)

    all_a: list[Any] = []
    all_b: list[Any] = []
    for rid in sorted(joint_ids):
        rec_a = index_a.get(rid)
        rec_b = index_b.get(rid)
        if rec_a is None or rec_b is None:
            continue
        labels_a, labels_b = field_getter(rec_a, rec_b)
        all_a.extend(labels_a)
        all_b.extend(labels_b)
    return _cohens_kappa(all_a, all_b)


def _intent_getter(rec_a: AnnotationRecord, rec_b: AnnotationRecord) -> tuple[list[Any], list[Any]]:
    """Record-level intent as a one-element aligned pair (Req 21.2)."""
    return ([getattr(rec_a, "intent", None)], [getattr(rec_b, "intent", None)])


def _aspect_field_getter(field: str) -> Callable[[AnnotationRecord, AnnotationRecord], tuple[list[Any], list[Any]]]:
    """Aligns aspect spans by identical (start, end) offsets and returns the
    paired `<field>` labels for the spans BOTH annotators marked
    (Req 21.3/21.4). Unmatched spans contribute no pair."""

    def getter(rec_a: AnnotationRecord, rec_b: AnnotationRecord) -> tuple[list[Any], list[Any]]:
        map_a = _offset_to_label(rec_a, field)
        map_b = _offset_to_label(rec_b, field)
        shared = sorted(set(map_a) & set(map_b))
        labels_a = [map_a[span] for span in shared]
        labels_b = [map_b[span] for span in shared]
        return (labels_a, labels_b)

    return getter


# ---------------------------------------------------------------------------
# Exact span agreement (Req 21.5)
# ---------------------------------------------------------------------------


def exact_span_agreement(
    records_a: list[AnnotationRecord],
    records_b: list[AnnotationRecord],
    joint_ids: set[str],
) -> float:
    """Fraction of joint records where both annotators' aspect span SETS
    (each as a set of `(start, end)` tuples) match exactly. Returns 0.0 when
    there are no joint records."""
    if not joint_ids:
        return 0.0
    index_a = _index_by_record_id(records_a)
    index_b = _index_by_record_id(records_b)

    matches = 0
    total = 0
    for rid in joint_ids:
        rec_a = index_a.get(rid)
        rec_b = index_b.get(rid)
        if rec_a is None or rec_b is None:
            continue
        total += 1
        if _span_offset_set(rec_a) == _span_offset_set(rec_b):
            matches += 1
    if total == 0:
        return 0.0
    return matches / total


# ---------------------------------------------------------------------------
# Token-level P/R/F1 (Req 21.6)
# ---------------------------------------------------------------------------


def token_level_prf(
    records_a: list[AnnotationRecord],
    records_b: list[AnnotationRecord],
    joint_ids: set[str],
) -> dict:
    """Token-level aspect precision/recall/F1 over the joint records,
    treating annotator A's char-offset spans (expanded to whitespace-token
    indices) as the reference set and annotator B's as the hypothesis set.

    Reference/hypothesis are global sets of `(record_id, token_index)` pairs
    across all joint records. Precision = |ref ∩ hyp| / |hyp|,
    recall = |ref ∩ hyp| / |ref|, F1 = harmonic mean. A denominator of zero
    yields 0.0 for that metric (documented convention: no predicted/expected
    tokens)."""
    index_a = _index_by_record_id(records_a)
    index_b = _index_by_record_id(records_b)

    reference: set[tuple[str, int]] = set()
    hypothesis: set[tuple[str, int]] = set()
    for rid in joint_ids:
        rec_a = index_a.get(rid)
        rec_b = index_b.get(rid)
        if rec_a is None or rec_b is None:
            continue
        for tok_idx in _token_indices_for_spans(rec_a):
            reference.add((rid, tok_idx))
        for tok_idx in _token_indices_for_spans(rec_b):
            hypothesis.add((rid, tok_idx))

    true_positive = len(reference & hypothesis)
    precision = true_positive / len(hypothesis) if hypothesis else 0.0
    recall = true_positive / len(reference) if reference else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


# ---------------------------------------------------------------------------
# Disagreements (Req 21.7, 21.8, 21.10, 21.11)
# ---------------------------------------------------------------------------


def disagreements(
    records_a: list[AnnotationRecord],
    records_b: list[AnnotationRecord],
    joint_ids: set[str],
) -> list[dict]:
    """Per joint record, list which fields disagree and both annotators'
    values, for writing verbatim to the disagreements JSONL (Req 21.10).

    Detects four disagreement types (Req 21.7):
    - `intent`: the record-level intent labels differ.
    - `span`: the sets of `(start, end)` aspect spans differ.
    - `category`: for a span BOTH annotators marked, the categories differ.
    - `sentiment`: for a span BOTH annotators marked, the sentiments differ.

    Records with no disagreement produce no entry. Both original values are
    preserved verbatim; nothing is auto-resolved or mutated (Req 21.11)."""
    index_a = _index_by_record_id(records_a)
    index_b = _index_by_record_id(records_b)

    results: list[dict] = []
    for rid in sorted(joint_ids):
        rec_a = index_a.get(rid)
        rec_b = index_b.get(rid)
        if rec_a is None or rec_b is None:
            continue

        record_disagreements: list[dict] = []

        # Intent (record-level).
        intent_a = getattr(rec_a, "intent", None)
        intent_b = getattr(rec_b, "intent", None)
        if intent_a != intent_b:
            record_disagreements.append(
                {"type": "intent", "annotator_a": intent_a, "annotator_b": intent_b}
            )

        # Span sets.
        spans_a = _span_offset_set(rec_a)
        spans_b = _span_offset_set(rec_b)
        if spans_a != spans_b:
            record_disagreements.append(
                {
                    "type": "span",
                    "annotator_a": sorted(list(s) for s in spans_a),
                    "annotator_b": sorted(list(s) for s in spans_b),
                }
            )

        # Category / sentiment on spans both annotators marked.
        cat_a = _offset_to_label(rec_a, "category")
        cat_b = _offset_to_label(rec_b, "category")
        sent_a = _offset_to_label(rec_a, "sentiment")
        sent_b = _offset_to_label(rec_b, "sentiment")
        for span in sorted(set(cat_a) & set(cat_b)):
            if cat_a[span] != cat_b[span]:
                record_disagreements.append(
                    {
                        "type": "category",
                        "span": list(span),
                        "annotator_a": cat_a[span],
                        "annotator_b": cat_b[span],
                    }
                )
        for span in sorted(set(sent_a) & set(sent_b)):
            if sent_a[span] != sent_b[span]:
                record_disagreements.append(
                    {
                        "type": "sentiment",
                        "span": list(span),
                        "annotator_a": sent_a[span],
                        "annotator_b": sent_b[span],
                    }
                )

        if record_disagreements:
            results.append(
                {
                    "record_id": rid,
                    "disagreement_count": len(record_disagreements),
                    "disagreements": record_disagreements,
                }
            )
    return results


def _disagreement_counts_by_type(disagreement_records: list[dict]) -> dict[str, int]:
    """Aggregate disagreement counts by label type across all records
    (Req 21.7)."""
    counts: Counter = Counter()
    for entry in disagreement_records:
        for item in entry["disagreements"]:
            counts[item["type"]] += 1
    return dict(counts)


def _most_disagreement_records(disagreement_records: list[dict]) -> list[dict]:
    """Record ids with their disagreement counts, sorted descending by count
    (Req 21.8). Ties broken by record_id for determinism."""
    ranked = sorted(
        (
            {"record_id": entry["record_id"], "disagreement_count": entry["disagreement_count"]}
            for entry in disagreement_records
        ),
        key=lambda e: (-e["disagreement_count"], e["record_id"]),
    )
    return ranked


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    """Parse args -> read both annotators' JSONL -> optional filtering ->
    compute every agreement metric over the jointly-annotated records ->
    write the JSON report to `--output` and the per-record disagreements to
    the disagreements output -> return 0. A genuinely unreadable/unparsable
    input file prints a descriptive error to stderr and returns a non-zero
    exit code."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # --disagreements takes precedence over --disagreements-output.
    disagreements_output = args.disagreements if args.disagreements else args.disagreements_output

    logger = get_logger("calculate_agreement")

    try:
        records_a = annotations.read_jsonl(args.annotator_a)
    except FileNotFoundError:
        print(f"error: annotator-a file not found: {args.annotator_a}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print(f"error: could not read/parse --annotator-a ({args.annotator_a}): {exc}", file=sys.stderr)
        return 1

    try:
        records_b = annotations.read_jsonl(args.annotator_b)
    except FileNotFoundError:
        print(f"error: annotator-b file not found: {args.annotator_b}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print(f"error: could not read/parse --annotator-b ({args.annotator_b}): {exc}", file=sys.stderr)
        return 1

    # --require-complete: fail early if either file contains incomplete records.
    if args.require_complete:
        incomplete_a = [
            str(getattr(r, "record_id", "<unknown>"))
            for r in records_a
            if getattr(r, "annotation_status", None) != "completed"
        ]
        incomplete_b = [
            str(getattr(r, "record_id", "<unknown>"))
            for r in records_b
            if getattr(r, "annotation_status", None) != "completed"
        ]
        if incomplete_a or incomplete_b:
            if incomplete_a:
                print(
                    f"error: --require-complete failed: {len(incomplete_a)} incomplete "
                    f"record(s) in annotator-a file",
                    file=sys.stderr,
                )
            if incomplete_b:
                print(
                    f"error: --require-complete failed: {len(incomplete_b)} incomplete "
                    f"record(s) in annotator-b file",
                    file=sys.stderr,
                )
            return 1

    # --completed-only: restrict to records where both annotators are done.
    if args.completed_only:
        completed_ids_a = {
            str(getattr(r, "record_id", ""))
            for r in records_a
            if getattr(r, "annotation_status", None) == "completed"
        }
        completed_ids_b = {
            str(getattr(r, "record_id", ""))
            for r in records_b
            if getattr(r, "annotation_status", None) == "completed"
        }
        both_done = completed_ids_a & completed_ids_b
        records_a = [r for r in records_a if str(getattr(r, "record_id", "")) in both_done]
        records_b = [r for r in records_b if str(getattr(r, "record_id", "")) in both_done]

    joint_ids = joint_record_ids(records_a, records_b)

    intent_kappa = cohens_kappa_for_field(records_a, records_b, joint_ids, _intent_getter)
    category_kappa = cohens_kappa_for_field(
        records_a, records_b, joint_ids, _aspect_field_getter("category")
    )
    sentiment_kappa = cohens_kappa_for_field(
        records_a, records_b, joint_ids, _aspect_field_getter("sentiment")
    )
    span_agreement = exact_span_agreement(records_a, records_b, joint_ids)
    prf = token_level_prf(records_a, records_b, joint_ids)
    disagreement_records = disagreements(records_a, records_b, joint_ids)

    report = {
        "joint_record_count": len(joint_ids),
        "intent_kappa": intent_kappa,
        "category_kappa": category_kappa,
        "sentiment_kappa": sentiment_kappa,
        "exact_span_agreement": span_agreement,
        "token_level_prf": prf,
        "disagreement_counts_by_type": _disagreement_counts_by_type(disagreement_records),
        "most_disagreement_records": _most_disagreement_records(disagreement_records),
        "kappa_backend": "sklearn" if _HAVE_SKLEARN else "pure_python",
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    disagreements_path = Path(disagreements_output)
    disagreements_path.parent.mkdir(parents=True, exist_ok=True)
    with open(disagreements_path, "w", encoding="utf-8") as handle:
        for entry in disagreement_records:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(
        "Computed agreement over %d jointly-annotated records "
        "(intent_kappa=%s, category_kappa=%s, sentiment_kappa=%s); "
        "report -> %s, %d disagreement records -> %s",
        len(joint_ids),
        intent_kappa,
        category_kappa,
        sentiment_kappa,
        output_path,
        len(disagreement_records),
        disagreements_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
