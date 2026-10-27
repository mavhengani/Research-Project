"""Tests for the combined gold sample-plan builder (Requirements Section 10).

Uses small synthetic fixtures for both sources (reusing the same shapes as
``test_sa_sampling.py`` / ``test_new_pipeline_sampling.py``) so the suite is
fast and hermetic, and does not depend on the real materialised corpora being
present.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from banking_tasci.data.gold_sample_plan import (  # noqa: E402
    ANNOTATION_RECORD_FIELDS,
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    PIPELINE_VERSION,
    REGION_TARGETS,
    SOURCE_TARGETS,
    SOUTH_AFRICA_TWEET,
    TOTAL_TARGET,
    build_combined_sample_plan,
    build_gold_sample_plan_manifest,
    to_annotation_records,
    write_jsonl,
)
from banking_tasci.data.manifest import sha256_file  # noqa: E402


def _make_sa_corpus(tmp_path: Path, per_bank: int = 150) -> Path:
    rows = []
    banks = ["fnb", "absa", "nedbank", "standard_bank", "capitec"]
    for bank in banks:
        for i in range(per_bank):
            text = "my bank card payment failed again " * (1 + (i % 6))
            rows.append(
                {
                    "record_id": f"sa_{bank}_{i:04d}",
                    "source": "south_african_bank_tweets",
                    "region": "south_africa",
                    "bank": bank,
                    "text": text.strip(),
                    "previous_text": "[NO_CONTEXT]",
                    "context_available": False,
                    "created_at": f"{2018 + (i % 5)}-06-15",
                    "near_dup_group_id": None,
                    "near_dup_flag": False,
                    "thread_id": None,
                    "rating": None,
                    "title": None,
                }
            )
    path = tmp_path / "sa_candidates.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _make_international_source(tmp_path: Path, n_tweets: int = 400, n_reviews: int = 400) -> Path:
    rows = []
    for i in range(n_tweets):
        text = "bank app issue " * (1 + (i % 7))
        rows.append(
            {
                "record_id": f"tw{i:04d}",
                "source": "international_bank_tweets",
                "region": "international",
                "bank": None,
                "rating": None,
                "title": None,
                "text": text.strip(),
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "thread_id": None,
                "created_at": None,
                "split": None,
            }
        )
    for i in range(n_reviews):
        sentences = 1 + (i % 5)
        text = " ".join(f"The service was notable in respect {j}." for j in range(sentences))
        rows.append(
            {
                "record_id": f"rv{i:04d}",
                "source": "bank_reviews",
                "region": "international",
                "bank": f"bank_{i % 4}",
                "rating": [0.5, 2.0, 3.0, 4.0, 5.0][i % 5],
                "title": "t",
                "text": text,
                "previous_text": "[NO_CONTEXT]",
                "context_available": i % 3 == 0,
                "thread_id": None,
                "created_at": "2021-03-04",
                "split": None,
            }
        )
    path = tmp_path / "prepared.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def sa_source(tmp_path) -> Path:
    return _make_sa_corpus(tmp_path)


@pytest.fixture
def intl_source(tmp_path) -> Path:
    return _make_international_source(tmp_path)


@pytest.fixture
def plan(sa_source, intl_source):
    return build_combined_sample_plan(sa_source, intl_source, seed=42)


# ---------------------------------------------------------------------------
# Counts and allocation
# ---------------------------------------------------------------------------


def test_total_target_is_1000():
    assert TOTAL_TARGET == 1000


def test_exactly_1000_records(plan):
    records, _ = plan
    assert len(records) == 1000


def test_exactly_1000_unique_canonical_ids(plan):
    records, _ = plan
    ids = [r["record_id"] for r in records]
    assert len(set(ids)) == 1000


def test_source_allocation(plan):
    records, _ = plan
    from collections import Counter

    counts = Counter(r["source"] for r in records)
    assert counts[SOUTH_AFRICA_TWEET] == 500
    assert counts[INTERNATIONAL_TWEET] == 250
    assert counts[INTERNATIONAL_REVIEW] == 250


def test_regional_allocation(plan):
    records, _ = plan
    from collections import Counter

    counts = Counter(r["region"] for r in records)
    assert counts["south_africa"] == 500
    assert counts["international"] == 500


def test_report_matches_targets(plan):
    _, report = plan
    assert report.total == 1000
    assert report.unique_record_count == 1000
    assert report.by_source == dict(sorted(SOURCE_TARGETS.items()))
    assert report.by_region == dict(sorted(REGION_TARGETS.items()))
    assert report.cross_source_collision_count == 0
    assert report.pipeline_version == PIPELINE_VERSION
    assert report.seed == 42


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_stable_source_record_ids_preserved(plan):
    records, _ = plan
    for record in records:
        assert record["record_id"].endswith("::" + str(record["source_record_id"]))


def test_deterministic_namespaced_ids(plan):
    records, _ = plan
    for record in records:
        assert record["record_id"] == f"{record['source']}::{record['source_record_id']}"


def test_no_cross_source_id_collision(sa_source, intl_source):
    records, report = build_combined_sample_plan(sa_source, intl_source, seed=42)
    source_id_sources: dict[str, set] = {}
    for r in records:
        source_id_sources.setdefault(str(r["source_record_id"]), set()).add(r["source"])
    collisions = {k: v for k, v in source_id_sources.items() if len(v) > 1}
    assert collisions == {}
    assert report.cross_source_collision_count == 0


def test_deterministic_under_seed_42(sa_source, intl_source):
    first, _ = build_combined_sample_plan(sa_source, intl_source, seed=42)
    second, _ = build_combined_sample_plan(sa_source, intl_source, seed=42)
    assert [r["record_id"] for r in first] == [r["record_id"] for r in second]


# ---------------------------------------------------------------------------
# Provenance preservation
# ---------------------------------------------------------------------------


def test_source_checksums_preserved(sa_source, intl_source):
    _, report = build_combined_sample_plan(sa_source, intl_source, seed=42)
    assert report.south_africa_source_sha256 == sha256_file(sa_source)
    assert report.international_source_sha256 == sha256_file(intl_source)


def test_selection_reasons_preserved(plan):
    records, _ = plan
    assert all(r["selection_reason"] for r in records)


def test_source_inputs_remain_unchanged(sa_source, intl_source):
    before_sa = sha256_file(sa_source)
    before_intl = sha256_file(intl_source)
    build_combined_sample_plan(sa_source, intl_source, seed=42)
    assert sha256_file(sa_source) == before_sa
    assert sha256_file(intl_source) == before_intl


# ---------------------------------------------------------------------------
# No task labels in the plan view
# ---------------------------------------------------------------------------


def test_plan_records_carry_no_task_label_fields(plan):
    records, _ = plan
    forbidden = {"primary_intent", "public_warning", "opinions", "annotation_status"}
    for record in records:
        assert forbidden.isdisjoint(record.keys())


# ---------------------------------------------------------------------------
# Annotation (label-hidden) view
# ---------------------------------------------------------------------------


def test_annotation_records_have_required_fields(plan):
    records, _ = plan
    annotation_records = to_annotation_records(records)
    assert len(annotation_records) == 1000
    for record in annotation_records:
        assert set(record.keys()) == set(ANNOTATION_RECORD_FIELDS)


def test_annotation_records_are_label_hidden(plan):
    records, _ = plan
    for record in to_annotation_records(records):
        assert record["primary_intent"] is None
        assert record["public_warning"] is None
        assert record["opinions"] == []
        assert record["annotation_status"] == "not_started"
        assert record["annotation_version"] == PIPELINE_VERSION


def test_annotation_records_never_carry_selection_reason(plan):
    records, _ = plan
    for record in to_annotation_records(records):
        assert "selection_reason" not in record


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_contains_required_fields(plan):
    records, report = plan
    manifest = build_gold_sample_plan_manifest(report)
    for key in (
        "total",
        "by_source",
        "by_region",
        "unique_record_count",
        "south_africa_source_sha256",
        "international_source_sha256",
        "seed",
        "pipeline_version",
        "git_commit",
    ):
        assert key in manifest
    assert manifest["total"] == 1000


# ---------------------------------------------------------------------------
# Dry-run / write behaviour
# ---------------------------------------------------------------------------


def test_write_jsonl_round_trips(tmp_path, plan):
    records, _ = plan
    out = tmp_path / "gold_sample_plan.jsonl"
    write_jsonl(records, out)
    assert out.is_file()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1000


def test_building_plan_alone_writes_nothing(tmp_path, sa_source, intl_source):
    before = set(tmp_path.iterdir())
    build_combined_sample_plan(sa_source, intl_source, seed=42)
    after = set(tmp_path.iterdir())
    assert before == after


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_raises_when_sa_source_cannot_satisfy_total(tmp_path, intl_source):
    small_sa = _make_sa_corpus(tmp_path, per_bank=10)
    with pytest.raises(Exception):
        build_combined_sample_plan(small_sa, intl_source, seed=42)
