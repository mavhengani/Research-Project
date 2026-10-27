"""Supervised-training readiness gate (Phase 3A, Part 6).

This is a *stricter, more granular* readiness check than
:mod:`banking_tasci.training.readiness`. Where that module answers "does a
minimal gold file + manifests exist?", this module performs the full set of
Part-6 checks a real baseline-training run must pass, and it is the single
importable entry point every baseline training command calls before building
any model.

It NEVER fabricates, infers, or generates any label, span, or split — it only
reads and inspects the adjudicated gold JSONL and the split manifests.

The 13 checks (Part 6):
 1. the adjudicated annotation file exists;
 2. the file is not the unannotated pilot;
 3. all records have a valid annotation status;
 4. valid aspect spans exist;
 5. aspect sentiment labels exist;
 6. intent labels exist;
 7. train, validation, and test manifests exist;
 8. no record id appears in multiple splits;
 9. reviews/threads (leakage groups) do not cross splits;
10. no unannotated record is included in any split;
11. required classes exist in the training split;
12. validation and test labels are valid;
13. the test set is not usable for model selection (a distinct, non-empty
    validation split exists and is disjoint from test).

When not ready, :func:`assert_supervised_ready` raises ``RuntimeError`` whose
message is exactly :data:`SUPERVISED_BLOCKED_MESSAGE`.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from banking_tasci.data.annotations import (
    ASPECT_SENTIMENTS,
    INTENT_LABELS,
    AnnotationRecord,
    AspectSpan,
    read_jsonl,
    validate_all,
)

# The exact blocked message required by Part 6.
SUPERVISED_BLOCKED_MESSAGE = (
    "Supervised training is blocked: adjudicated gold annotations and "
    "leakage-safe split manifests are missing."
)

_REQUIRED_MANIFESTS = ("train_manifest.csv", "validation_manifest.csv", "test_manifest.csv")

# The unannotated pilot filename must never be accepted as the gold file.
_UNANNOTATED_PILOT_NAME = "pilot_unannotated.jsonl"

_VALID_STATUSES = {"not_started", "in_progress", "completed"}


@dataclass
class CheckResult:
    """One named check outcome."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class ReadinessReport:
    """Aggregate result of the supervised-training readiness gate."""

    ready: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


def _read_manifest_ids(path: Path) -> list[str]:
    """Read the ``record_id`` column from a manifest CSV (order preserved)."""
    ids: list[str] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rid = row.get("record_id")
            if rid is not None and rid != "":
                ids.append(str(rid))
    return ids


def _read_group_keys(path: Path) -> dict[str, str]:
    """Map ``record_id -> leakage group key`` from the raw JSONL.

    The group key is ``source_record_id`` when present/truthy (review
    sentences from one review share it) or ``thread_id`` when present,
    otherwise the record's own id (tweets). Mirrors ``create_splits.group_key``.
    """
    mapping: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rid = obj.get("record_id")
            if rid is None:
                continue
            group = obj.get("source_record_id") or obj.get("thread_id") or rid
            mapping[str(rid)] = str(group)
    return mapping


def _completed(records: list[AnnotationRecord]) -> list[AnnotationRecord]:
    return [r for r in records if getattr(r, "annotation_status", None) == "completed"]


