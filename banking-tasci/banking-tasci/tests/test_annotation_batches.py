"""Tests for calibration + batching (Requirements Section 13).

Uses a small deterministic synthetic 1,000-record annotation-style plan (not
the real samplers) so group-aware batching, oversized-group detection, and
exact batch sizing can be exercised directly and fast.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from banking_tasci.data.annotation_batches import (  # noqa: E402
    BATCH_SPECS,
    CALIBRATION_SIZE,
    FINAL_BATCH_SIZE,
    MAIN_BATCH_COUNT,
    MAIN_BATCH_SIZE,
    TOTAL_RECORDS,
    assign_batches,
    build_batch_metadata,
    build_combined_batch_manifest,
    compute_annotation_group_key,
    freeze_calibration_guide,
    group_components,
    next_incomplete_record,
    transition_batch_status,
    update_batch_progress,
    validate_submission,
    write_batches,
)

SOURCES = ("south_africa_tweet", "international_tweet", "international_review")
BANKS = ("FNB", "Absa", "Nedbank", "Standard Bank", "Capitec")


def _make_records(n: int = 1000, *, grouped_pairs: int = 0) -> list[dict]:
    """1,000 synthetic label-hidden records with varied source/bank/context/length.

    ``grouped_pairs`` creates that many pairs of records sharing a
    ``duplicate_group`` value, to exercise group-aware batching.
    """
    records = []
    for i in range(n):
        source = SOURCES[i % 3]
        region = "south_africa" if source == "south_africa_tweet" else "international"
        bank = BANKS[i % len(BANKS)] if source == "south_africa_tweet" else None
        text = "word " * (1 + (i % 40))
        records.append(
            {
                "record_id": f"{source}::rec{i:04d}",
                "source_record_id": f"rec{i:04d}",
                "source": source,
                "region": region,
                "bank": bank,
                "review_id": f"rv{i:04d}" if source == "international_review" else None,
                "thread_id": None,
                "conversation_id": None,
                "publish_year": 2020,
                "text": text.strip(),
                "previous_text": None,
                "context_available": i % 4 == 0,
                "duplicate_group": None,
                "leakage_group": None,
                "privacy_status": "anonymised",
                "primary_intent": None,
                "public_warning": None,
                "opinions": [],
                "annotation_status": "not_started",
                "annotation_version": "new_pipeline_v1",
                "annotation_notes": None,
            }
        )
    for pair in range(grouped_pairs):
        a, b = 2 * pair, 2 * pair + 1
        records[a]["duplicate_group"] = f"group_{pair}"
        records[b]["duplicate_group"] = f"group_{pair}"
    return records


@pytest.fixture
def records() -> list[dict]:
    return _make_records()


# ---------------------------------------------------------------------------
# Structural constants
# ---------------------------------------------------------------------------


def test_total_is_1000():
    assert TOTAL_RECORDS == 1000
    assert CALIBRATION_SIZE + MAIN_BATCH_SIZE * MAIN_BATCH_COUNT + FINAL_BATCH_SIZE == 1000


def test_exactly_11_batches():
    assert len(BATCH_SPECS) == 11


def test_batch_sizes_are_correct():
    sizes = {name: size for name, _type, size in BATCH_SPECS}
    assert sizes["calibration_001"] == 50
    for i in range(1, 10):
        assert sizes[f"main_{i:03d}"] == 100
    assert sizes["final_001"] == 50


def test_batch_types_are_correct():
    types = {name: t for name, t, _size in BATCH_SPECS}
    assert types["calibration_001"] == "calibration"
    assert all(types[f"main_{i:03d}"] == "main" for i in range(1, 10))
    assert types["final_001"] == "final"


# ---------------------------------------------------------------------------
# Assignment correctness
# ---------------------------------------------------------------------------


def test_every_batch_has_expected_size(records):
    assignment = assign_batches(records, seed=42)
    sizes = {name: size for name, _type, size in BATCH_SPECS}
    for name, indices in assignment.batches.items():
        assert len(indices) == sizes[name]


def test_every_record_appears_exactly_once(records):
    assignment = assign_batches(records, seed=42)
    all_indices = [i for indices in assignment.batches.values() for i in indices]
    assert sorted(all_indices) == list(range(len(records)))
    assert len(all_indices) == len(set(all_indices))


def test_no_record_omitted(records):
    assignment = assign_batches(records, seed=42)
    assigned = {i for indices in assignment.batches.values() for i in indices}
    assert assigned == set(range(len(records)))


def test_deterministic_under_seed_42(records):
    first = assign_batches(records, seed=42)
    second = assign_batches(records, seed=42)
    assert first.batches == second.batches


def test_different_seed_can_change_assignment(records):
    first = assign_batches(records, seed=42)
    second = assign_batches(records, seed=7)
    assert first.batches != second.batches


def test_batch_ids_are_stable(records):
    assignment = assign_batches(records, seed=42)
    assert set(assignment.batches.keys()) == {name for name, _t, _s in BATCH_SPECS}


# ---------------------------------------------------------------------------
# Group integrity
# ---------------------------------------------------------------------------


def test_groups_remain_intact(records):
    grouped = _make_records(grouped_pairs=20)
    assignment = assign_batches(grouped, seed=42)
    index_to_batch = {
        i: name for name, indices in assignment.batches.items() for i in indices
    }
    for pair in range(20):
        a, b = 2 * pair, 2 * pair + 1
        assert index_to_batch[a] == index_to_batch[b]


def test_review_id_keeps_records_together():
    records = _make_records()
    # Force two review records to share a review_id.
    records[2]["review_id"] = "shared_review"
    records[5]["review_id"] = "shared_review"
    assignment = assign_batches(records, seed=42)
    index_to_batch = {
        i: name for name, indices in assignment.batches.items() for i in indices
    }
    assert index_to_batch[2] == index_to_batch[5]


def test_compute_annotation_group_key_priority():
    record = {
        "duplicate_group": "d1",
        "leakage_group": "l1",
        "review_id": "r1",
        "thread_id": "t1",
        "conversation_id": "c1",
    }
    assert compute_annotation_group_key(record) == "duplicate_group:d1"


def test_compute_annotation_group_key_none_when_ungrouped():
    record = {
        "duplicate_group": None,
        "leakage_group": None,
        "review_id": None,
        "thread_id": None,
        "conversation_id": None,
    }
    assert compute_annotation_group_key(record) is None


def test_group_components_links_across_different_fields():
    records = _make_records(grouped_pairs=0)
    records[0]["review_id"] = "shared"
    records[1]["thread_id"] = "shared"  # different field, same value - NOT linked
    components = group_components(records)
    # review_id "shared" and thread_id "shared" are different keys (field, value),
    # so records[0] and records[1] must NOT be forced together by this alone.
    comp_of_0 = next(c for c in components if 0 in c)
    assert 1 not in comp_of_0


def test_oversized_group_raises():
    records = _make_records()
    # Force 101 records into one duplicate_group - exceeds the largest batch (100).
    for i in range(101):
        records[i]["duplicate_group"] = "huge_group"
    with pytest.raises(ValueError):
        assign_batches(records, seed=42)


def test_requires_exactly_1000_records():
    with pytest.raises(ValueError):
        assign_batches(_make_records(n=999), seed=42)


# ---------------------------------------------------------------------------
# Calibration diversity (soft heuristic, checked on the synthetic mix)
# ---------------------------------------------------------------------------


def test_calibration_batch_covers_multiple_sources(records):
    assignment = assign_batches(records, seed=42)
    calibration = [records[i] for i in assignment.batches["calibration_001"]]
    sources_covered = {r["source"] for r in calibration}
    assert len(sources_covered) == 3


def test_calibration_batch_covers_context_available_and_not(records):
    assignment = assign_batches(records, seed=42)
    calibration = [records[i] for i in assignment.batches["calibration_001"]]
    contexts = {r["context_available"] for r in calibration}
    assert contexts == {True, False}


# ---------------------------------------------------------------------------
# Metadata and manifests
# ---------------------------------------------------------------------------


def test_build_batch_metadata_fields(records):
    assignment = assign_batches(records, seed=42)
    batch_records = [records[i] for i in assignment.batches["calibration_001"]]
    metadata = build_batch_metadata(
        "calibration_001", "calibration", batch_records,
        source_sample_manifest_checksum="abc123",
    )
    assert metadata.batch_id == "calibration_001"
    assert metadata.batch_type == "calibration"
    assert metadata.batch_status == "generated"
    assert metadata.record_count == 50
    assert metadata.checksum
    assert metadata.pipeline_version == "new_pipeline_v1"
    assert len(metadata.record_ids) == 50


def test_combined_batch_manifest_contains_all_batches(records):
    assignment = assign_batches(records, seed=42)
    metadatas = [
        build_batch_metadata(name, btype, [records[i] for i in assignment.batches[name]])
        for name, btype, _size in BATCH_SPECS
    ]
    manifest = build_combined_batch_manifest(metadatas, assignment)
    assert manifest["total_batches"] == 11
    assert manifest["total_records"] == 1000
    assert set(manifest["batch_ids"]) == {name for name, _t, _s in BATCH_SPECS}
    assert manifest["seed"] == 42


# ---------------------------------------------------------------------------
# Writing: dry-run default, overwrite protection, atomicity
# ---------------------------------------------------------------------------


def test_write_batches_creates_files(tmp_path, records):
    assignment = assign_batches(records, seed=42)
    batches = {
        name: [records[i] for i in indices] for name, indices in assignment.batches.items()
    }
    paths = write_batches(batches, tmp_path / "batches")
    assert len(paths) == 11
    for name, path in paths.items():
        assert path.is_file()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        expected_size = {n: s for n, _t, s in BATCH_SPECS}[name]
        assert len(lines) == expected_size


def test_write_batches_refuses_overwrite_without_flag(tmp_path, records):
    assignment = assign_batches(records, seed=42)
    batches = {
        name: [records[i] for i in indices] for name, indices in assignment.batches.items()
    }
    write_batches(batches, tmp_path / "batches")
    with pytest.raises(FileExistsError):
        write_batches(batches, tmp_path / "batches")


def test_write_batches_allows_overwrite_with_flag(tmp_path, records):
    assignment = assign_batches(records, seed=42)
    batches = {
        name: [records[i] for i in indices] for name, indices in assignment.batches.items()
    }
    write_batches(batches, tmp_path / "batches")
    # Should not raise.
    write_batches(batches, tmp_path / "batches", overwrite=True)


# ---------------------------------------------------------------------------
# Deterministic record order within each batch (Requirements Section 15)
# ---------------------------------------------------------------------------


def test_batch_record_order_is_sorted_by_record_id(records):
    assignment = assign_batches(records, seed=42)
    for indices in assignment.batches.values():
        ids = [records[i]["record_id"] for i in indices]
        assert ids == sorted(ids)


def test_batch_record_order_is_deterministic_across_runs(records):
    first = assign_batches(records, seed=42)
    second = assign_batches(records, seed=42)
    for name in first.batches:
        first_ids = [records[i]["record_id"] for i in first.batches[name]]
        second_ids = [records[i]["record_id"] for i in second.batches[name]]
        assert first_ids == second_ids


# ---------------------------------------------------------------------------
# Calibration-freeze status transitions (Requirements Section 14)
# ---------------------------------------------------------------------------


def test_new_batch_metadata_starts_generated(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    assert metadata.batch_status == "generated"
    assert metadata.opened_at is None
    assert metadata.completed_at is None
    assert metadata.validated_at is None


def test_valid_transition_sequence(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    assert metadata.batch_status == "in_progress"
    assert metadata.opened_at is not None

    completed_records = [dict(record, annotation_status="completed") for record in records[:50]]
    metadata = update_batch_progress(metadata, completed_records)
    metadata = transition_batch_status(metadata, "completed")
    assert metadata.batch_status == "completed"
    assert metadata.completed_at is not None

    metadata = transition_batch_status(metadata, "validated", validation_passed=True)
    assert metadata.batch_status == "validated"
    assert metadata.validated_at is not None

    with pytest.warns(DeprecationWarning):
        metadata = freeze_calibration_guide(metadata, guide_version="guide-v1", approval=approval)
    assert metadata.batch_status == "validated"
    assert metadata.annotation_guide_version == "guide-v1"


def test_cannot_skip_straight_to_completed(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    with pytest.raises(ValueError):
        transition_batch_status(metadata, "completed")


def test_cannot_transition_out_of_frozen(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    completed_records = [dict(record, annotation_status="completed") for record in records[:50]]
    metadata = update_batch_progress(metadata, completed_records)
    metadata = transition_batch_status(metadata, "completed")
    metadata = transition_batch_status(metadata, "validated", validation_passed=True)
    metadata = transition_batch_status(metadata, "frozen")
    with pytest.raises(ValueError):
        transition_batch_status(metadata, "in_progress")


def test_validation_failed_allows_retry(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    completed_records = [dict(record, annotation_status="completed") for record in records[:50]]
    metadata = update_batch_progress(metadata, completed_records)
    metadata = transition_batch_status(metadata, "completed")
    metadata = transition_batch_status(metadata, "validation_failed")
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    assert metadata.batch_status == "in_progress"


def test_rejects_unapproved_status(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    with pytest.raises(ValueError):
        transition_batch_status(metadata, "not_a_real_status")


def test_cannot_complete_batch_with_incomplete_records(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    with pytest.raises(ValueError, match="completed records"):
        transition_batch_status(metadata, "completed")


def test_validated_transition_requires_explicit_pass(records):
    metadata = build_batch_metadata("calibration_001", "calibration", records[:50])
    approval = {"approval_status": "APPROVED", "pipeline_version": "new_pipeline_v1"}
    metadata = transition_batch_status(metadata, "in_progress", approval=approval)
    completed_records = [dict(record, annotation_status="completed") for record in records[:50]]
    metadata = update_batch_progress(metadata, completed_records)
    metadata = transition_batch_status(metadata, "completed")
    with pytest.raises(ValueError, match="validation_passed"):
        transition_batch_status(metadata, "validated")


# ---------------------------------------------------------------------------
# Safe resumption (Requirements Section 15)
# ---------------------------------------------------------------------------


def test_validate_submission_accepts_matching_batch(records):
    batch_records = records[:50]
    metadata = build_batch_metadata("calibration_001", "calibration", batch_records)
    assert validate_submission(metadata, batch_records) == []


def test_validate_submission_rejects_duplicate_record_ids(records):
    batch_records = records[:50]
    metadata = build_batch_metadata("calibration_001", "calibration", batch_records)
    submitted = batch_records + [batch_records[0]]
    issues = validate_submission(metadata, submitted)
    assert any("duplicate" in issue for issue in issues)


def test_validate_submission_rejects_foreign_records(records):
    batch_records = records[:50]
    metadata = build_batch_metadata("calibration_001", "calibration", batch_records)
    foreign_record = dict(records[500])
    submitted = batch_records[:-1] + [foreign_record]
    issues = validate_submission(metadata, submitted)
    assert any("do not belong" in issue for issue in issues)


def test_validate_submission_rejects_missing_records(records):
    batch_records = records[:50]
    metadata = build_batch_metadata("calibration_001", "calibration", batch_records)
    submitted = batch_records[:-1]  # one record missing
    issues = validate_submission(metadata, submitted)
    assert any("missing" in issue for issue in issues)


def test_validate_submission_rejects_wrong_pipeline_version(records):
    batch_records = [dict(r) for r in records[:50]]
    metadata = build_batch_metadata("calibration_001", "calibration", batch_records)
    batch_records[0]["annotation_version"] = "some_other_pipeline_v0"
    issues = validate_submission(metadata, batch_records)
    assert any("annotation_version" in issue for issue in issues)


def test_next_incomplete_record_returns_first_not_started(records):
    batch_records = [dict(r) for r in records[:5]]
    for r in batch_records:
        r["annotation_status"] = "completed"
    batch_records[3]["annotation_status"] = "not_started"
    incomplete = next_incomplete_record(batch_records)
    assert incomplete is not None
    assert incomplete["record_id"] == batch_records[3]["record_id"]


def test_next_incomplete_record_returns_none_when_all_completed(records):
    batch_records = [dict(r) for r in records[:5]]
    for r in batch_records:
        r["annotation_status"] = "completed"
    assert next_incomplete_record(batch_records) is None


def test_canonical_batch_source_targets_reconcile_and_fit_sizes():
    from banking_tasci.data.annotation_batches import batch_source_targets

    targets = batch_source_targets()
    expected_totals = {"south_africa_tweet": 500, "international_tweet": 250, "international_review": 250}
    assert {source: sum(batch[source] for batch in targets.values()) for source in expected_totals} == expected_totals
    assert all(sum(targets[name].values()) == size for name, _kind, size in BATCH_SPECS)
    assert targets["calibration_001"] == {
        "south_africa_tweet": 25, "international_tweet": 13, "international_review": 12,
    }
    assert targets["final_001"] == {
        "south_africa_tweet": 25, "international_tweet": 12, "international_review": 13,
    }


def test_assignment_records_observed_targets_deviations_and_warnings():
    records = _make_records()
    assignment = assign_batches(records, seed=42)
    assert set(assignment.source_targets) == set(assignment.source_observed)
    assert all(name in assignment.group_counts for name, _kind, _size in BATCH_SPECS)
    for name, deviations in assignment.source_deviations.items():
        assert deviations
        assert name in assignment.grouping_balance_explanations
        assert any(name in warning for warning in assignment.unresolved_balancing_warnings)


def test_batch_metadata_can_capture_balance_evidence(records):
    from banking_tasci.data.annotation_batches import batch_source_targets

    assignment = assign_batches(records, seed=42)
    name = "calibration_001"
    metadata = build_batch_metadata(
        name, "calibration", [records[i] for i in assignment.batches[name]],
        source_target_distribution=assignment.source_targets[name],
        source_deviation=assignment.source_deviations.get(name, {}),
        region_target_distribution=assignment.region_targets[name],
        region_deviation=assignment.region_deviations.get(name, {}),
        group_count=assignment.group_counts[name],
        constraint_warnings=[warning for warning in assignment.unresolved_balancing_warnings if name in warning],
        balancing_explanation=assignment.grouping_balance_explanations.get(name),
    )
    assert metadata.source_target_distribution == assignment.source_targets[name]
    assert batch_source_targets()[name] == {
        "south_africa_tweet": 25,
        "international_tweet": 13,
        "international_review": 12,
    }
    assert metadata.region_target_distribution == assignment.region_targets[name]
    assert metadata.group_count > 0


def test_oversized_connected_group_fails_without_splitting():
    records = _make_records()
    for index in range(101):
        records[index]["leakage_group"] = "oversized-connected-component"
    with pytest.raises(ValueError, match="exceed largest batch capacity"):
        assign_batches(records, seed=42)


def test_all_public_workflow_api_names_are_exported():
    import banking_tasci.data.annotation_batches as module

    expected = {
        "BatchMetadata", "BatchAssignment", "assign_batches", "build_batch_metadata",
        "build_combined_batch_manifest", "write_batches", "validate_submission",
        "next_incomplete_record", "transition_batch_status", "freeze_calibration_guide",
        "assert_main_annotation_allowed", "annotation_records_checksum",
        "update_batch_progress", "save_annotation_checkpoint", "batch_source_targets",
    }
    assert expected.issubset(set(module.__all__))
    assert all(hasattr(module, name) for name in expected)

