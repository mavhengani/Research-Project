"""Adjudication_Tool: resolve disagreements between two annotators' JSONL
Annotation_Record files into a single trustworthy gold set, without
discarding either annotator's original judgment (Requirement 22).

Usage:
    python scripts/adjudicate_annotations.py \\
        --annotator-a data/annotations/pilot_alice.jsonl \\
        --annotator-b data/annotations/pilot_bob.jsonl \\
        --adjudicator-id lead_annotator \\
        --output data/annotations/pilot_adjudicated.jsonl

Workflow (Req 22.1-22.6):
- Read both annotators' files and identify records with a field-level
  disagreement (Req 22.1), reusing the disagreement-detection logic already
  implemented in `scripts/calculate_agreement.py` rather than duplicating it.
- Present each disagreement to a human adjudicator (Req 22.2) and let them
  select annotator A's value, annotator B's value, or type a new final value
  per disputed field (Req 22.3).
- Write the resolved gold set to `data/annotations/pilot_adjudicated.jsonl`
  by default (Req 22.4).
- Preserve BOTH original annotators' values for every adjudicated record via
  a per-disputed-field `adjudication` sub-object (Req 22.5), which also
  records the adjudicator identifier and adjudication notes (Req 22.6).

Design note — testability:
The interactive stdin loop (`adjudicate_interactive`) is deliberately thin:
it only turns `input()` responses into a plain `decisions` structure and
then delegates to `merge_adjudicated`, which is a pure function containing
all of the record-merging logic and is fully unit-testable WITHOUT stdin.

The adjudicated file is the resolved gold set, so it contains EVERY jointly
annotated record: records the two annotators already agreed on pass through
carrying the agreed value (no `adjudication` sub-object), while disputed
records carry the adjudicated value plus the `adjudication` sub-object. The
extra `adjudication` key is written alongside the standard Annotation_Record
fields; `annotations.read_jsonl` ignores unknown keys, so the file remains a
valid Annotation_Record JSONL that downstream tooling (e.g. create_splits.py)
can consume.

The `decisions` structure consumed by `merge_adjudicated` is::

    {record_id: {field: {"choice": "a" | "b" | "new",
                         "value": <final value, only used when choice == "new">,
                         "notes": <str>,
                         "adjudicator_id": <str>}}}

where `field` is one of the adjudicable fields in `ADJUDICABLE_FIELDS`
(``"intent"`` — a scalar label — and ``"aspects"`` — the whole aspect-span
list, since span/category/sentiment disagreements are all aspect-level).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

# Allow running this script directly without installing the package, and
# allow importing the sibling calculate_agreement module.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _dir in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from banking_tasci.data import annotations  # noqa: E402
from banking_tasci.data.annotations import (  # noqa: E402
    AnnotationRecord,
    AspectSpan,
    _aspect_to_dict,
    _record_to_dict,
)
from banking_tasci.logging_utils import get_logger  # noqa: E402

# Reuse the existing, tested disagreement-detection logic from the
# Agreement_Calculator rather than re-implementing it (Req 22.1).
import calculate_agreement as agreement  # noqa: E402
from calculate_agreement import (  # noqa: E402
    _index_by_record_id,
    _valid_aspects,
    disagreements as _agreement_disagreements,
    joint_record_ids,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "annotations" / "pilot_adjudicated.jsonl"

# Adjudicable fields. Intent is a record-level scalar; "aspects" adjudicates
# the whole aspect-span list at once (span/category/sentiment disagreements
# are all aspect-level, and resolving the list as a unit keeps the resulting
# record a valid, non-overlapping Annotation_Record).
ADJUDICABLE_FIELDS = ("intent", "aspects")
_ASPECT_DISAGREEMENT_TYPES = {"span", "category", "sentiment"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Defines `--annotator-a`, `--annotator-b`, `--output`
    (default: `data/annotations/pilot_adjudicated.jsonl`, Req 22.4), and
    `--adjudicator-id` (Req 22.6)."""
    parser = argparse.ArgumentParser(
        prog="adjudicate_annotations.py",
        description=(
            "Resolve disagreements between two annotators' JSONL "
            "Annotation_Record files into a single adjudicated gold set, "
            "preserving both original annotators' values per disputed field."
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
        default=str(_DEFAULT_OUTPUT_PATH),
        help=(
            "Path to write the adjudicated JSONL to "
            "(default: data/annotations/pilot_adjudicated.jsonl)."
        ),
    )
    parser.add_argument(
        "--adjudicator-id",
        required=True,
        help="Identifier of the human adjudicator making the decisions.",
    )
    parser.add_argument(
        "--disagreements",
        default=None,
        help=(
            "Optional path to a pre-computed disagreements JSONL (output of "
            "calculate_agreement.py --disagreements). When supplied, the tool "
            "reads disagreements from this file instead of recomputing them. "
            "The annotator files are still read to perform the merge."
        ),
    )
    parser.add_argument(
        "--decision-file",
        default=None,
        dest="decision_file",
        help=(
            "Path to a JSONL file containing pre-saved adjudication decisions "
            "(one JSON object per line, each with record_id, final_intent, "
            "final_aspects, decision_source, adjudication_reason, etc.). "
            "When supplied together with --resume, the tool converts these "
            "saved decisions into the internal decisions dict and bypasses the "
            "interactive stdin loop for any record that already has a saved "
            "decision."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help=(
            "When set alongside --decision-file, load already-saved decisions "
            "from the decision file and skip the interactive prompt for those "
            "records. Records not yet in the decision file are presented "
            "interactively. Without --decision-file this flag has no effect."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Field access helpers (drive the generic, pure merge logic)
# ---------------------------------------------------------------------------


def _get_field(record: AnnotationRecord, field: str) -> Any:
    """The current value of an adjudicable `field` on `record`."""
    if field == "aspects":
        return _valid_aspects(record)
    return getattr(record, field, None)


def _set_field(record: AnnotationRecord, field: str, value: Any) -> None:
    """Set an adjudicable `field` on `record` to `value` (mutates `record`;
    callers pass a copy they own)."""
    setattr(record, field, value)


def _serialize_field_value(field: str, value: Any) -> Any:
    """JSON-serialisable representation of a field value for storage in the
    `adjudication` sub-object (Req 22.5)."""
    if field == "aspects":
        aspects = value if isinstance(value, list) else []
        return [_aspect_to_dict(a) for a in aspects if isinstance(a, AspectSpan)]
    return value


# ---------------------------------------------------------------------------
# Disagreement detection (Req 22.1) — reuses calculate_agreement.disagreements
# ---------------------------------------------------------------------------


def find_disagreements(
    records_a: list[AnnotationRecord], records_b: list[AnnotationRecord]
) -> list[dict]:
    """Return one entry per jointly-annotated record that has a field-level
    disagreement between the two annotators (Req 22.1).

    Reuses the tested disagreement detection in
    `calculate_agreement.disagreements`, then collapses its granular
    span/category/sentiment items into the single adjudicable `aspects`
    field while preserving the granular items under `detail` for display.

    Each returned dict has the shape::

        {"record_id": str,
         "text": str | None,
         "fields": {"intent": {"annotator_a": ..., "annotator_b": ...},
                    "aspects": {"annotator_a": [...], "annotator_b": [...]}},
         "detail": [ <raw disagreement items> ]}

    where `fields` contains only the fields that actually disagree.
    """
    joint = joint_record_ids(records_a, records_b)
    raw_entries = _agreement_disagreements(records_a, records_b, joint)

    index_a = _index_by_record_id(records_a)
    index_b = _index_by_record_id(records_b)

    results: list[dict] = []
    for entry in raw_entries:
        rid = entry["record_id"]
        rec_a = index_a.get(rid)
        rec_b = index_b.get(rid)
        if rec_a is None or rec_b is None:  # pragma: no cover - defensive
            continue

        disputed_types = {item["type"] for item in entry["disagreements"]}
        fields: dict[str, dict] = {}

        if "intent" in disputed_types:
            fields["intent"] = {
                "annotator_a": getattr(rec_a, "intent", None),
                "annotator_b": getattr(rec_b, "intent", None),
            }

        if disputed_types & _ASPECT_DISAGREEMENT_TYPES:
            fields["aspects"] = {
                "annotator_a": _serialize_field_value("aspects", _valid_aspects(rec_a)),
                "annotator_b": _serialize_field_value("aspects", _valid_aspects(rec_b)),
            }

        results.append(
            {
                "record_id": rid,
                "text": getattr(rec_a, "text", None),
                "fields": fields,
                "detail": entry["disagreements"],
            }
        )
    return results


# ---------------------------------------------------------------------------
# Pure merge logic (Req 22.3, 22.5, 22.6) — no stdin, fully testable
# ---------------------------------------------------------------------------


def merge_adjudicated(
    records_a: list[AnnotationRecord],
    records_b: list[AnnotationRecord],
    decisions: dict,
) -> list[AnnotationRecord]:
    """Produce the adjudicated gold set for every jointly-annotated record.

    `decisions` maps ``record_id -> {field -> {"choice", "value", "notes",
    "adjudicator_id"}}`` (see the module docstring). For each field with a
    decision, the final record uses the adjudicated value (annotator A's,
    annotator B's, or a typed new value) and gains an `adjudication`
    sub-object entry preserving BOTH annotators' original values plus the
    adjudicator id and notes (Req 22.3, 22.5, 22.6).

    Records with no decision entry pass through carrying the agreed value
    (no `adjudication` sub-object). This is a pure function: the input
    records are never mutated (each output is built from a deep copy).
    """
    index_a = _index_by_record_id(records_a)
    index_b = _index_by_record_id(records_b)
    joint_ids = sorted(set(index_a) & set(index_b))

    merged: list[AnnotationRecord] = []
    for rid in joint_ids:
        rec_a = index_a[rid]
        rec_b = index_b[rid]

        final = copy.deepcopy(rec_a)
        record_decisions = decisions.get(rid) or {}

        adjudication: dict[str, dict] = {}
        for field, decision in record_decisions.items():
            if field not in ADJUDICABLE_FIELDS:
                continue
            choice = decision.get("choice")
            notes = decision.get("notes", "")
            adjudicator_id = decision.get("adjudicator_id", "")

            a_value = _get_field(rec_a, field)
            b_value = _get_field(rec_b, field)

            if choice == "a":
                final_value = copy.deepcopy(a_value)
            elif choice == "b":
                final_value = copy.deepcopy(b_value)
            else:  # "new" — adjudicator supplied a fresh value
                final_value = copy.deepcopy(decision.get("value"))

            _set_field(final, field, final_value)
            adjudication[field] = {
                "annotator_a_value": _serialize_field_value(field, a_value),
                "annotator_b_value": _serialize_field_value(field, b_value),
                "final_value": _serialize_field_value(field, final_value),
                "adjudicator_id": adjudicator_id,
                "notes": notes,
            }

        if adjudication:
            # Attach as a dynamic attribute; AnnotationRecord has no
            # `adjudication` field, and `_write_adjudicated` serialises it
            # alongside the standard fields.
            final.adjudication = adjudication

        merged.append(final)
    return merged


# ---------------------------------------------------------------------------
# Interactive path (Req 22.2, 22.3) — thin wrapper over stdin -> decisions
# ---------------------------------------------------------------------------


def adjudicate_interactive(disagreements: list[dict], adjudicator_id: str) -> dict:
    """Prompt the adjudicator once per disputed field and build the
    `decisions` structure consumed by `merge_adjudicated` (Req 22.2, 22.3).

    For every disagreement, both annotators' values are shown and the
    adjudicator may enter ``a`` (keep annotator A's value), ``b`` (keep
    annotator B's value), or — for the scalar `intent` field — type a new
    final value. A per-decision note is also collected (Req 22.6).

    This function contains no merging logic; it only turns `input()`
    responses into the plain `decisions` dict, so the real work stays in the
    pure, stdin-free `merge_adjudicated`.
    """
    decisions: dict[str, dict] = {}
    for entry in disagreements:
        rid = entry["record_id"]
        print("\n" + "=" * 70)
        print(f"Record: {rid}")
        text = entry.get("text")
        if text is not None:
            print(f"Text: {text}")

        record_decisions: dict[str, dict] = {}
        for field, values in entry["fields"].items():
            print("-" * 70)
            print(f"Disputed field: {field}")
            print(f"  [a] annotator A: {values['annotator_a']}")
            print(f"  [b] annotator B: {values['annotator_b']}")

            allow_new = field == "intent"
            if allow_new:
                prompt = "Choose 'a', 'b', or type a new value: "
            else:
                prompt = "Choose 'a' or 'b': "

            while True:
                choice_raw = input(prompt).strip()
                lowered = choice_raw.lower()
                if lowered == "a":
                    decision = {"choice": "a", "value": None}
                    break
                if lowered == "b":
                    decision = {"choice": "b", "value": None}
                    break
                if allow_new and choice_raw:
                    decision = {"choice": "new", "value": choice_raw}
                    break
                print("Invalid choice; please try again.")

            note = input("Adjudication note (optional): ").strip()
            decision["notes"] = note
            decision["adjudicator_id"] = adjudicator_id
            record_decisions[field] = decision

        if record_decisions:
            decisions[rid] = record_decisions
    return decisions


# ---------------------------------------------------------------------------
# Output serialisation (adds the `adjudication` key alongside standard fields)
# ---------------------------------------------------------------------------


def _write_adjudicated(records: list[AnnotationRecord], path: "str | Path") -> None:
    """Write `records` as JSONL, appending an `adjudication` key to any
    record that carries a dynamically-attached `adjudication` attribute.

    The standard Annotation_Record fields are serialised via
    `annotations._record_to_dict`, so the file remains readable by
    `annotations.read_jsonl` (which ignores the extra `adjudication` key)."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for record in records:
            data = _record_to_dict(record)
            adjudication = getattr(record, "adjudication", None)
            if adjudication:
                data["adjudication"] = adjudication
            handle.write(json.dumps(data, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Decision-file loader (--decision-file / --resume support)
# ---------------------------------------------------------------------------


def _load_decision_file(path: "str | Path") -> dict:
    """Load a JSONL decision file produced by the incremental adjudication
    workflow into the internal ``decisions`` dict consumed by
    ``merge_adjudicated``.

    Each line must be a JSON object with at least:
      - ``record_id``
      - ``final_intent``
      - ``final_aspects``  (list of dicts with term/start/end/category/sentiment)
      - ``adjudicator_id``
      - ``adjudication_reason``

    The function maps each record to the ``decisions`` format:
      ``{record_id: {"intent": {choice, value, notes, adjudicator_id},
                     "aspects": {choice, value, notes, adjudicator_id}}}``

    Both ``intent`` and ``aspects`` are always emitted as ``choice="new"``
    with the final values, so ``merge_adjudicated`` always uses the
    adjudicated value rather than one annotator's raw value.
    """
    decisions: dict = {}
    decision_file = Path(path)
    if not decision_file.is_file():
        return decisions
    with open(decision_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = entry.get("record_id")
            if not rid:
                continue
            adjudicator_id = entry.get("adjudicator_id", "")
            notes = entry.get("adjudication_reason", "")

            # Build AspectSpan-compatible dicts for the aspects value.
            raw_aspects = entry.get("final_aspects", [])
            # The merge logic accepts a list of AspectSpan objects for "aspects".
            # We pass raw dicts here; merge_adjudicated calls _set_field which
            # uses setattr, so we need actual AspectSpan objects.
            from banking_tasci.data.annotations import AspectSpan as _AS
            aspect_objects = []
            for a in raw_aspects:
                try:
                    asp = _AS(
                        term=a["term"],
                        start=a["start"],
                        end=a["end"],
                        category=a["category"],
                        sentiment=a["sentiment"],
                    )
                    aspect_objects.append(asp)
                except (KeyError, TypeError):
                    pass

            record_decisions: dict = {}
            record_decisions["intent"] = {
                "choice": "new",
                "value": entry.get("final_intent"),
                "notes": notes,
                "adjudicator_id": adjudicator_id,
            }
            record_decisions["aspects"] = {
                "choice": "new",
                "value": aspect_objects,
                "notes": notes,
                "adjudicator_id": adjudicator_id,
            }
            decisions[rid] = record_decisions
    return decisions


def _patch_ambiguity_from_decision_file(
    merged: "list[AnnotationRecord]", decision_file_path: "str | Path"
) -> None:
    """Patch ``intent_ambiguous`` and ``alternative_intent`` onto already-merged
    records using values from the decision file. Called after ``merge_adjudicated``
    because those fields are not in ``ADJUDICABLE_FIELDS``."""
    patches: dict[str, dict] = {}
    try:
        with open(decision_file_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = entry.get("record_id")
                if not rid:
                    continue
                patches[rid] = {
                    "intent_ambiguous": entry.get("intent_ambiguous", False),
                    "alternative_intent": entry.get("alternative_intent"),
                }
    except (OSError, FileNotFoundError):
        return
    for record in merged:
        rid = getattr(record, "record_id", None)
        if rid and rid in patches:
            record.intent_ambiguous = patches[rid]["intent_ambiguous"]
            record.alternative_intent = patches[rid]["alternative_intent"]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    """Parse args -> read both annotators' JSONL -> find disagreements ->
    interactively adjudicate them -> merge into the adjudicated gold set ->
    write `--output` (default `data/annotations/pilot_adjudicated.jsonl`).

    A genuinely unreadable/unparsable input file prints a descriptive error
    to stderr and returns a non-zero exit code."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logger = get_logger("adjudicate_annotations")

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

    # Use pre-computed disagreements file when supplied, else recompute.
    if args.disagreements:
        disagreements_path = Path(args.disagreements)
        if not disagreements_path.is_file():
            print(f"error: --disagreements file not found: {args.disagreements}", file=sys.stderr)
            return 1
        try:
            with open(disagreements_path, "r", encoding="utf-8") as _fh:
                raw_entries = [json.loads(line) for line in _fh if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read --disagreements ({args.disagreements}): {exc}", file=sys.stderr)
            return 1
        # The pre-computed format from calculate_agreement matches find_disagreements
        # when field-level details are available; use it directly.
        index_a = _index_by_record_id(records_a)
        index_b = _index_by_record_id(records_b)
        disagreement_entries = []
        for entry in raw_entries:
            rid = entry.get("record_id")
            rec_a = index_a.get(rid) if rid else None
            rec_b = index_b.get(rid) if rid else None
            if rec_a is None or rec_b is None:
                continue
            disputed_types = {item["type"] for item in entry.get("disagreements", [])}
            fields: dict = {}
            if "intent" in disputed_types:
                fields["intent"] = {
                    "annotator_a": getattr(rec_a, "intent", None),
                    "annotator_b": getattr(rec_b, "intent", None),
                }
            if disputed_types & {"span", "category", "sentiment"}:
                from adjudicate_annotations import _serialize_field_value, _valid_aspects as _va
                fields["aspects"] = {
                    "annotator_a": _serialize_field_value("aspects", _va(rec_a)),
                    "annotator_b": _serialize_field_value("aspects", _va(rec_b)),
                }
            if fields:
                disagreement_entries.append({
                    "record_id": rid,
                    "text": getattr(rec_a, "text", None),
                    "fields": fields,
                    "detail": entry.get("disagreements", []),
                })
        logger.info(
            "Loaded %d disagreement records from %s.",
            len(disagreement_entries), args.disagreements,
        )
    else:
        disagreement_entries = find_disagreements(records_a, records_b)
        logger.info(
            "Found %d jointly-annotated records with disagreements to adjudicate.",
            len(disagreement_entries),
        )
    if disagreement_entries:
        # --resume + --decision-file: load saved decisions, skip already-resolved records.
        if args.resume and args.decision_file:
            saved_decisions = _load_decision_file(args.decision_file)
            logger.info(
                "Loaded %d saved decisions from %s.",
                len(saved_decisions), args.decision_file,
            )
            # Only present records not yet in the saved decisions.
            unresolved = [e for e in disagreement_entries if e["record_id"] not in saved_decisions]
            if unresolved:
                logger.info(
                    "%d records still unresolved; presenting interactively.",
                    len(unresolved),
                )
                new_decisions = adjudicate_interactive(unresolved, args.adjudicator_id)
                saved_decisions.update(new_decisions)
            decisions = saved_decisions
        else:
            decisions = adjudicate_interactive(disagreement_entries, args.adjudicator_id)
    else:
        decisions = {}
        print("No disagreements found; writing the agreed gold set unchanged.")

    merged = merge_adjudicated(records_a, records_b, decisions)

    # Post-merge: apply intent_ambiguous and alternative_intent from decision file.
    # merge_adjudicated only handles ADJUDICABLE_FIELDS (intent, aspects); the
    # extra ambiguity fields must be patched onto the merged records directly.
    if args.resume and args.decision_file:
        _patch_ambiguity_from_decision_file(merged, args.decision_file)

    _write_adjudicated(merged, args.output)

    logger.info(
        "Wrote %d adjudicated records (%d resolved via adjudication) -> %s",
        len(merged),
        len(decisions),
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
