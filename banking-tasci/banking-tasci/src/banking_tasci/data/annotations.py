"""Annotation_Record schema and validation rules for the banking-tasci
annotation pipeline.

Every tool in the Phase 2 annotation pipeline (Annotation_Sampler,
Annotation_Interface, Annotation_Validator, Agreement_Calculator,
Adjudication_Tool, Split_Manager) reads and writes the single JSONL
`AnnotationRecord` schema defined here, and reuses the pure validation
functions in this module rather than re-implementing checks.

Requirements:
- 12.1-12.8: Annotation_Record / Aspect_Span schema, offset semantics,
  empty-aspects support, overlap rejection.
- 19.1-19.14: Annotation_Validator rules (unknown labels, missing fields,
  invalid/mismatched offsets, overlapping/duplicate spans, context
  consistency, completed-intent requirement, raw-identifier detection,
  no auto-correction, and the JSON report produced by
  `scripts/validate_annotations.py` from `validate_all`'s output).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from banking_tasci.config import load_config
from banking_tasci.data.anonymise import EMAIL_PATTERN, MENTION_PATTERN, URL_PATTERN

if TYPE_CHECKING:
    from banking_tasci.config import Config

# ---------------------------------------------------------------------------
# Fixed label spaces (Req 12.1-12.2, 13.1, 14.1, 15.1). Future phases extend
# these constants rather than redefining the label spaces elsewhere.
# ---------------------------------------------------------------------------

ASPECT_CATEGORIES = [
    "customer_support", "digital_banking", "transactions", "cards",
    "accounts", "fees", "fraud_security", "branch_service", "general_service",
]
ASPECT_SENTIMENTS = ["positive", "negative", "neutral"]
INTENT_LABELS = [
    "complaint", "compliment", "request_for_assistance", "suggestion",
    "warning", "churn_signal", "general_feedback",
]

# Sentinel used internally (never serialized) to distinguish "key absent
# from the JSONL object" from "key present with an explicit null value" —
# the latter is legitimate for `intent`/`alternative_intent` (Req 19.5).
_MISSING = object()

_TOP_LEVEL_REQUIRED_FIELDS = [
    "record_id", "source", "region", "text", "previous_text",
    "context_available", "aspects", "intent", "intent_ambiguous",
    "alternative_intent", "annotator_id", "annotation_status", "notes",
]
_ASPECT_REQUIRED_FIELDS = ["term", "start", "end", "category", "sentiment"]

# Default config used by `check_no_raw_identifiers` when no `cfg` is
# supplied by the caller (e.g. when `validate_record`/`validate_all` are
# called without an explicit `cfg`, matching design.md's documented call
# shape). Resolved relative to this file so it works regardless of CWD.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "base.yaml"


@lru_cache(maxsize=1)
def _default_cfg() -> "Config":
    return load_config(_DEFAULT_CONFIG_PATH)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass
class AspectSpan:
    """One annotated aspect term within an `AnnotationRecord.text` (Req 12.2)."""

    term: Any
    start: Any
    end: Any
    category: Any
    sentiment: Any


@dataclass
class AnnotationRecord:
    """One Annotation_Record, one JSON object per JSONL line (Req 12.1)."""

    record_id: Any
    source: Any
    region: Any
    text: Any
    previous_text: Any
    context_available: Any
    aspects: Any
    intent: Any
    intent_ambiguous: Any
    alternative_intent: Any
    annotator_id: Any
    annotation_status: Any
    notes: Any


@dataclass(frozen=True)
class ValidationError:
    """One reported problem found while validating an `AnnotationRecord`.

    Carries only `error_type`, `record_id`, and a `message` describing the
    structural/label problem — never the record's raw `text` or any other
    potentially sensitive field value (Req 19.13).
    """

    error_type: str
    record_id: str
    message: str


def _record_id(record: AnnotationRecord) -> str:
    """Best-effort record id for error reporting, even when `record_id`
    itself is missing or malformed."""
    rid = getattr(record, "record_id", _MISSING)
    if isinstance(rid, str) and rid:
        return rid
    return "<unknown>"


# ---------------------------------------------------------------------------
# Validation rules (Requirement 19)
# ---------------------------------------------------------------------------


def _check_required_fields(record: AnnotationRecord) -> list[ValidationError]:
    """Structural check: every field in Requirement 12 must be present
    (Req 19.5). A key present with an explicit `null` value (legitimate for
    `intent`/`alternative_intent`) is NOT a missing-field violation; only a
    genuinely absent key (represented internally by `_MISSING`) is."""
    errors: list[ValidationError] = []
    rid = _record_id(record)

    for field_name in _TOP_LEVEL_REQUIRED_FIELDS:
        if getattr(record, field_name, _MISSING) is _MISSING:
            errors.append(
                ValidationError("missing_required_field", rid, f"Missing required field '{field_name}'")
            )

    aspects = getattr(record, "aspects", _MISSING)
    if aspects is _MISSING:
        pass  # already reported above via the top-level loop
    elif not isinstance(aspects, list):
        errors.append(ValidationError("missing_required_field", rid, "Field 'aspects' must be a list"))
    else:
        for idx, aspect in enumerate(aspects):
            if not isinstance(aspect, AspectSpan):
                errors.append(
                    ValidationError(
                        "missing_required_field", rid, f"Aspect span at index {idx} is not a valid object"
                    )
                )
                continue
            for field_name in _ASPECT_REQUIRED_FIELDS:
                if getattr(aspect, field_name, _MISSING) is _MISSING:
                    errors.append(
                        ValidationError(
                            "missing_required_field",
                            rid,
                            f"Aspect span at index {idx} missing required field '{field_name}'",
                        )
                    )
    return errors


def _valid_aspect_list(record: AnnotationRecord) -> list[AspectSpan]:
    aspects = getattr(record, "aspects", _MISSING)
    if not isinstance(aspects, list):
        return []
    return aspects


def check_offsets(record: AnnotationRecord) -> list[ValidationError]:
    """Reject out-of-bounds/negative/`start>=end` offsets (Req 19.6), and
    reject `text[start:end] != term` (Req 12.3-12.4, 19.7)."""
    errors: list[ValidationError] = []
    text = getattr(record, "text", _MISSING)
    if not isinstance(text, str):
        return errors  # missing/invalid text already reported structurally

    rid = _record_id(record)
    for idx, aspect in enumerate(_valid_aspect_list(record)):
        if not isinstance(aspect, AspectSpan):
            continue
        start, end, term = aspect.start, aspect.end, aspect.term
        if start is _MISSING or end is _MISSING or term is _MISSING:
            continue  # missing-field violation already reported structurally

        is_int_pair = (
            isinstance(start, int) and isinstance(end, int)
            and not isinstance(start, bool) and not isinstance(end, bool)
        )
        if not is_int_pair:
            errors.append(
                ValidationError("invalid_offset", rid, f"Aspect span at index {idx} has non-integer start/end")
            )
            continue

        if start < 0 or end > len(text) or start >= end:
            errors.append(
                ValidationError(
                    "invalid_offset",
                    rid,
                    f"Aspect span at index {idx} has an out-of-bounds or invalid offset [{start}:{end}]",
                )
            )
            continue

        if text[start:end] != term:
            errors.append(
                ValidationError(
                    "offset_mismatch",
                    rid,
                    f"Aspect span at index {idx}: text[{start}:{end}] does not match its recorded term",
                )
            )
    return errors


def check_overlap(record: AnnotationRecord) -> list[ValidationError]:
    """Reject overlapping Aspect_Spans (Req 12.7-12.8, 19.8) and duplicate
    spans with identical `start`/`end` (Req 19.9)."""
    errors: list[ValidationError] = []
    rid = _record_id(record)

    valid_spans: list[tuple[int, int, int]] = []
    for idx, aspect in enumerate(_valid_aspect_list(record)):
        if not isinstance(aspect, AspectSpan):
            continue
        start, end = aspect.start, aspect.end
        if start is _MISSING or end is _MISSING:
            continue
        if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool):
            continue  # already reported as invalid_offset by check_offsets
        valid_spans.append((idx, start, end))

    for i in range(len(valid_spans)):
        idx_i, start_i, end_i = valid_spans[i]
        for j in range(i + 1, len(valid_spans)):
            idx_j, start_j, end_j = valid_spans[j]
            if start_i == start_j and end_i == end_j:
                errors.append(
                    ValidationError(
                        "duplicate_span",
                        rid,
                        f"Aspect spans at indices {idx_i} and {idx_j} are duplicates",
                    )
                )
            elif start_i < end_j and start_j < end_i:
                errors.append(
                    ValidationError(
                        "overlapping_spans",
                        rid,
                        f"Aspect spans at indices {idx_i} and {idx_j} overlap",
                    )
                )
    return errors


def check_labels(record: AnnotationRecord) -> list[ValidationError]:
    """Reject unknown aspect `category`/`sentiment` (Req 19.2, 19.3) and
    unknown `intent` (Req 19.4, when `intent` is not `None`)."""
    errors: list[ValidationError] = []
    rid = _record_id(record)

    for idx, aspect in enumerate(_valid_aspect_list(record)):
        if not isinstance(aspect, AspectSpan):
            continue
        if aspect.category is not _MISSING and aspect.category not in ASPECT_CATEGORIES:
            errors.append(
                ValidationError("unknown_category", rid, f"Aspect span at index {idx} has an unknown category")
            )
        if aspect.sentiment is not _MISSING and aspect.sentiment not in ASPECT_SENTIMENTS:
            errors.append(
                ValidationError("unknown_sentiment", rid, f"Aspect span at index {idx} has an unknown sentiment")
            )

    intent = getattr(record, "intent", _MISSING)
    if intent is not _MISSING and intent is not None and intent not in INTENT_LABELS:
        errors.append(ValidationError("unknown_intent", rid, "Record has an unknown intent value"))
    return errors


def check_context_consistency(record: AnnotationRecord) -> list[ValidationError]:
    """Reject `context_available`/`previous_text` inconsistency (Req 19.10)."""
    errors: list[ValidationError] = []
    ctx = getattr(record, "context_available", _MISSING)
    prev = getattr(record, "previous_text", _MISSING)
    if ctx is _MISSING or prev is _MISSING:
        return errors  # already reported structurally

    rid = _record_id(record)
    if ctx is False and prev != "[NO_CONTEXT]":
        errors.append(
            ValidationError(
                "context_inconsistency", rid, "context_available=False but previous_text is not [NO_CONTEXT]"
            )
        )
    elif ctx is True and prev == "[NO_CONTEXT]":
        errors.append(
            ValidationError(
                "context_inconsistency", rid, "context_available=True but previous_text is [NO_CONTEXT]"
            )
        )
    return errors


def check_completed_intent(record: AnnotationRecord) -> list[ValidationError]:
    """Reject `annotation_status="completed"` with a null/empty `intent`
    (Req 15.5, 19.11). Any other `annotation_status` value is never
    rejected by this check, even with a null `intent`."""
    errors: list[ValidationError] = []
    status = getattr(record, "annotation_status", _MISSING)
    if status is _MISSING or status != "completed":
        return errors

    intent = getattr(record, "intent", _MISSING)
    if intent is _MISSING or intent is None or intent == "":
        errors.append(
            ValidationError(
                "missing_intent", _record_id(record), "annotation_status=completed but intent is null or empty"
            )
        )
    return errors


def check_no_raw_identifiers(record: AnnotationRecord, cfg: "Config") -> list[ValidationError]:
    """Flag (never modify) `record.text` if it still appears to contain an
    unanonymised email/URL/mention/account-or-reference/phone identifier
    (Req 19.12). Reuses the fixed email/URL/mention regexes and the
    cfg-configured account-reference/phone regexes from `anonymise.py`
    rather than duplicating them."""
    errors: list[ValidationError] = []
    text = getattr(record, "text", _MISSING)
    if not isinstance(text, str):
        return errors

    rid = _record_id(record)
    patterns = [
        ("email", EMAIL_PATTERN),
        ("url", URL_PATTERN),
        ("mention", MENTION_PATTERN),
        ("account_or_reference", re.compile(cfg.anonymise.account_reference_pattern)),
        ("phone", re.compile(cfg.anonymise.phone_pattern)),
    ]
    for name, pattern in patterns:
        if pattern.search(text):
            errors.append(
                ValidationError(
                    "raw_identifier", rid, f"text appears to contain an unanonymised {name} identifier"
                )
            )
    return errors


def validate_record(record: AnnotationRecord, cfg: "Config | None" = None) -> list[ValidationError]:
    """Run every check in Requirement 19 against `record`; return every
    violation found (never stops at the first). Never mutates `record`
    (Req 19.13)."""
    if cfg is None:
        cfg = _default_cfg()
    errors: list[ValidationError] = []
    errors.extend(_check_required_fields(record))
    errors.extend(check_offsets(record))
    errors.extend(check_overlap(record))
    errors.extend(check_labels(record))
    errors.extend(check_context_consistency(record))
    errors.extend(check_completed_intent(record))
    errors.extend(check_no_raw_identifiers(record, cfg))
    return errors


def validate_all(
    records: list[AnnotationRecord], cfg: "Config | None" = None
) -> tuple[list[AnnotationRecord], dict[str, list[ValidationError]]]:
    """Partition `records` into `(valid_records, {record_id: [errors]})`."""
    valid: list[AnnotationRecord] = []
    invalid: dict[str, list[ValidationError]] = {}
    for record in records:
        errors = validate_record(record, cfg=cfg)
        if errors:
            invalid[_record_id(record)] = errors
        else:
            valid.append(record)
    return valid, invalid


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------


def _aspect_from_dict(data: dict) -> AspectSpan:
    return AspectSpan(
        term=data.get("term", _MISSING),
        start=data.get("start", _MISSING),
        end=data.get("end", _MISSING),
        category=data.get("category", _MISSING),
        sentiment=data.get("sentiment", _MISSING),
    )


def _record_from_dict(data: dict) -> AnnotationRecord:
    aspects_raw = data.get("aspects", _MISSING)
    if isinstance(aspects_raw, list):
        aspects: Any = [_aspect_from_dict(a) for a in aspects_raw if isinstance(a, dict)]
    else:
        aspects = aspects_raw

    return AnnotationRecord(
        record_id=data.get("record_id", _MISSING),
        source=data.get("source", _MISSING),
        region=data.get("region", _MISSING),
        text=data.get("text", _MISSING),
        previous_text=data.get("previous_text", _MISSING),
        context_available=data.get("context_available", _MISSING),
        aspects=aspects,
        intent=data.get("intent", _MISSING),
        intent_ambiguous=data.get("intent_ambiguous", _MISSING),
        alternative_intent=data.get("alternative_intent", _MISSING),
        annotator_id=data.get("annotator_id", _MISSING),
        annotation_status=data.get("annotation_status", _MISSING),
        notes=data.get("notes", _MISSING),
    )


def _serializable(value: Any) -> Any:
    return None if value is _MISSING else value


def _aspect_to_dict(aspect: AspectSpan) -> dict:
    return {
        "term": _serializable(aspect.term),
        "start": _serializable(aspect.start),
        "end": _serializable(aspect.end),
        "category": _serializable(aspect.category),
        "sentiment": _serializable(aspect.sentiment),
    }


def _record_to_dict(record: AnnotationRecord) -> dict:
    aspects = record.aspects if isinstance(record.aspects, list) else []
    return {
        "record_id": _serializable(record.record_id),
        "source": _serializable(record.source),
        "region": _serializable(record.region),
        "text": _serializable(record.text),
        "previous_text": _serializable(record.previous_text),
        "context_available": _serializable(record.context_available),
        "aspects": [_aspect_to_dict(a) for a in aspects if isinstance(a, AspectSpan)],
        "intent": _serializable(record.intent),
        "intent_ambiguous": _serializable(record.intent_ambiguous),
        "alternative_intent": _serializable(record.alternative_intent),
        "annotator_id": _serializable(record.annotator_id),
        "annotation_status": _serializable(record.annotation_status),
        "notes": _serializable(record.notes),
    }


def read_jsonl(path: "str | Path") -> list[AnnotationRecord]:
    """Read one `AnnotationRecord` per non-blank line from `path`.

    A JSONL object missing one or more schema fields is still returned as
    an `AnnotationRecord` (with those fields left internally unset) rather
    than raising, so `validate_all` can classify it as invalid with a
    `missing_required_field` error instead of the read itself crashing."""
    records: list[AnnotationRecord] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(_record_from_dict(json.loads(line)))
    return records


def write_jsonl(records: list[AnnotationRecord], path: "str | Path") -> None:
    """Write `records` as one JSON object per line, matching the
    Annotation_Record schema exactly (including nested `aspects`)."""
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_record_to_dict(record), ensure_ascii=False) + "\n")
