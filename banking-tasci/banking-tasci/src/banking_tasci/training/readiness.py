"""Readiness_Gate for Phase 3A baseline training.

This module is the single choke point every Phase 3A training entry point
must pass through before constructing any dataset-for-training, model, or
optimiser. It verifies that a validated adjudicated gold dataset and
leakage-safe split manifests actually exist and contain at least one
completed, labelled record. Until they do, training is hard-blocked with a
fixed message.

It NEVER generates, infers, or fabricates any aspect span, sentiment, or
intent label from ratings, keywords, rules, metadata, or a language model
(Req 30.3) -- it only reads and inspects existing files.

Requirements:
- 30.1: readiness = adjudicated gold file exists AND train/validation/test
  manifests exist under the split directory AND >=1 record is
  `annotation_status="completed"` with a non-empty `intent`.
- 30.2: when not ready, raise an error whose message is exactly
  `BLOCKED_MESSAGE`.
- 30.3: never infer or fabricate labels; only read and inspect.
- 30.4: `assert_ready` is called first by every training entry point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from banking_tasci.data.annotations import read_jsonl

# The exact, verbatim blocked message. Any deviation is a bug -- downstream
# tests and CLIs assert on this exact string (Req 30.2).
BLOCKED_MESSAGE = (
    "Gold annotations are missing. Complete annotation, agreement, "
    "adjudication, validation, and split creation before training."
)

# The three split manifests that must all exist under the split directory
# (Req 30.1).
_REQUIRED_MANIFESTS = (
    "train_manifest.csv",
    "validation_manifest.csv",
    "test_manifest.csv",
)


@dataclass
class ReadinessResult:
    """Outcome of a (non-raising) readiness check.

    `ready` is True only when every precondition in Requirement 30.1 holds.
    `reasons` holds one human-readable message per failed check (empty when
    `ready` is True).
    """

    ready: bool
    reasons: list[str] = field(default_factory=list)


def _has_completed_labelled_record(annotations_path: Path) -> tuple[bool, str | None]:
    """Return (found, read_error).

    `found` is True when at least one record read from `annotations_path`
    has `annotation_status == "completed"` and a non-empty (non-null,
    non-empty-string) `intent`. `read_error` is a message describing a
    read/parse failure, or None when the file was read successfully.

    Never infers or fabricates a label -- it only inspects the gold fields
    that a human annotator/adjudicator produced (Req 30.3).
    """
    try:
        records = read_jsonl(annotations_path)
    except Exception as exc:  # pragma: no cover - defensive, non-raising API
        return False, f"could not read annotations file '{annotations_path}': {exc}"

    for record in records:
        status = getattr(record, "annotation_status", None)
        intent = getattr(record, "intent", None)
        if status == "completed" and isinstance(intent, str) and intent != "":
            return True, None
    return False, None


def check_readiness(annotations_path: "str | Path", split_dir: "str | Path") -> ReadinessResult:
    """Non-raising readiness check (Req 30.1, 30.3).

    Returns a `ReadinessResult`. `ready` is True ONLY when ALL of the
    following hold:
      * the adjudicated gold file at `annotations_path` exists;
      * `train_manifest.csv`, `validation_manifest.csv`, and
        `test_manifest.csv` all exist under `split_dir`; and
      * at least one record read from `annotations_path` has
        `annotation_status == "completed"` with a non-empty `intent`.

    Otherwise `ready` is False and `reasons` contains one message per failed
    check. A missing `annotations_path` is simply one of the not-ready
    reasons -- this function never crashes on absent/unreadable files.

    This function never infers, generates, or fabricates any label; it only
    reads and inspects existing files (Req 30.3).
    """
    annotations_path = Path(annotations_path)
    split_dir = Path(split_dir)
    reasons: list[str] = []

    gold_exists = annotations_path.is_file()
    if not gold_exists:
        reasons.append(f"adjudicated gold file does not exist: '{annotations_path}'")

    for manifest_name in _REQUIRED_MANIFESTS:
        manifest_path = split_dir / manifest_name
        if not manifest_path.is_file():
            reasons.append(f"split manifest does not exist: '{manifest_path}'")

    if gold_exists:
        has_record, read_error = _has_completed_labelled_record(annotations_path)
        if read_error is not None:
            reasons.append(read_error)
        elif not has_record:
            reasons.append(
                "no annotation record has annotation_status='completed' with a non-empty intent"
            )
    else:
        # Cannot have a completed labelled record when the file is absent.
        reasons.append(
            "no annotation record has annotation_status='completed' with a non-empty intent"
        )

    return ReadinessResult(ready=not reasons, reasons=reasons)


def assert_ready(annotations_path: "str | Path", split_dir: "str | Path") -> None:
    """Raise `RuntimeError(BLOCKED_MESSAGE)` -- the exact string -- when
    `check_readiness(...).ready` is False; return None when ready (Req 30.2,
    30.4).

    Every Phase 3A training entry point calls this first, before building
    any dataset-for-training, model, or optimiser.
    """
    result = check_readiness(annotations_path, split_dir)
    if not result.ready:
        raise RuntimeError(BLOCKED_MESSAGE)
