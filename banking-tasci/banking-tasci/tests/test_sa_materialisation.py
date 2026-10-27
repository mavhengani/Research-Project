"""Tests for the canonical v2 selection and the materialisation command.

The central invariant: the materialised South African candidate corpus must be
the **verified** 100,768-record v2 selection, produced by one canonical filter,
with every assertion running *before* any write and no coercion toward the
expected count.

Most tests use small synthetic fixtures so they are fast. Two explicitly-marked
integration tests touch the real corpora read-only; both are skipped when those
files are absent.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from banking_tasci.data.sa_candidates_v2 import (  # noqa: E402
    EXPECTED_RULE_COUNTS,
    EXPECTED_TOTAL,
    REQUIRED_SOURCE_COLUMNS,
    RULE_PRECEDENCE,
    SELECTION_VERSION,
    select_v2_candidates,
)

REAL_PARENT = _PROJECT_ROOT / "data" / "interim" / "south_africa_prepared.parquet"
REAL_OUTPUT = (
    _PROJECT_ROOT
    / "data"
    / "processed"
    / "new_pipeline_v1"
    / "south_africa_candidates_v2.parquet"
)
REAL_REPORT = (
    _PROJECT_ROOT
    / "artifacts"
    / "manifests"
    / "new_pipeline_v1"
    / "south_africa_candidates_v2_materialisation.json"
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "materialize_sa_v2",
        _PROJECT_ROOT / "scripts" / "materialize_south_africa_candidates_v2.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------


def _synthetic_parent(tmp_path: Path) -> Path:
    """A small parent corpus with a known, hand-checkable selection."""
    rows = [
        # Rule A: aspect + problem.
        {"record_id": "a1", "text": "my card was declined and it failed again today",
         "created_at": "2021-01-01", "possible_official_account": False},
        # Rule B: aspect + request.
        {"record_id": "b1", "text": "please help me with my account transfer issue",
         "created_at": "2020-05-05", "possible_official_account": False},
        # Outside the study year range -> excluded.
        {"record_id": "y1", "text": "my card was declined and it failed again today",
         "created_at": "2017-01-01", "possible_official_account": False},
        # Official account -> excluded.
        {"record_id": "o1", "text": "my card was declined and it failed again today",
         "created_at": "2021-01-01", "possible_official_account": True},
        # No banking content -> excluded.
        {"record_id": "n1", "text": "the weather today is lovely and warm outside",
         "created_at": "2021-01-01", "possible_official_account": False},
        # Too short -> excluded.
        {"record_id": "s1", "text": "card bad",
         "created_at": "2021-01-01", "possible_official_account": False},
    ]
    frame = pd.DataFrame(rows)
    frame["source"] = "south_african_bank_tweets"
    frame["region"] = "south_africa"
    frame["bank"] = ["fnb", "absa", "fnb", "fnb", "nedbank", "capitec"]
    frame["previous_text"] = "[NO_CONTEXT]"
    frame["context_available"] = False
    frame["near_dup_group_id"] = None
    frame["near_dup_flag"] = False
    frame["thread_id"] = None
    frame["rating"] = None
    frame["title"] = None
    # Candidate-rule metadata that must NOT reach the output.
    frame["candidate_strata"] = "x"
    frame["filter_reason"] = "y"
    frame["customer_feedback_candidate"] = True

    path = tmp_path / "parent.parquet"
    frame.to_parquet(path, index=False)
    return path


@pytest.fixture
def synthetic_parent(tmp_path) -> Path:
    return _synthetic_parent(tmp_path)


# ---------------------------------------------------------------------------
# Canonical selection function
# ---------------------------------------------------------------------------


def test_selection_version_is_recorded():
    assert SELECTION_VERSION == "sa_candidates_v2"


def test_rule_precedence_is_documented_order():
    assert RULE_PRECEDENCE == ("F", "A", "B", "C", "D", "E")


def test_expected_rule_counts_sum_to_expected_total():
    assert sum(EXPECTED_RULE_COUNTS.values()) == EXPECTED_TOTAL == 100_768


def test_selection_requires_expected_columns(tmp_path):
    frame = pd.DataFrame({"record_id": ["a"], "text": ["x"]})
    with pytest.raises(ValueError, match="missing required column"):
        select_v2_candidates(frame)


def test_selection_rejects_obvious_non_candidates(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = set(frame.loc[result.mask, "record_id"])
    # Year range, official account, no-banking, and too-short are all excluded.
    assert "y1" not in selected
    assert "o1" not in selected
    assert "n1" not in selected
    assert "s1" not in selected


def test_selection_accepts_rule_matching_records(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = set(frame.loc[result.mask, "record_id"])
    assert "a1" in selected
    assert "b1" in selected


def test_selection_does_not_mutate_input(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    before = frame.copy(deep=True)
    select_v2_candidates(frame)
    pd.testing.assert_frame_equal(frame, before)


def test_selection_is_deterministic(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    first = select_v2_candidates(frame)
    second = select_v2_candidates(frame)
    assert first.total == second.total
    assert first.rule_counts == second.rule_counts
    assert list(first.mask) == list(second.mask)


def test_rule_counts_sum_to_total(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    assert sum(result.rule_counts.values()) == result.total


def test_result_to_dict_omits_large_series(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    payload = select_v2_candidates(frame).to_dict()
    assert "mask" not in payload
    assert "rule_labels" not in payload
    assert payload["selection_version"] == SELECTION_VERSION


# ---------------------------------------------------------------------------
# Verification gate: mismatch must fail, never coerce
# ---------------------------------------------------------------------------


def test_mismatched_count_raises_rather_than_coercing(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = frame.loc[result.mask]
    with pytest.raises(SCRIPT.VerificationError, match="Refusing to write"):
        SCRIPT.verify_selection(
            frame, selected, result, expected_total=100_768, allow_count_change=False
        )


def test_allow_count_change_permits_a_documented_difference(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = frame.loc[result.mask][["record_id", "text"]]
    checks = SCRIPT.verify_selection(
        frame, selected, result, expected_total=100_768, allow_count_change=True
    )
    # It reports the true observed count, not the expected one.
    assert checks["row_count"] == int(result.total)
    assert checks["row_count"] != 100_768


def test_duplicate_identifiers_are_rejected(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = frame.loc[result.mask].copy()
    selected = pd.concat([selected, selected.head(1)])  # inject a duplicate
    with pytest.raises(SCRIPT.VerificationError, match="duplicate record_id"):
        SCRIPT.verify_selection(
            frame, selected, result, expected_total=len(selected), allow_count_change=True
        )


def test_identifier_absent_from_parent_is_rejected(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = frame.loc[result.mask].copy()
    selected.loc[selected.index[0], "record_id"] = "not_in_parent"
    with pytest.raises(SCRIPT.VerificationError, match="absent from the parent"):
        SCRIPT.verify_selection(
            frame, selected, result, expected_total=len(selected), allow_count_change=True
        )


def test_non_strict_subset_is_rejected(synthetic_parent):
    """A selection equal to the whole parent is not a STRICT subset."""
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    with pytest.raises(SCRIPT.VerificationError, match="STRICT subset"):
        SCRIPT.verify_selection(
            frame, frame, result, expected_total=len(frame), allow_count_change=True
        )


def test_forbidden_columns_are_rejected(synthetic_parent):
    """Candidate-rule and task-label columns must never reach the output."""
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = frame.loc[result.mask]  # still carries candidate_strata etc.
    with pytest.raises(SCRIPT.VerificationError, match="forbidden column"):
        SCRIPT.verify_selection(
            frame, selected, result, expected_total=len(selected), allow_count_change=True
        )


def test_raw_identifier_columns_are_rejected(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    selected = frame.loc[result.mask][["record_id", "text"]].copy()
    selected["username"] = "@someone"
    with pytest.raises(SCRIPT.VerificationError, match="raw identifier column"):
        SCRIPT.verify_selection(
            frame, selected, result, expected_total=len(selected), allow_count_change=True
        )


def test_clean_selection_passes_verification(synthetic_parent):
    frame = pd.read_parquet(synthetic_parent)
    result = select_v2_candidates(frame)
    carry = [c for c in SCRIPT.CARRY_COLUMNS if c in frame.columns]
    selected = frame.loc[result.mask][carry]
    checks = SCRIPT.verify_selection(
        frame, selected, result, expected_total=len(selected), allow_count_change=True
    )
    assert checks["duplicate_record_count"] == 0
    assert checks["ids_present_in_parent"] is True
    assert checks["strict_subset_verified"] is True
    assert checks["forbidden_columns_present"] == []


def test_carry_columns_exclude_candidate_metadata():
    """Requirements 6.5: candidate rules must not become task labels."""
    for forbidden in ("candidate_strata", "filter_reason", "customer_feedback_candidate"):
        assert forbidden not in SCRIPT.CARRY_COLUMNS
        assert forbidden in SCRIPT.FORBIDDEN_OUTPUT_COLUMNS


def test_task_label_columns_are_all_forbidden():
    for label in ("target", "category", "sentiment", "intent", "opinions", "aspects"):
        assert label in SCRIPT.FORBIDDEN_OUTPUT_COLUMNS


# ---------------------------------------------------------------------------
# Atomic write and overwrite protection
# ---------------------------------------------------------------------------


def test_write_atomic_produces_the_file(tmp_path):
    frame = pd.DataFrame({"record_id": ["a", "b"], "text": ["x", "y"]})
    out = tmp_path / "nested" / "out.parquet"
    SCRIPT.write_atomic(frame, out)
    assert out.is_file()
    assert len(pd.read_parquet(out)) == 2


def test_write_atomic_leaves_no_temp_file_on_success(tmp_path):
    frame = pd.DataFrame({"record_id": ["a"], "text": ["x"]})
    out = tmp_path / "out.parquet"
    SCRIPT.write_atomic(frame, out)
    leftovers = [p.name for p in out.parent.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_write_atomic_cleans_temp_file_on_failure(tmp_path):
    """A failure mid-write must not leave a temporary file behind."""

    class Exploding(pd.DataFrame):
        @property
        def _constructor(self):
            return Exploding

        def to_parquet(self, *args, **kwargs):  # noqa: D401
            raise RuntimeError("simulated write failure")

    out = tmp_path / "out.parquet"
    with pytest.raises(RuntimeError, match="simulated write failure"):
        SCRIPT.write_atomic(Exploding({"record_id": ["a"]}), out)

    assert not out.exists()
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_existing_output_is_not_overwritten_without_permission(tmp_path, synthetic_parent):
    out = tmp_path / "existing.parquet"
    out.write_bytes(b"sentinel")
    rc = SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(out),
        "--report", str(tmp_path / "r.json"),
    ])
    assert rc == 1
    assert out.read_bytes() == b"sentinel"  # untouched


def test_dry_run_writes_nothing(tmp_path, synthetic_parent):
    out = tmp_path / "dry.parquet"
    rc = SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(out),
        "--report", str(tmp_path / "r.json"),
        "--expected-total", "2",
        "--allow-count-change",
        "--dry-run",
    ])
    assert rc == 0
    assert not out.exists()


def test_verification_failure_returns_exit_code_2(tmp_path, synthetic_parent):
    out = tmp_path / "nope.parquet"
    rc = SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(out),
        "--report", str(tmp_path / "r.json"),
        # Deliberately wrong expectation, without --allow-count-change.
        "--expected-total", "999999",
    ])
    assert rc == 2
    assert not out.exists()


def test_missing_source_returns_exit_code_1(tmp_path):
    rc = SCRIPT.main([
        "--source", str(tmp_path / "absent.parquet"),
        "--output", str(tmp_path / "o.parquet"),
        "--report", str(tmp_path / "r.json"),
    ])
    assert rc == 1


# ---------------------------------------------------------------------------
# Determinism and checksums
# ---------------------------------------------------------------------------


def test_logical_checksum_is_order_independent():
    first = pd.DataFrame({"record_id": ["a", "b", "c"]})
    second = pd.DataFrame({"record_id": ["c", "a", "b"]})
    assert SCRIPT.logical_checksum(first) == SCRIPT.logical_checksum(second)


def test_logical_checksum_changes_with_membership():
    first = pd.DataFrame({"record_id": ["a", "b"]})
    second = pd.DataFrame({"record_id": ["a", "z"]})
    assert SCRIPT.logical_checksum(first) != SCRIPT.logical_checksum(second)


def test_repeated_materialisation_is_deterministic(tmp_path, synthetic_parent):
    """Repeated runs must select the same identifiers and logical checksum."""
    checksums = []
    for i in range(2):
        out = tmp_path / f"run{i}.parquet"
        rc = SCRIPT.main([
            "--source", str(synthetic_parent),
            "--output", str(out),
            "--report", str(tmp_path / f"r{i}.json"),
            "--expected-total", "2",
            "--allow-count-change",
        ])
        assert rc == 0
        checksums.append(SCRIPT.logical_checksum(pd.read_parquet(out)))
    assert checksums[0] == checksums[1]


def test_report_contains_all_required_fields(tmp_path, synthetic_parent):
    out = tmp_path / "o.parquet"
    report_path = tmp_path / "report.json"
    rc = SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(out),
        "--report", str(report_path),
        "--expected-total", "2",
        "--allow-count-change",
    ])
    assert rc == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    for field in (
        "pipeline_version",
        "source_path",
        "source_sha256",
        "source_row_count",
        "output_path",
        "output_sha256",
        "output_row_count",
        "unique_record_count",
        "duplicate_record_count",
        "strict_subset_verified",
        "privacy_status",
        "rule_counts",
        "generated_at",
        "generation_command",
        "git_commit",
    ):
        assert field in report, f"missing report field: {field}"

    assert report["pipeline_version"] == "new_pipeline_v1"
    assert report["git_commit"]  # either a hash or the explicit marker


def test_report_records_no_commit_marker(tmp_path, synthetic_parent):
    """With no commit in the repository the marker must be explicit."""
    report_path = tmp_path / "report.json"
    SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(tmp_path / "o.parquet"),
        "--report", str(report_path),
        "--expected-total", "2",
        "--allow-count-change",
    ])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # Either a real hash or the explicit marker - never invented.
    assert report["git_commit"] == SCRIPT.NO_COMMIT_MARKER or len(
        report["git_commit"]
    ) == 40


def test_output_excludes_candidate_metadata(tmp_path, synthetic_parent):
    out = tmp_path / "o.parquet"
    SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(out),
        "--report", str(tmp_path / "r.json"),
        "--expected-total", "2",
        "--allow-count-change",
    ])
    written = pd.read_parquet(out)
    for forbidden in ("candidate_strata", "filter_reason", "customer_feedback_candidate"):
        assert forbidden not in written.columns


def test_source_remains_byte_identical(tmp_path, synthetic_parent):
    before = synthetic_parent.read_bytes()
    before_hash = SCRIPT.sha256_file(synthetic_parent)
    SCRIPT.main([
        "--source", str(synthetic_parent),
        "--output", str(tmp_path / "o.parquet"),
        "--report", str(tmp_path / "r.json"),
        "--expected-total", "2",
        "--allow-count-change",
    ])
    assert synthetic_parent.read_bytes() == before
    assert SCRIPT.sha256_file(synthetic_parent) == before_hash


# ---------------------------------------------------------------------------
# Integration against the real corpora (read-only, skipped if absent)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_PARENT.is_file(), reason="real parent source absent")
def test_real_source_reproduces_exactly_100768():
    """The authoritative reproduction, via the canonical function."""
    columns = list(REQUIRED_SOURCE_COLUMNS)
    frame = pd.read_parquet(REAL_PARENT, columns=columns)
    result = select_v2_candidates(frame)

    assert result.total == EXPECTED_TOTAL == 100_768
    assert result.rule_counts == dict(sorted(EXPECTED_RULE_COUNTS.items()))
    assert sum(result.rule_counts.values()) == 100_768

    ids = frame.loc[result.mask, "record_id"].astype(str)
    assert ids.nunique() == 100_768  # unique
    assert len(ids) - ids.nunique() == 0  # zero duplicates

    parent_ids = set(frame["record_id"].astype(str))
    selected_ids = set(ids)
    assert selected_ids < parent_ids  # strict subset


@pytest.mark.skipif(not REAL_OUTPUT.is_file(), reason="materialised corpus absent")
def test_materialised_corpus_matches_expectations():
    frame = pd.read_parquet(REAL_OUTPUT)
    assert len(frame) == 100_768
    assert frame["record_id"].nunique() == 100_768
    for forbidden in SCRIPT.FORBIDDEN_OUTPUT_COLUMNS:
        assert forbidden not in frame.columns
    # All five banks represented.
    assert len(frame["bank"].dropna().unique()) == 5


@pytest.mark.skipif(not REAL_REPORT.is_file(), reason="materialisation report absent")
def test_materialisation_report_is_consistent():
    report = json.loads(REAL_REPORT.read_text(encoding="utf-8"))
    assert report["output_row_count"] == 100_768
    assert report["unique_record_count"] == 100_768
    assert report["duplicate_record_count"] == 0
    assert report["strict_subset_verified"] is True
    assert report["rule_counts_match_expected"] is True
    assert report["rule_counts_sum"] == 100_768
    assert report["source_sha256"] != report["output_sha256"]