def check_supervised_readiness(
    annotations_path: "str | Path", split_dir: "str | Path"
) -> ReadinessReport:
    """Run all Part-6 checks (non-raising) and return a :class:`ReadinessReport`.

    Never raises on missing/absent files; a missing input is simply a failed
    check. Never fabricates or infers labels.
    """
    annotations_path = Path(annotations_path)
    split_dir = Path(split_dir)
    checks: list[CheckResult] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append(CheckResult(name=name, passed=passed, detail=detail))

    # 1. adjudicated gold file exists.
    gold_exists = annotations_path.is_file()
    add("adjudicated_file_exists", gold_exists,
        "" if gold_exists else f"missing gold file: {annotations_path}")

    # 2. not the unannotated pilot (by name).
    not_unannotated_name = annotations_path.name != _UNANNOTATED_PILOT_NAME
    add("not_the_unannotated_pilot", not_unannotated_name,
        "" if not_unannotated_name else "refusing the unannotated pilot file")

    # 7. manifests exist.
    manifest_paths = {name: split_dir / name for name in _REQUIRED_MANIFESTS}
    manifests_exist = all(p.is_file() for p in manifest_paths.values())
    missing_manifests = [n for n, p in manifest_paths.items() if not p.is_file()]
    add("split_manifests_exist", manifests_exist,
        "" if manifests_exist else f"missing manifests: {missing_manifests}")

    # If the gold file is absent we cannot inspect records; short-circuit the
    # record-dependent checks as failures with a clear reason.
    if not gold_exists:
        for name in (
            "valid_annotation_status", "valid_aspect_spans_exist",
            "aspect_sentiment_labels_exist", "intent_labels_exist",
            "no_record_in_multiple_splits", "leakage_groups_not_crossing_splits",
            "no_unannotated_record_in_splits", "required_classes_in_train",
            "validation_and_test_labels_valid", "test_not_used_for_selection",
        ):
            add(name, False, "gold annotation file absent")
        return ReadinessReport(ready=False, checks=checks)

    records = read_jsonl(annotations_path)
    id_to_record = {
        str(getattr(r, "record_id", "")): r for r in records
        if isinstance(getattr(r, "record_id", None), str)
    }

    # 3. all records have a valid annotation status.
    bad_status = [
        str(getattr(r, "record_id", "<unknown>"))
        for r in records
        if getattr(r, "annotation_status", None) not in _VALID_STATUSES
    ]
    add("valid_annotation_status", not bad_status,
        "" if not bad_status else f"records with invalid status: {bad_status[:5]}")

    completed = _completed(records)

    # Validate completed records with the Phase-2 validator (no fabrication).
    _valid, invalid = validate_all(records)

    # 4. valid aspect spans exist (>=1 completed record with a valid span).
    def _valid_spans(rec: AnnotationRecord) -> list[AspectSpan]:
        text = getattr(rec, "text", None)
        spans: list[AspectSpan] = []
        aspects = getattr(rec, "aspects", None)
        if not isinstance(text, str) or not isinstance(aspects, list):
            return spans
        for a in aspects:
            if not isinstance(a, AspectSpan):
                continue
            s, e = a.start, a.end
            if isinstance(s, int) and isinstance(e, int) and not isinstance(s, bool) and not isinstance(e, bool):
                if 0 <= s < e <= len(text) and text[s:e] == a.term:
                    spans.append(a)
        return spans

    any_valid_span = any(_valid_spans(r) for r in completed)
    add("valid_aspect_spans_exist", any_valid_span,
        "" if any_valid_span else "no completed record has a valid aspect span")

    # 5. aspect sentiment labels exist.
    any_sentiment = any(
        a.sentiment in ASPECT_SENTIMENTS
        for r in completed for a in _valid_spans(r)
    )
    add("aspect_sentiment_labels_exist", any_sentiment,
        "" if any_sentiment else "no valid aspect carries a known sentiment label")

    # 6. intent labels exist.
    train_intents_all = [
        getattr(r, "intent", None) for r in completed
        if getattr(r, "intent", None) in INTENT_LABELS
    ]
    any_intent = len(train_intents_all) > 0
    add("intent_labels_exist", any_intent,
        "" if any_intent else "no completed record has a known intent label")

    # Manifest-dependent checks require the manifests to exist.
    if manifests_exist:
        split_ids = {name.split("_")[0]: _read_manifest_ids(p)
                     for name, p in manifest_paths.items()}
        # keys: train, validation, test
        train_ids = set(split_ids.get("train", []))
        val_ids = set(split_ids.get("validation", []))
        test_ids = set(split_ids.get("test", []))

        # 8. no record id in multiple splits.
        overlap = (train_ids & val_ids) | (train_ids & test_ids) | (val_ids & test_ids)
        add("no_record_in_multiple_splits", not overlap,
            "" if not overlap else f"record ids in multiple splits: {sorted(overlap)[:5]}")

        # 9. leakage groups do not cross splits.
        group_keys = _read_group_keys(annotations_path)
        group_to_splits: dict[str, set[str]] = defaultdict(set)
        for split_name, ids in (("train", train_ids), ("validation", val_ids), ("test", test_ids)):
            for rid in ids:
                group_to_splits[group_keys.get(rid, rid)].add(split_name)
        crossing = {g: sorted(s) for g, s in group_to_splits.items() if len(s) > 1}
        add("leakage_groups_not_crossing_splits", not crossing,
            "" if not crossing else f"leakage groups crossing splits: {list(crossing)[:3]}")

        # 10. no unannotated record included in any split.
        all_split_ids = train_ids | val_ids | test_ids
        unannotated_in_split = [
            rid for rid in all_split_ids
            if getattr(id_to_record.get(rid), "annotation_status", None) != "completed"
        ]
        add("no_unannotated_record_in_splits", not unannotated_in_split,
            "" if not unannotated_in_split
            else f"non-completed records present in splits: {unannotated_in_split[:5]}")

        # 11. required classes exist in the training split: every intent class
        #     that appears in val/test must also appear in train (no class the
        #     model could never have seen), and train must have >= 2 classes.
        def _intents(ids: set[str]) -> set[str]:
            out: set[str] = set()
            for rid in ids:
                rec = id_to_record.get(rid)
                intent = getattr(rec, "intent", None)
                if intent in INTENT_LABELS:
                    out.add(intent)
            return out

        train_classes = _intents(train_ids)
        eval_classes = _intents(val_ids) | _intents(test_ids)
        unseen_at_train = eval_classes - train_classes
        required_ok = len(train_classes) >= 2 and not unseen_at_train
        add("required_classes_in_train", required_ok,
            "" if required_ok
            else f"train classes={sorted(train_classes)}, unseen_at_train={sorted(unseen_at_train)}")

        # 12. validation and test labels are valid.
        def _labels_valid(ids: set[str]) -> bool:
            for rid in ids:
                rec = id_to_record.get(rid)
                if rec is None:
                    return False
                intent = getattr(rec, "intent", None)
                if intent is not None and intent not in INTENT_LABELS:
                    return False
                for a in _valid_spans(rec):
                    if a.sentiment not in ASPECT_SENTIMENTS:
                        return False
            return True

        eval_labels_ok = _labels_valid(val_ids) and _labels_valid(test_ids)
        add("validation_and_test_labels_valid", eval_labels_ok,
            "" if eval_labels_ok else "validation/test contain invalid labels")

        # 13. test set is not usable for model selection: a distinct, non-empty
        #     validation split exists and is disjoint from test.
        selection_ok = bool(val_ids) and not (val_ids & test_ids)
        add("test_not_used_for_selection", selection_ok,
            "" if selection_ok
            else "validation split empty or overlaps test; selection would leak test")
    else:
        for name in (
            "no_record_in_multiple_splits", "leakage_groups_not_crossing_splits",
            "no_unannotated_record_in_splits", "required_classes_in_train",
            "validation_and_test_labels_valid", "test_not_used_for_selection",
        ):
            add(name, False, "split manifests missing")

    # Also fold in Phase-2 validation: any invalid record blocks training.
    add("all_records_schema_valid", not invalid,
        "" if not invalid else f"{len(invalid)} record(s) fail schema validation")

    ready = all(c.passed for c in checks)
    return ReadinessReport(ready=ready, checks=checks)


def assert_supervised_ready(annotations_path: "str | Path", split_dir: "str | Path") -> ReadinessReport:
    """Raise ``RuntimeError(SUPERVISED_BLOCKED_MESSAGE)`` when not ready; return
    the passing :class:`ReadinessReport` when ready.

    Every baseline training command calls this before constructing a model.
    """
    report = check_supervised_readiness(annotations_path, split_dir)
    if not report.ready:
        raise RuntimeError(SUPERVISED_BLOCKED_MESSAGE)
    return report

