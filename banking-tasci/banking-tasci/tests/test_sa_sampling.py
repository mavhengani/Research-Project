"""Tests for the South African `new_pipeline_v1` gold sampler.

Covers Requirements Section 7.1 for the South African source: 500 records,
100 per bank, deterministic under seed 42, no replacement, group integrity,
source-specific quantile bands, rule/year coverage reporting, label-hidden
output, and write authorisation.

Synthetic fixtures are used throughout except for two explicitly-marked
integration tests, so the suite stays fast and does not depend on the 12 MB
materialised corpus being present.
"""
from __future__ import annotations

import importlib.util
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

from banking_tasci.data.south_africa_sampler import (  # noqa: E402
    BANK_ALIASES,
    CANONICAL_BANKS,
    DEFAULT_SEED,
    PER_BANK_TARGET,
    TARGET_TOTAL,
    assign_length_band,
    build_selection_manifest,
    compute_length_bands,
    dry_run,
    normalise_bank,
    sample_south_africa,
    to_label_hidden_records,
)

REAL_CORPUS = (
    _PROJECT_ROOT
    / "data"
    / "processed"
    / "new_pipeline_v1"
    / "south_africa_candidates_v2.parquet"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "sa_gold_cli", _PROJECT_ROOT / "scripts" / "sample_south_africa_gold.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = _load_cli()


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------


def _make_corpus(tmp_path: Path, per_bank: int = 300) -> Path:
    rows = []
    banks = ["fnb", "absa", "nedbank", "standard_bank", "capitec"]
    for bank_index, bank in enumerate(banks):
        for i in range(per_bank):
            # Vary length so quantile bands are meaningful.
            text = "my bank card payment failed again " * (1 + (i % 6))
            rows.append(
                {
                    "record_id": f"{bank}_{i:04d}",
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


@pytest.fixture
def corpus(tmp_path) -> Path:
    return _make_corpus(tmp_path)


# ---------------------------------------------------------------------------
# Constants and bank normalisation
# ---------------------------------------------------------------------------


def test_targets_match_requirements():
    assert TARGET_TOTAL == 500
    assert PER_BANK_TARGET == 100
    assert len(CANONICAL_BANKS) * PER_BANK_TARGET == TARGET_TOTAL


def test_canonical_banks_match_requirements():
    assert set(CANONICAL_BANKS) == {
        "FNB", "Absa", "Nedbank", "Standard Bank", "Capitec"
    }


def test_default_seed_is_42():
    assert DEFAULT_SEED == 42


@pytest.mark.parametrize(
    "stored,expected",
    [
        ("fnb", "FNB"),
        ("absa", "Absa"),
        ("nedbank", "Nedbank"),
        ("standard_bank", "Standard Bank"),
        ("standardbank", "Standard Bank"),
        ("capitec", "Capitec"),
        ("FNB", "FNB"),
        (None, "unknown"),
    ],
)
def test_bank_normalisation(stored, expected):
    assert normalise_bank(stored) == expected


def test_every_canonical_bank_has_an_alias():
    assert set(BANK_ALIASES.values()) == set(CANONICAL_BANKS)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_under_seed_42(corpus):
    first, _ = sample_south_africa(corpus, seed=42)
    second, _ = sample_south_africa(corpus, seed=42)
    assert list(first["record_id"]) == list(second["record_id"])


def test_different_seeds_differ(corpus):
    first, _ = sample_south_africa(corpus, seed=42)
    second, _ = sample_south_africa(corpus, seed=7)
    assert list(first["record_id"]) != list(second["record_id"])


def test_global_rng_is_untouched(corpus):
    import random

    import numpy as np

    random.seed(99)
    np.random.seed(99)
    py_before = random.random()
    np_before = float(np.random.random())

    random.seed(99)
    np.random.seed(99)
    sample_south_africa(corpus, seed=42)
    assert random.random() == py_before
    assert float(np.random.random()) == np_before


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def test_total_allocation_is_500(corpus):
    selected, report = sample_south_africa(corpus)
    assert len(selected) == 500
    assert report.selected_total == 500


def test_allocation_is_100_per_bank(corpus):
    _, report = sample_south_africa(corpus)
    for bank in CANONICAL_BANKS:
        assert report.selected_by_bank[bank] == 100, bank


def test_requested_by_bank_is_reported(corpus):
    _, report = sample_south_africa(corpus)
    assert report.requested_by_bank == {bank: 100 for bank in CANONICAL_BANKS}


def test_no_replacement(corpus):
    selected, _ = sample_south_africa(corpus)
    assert selected["record_id"].nunique() == len(selected)
    assert len(set(selected.index)) == len(selected)


def test_manifest_declares_no_replacement(corpus):
    _, report = sample_south_africa(corpus)
    assert build_selection_manifest(report)["replacement_sampling"] is False


# ---------------------------------------------------------------------------
# Shortages and missing banks
# ---------------------------------------------------------------------------


def test_bank_shortage_is_reported(tmp_path):
    path = _make_corpus(tmp_path, per_bank=20)
    selected, report = sample_south_africa(path)
    assert report.shortages
    banks_short = {e.get("bank") for e in report.shortages if e.get("bank")}
    assert banks_short  # at least one bank fell short
    assert report.can_select_full_per_bank is False
    # Still no duplicates despite the shortfall.
    assert selected["record_id"].nunique() == len(selected)


def test_missing_bank_is_reported(tmp_path):
    """A bank with no records must be reported, not silently skipped."""
    rows = []
    for i in range(200):
        rows.append(
            {
                "record_id": f"fnb_{i:04d}",
                "source": "south_african_bank_tweets",
                "region": "south_africa",
                "bank": "fnb",
                "text": "my bank card payment failed again and again",
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "created_at": "2021-01-01",
                "near_dup_group_id": None,
                "near_dup_flag": False,
                "thread_id": None,
                "rating": None,
                "title": None,
            }
        )
    path = tmp_path / "one_bank.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)

    _, report = sample_south_africa(path)
    missing = {
        e["bank"] for e in report.shortages
        if e.get("available") == 0
    }
    assert "Absa" in missing
    assert "Capitec" in missing


def test_shortage_reason_mentions_prohibited_replacement(tmp_path):
    path = _make_corpus(tmp_path, per_bank=10)
    _, report = sample_south_africa(path)
    joined = " ".join(e.get("reason", "") for e in report.shortages)
    assert "replacement" in joined.lower()


def test_no_shortage_when_sufficient(corpus):
    _, report = sample_south_africa(corpus)
    assert report.shortages == []
    assert report.can_select_full_total is True
    assert report.can_select_full_per_bank is True


# ---------------------------------------------------------------------------
# Source-specific quantile bands
# ---------------------------------------------------------------------------


def test_bands_are_computed_from_this_corpus(corpus):
    frame = pd.read_parquet(corpus)
    bands = compute_length_bands(frame)
    lengths = frame["text"].astype(str).str.len()
    assert bands["q_low"] == pytest.approx(float(lengths.quantile(0.33)))
    assert bands["q_high"] == pytest.approx(float(lengths.quantile(0.66)))
    assert bands["quantiles"] == [0.33, 0.66]


def test_band_assignment(corpus):
    frame = pd.read_parquet(corpus)
    bands = compute_length_bands(frame)
    assert assign_length_band(int(bands["q_low"]) - 1, bands) == "short"
    assert assign_length_band(int(bands["q_high"]) + 1, bands) == "long"


def test_all_bands_covered_in_selection(corpus):
    _, report = sample_south_africa(corpus)
    assert set(report.selected_by_stratum) == {"short", "medium", "long"}


def test_sa_bands_differ_from_international_bands():
    """Each source must derive its own thresholds (Requirements 7.4)."""
    if not REAL_CORPUS.is_file():
        pytest.skip("materialised corpus absent")
    intl_source = _PROJECT_ROOT / "data" / "interim" / "prepared.csv"
    if not intl_source.is_file():
        pytest.skip("international source absent")

    from banking_tasci.data.international_sampler import (
        REVIEW_SOURCE,
        TWEET_SOURCE,
        compute_length_bands as intl_bands,
    )

    sa = compute_length_bands(pd.read_parquet(REAL_CORPUS, columns=["text"]))
    intl = pd.read_csv(intl_source)
    tweets = intl_bands(intl, TWEET_SOURCE)
    reviews = intl_bands(intl, REVIEW_SOURCE)

    sa_pair = (sa["q_low"], sa["q_high"])
    assert sa_pair != (tweets.q_low, tweets.q_high)
    assert sa_pair != (reviews.q_low, reviews.q_high)


# ---------------------------------------------------------------------------
# Coverage reporting
# ---------------------------------------------------------------------------


def test_year_coverage_reported(corpus):
    _, report = sample_south_africa(corpus)
    assert report.year_distribution_available
    assert report.year_distribution_selected
    assert len(report.year_distribution_selected) >= 2


def test_rule_coverage_reported_when_labels_supplied(corpus):
    frame = pd.read_parquet(corpus)
    labels = pd.Series("A", index=frame["record_id"].astype(str))
    _, report = sample_south_africa(corpus, rule_labels=labels)
    assert report.rule_distribution_selected == {"A": 500}


def test_rule_labels_map_by_record_id_not_position(corpus):
    """Rule labels come from the parent corpus, whose row positions differ, so
    the join must be by record_id."""
    frame = pd.read_parquet(corpus)
    ids = frame["record_id"].astype(str).tolist()
    # Reverse the order to prove positional alignment is not being used.
    labels = pd.Series(["F"] * len(ids), index=list(reversed(ids)))
    _, report = sample_south_africa(corpus, rule_labels=labels)
    assert report.rule_distribution_selected == {"F": 500}


def test_rule_distribution_unavailable_without_labels(corpus):
    _, report = sample_south_africa(corpus)
    assert report.rule_distribution_selected == {"unavailable": 500}


def test_duplicate_group_coverage_reported(corpus):
    _, report = sample_south_africa(corpus)
    coverage = report.duplicate_group_coverage
    assert "records_with_group" in coverage
    assert "distinct_groups" in coverage


def test_missing_fields_reported(tmp_path):
    rows = [
        {
            "record_id": f"fnb_{i}",
            "source": "south_african_bank_tweets",
            "region": "south_africa",
            "bank": "fnb",
            "text": "my bank card payment failed again today here",
        }
        for i in range(10)
    ]
    path = tmp_path / "sparse.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    _, report = sample_south_africa(path)
    assert "created_at" in report.missing_fields
    assert "near_dup_group_id" in report.missing_fields


# ---------------------------------------------------------------------------
# Group integrity
# ---------------------------------------------------------------------------


def test_duplicate_group_integrity(tmp_path):
    rows = []
    for i in range(500):
        rows.append(
            {
                "record_id": f"fnb_{i:04d}",
                "source": "south_african_bank_tweets",
                "region": "south_africa",
                "bank": "fnb",
                "text": "my bank card payment failed again " * (1 + i % 4),
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "created_at": "2021-01-01",
                "near_dup_group_id": f"g{i // 3}",  # 3 records per group
                "near_dup_flag": True,
                "thread_id": None,
                "rating": None,
                "title": None,
            }
        )
    path = tmp_path / "grouped.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)

    selected, report = sample_south_africa(path, per_bank_target=50)
    groups = [g for g in selected["_group"] if g]
    assert len(groups) == len(set(groups)), "a duplicate group was split"
    assert report.duplicate_group_conflicts > 0  # conflicts were detected


def test_leakage_group_uses_thread_id_when_present(tmp_path):
    rows = []
    for i in range(200):
        rows.append(
            {
                "record_id": f"fnb_{i:04d}",
                "source": "south_african_bank_tweets",
                "region": "south_africa",
                "bank": "fnb",
                "text": "my bank card payment failed again and again today",
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "created_at": "2021-01-01",
                "near_dup_group_id": None,
                "near_dup_flag": False,
                "thread_id": f"t{i // 4}",
                "rating": None,
                "title": None,
            }
        )
    path = tmp_path / "threads.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    selected, _ = sample_south_africa(path, per_bank_target=25)
    groups = [g for g in selected["_group"] if g]
    assert len(groups) == len(set(groups))


# ---------------------------------------------------------------------------
# Label-hidden output
# ---------------------------------------------------------------------------


def test_output_has_no_opinions(corpus):
    selected, _ = sample_south_africa(corpus)
    for record in to_label_hidden_records(selected):
        assert record["opinions"] == []


def test_output_has_no_intent(corpus):
    selected, _ = sample_south_africa(corpus)
    for record in to_label_hidden_records(selected):
        assert record["primary_intent"] is None
        assert record["public_warning"] is None


def test_output_has_no_target_category_or_sentiment(corpus):
    selected, _ = sample_south_africa(corpus)
    for record in to_label_hidden_records(selected):
        for forbidden in ("target", "category", "sentiment", "entity", "attribute"):
            assert forbidden not in record


def test_output_excludes_v2_rule_and_sampling_fields(corpus):
    """Requirements 6.5: candidate rules must not become annotation labels."""
    frame = pd.read_parquet(corpus)
    labels = pd.Series("C", index=frame["record_id"].astype(str))
    selected, _ = sample_south_africa(corpus, rule_labels=labels)
    for record in to_label_hidden_records(selected):
        for leaked in ("_v2_rule", "v2_rule", "rule_matched", "_band", "_text_length", "_bank"):
            assert leaked not in record


def test_output_status_is_not_started(corpus):
    selected, _ = sample_south_africa(corpus)
    for record in to_label_hidden_records(selected):
        assert record["annotation_status"] == "not_started"


def test_output_preserves_record_ids(corpus):
    selected, _ = sample_south_africa(corpus)
    records = to_label_hidden_records(selected)
    assert {r["record_id"] for r in records} == set(selected["record_id"])


def test_output_preserves_privacy_safe_text(corpus):
    selected, _ = sample_south_africa(corpus)
    for record in to_label_hidden_records(selected):
        assert record["text"]
        assert record["privacy_status"] == "anonymised"


def test_output_context_defaults_to_no_context(corpus):
    selected, _ = sample_south_africa(corpus)
    for record in to_label_hidden_records(selected):
        assert record["previous_text"] == "[NO_CONTEXT]"
        assert record["context_available"] is False


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_source_checksum_recorded(corpus):
    import hashlib

    _, report = sample_south_africa(corpus)
    assert report.source_sha256 == hashlib.sha256(corpus.read_bytes()).hexdigest()


def test_selection_reasons_recorded_for_every_record(corpus):
    selected, report = sample_south_africa(corpus)
    for record_id in selected["record_id"]:
        reason = report.selection_reasons[str(record_id)]
        assert "bank=" in reason
        assert "length_band=" in reason


def test_source_file_never_modified(corpus):
    before = corpus.read_bytes()
    sample_south_africa(corpus)
    dry_run(corpus)
    assert corpus.read_bytes() == before


def test_seed_recorded_in_manifest(corpus):
    _, report = sample_south_africa(corpus, seed=42)
    manifest = build_selection_manifest(report)
    assert manifest["seed"] == 42
    assert manifest["pipeline_version"] == "new_pipeline_v1"


# ---------------------------------------------------------------------------
# Dry run and write authorisation
# ---------------------------------------------------------------------------


def test_dry_run_selects_nothing(corpus):
    report = dry_run(corpus)
    assert report.dry_run is True
    assert report.available_total > 0


def test_dry_run_reports_required_fields(corpus):
    report = dry_run(corpus)
    for attribute in (
        "available_by_bank",
        "requested_by_bank",
        "length_bands",
        "year_distribution_available",
        "duplicate_group_coverage",
    ):
        assert getattr(report, attribute)
    assert report.can_select_full_total is True
    assert report.can_select_full_per_bank is True


def test_cli_dry_run_writes_nothing(corpus, tmp_path):
    out = tmp_path / "should_not_exist.jsonl"
    rc = CLI.main(["--input", str(corpus), "--output", str(out)])
    assert rc == 0
    assert not out.exists()


def test_cli_write_requires_second_authorisation(corpus, tmp_path):
    """A single --write flag must not be enough to produce gold input."""
    out = tmp_path / "blocked.jsonl"
    rc = CLI.main(["--input", str(corpus), "--output", str(out), "--write"])
    assert rc == 2
    assert not out.exists()


def test_cli_missing_source_errors(tmp_path):
    rc = CLI.main(["--input", str(tmp_path / "absent.parquet")])
    assert rc == 1


# ---------------------------------------------------------------------------
# Integration against the real materialised corpus (read-only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_CORPUS.is_file(), reason="materialised corpus absent")
def test_real_corpus_can_satisfy_500_and_100_per_bank():
    report = dry_run(REAL_CORPUS)
    assert report.available_total == 100_768
    assert report.can_select_full_total is True
    assert report.can_select_full_per_bank is True
    for bank in CANONICAL_BANKS:
        assert report.available_by_bank[bank] >= 100


@pytest.mark.skipif(not REAL_CORPUS.is_file(), reason="materialised corpus absent")
def test_real_corpus_selection_is_exactly_500_and_100_per_bank():
    selected, report = sample_south_africa(REAL_CORPUS, seed=42)
    assert len(selected) == 500
    assert selected["record_id"].nunique() == 500
    for bank in CANONICAL_BANKS:
        assert report.selected_by_bank[bank] == 100
    assert report.shortages == []
