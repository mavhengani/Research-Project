"""Tests for the `new_pipeline_v1` source-manifest generator.

The central property under test is the **evidentiary discipline** required by
NEW_PIPELINE_REQUIREMENTS.md Migration Principle 6 ("Do not fabricate
annotations, identifiers, context, or metrics") and Section 36 ("Assumptions
are not evidence"):

    When the observed row count does not match the expected count, the
    manifest must report REQUIRES_DATA_CONFIRMATION and leave the data
    untouched. It must never sample, truncate, or filter to reach a target.

This matters because the South African expected count (100,768) does not match
the available data (2,250,776) - see gap-analysis finding R3. These tests lock
in the behaviour that makes that mismatch visible rather than silently
"resolved".

All tests build small synthetic CSV/parquet fixtures in tmp_path. None reads a
real repository data file, so the suite stays fast and hermetic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.manifest import (  # noqa: E402
    MANIFEST_STATUSES,
    STATUS_FILE_MISSING,
    STATUS_INVALID_SCHEMA,
    STATUS_MISMATCH,
    STATUS_PRIVACY_FAILURE,
    STATUS_REQUIRES_DATA_CONFIRMATION,
    STATUS_SOURCE_MISSING,
    STATUS_VERIFIED,
    build_manifest,
    sha256_file,
    write_manifest,
)

PIPELINE_VERSION = "new_pipeline_v1"


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "record_id": [f"r{i}" for i in range(10)],
            "bank": ["FNB"] * 3 + ["Absa"] * 3 + ["Nedbank"] * 4,
            "text": [f"banking feedback {i}" for i in range(10)],
            "created_at": ["2021-05-01"] * 6 + ["2022-07-01"] * 4,
            "near_dup_group_id": ["g1", "g1", None, None, None, None, "g2", "g2", None, None],
            "customer_feedback_candidate": [True] * 7 + [False] * 3,
        }
    )


@pytest.fixture
def csv_source(tmp_path: Path, frame: pd.DataFrame) -> Path:
    path = tmp_path / "source.csv"
    frame.to_csv(path, index=False)
    return path


@pytest.fixture
def parquet_source(tmp_path: Path, frame: pd.DataFrame) -> Path:
    path = tmp_path / "source.parquet"
    frame.to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Count verification: the core evidentiary behaviour
# ---------------------------------------------------------------------------


def test_matching_count_is_verified(csv_source):
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=10
    )
    assert result.status == STATUS_VERIFIED
    assert result.row_count == 10
    assert result.row_count_difference == 0


def test_mismatched_count_is_reported_as_mismatch(csv_source):
    """An unexplained count mismatch is MISMATCH.

    Phase 1 reported every mismatch as REQUIRES_DATA_CONFIRMATION. The Phase 2
    vocabulary distinguishes an unexplained mismatch (MISMATCH) from one
    accompanied by a documented derived-selection process
    (REQUIRES_DATA_CONFIRMATION). Neither is ever VERIFIED.
    """
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=100_768
    )
    assert result.status == STATUS_MISMATCH
    assert result.count_status == STATUS_MISMATCH
    assert result.row_count == 10
    assert result.expected_row_count == 100_768
    assert result.row_count_difference == 10 - 100_768


def test_mismatch_with_derived_selection_requires_data_confirmation(csv_source):
    """A mismatch explained by a reproducible derived selection is
    REQUIRES_DATA_CONFIRMATION - understood, but still not VERIFIED, because
    the raw file does not itself hold the expected row count."""
    result = build_manifest(
        csv_source,
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=100_768,
        derived_selection={
            "method": "v2_evidence_based_candidate_filter",
            "generator": "scripts/resample_south_africa_v2.py",
            "observed_selected_count": 100_768,
        },
    )
    assert result.status == STATUS_REQUIRES_DATA_CONFIRMATION
    assert result.count_status == STATUS_REQUIRES_DATA_CONFIRMATION
    assert result.row_count == 10  # still the true observed raw count
    assert result.derived_selection["observed_selected_count"] == 100_768


def test_mismatch_reports_both_counts_in_notes(csv_source):
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=999
    )
    joined = " ".join(result.notes)
    assert "999" in joined
    assert "10" in joined
    assert "not corrected" in joined.lower()


def test_mismatch_does_not_alter_the_source_file(csv_source):
    """The generator must be strictly read-only."""
    before_bytes = csv_source.read_bytes()
    before_hash = sha256_file(csv_source)

    build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=100_768
    )

    assert csv_source.read_bytes() == before_bytes
    assert sha256_file(csv_source) == before_hash


def test_mismatch_never_reports_the_expected_count_as_observed(csv_source):
    """Guards against the specific failure of coercing data to fit a target."""
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=100_768
    )
    assert result.row_count != result.expected_row_count
    assert result.row_count == 10  # the true observed value


def test_no_expected_count_is_verified_as_description_only(csv_source):
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=None
    )
    assert result.status == STATUS_VERIFIED
    assert result.expected_row_count is None
    assert result.row_count_difference is None


def test_candidate_flag_mismatch_is_flagged_as_insufficient(csv_source):
    """A candidate flag that does not reproduce the expected count must be
    called out explicitly (the concrete shape of finding R3)."""
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=100_768
    )
    assert result.candidate_status["true_count"] == 7
    joined = " ".join(result.notes)
    assert "does not define the required corpus" in joined


# ---------------------------------------------------------------------------
# Missing files
# ---------------------------------------------------------------------------


def test_missing_file_is_reported(tmp_path):
    result = build_manifest(
        tmp_path / "absent.parquet",
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=100_768,
    )
    assert result.status == STATUS_FILE_MISSING
    assert result.exists is False
    assert result.row_count is None
    assert result.sha256 is None


# ---------------------------------------------------------------------------
# Recorded fields (this session's Step 6 field list)
# ---------------------------------------------------------------------------


def test_manifest_records_all_required_fields(csv_source):
    result = build_manifest(
        csv_source,
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=10,
        source="test_source",
        region="test_region",
        generation_command="pytest",
    )

    assert result.source_file.endswith("source.csv")       # source file
    assert result.row_count == 10                           # row count
    assert result.sha256                                    # checksum
    assert result.schema                                    # schema
    assert result.source == "test_source"                   # source
    assert result.region == "test_region"                   # region
    assert result.bank_distribution                         # bank distribution
    assert result.year_distribution                         # year distribution
    assert result.duplicate_group_coverage                  # duplicate-group coverage
    assert result.privacy_status                            # privacy status
    assert result.candidate_status                          # candidate status
    assert result.generation_command == "pytest"            # generation command
    assert result.pipeline_version == PIPELINE_VERSION      # pipeline version
    assert result.generated_at
    assert result.git_commit


def test_bank_distribution_is_accurate(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.bank_distribution == {"Absa": 3, "FNB": 3, "Nedbank": 4}


def test_year_distribution_is_derived_from_dates(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.year_distribution == {"2021": 6, "2022": 4}


def test_duplicate_group_coverage_is_accurate(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    coverage = result.duplicate_group_coverage
    assert coverage["distinct_groups"] == 2
    assert coverage["records_with_group"] == 4
    assert coverage["records_without_group"] == 6


def test_candidate_status_is_accurate(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.candidate_status["true_count"] == 7
    assert result.candidate_status["false_or_null_count"] == 3


def test_checksum_matches_independent_hash(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.sha256 == sha256_file(csv_source)


def test_checksum_changes_when_content_changes(tmp_path, frame):
    path = tmp_path / "mutable.csv"
    frame.to_csv(path, index=False)
    first = build_manifest(path, pipeline_version=PIPELINE_VERSION).sha256

    frame.iloc[0, frame.columns.get_loc("text")] = "changed"
    frame.to_csv(path, index=False)
    second = build_manifest(path, pipeline_version=PIPELINE_VERSION).sha256

    assert first != second


def test_missing_optional_columns_are_noted(tmp_path):
    pd.DataFrame({"record_id": ["a"], "text": ["hello"]}).to_csv(
        tmp_path / "sparse.csv", index=False
    )
    result = build_manifest(tmp_path / "sparse.csv", pipeline_version=PIPELINE_VERSION)
    joined = " ".join(result.notes)
    assert "bank" in joined
    assert result.bank_distribution is None
    assert result.candidate_status is None


# ---------------------------------------------------------------------------
# Parquet support
# ---------------------------------------------------------------------------


def test_parquet_row_count_and_schema(parquet_source):
    result = build_manifest(
        parquet_source, pipeline_version=PIPELINE_VERSION, expected_row_count=10
    )
    assert result.status == STATUS_VERIFIED
    assert result.row_count == 10
    assert "record_id" in result.schema
    assert "customer_feedback_candidate" in result.schema


def test_parquet_and_csv_agree_on_summaries(csv_source, parquet_source):
    from_csv = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    from_parquet = build_manifest(parquet_source, pipeline_version=PIPELINE_VERSION)
    assert from_csv.row_count == from_parquet.row_count
    assert from_csv.bank_distribution == from_parquet.bank_distribution
    assert from_csv.candidate_status["true_count"] == (
        from_parquet.candidate_status["true_count"]
    )


def test_unsupported_extension_requires_confirmation(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a dataset", encoding="utf-8")
    result = build_manifest(path, pipeline_version=PIPELINE_VERSION)
    assert result.status == STATUS_REQUIRES_DATA_CONFIRMATION
    assert result.sha256  # still checksummed


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def test_write_manifest_produces_valid_json(tmp_path, csv_source):
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=10
    )
    out = write_manifest(result, tmp_path / "nested" / "manifest.json")

    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_VERIFIED
    assert payload["pipeline_version"] == PIPELINE_VERSION
    assert payload["row_count"] == 10
    assert payload["sha256"] == result.sha256
    assert "environment" in payload


def test_written_manifest_preserves_mismatch_status(tmp_path, csv_source):
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=100_768
    )
    out = write_manifest(result, tmp_path / "manifest.json")
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["status"] == STATUS_MISMATCH
    assert payload["row_count"] == 10
    assert payload["expected_row_count"] == 100_768
    assert payload["row_count_difference"] == 10 - 100_768


# ---------------------------------------------------------------------------
# Phase 2 extension: status vocabulary
# ---------------------------------------------------------------------------


def test_status_vocabulary_is_complete():
    """Every status required by the Phase 2 brief must exist."""
    for status in (
        "VERIFIED",
        "MISMATCH",
        "REQUIRES_DATA_CONFIRMATION",
        "SOURCE_MISSING",
        "INVALID_SCHEMA",
        "PRIVACY_FAILURE",
    ):
        assert status in MANIFEST_STATUSES


def test_file_missing_alias_matches_source_missing():
    """FILE_MISSING is retained as a backwards-compatible alias."""
    assert STATUS_FILE_MISSING == STATUS_SOURCE_MISSING == "SOURCE_MISSING"


def test_missing_file_reports_source_missing(tmp_path):
    result = build_manifest(
        tmp_path / "absent.parquet",
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=100_768,
    )
    assert result.status == STATUS_SOURCE_MISSING
    assert result.count_status == STATUS_SOURCE_MISSING


def test_required_columns_missing_produces_invalid_schema(tmp_path):
    pd.DataFrame({"record_id": ["a"], "text": ["hello"]}).to_csv(
        tmp_path / "sparse.csv", index=False
    )
    result = build_manifest(
        tmp_path / "sparse.csv",
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=1,
        required_columns=("record_id", "text", "region", "source"),
    )
    assert result.status == STATUS_INVALID_SCHEMA
    joined = " ".join(result.notes)
    assert "region" in joined and "source" in joined


def test_satisfied_required_columns_do_not_trigger_invalid_schema(csv_source):
    result = build_manifest(
        csv_source,
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=10,
        required_columns=("record_id", "text", "bank"),
    )
    assert result.status == STATUS_VERIFIED


def test_raw_username_column_produces_privacy_failure(tmp_path):
    """A surviving raw handle column must never be reported VERIFIED."""
    pd.DataFrame(
        {
            "record_id": ["a", "b"],
            "text": ["feedback one", "feedback two"],
            "username": ["@alice", "@bob"],
        }
    ).to_csv(tmp_path / "leaky.csv", index=False)

    result = build_manifest(
        tmp_path / "leaky.csv",
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=2,
    )
    assert result.status == STATUS_PRIVACY_FAILURE
    # The count itself matched - privacy outranks the count verdict.
    assert result.count_status == STATUS_VERIFIED
    assert result.privacy_status["username_column_present"] is True


def test_privacy_failure_outranks_count_match(tmp_path):
    """Explicitly pins precedence: a privacy failure is never VERIFIED even
    when the observed count equals the expected count."""
    pd.DataFrame(
        {"record_id": ["a"], "text": ["x"], "screen_name": ["@a"]}
    ).to_csv(tmp_path / "leaky2.csv", index=False)
    result = build_manifest(
        tmp_path / "leaky2.csv", pipeline_version=PIPELINE_VERSION, expected_row_count=1
    )
    assert result.status != STATUS_VERIFIED
    assert result.status == STATUS_PRIVACY_FAILURE


# ---------------------------------------------------------------------------
# Phase 2 extension: new recorded fields
# ---------------------------------------------------------------------------


def test_unique_and_duplicate_record_counts(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.unique_record_count == 10
    assert result.duplicate_record_count == 0


def test_duplicate_record_ids_are_counted_and_noted(tmp_path):
    pd.DataFrame(
        {
            "record_id": ["a", "a", "b"],
            "text": ["one", "two", "three"],
        }
    ).to_csv(tmp_path / "dups.csv", index=False)
    result = build_manifest(tmp_path / "dups.csv", pipeline_version=PIPELINE_VERSION)
    assert result.unique_record_count == 2
    assert result.duplicate_record_count == 1
    assert any("duplicate" in note.lower() for note in result.notes)


def test_null_counts_are_recorded(tmp_path):
    pd.DataFrame(
        {"record_id": ["a", "b"], "bank": ["FNB", None], "text": ["x", "y"]}
    ).to_csv(tmp_path / "nulls.csv", index=False)
    result = build_manifest(tmp_path / "nulls.csv", pipeline_version=PIPELINE_VERSION)
    assert result.null_counts["bank"] == 1
    assert result.null_counts["record_id"] == 0


def test_source_and_region_distributions(tmp_path):
    pd.DataFrame(
        {
            "record_id": ["a", "b", "c"],
            "text": ["x", "y", "z"],
            "source": ["bank_reviews", "bank_reviews", "international_bank_tweets"],
            "region": ["international"] * 3,
        }
    ).to_csv(tmp_path / "srcreg.csv", index=False)
    result = build_manifest(tmp_path / "srcreg.csv", pipeline_version=PIPELINE_VERSION)
    assert result.source_distribution == {
        "bank_reviews": 2,
        "international_bank_tweets": 1,
    }
    assert result.region_distribution == {"international": 3}


def test_context_availability_is_recorded(tmp_path):
    pd.DataFrame(
        {
            "record_id": ["a", "b", "c"],
            "text": ["x", "y", "z"],
            "context_available": [True, False, False],
        }
    ).to_csv(tmp_path / "ctx.csv", index=False)
    result = build_manifest(tmp_path / "ctx.csv", pipeline_version=PIPELINE_VERSION)
    assert result.context_availability["context_available_true"] == 1
    assert result.context_availability["context_available_false"] == 2


def test_review_group_coverage_is_recorded(tmp_path):
    pd.DataFrame(
        {
            "record_id": ["a", "b", "c", "d"],
            "text": ["w", "x", "y", "z"],
            "review_id": ["r1", "r1", "r2", None],
        }
    ).to_csv(tmp_path / "rev.csv", index=False)
    result = build_manifest(tmp_path / "rev.csv", pipeline_version=PIPELINE_VERSION)
    coverage = result.review_group_coverage
    assert coverage["distinct_groups"] == 2
    assert coverage["records_with_group"] == 3
    assert coverage["records_without_group"] == 1


def test_git_commit_and_timestamp_are_recorded(csv_source):
    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.git_commit
    assert result.generated_at.endswith("Z")


# ---------------------------------------------------------------------------
# Anti-coercion invariants (re-asserted against the extended generator)
# ---------------------------------------------------------------------------


def test_expected_is_never_copied_into_observed_fields(csv_source):
    """Guards the specific failure mode of writing an expectation as an
    observation."""
    result = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=100_768
    )
    assert result.row_count == 10
    assert result.unique_record_count == 10
    assert result.expected_row_count == 100_768
    assert result.row_count != result.expected_row_count


def test_derived_selection_does_not_overwrite_observed_count(csv_source):
    """Even with a derived-selection record present, the observed raw count
    must remain the true file row count."""
    result = build_manifest(
        csv_source,
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=100_768,
        derived_selection={"observed_selected_count": 100_768},
    )
    assert result.row_count == 10
    assert result.status != STATUS_VERIFIED


def test_mismatch_cannot_be_verified_under_any_option(csv_source):
    """No combination of options may turn a count mismatch into VERIFIED."""
    for kwargs in (
        {},
        {"derived_selection": {"method": "x"}},
        {"required_columns": ("record_id", "text")},
        {"source": "s", "region": "r"},
    ):
        result = build_manifest(
            csv_source,
            pipeline_version=PIPELINE_VERSION,
            expected_row_count=100_768,
            **kwargs,
        )
        assert result.status != STATUS_VERIFIED, kwargs


def test_manifest_is_deterministic_apart_from_timestamp(csv_source):
    """Two runs over an unchanged source must agree on every substantive
    field; only the generation timestamp may differ."""
    first = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=10
    ).to_dict()
    second = build_manifest(
        csv_source, pipeline_version=PIPELINE_VERSION, expected_row_count=10
    ).to_dict()

    for volatile in ("generated_at", "generation_command"):
        first.pop(volatile, None)
        second.pop(volatile, None)
    assert first == second


def test_source_bytes_unchanged_by_extended_generator(csv_source):
    before = csv_source.read_bytes()
    before_hash = sha256_file(csv_source)
    build_manifest(
        csv_source,
        pipeline_version=PIPELINE_VERSION,
        expected_row_count=100_768,
        required_columns=("record_id", "text"),
        derived_selection={"method": "x"},
    )
    assert csv_source.read_bytes() == before
    assert sha256_file(csv_source) == before_hash


# ---------------------------------------------------------------------------
# Git provenance marker
# ---------------------------------------------------------------------------


def test_no_commit_marker_is_an_explicit_token():
    """Requirements Section 25: a provenance gap must be machine-detectable,
    and a commit hash must never be invented."""
    from banking_tasci.data.manifest import NO_COMMIT_MARKER, git_commit

    assert NO_COMMIT_MARKER == "UNKNOWN_NO_COMMIT"
    commit = git_commit()
    # Either the explicit marker or a real 40-character hash - nothing else.
    assert commit == NO_COMMIT_MARKER or len(commit) == 40


def test_manifest_records_the_commit_marker(csv_source):
    from banking_tasci.data.manifest import NO_COMMIT_MARKER

    result = build_manifest(csv_source, pipeline_version=PIPELINE_VERSION)
    assert result.git_commit == NO_COMMIT_MARKER or len(result.git_commit) == 40


# ---------------------------------------------------------------------------
# Combined relevant-corpus manifest
# ---------------------------------------------------------------------------


def _load_combined_cli():
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "combined_manifest_cli",
        root / "scripts" / "build_combined_relevant_manifest.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMBINED_CLI = _load_combined_cli()


def _write_manifest_file(path: Path, **overrides) -> Path:
    payload = {
        "status": STATUS_VERIFIED,
        "pipeline_version": PIPELINE_VERSION,
        "row_count": 100_768,
        "sha256": "a" * 64,
        "region": "south_africa",
        "source": "south_african_bank_tweets",
        "source_file": "x.parquet",
        "unique_record_count": 100_768,
        "duplicate_record_count": 0,
        "privacy_status": {"username_column_present": False},
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_namespaced_identifier_format():
    assert (
        COMBINED_CLI.namespaced_id("south_africa", "abc123")
        == "south_africa::abc123"
    )
    assert (
        COMBINED_CLI.namespaced_id("international_tweet", "t1")
        == "international_tweet::t1"
    )


def test_namespacing_preserves_the_original_identifier():
    """The original must survive verbatim after the separator."""
    original = "c651f8100768331e"
    namespaced = COMBINED_CLI.namespaced_id("south_africa", original)
    assert namespaced.endswith(original)
    assert namespaced.split(COMBINED_CLI.NAMESPACE_SEPARATOR, 1)[1] == original


def test_namespacing_prevents_collisions_between_sources():
    """The same raw identifier in both corpora must not collide."""
    shared = "same_id"
    sa = COMBINED_CLI.namespaced_id(COMBINED_CLI.NAMESPACE_SOUTH_AFRICA, shared)
    intl = COMBINED_CLI.namespaced_id(COMBINED_CLI.NAMESPACE_INTL_TWEET, shared)
    assert sa != intl


def test_combined_manifest_written_when_both_sources_verified(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json")
    intl = _write_manifest_file(
        tmp_path / "intl.json",
        row_count=10_847,
        unique_record_count=10_847,
        region="international",
        source="international_bank_tweets+bank_reviews",
    )
    out = tmp_path / "combined.json"

    rc = COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    assert rc == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_VERIFIED
    assert payload["counts"]["combined_relevant"] == 111_615
    assert payload["counts"]["counts_reconcile"] is True
    assert payload["construction"] == "by_reference"


def test_combined_manifest_refuses_unverified_source(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json", status=STATUS_MISMATCH)
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"

    rc = COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    assert rc == 2
    assert not out.exists()


def test_combined_manifest_refuses_wrong_counts(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json", row_count=99_999)
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"

    rc = COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    assert rc == 2
    assert not out.exists()


def test_combined_manifest_refuses_privacy_failure(tmp_path):
    sa = _write_manifest_file(
        tmp_path / "sa.json", privacy_status={"username_column_present": True}
    )
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"

    rc = COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    assert rc == 2
    assert not out.exists()


def test_combined_manifest_refuses_pipeline_version_mismatch(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json", pipeline_version="legacy")
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"

    rc = COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    assert rc == 2


def test_combined_manifest_refuses_invalid_region(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json", region="atlantis")
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    rc = COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(tmp_path / "c.json"),
    ])
    assert rc == 2


def test_combined_manifest_records_identifier_policy(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json")
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"
    COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    policy = json.loads(out.read_text(encoding="utf-8"))["identifier_policy"]
    assert policy["original_identifier_field"] == "source_record_id"
    assert policy["original_identifier_preserved"] is True
    assert policy["separator"] == "::"
    assert len(policy["namespaces"]) == 3


def test_combined_manifest_records_source_checksums(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json", sha256="b" * 64)
    intl = _write_manifest_file(
        tmp_path / "intl.json",
        row_count=10_847,
        region="international",
        sha256="c" * 64,
    )
    out = tmp_path / "combined.json"
    COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    sources = json.loads(out.read_text(encoding="utf-8"))["sources"]
    assert sources["south_africa"]["source_sha256"] == "b" * 64
    assert sources["international"]["source_sha256"] == "c" * 64


def test_combined_manifest_notes_strict_corpus_is_not_built(tmp_path):
    sa = _write_manifest_file(tmp_path / "sa.json")
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"
    COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    note = json.loads(out.read_text(encoding="utf-8"))["downstream_note"].lower()
    assert "110,615" in note or "110615" in note
    assert "do not exist yet" in note or "cannot be built" in note


def test_combined_manifest_warns_about_missing_commit(tmp_path):
    from banking_tasci.data.manifest import NO_COMMIT_MARKER

    sa = _write_manifest_file(tmp_path / "sa.json")
    intl = _write_manifest_file(
        tmp_path / "intl.json", row_count=10_847, region="international"
    )
    out = tmp_path / "combined.json"
    COMBINED_CLI.main([
        "--south-africa-manifest", str(sa),
        "--international-manifest", str(intl),
        "--output", str(out),
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    if payload["git_commit"] == NO_COMMIT_MARKER:
        assert "provenance_warning" in payload
