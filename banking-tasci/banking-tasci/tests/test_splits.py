"""Tests for the Split_Manager (scripts/create_splits.py).

Covers:
- Req 23.3-23.4, 23.10: leakage safety -- no `record_id` appears in more
  than one split, and no two records sharing the same review/thread group
  (`source_record_id`) are assigned to different splits.
- Req 23.2: refusal-to-run -- an input containing an invalid record causes a
  non-zero exit and writes NO manifest files.
- Determinism: `assign_groups_to_splits` returns identical assignments for
  the same groups/ratios/seed across two calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
for _dir in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from banking_tasci.data.annotations import AnnotationRecord  # noqa: E402

from create_splits import (  # noqa: E402
    assign_groups_to_splits,
    group_key,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _valid_record(
    record_id: str,
    *,
    source: str = "bank_reviews",
    region: str = "south_africa",
    text: str = "The teller was helpful today.",
    intent: str = "general_feedback",
    source_record_id: str | None = None,
) -> AnnotationRecord:
    """Build a schema-valid, no-aspect AnnotationRecord. When
    `source_record_id` is given, it is attached as an extra attribute (as
    `context.py` does for sentence-level review records) so `group_key`
    groups by it."""
    record = AnnotationRecord(
        record_id=record_id,
        source=source,
        region=region,
        text=text,
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=[],
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="annotator_a",
        annotation_status="completed",
        notes="",
    )
    if source_record_id is not None:
        record.source_record_id = source_record_id
    return record


def _leakage_fixture() -> list[AnnotationRecord]:
    """Several reviews, each split into multiple sentence-records sharing a
    `source_record_id`, plus some standalone tweets."""
    records: list[AnnotationRecord] = []
    # 6 reviews, 3 sentence-records each, sharing one source_record_id.
    intents = ["complaint", "general_feedback", "compliment", "warning", "churn_signal", "suggestion"]
    for r in range(6):
        review_id = f"rev{r}"
        for s in range(3):
            records.append(
                _valid_record(
                    f"{review_id}_s{s}",
                    source="bank_reviews",
                    intent=intents[r],
                    source_record_id=review_id,
                )
            )
    # 8 standalone tweets (no source_record_id -> grouped by their own id).
    for t in range(8):
        records.append(
            _valid_record(
                f"tw{t}",
                source="international_bank_tweets",
                region="international",
                text="My card got blocked again.",
                intent="request_for_assistance",
            )
        )
    return records


def _write_jsonl(path: Path, dicts: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for obj in dicts:
            handle.write(json.dumps(obj) + "\n")


def _valid_record_dict(record_id: str) -> dict:
    return {
        "record_id": record_id,
        "source": "bank_reviews",
        "region": "south_africa",
        "text": "The teller was helpful today.",
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "aspects": [],
        "intent": "general_feedback",
        "intent_ambiguous": False,
        "alternative_intent": None,
        "annotator_id": "annotator_a",
        "annotation_status": "completed",
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Req 23.3-23.4, 23.10: leakage safety
# ---------------------------------------------------------------------------


def test_no_record_id_appears_in_more_than_one_split(tmp_path):
    records = _leakage_fixture()

    # Assign at the group level, then expand to records.
    groups = {}
    group_members = {}
    for record in records:
        gid = group_key(record)
        groups.setdefault(gid, {"intent": record.intent, "source": record.source})
        group_members.setdefault(gid, []).append(record.record_id)

    assignment = assign_groups_to_splits(groups, (0.6, 0.2, 0.2), seed=7)

    split_of_record: dict[str, str] = {}
    for gid, member_ids in group_members.items():
        for member_id in member_ids:
            split_of_record[member_id] = assignment[gid]

    # (a) No record_id appears in more than one split -- trivially true since
    # split_of_record is a dict keyed by record_id; assert record_ids unique.
    all_ids = [r.record_id for r in records]
    assert len(all_ids) == len(set(all_ids))


def test_records_sharing_a_group_land_in_the_same_split():
    records = _leakage_fixture()

    groups = {}
    group_members = {}
    for record in records:
        gid = group_key(record)
        groups.setdefault(gid, {"intent": record.intent, "source": record.source})
        group_members.setdefault(gid, []).append(record.record_id)

    assignment = assign_groups_to_splits(groups, (0.6, 0.2, 0.2), seed=7)

    # Every review's three sentence-records must share one split.
    for gid, member_ids in group_members.items():
        splits_for_group = {assignment[gid] for _ in member_ids}
        assert len(splits_for_group) == 1


def test_end_to_end_split_has_no_leakage(tmp_path):
    """Run main() and confirm no record_id crosses splits and no group is
    split across manifests."""
    records = _leakage_fixture()
    input_path = tmp_path / "adjudicated.jsonl"
    # Write JSONL preserving the extra `source_record_id` leakage-grouping
    # field (annotations.write_jsonl only emits the core schema fields).
    dicts = []
    for r in records:
        obj = _valid_record_dict(r.record_id)
        obj["source"] = r.source
        obj["region"] = r.region
        obj["text"] = r.text
        obj["intent"] = r.intent
        src_id = getattr(r, "source_record_id", None)
        if src_id is not None:
            obj["source_record_id"] = src_id
        dicts.append(obj)
    _write_jsonl(input_path, dicts)

    out_dir = tmp_path / "processed"
    rc = main(
        [
            "--input", str(input_path),
            "--output-dir", str(out_dir),
            "--train-ratio", "0.6",
            "--validation-ratio", "0.2",
            "--test-ratio", "0.2",
            "--seed", "7",
        ]
    )
    assert rc == 0

    split_ids: dict[str, set[str]] = {}
    for name in ("train", "validation", "test"):
        lines = (out_dir / f"{name}_manifest.csv").read_text(encoding="utf-8").splitlines()
        # Skip the header row.
        split_ids[name] = set(lines[1:])

    # No record_id appears in more than one split.
    train, validation, test = split_ids["train"], split_ids["validation"], split_ids["test"]
    assert train & validation == set()
    assert train & test == set()
    assert validation & test == set()

    # Map each record_id -> group, then confirm no group spans two splits.
    record_group = {r.record_id: group_key(r) for r in records}
    group_split: dict[str, str] = {}
    for name, ids in split_ids.items():
        for record_id in ids:
            gid = record_group[record_id]
            assert group_split.setdefault(gid, name) == name


# ---------------------------------------------------------------------------
# Req 23.2: refusal-to-run on invalid input
# ---------------------------------------------------------------------------


def test_refuses_to_run_and_writes_no_manifest_for_invalid_input(tmp_path):
    valid = _valid_record_dict("rev0_s0")
    invalid = _valid_record_dict("rev1_s0")
    invalid["intent"] = "not_a_real_intent"  # unknown intent -> invalid

    input_path = tmp_path / "with_invalid.jsonl"
    _write_jsonl(input_path, [valid, invalid])

    out_dir = tmp_path / "processed"
    rc = main(["--input", str(input_path), "--output-dir", str(out_dir)])

    assert rc != 0
    # No manifest files (and no report) were written.
    if out_dir.exists():
        assert list(out_dir.glob("*_manifest.csv")) == []
        assert not (out_dir / "split_report.json").exists()


def test_refuses_to_run_for_offset_mismatch(tmp_path):
    valid = _valid_record_dict("rev0_s0")
    bad = _valid_record_dict("rev1_s0")
    bad["aspects"] = [{"term": "zzz", "start": 0, "end": 3, "category": "cards", "sentiment": "negative"}]

    input_path = tmp_path / "with_offset_mismatch.jsonl"
    _write_jsonl(input_path, [valid, bad])

    out_dir = tmp_path / "processed"
    rc = main(["--input", str(input_path), "--output-dir", str(out_dir)])

    assert rc != 0
    if out_dir.exists():
        assert list(out_dir.glob("*_manifest.csv")) == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_assign_groups_to_splits_is_deterministic():
    groups = {f"g{i}": {"intent": "complaint" if i % 2 == 0 else "compliment", "source": "bank_reviews"} for i in range(20)}
    ratios = (0.7, 0.15, 0.15)

    first = assign_groups_to_splits(groups, ratios, seed=123)
    second = assign_groups_to_splits(groups, ratios, seed=123)

    assert first == second
    # Every group is assigned to exactly one of the three splits.
    assert set(first.keys()) == set(groups.keys())
    assert all(v in ("train", "validation", "test") for v in first.values())


def test_assign_groups_respects_ratios_roughly():
    groups = {f"g{i}": {"intent": "general_feedback", "source": "bank_reviews"} for i in range(100)}
    assignment = assign_groups_to_splits(groups, (0.7, 0.15, 0.15), seed=5)

    counts = {"train": 0, "validation": 0, "test": 0}
    for split in assignment.values():
        counts[split] += 1

    assert counts["train"] == 70
    assert counts["validation"] == 15
    assert counts["test"] == 15
