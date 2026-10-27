"""Tests for the international `new_pipeline_v1` gold sampler.

Covers Requirements Section 7 for the international sources only: determinism
under seed 42, exact 250/250 allocation, no replacement, group integrity,
source-specific quantile bands, rating-as-metadata-only, context preservation,
shortage/unsatisfied-strata reporting, and label-hidden output.

Most tests use small synthetic in-memory fixtures so they are fast and
hermetic. A small number of explicitly-marked tests read the real VERIFIED
10,847-record international source read-only, because properties like "the two
sources genuinely need different length thresholds" are only meaningful against
real data.
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

from banking_tasci.data.international_sampler import (  # noqa: E402
    DEFAULT_SEED,
    REVIEW_SOURCE,
    TWEET_SOURCE,
    assign_length_band,
    assign_rating_band,
    build_selection_manifest,
    compute_length_bands,
    count_sentences,
    dry_run,
    sample_international,
    to_label_hidden_records,
)

REAL_SOURCE = _PROJECT_ROOT / "data" / "interim" / "prepared.csv"


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------


def _make_source(tmp_path: Path, n_tweets: int = 400, n_reviews: int = 400) -> Path:
    """Build a synthetic international source with realistic shape."""
    rows = []
    for i in range(n_tweets):
        # Vary length so quantile bands are meaningful.
        text = "bank app issue " * (1 + (i % 7))
        rows.append(
            {
                "record_id": f"tw{i:04d}",
                "source": TWEET_SOURCE,
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
                "source": REVIEW_SOURCE,
                "region": "international",
                "bank": f"bank_{i % 4}",
                "rating": [0.5, 2.0, 3.0, 4.0, 5.0][i % 5],
                "title": "t",
                "text": text,
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "thread_id": None,
                "created_at": "2021-03-04",
                "split": None,
            }
        )
    path = tmp_path / "prepared.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def source(tmp_path) -> Path:
    return _make_source(tmp_path)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_under_seed_42(source):
    first, _ = sample_international(source, seed=42)
    second, _ = sample_international(source, seed=42)
    assert list(first["record_id"]) == list(second["record_id"])


def test_default_seed_is_42():
    assert DEFAULT_SEED == 42


def test_different_seeds_give_different_selections(source):
    first, _ = sample_international(source, seed=42)
    second, _ = sample_international(source, seed=7)
    assert list(first["record_id"]) != list(second["record_id"])


def test_sampler_does_not_touch_global_rng(source):
    """Selection must flow only through the injected generator."""
    import random

    import numpy as np

    random.seed(123)
    np.random.seed(123)
    py_before = random.random()
    np_before = float(np.random.random())

    random.seed(123)
    np.random.seed(123)
    sample_international(source, seed=42)
    assert random.random() == py_before
    assert float(np.random.random()) == np_before


# ---------------------------------------------------------------------------
# Counts and no-replacement
# ---------------------------------------------------------------------------


def test_exactly_250_tweets_when_data_sufficient(source):
    _, report = sample_international(source)
    assert report.selected_by_source[TWEET_SOURCE] == 250


def test_exactly_250_reviews_when_data_sufficient(source):
    _, report = sample_international(source)
    assert report.selected_by_source[REVIEW_SOURCE] == 250


def test_total_international_selection_is_500(source):
    selected, _ = sample_international(source)
    assert len(selected) == 500


def test_no_replacement_record_ids_unique(source):
    selected, _ = sample_international(source)
    assert selected["record_id"].nunique() == len(selected)


def test_no_replacement_indices_unique(source):
    selected, _ = sample_international(source)
    assert len(set(selected.index)) == len(selected)


def test_manifest_declares_no_replacement_sampling(source):
    _, report = sample_international(source)
    assert build_selection_manifest(report)["replacement_sampling"] is False


# ---------------------------------------------------------------------------
# Source-specific quantile bands (Requirements 7.4)
# ---------------------------------------------------------------------------


def test_tweet_and_review_bands_computed_separately(source):
    _, report = sample_international(source)
    tweet = report.length_bands[TWEET_SOURCE]
    review = report.length_bands[REVIEW_SOURCE]
    assert tweet["source"] == TWEET_SOURCE
    assert review["source"] == REVIEW_SOURCE
    # Different distributions must yield different boundaries.
    assert (tweet["q_low"], tweet["q_high"]) != (review["q_low"], review["q_high"])


def test_band_boundaries_use_configured_quantiles(source):
    frame = pd.read_csv(source)
    bands = compute_length_bands(frame, TWEET_SOURCE)
    assert bands.quantiles == (0.33, 0.66)
    lengths = (
        frame[frame["source"] == TWEET_SOURCE]["text"].astype(str).str.len()
    )
    assert bands.q_low == pytest.approx(float(lengths.quantile(0.33)))
    assert bands.q_high == pytest.approx(float(lengths.quantile(0.66)))


def test_assign_length_band_boundaries(source):
    frame = pd.read_csv(source)
    bands = compute_length_bands(frame, TWEET_SOURCE)
    assert assign_length_band(int(bands.q_low) - 1, bands) == "short"
    assert assign_length_band(int(bands.q_high) + 1, bands) == "long"
    middle = (bands.q_low + bands.q_high) / 2
    assert assign_length_band(int(middle), bands) in {"short", "medium", "long"}


def test_no_shared_fixed_threshold_across_sources():
    """On the REAL source the two distributions are far apart, so a single
    shared threshold would be wrong. This is the concrete justification for
    Requirements 7.4."""
    if not REAL_SOURCE.is_file():
        pytest.skip("real international source not available")
    frame = pd.read_csv(REAL_SOURCE)
    tweets = compute_length_bands(frame, TWEET_SOURCE)
    reviews = compute_length_bands(frame, REVIEW_SOURCE)
    # Reviews are substantially longer; a tweet-derived threshold would put
    # essentially every review in the "long" band.
    assert reviews.q_low > tweets.q_high


# ---------------------------------------------------------------------------
# Group integrity
# ---------------------------------------------------------------------------


def test_duplicate_group_integrity(tmp_path):
    """At most one record per duplicate group may be selected."""
    rows = []
    for i in range(300):
        rows.append(
            {
                "record_id": f"tw{i:04d}",
                "source": TWEET_SOURCE,
                "region": "international",
                "bank": None,
                "rating": None,
                "title": None,
                "text": "bank card problem " * (1 + i % 5),
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "thread_id": None,
                "created_at": None,
                "split": None,
                # 3 records per duplicate group.
                "near_dup_group_id": f"g{i // 3}",
            }
        )
    path = tmp_path / "dup.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    selected, _ = sample_international(path, tweet_target=50, review_target=0)
    groups = [g for g in selected["_group"] if g]
    assert len(groups) == len(set(groups)), "a duplicate group was split"


def test_review_group_integrity(tmp_path):
    """All records sharing a review_id belong together; at most one may be
    selected so a review is never partially sampled."""
    rows = []
    for i in range(200):
        rows.append(
            {
                "record_id": f"rv{i:04d}",
                "source": REVIEW_SOURCE,
                "region": "international",
                "bank": "b",
                "rating": 3.0,
                "title": "t",
                "text": "The branch was busy. The teller was helpful.",
                "previous_text": "[NO_CONTEXT]",
                "context_available": False,
                "thread_id": None,
                "created_at": "2021-01-01",
                "split": None,
                "review_id": f"r{i // 4}",  # 4 sentences per review
            }
        )
    path = tmp_path / "rev.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    selected, _ = sample_international(path, tweet_target=0, review_target=25)
    groups = [g for g in selected["_group"] if g]
    assert len(groups) == len(set(groups)), "a review group was split"


# ---------------------------------------------------------------------------
# Rating is sampling metadata only (Requirements 7.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rating,expected",
    [
        (0.5, "low"), (1.0, "low"), (2.0, "low"),
        (2.5, "middle"), (3.0, "middle"), (3.5, "middle"),
        (4.0, "high"), (5.0, "high"),
        (None, None), ("", None), (float("nan"), None),
    ],
)
def test_rating_band_assignment(rating, expected):
    assert assign_rating_band(rating) == expected


def test_rating_bands_drive_diversity_reporting(source):
    _, report = sample_international(source)
    assert report.rating_band_counts
    assert set(report.rating_band_counts) <= {"low", "middle", "high"}


def test_rating_never_appears_in_annotation_output(source):
    """Rating must not reach the annotation view in any form."""
    selected, _ = sample_international(source)
    records = to_label_hidden_records(selected)
    for record in records:
        assert "rating" not in record
        assert "_rating_band" not in record


def test_rating_never_becomes_sentiment(source):
    """No sentiment value may be derived from a rating."""
    selected, _ = sample_international(source)
    for record in to_label_hidden_records(selected):
        assert record["opinions"] == []
        for opinion in record["opinions"]:
            assert opinion.get("sentiment") is None


# ---------------------------------------------------------------------------
# Label-hidden output (Requirements 13.1, 6.5)
# ---------------------------------------------------------------------------


def test_output_has_no_opinions(source):
    selected, _ = sample_international(source)
    for record in to_label_hidden_records(selected):
        assert record["opinions"] == []


def test_output_has_no_intent_label(source):
    selected, _ = sample_international(source)
    for record in to_label_hidden_records(selected):
        assert record["primary_intent"] is None


def test_output_has_no_target_or_category_or_sentiment(source):
    selected, _ = sample_international(source)
    for record in to_label_hidden_records(selected):
        # No opinion structures exist, so no target/category/sentiment can.
        assert record["opinions"] == []
        for forbidden in ("target", "category", "sentiment", "entity", "attribute"):
            assert forbidden not in record


def test_output_annotation_status_is_not_started(source):
    selected, _ = sample_international(source)
    for record in to_label_hidden_records(selected):
        assert record["annotation_status"] == "not_started"


def test_output_excludes_sampling_only_fields(source):
    """Stratum/band bookkeeping must not leak into the annotation view."""
    selected, _ = sample_international(source)
    for record in to_label_hidden_records(selected):
        for leaked in ("_text_length", "_sentence_band", "_rating_band", "stratum", "sample_role"):
            assert leaked not in record


def test_output_record_ids_are_stable_and_preserved(source):
    selected, _ = sample_international(source)
    records = to_label_hidden_records(selected)
    assert {r["record_id"] for r in records} == set(selected["record_id"])


# ---------------------------------------------------------------------------
# Context (Requirements 12)
# ---------------------------------------------------------------------------


def test_context_availability_is_preserved(tmp_path):
    rows = []
    for i in range(60):
        has_context = i % 2 == 0
        rows.append(
            {
                "record_id": f"rv{i:04d}",
                "source": REVIEW_SOURCE,
                "region": "international",
                "bank": "b",
                "rating": 3.0,
                "title": "t",
                "text": "The fees were high. The staff were kind.",
                "previous_text": "I have banked here for years." if has_context else "[NO_CONTEXT]",
                "context_available": has_context,
                "thread_id": None,
                "created_at": "2020-01-01",
                "split": None,
            }
        )
    path = tmp_path / "ctx.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    selected, report = sample_international(path, tweet_target=0, review_target=20)
    records = to_label_hidden_records(selected)
    for record in records:
        if record["context_available"]:
            assert record["previous_text"] != "[NO_CONTEXT]"
            assert record["previous_text"]
        else:
            assert record["previous_text"] == "[NO_CONTEXT]"
    assert "context_available_true" in report.context_availability


def test_genuine_previous_text_is_carried_through(tmp_path):
    rows = [
        {
            "record_id": "rv0001",
            "source": REVIEW_SOURCE,
            "region": "international",
            "bank": "b",
            "rating": 4.0,
            "title": "t",
            "text": "The second sentence here.",
            "previous_text": "The genuine preceding sentence.",
            "context_available": True,
            "thread_id": None,
            "created_at": "2020-01-01",
            "split": None,
        }
    ]
    path = tmp_path / "one.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    selected, _ = sample_international(path, tweet_target=0, review_target=1)
    record = to_label_hidden_records(selected)[0]
    assert record["previous_text"] == "The genuine preceding sentence."
    assert record["context_available"] is True


def test_missing_previous_text_becomes_no_context(tmp_path):
    rows = [
        {
            "record_id": "tw0001",
            "source": TWEET_SOURCE,
            "region": "international",
            "bank": None,
            "rating": None,
            "title": None,
            "text": "my card was declined again at the atm",
            "previous_text": None,
            "context_available": False,
            "thread_id": None,
            "created_at": None,
            "split": None,
        }
    ]
    path = tmp_path / "nc.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    selected, _ = sample_international(path, tweet_target=1, review_target=0)
    assert to_label_hidden_records(selected)[0]["previous_text"] == "[NO_CONTEXT]"


# ---------------------------------------------------------------------------
# Sentence counting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("One sentence.", 1),
        ("First. Second.", 2),
        ("A! B? C.", 3),
        ("No terminator", 1),
        ("", 0),
        (None, 0),
    ],
)
def test_count_sentences(text, expected):
    assert count_sentences(text) == expected


def test_sentence_bands_reported(source):
    _, report = sample_international(source)
    assert report.sentence_band_counts
    assert set(report.sentence_band_counts) <= {"single", "few", "many"}


# ---------------------------------------------------------------------------
# Shortages and unsatisfied strata (Requirements 7.5)
# ---------------------------------------------------------------------------


def test_shortage_is_reported_explicitly(tmp_path):
    """Fewer records than requested must produce an explicit shortage, never
    replacement sampling or silent under-delivery."""
    path = _make_source(tmp_path, n_tweets=10, n_reviews=10)
    selected, report = sample_international(path, tweet_target=250, review_target=250)

    assert report.shortages, "a shortage must be reported"
    by_source = {entry["source"]: entry for entry in report.shortages}
    assert by_source[TWEET_SOURCE]["requested"] == 250
    assert by_source[TWEET_SOURCE]["selected"] <= 10
    assert by_source[TWEET_SOURCE]["shortfall"] > 0
    # And still no duplicates despite the shortfall.
    assert selected["record_id"].nunique() == len(selected)


def test_shortage_reason_mentions_prohibited_replacement(tmp_path):
    path = _make_source(tmp_path, n_tweets=5, n_reviews=5)
    _, report = sample_international(path, tweet_target=250, review_target=250)
    joined = " ".join(entry["reason"] for entry in report.shortages)
    assert "replacement" in joined.lower()


def test_unsatisfied_strata_are_reported(tmp_path):
    path = _make_source(tmp_path, n_tweets=20, n_reviews=20)
    _, report = sample_international(path, tweet_target=250, review_target=250)
    assert report.unsatisfied_strata
    for entry in report.unsatisfied_strata:
        assert entry["selected"] < entry["requested"]


def test_no_shortage_when_data_is_sufficient(source):
    _, report = sample_international(source)
    assert report.shortages == []


# ---------------------------------------------------------------------------
# Provenance and immutability (Requirements 7.5, 25)
# ---------------------------------------------------------------------------


def test_source_checksum_is_recorded(source):
    import hashlib

    _, report = sample_international(source)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert report.source_sha256 == expected


def test_seed_and_config_are_recorded(source):
    _, report = sample_international(source, seed=42)
    assert report.seed == 42
    assert report.pipeline_version == "new_pipeline_v1"
    assert report.requested_by_source[TWEET_SOURCE] == 250


def test_selection_reasons_recorded_for_every_selected_record(source):
    """Requirements 7.5: record why each selected record was included."""
    selected, report = sample_international(source)
    for record_id in selected["record_id"]:
        assert str(record_id) in report.selection_reasons
        assert report.selection_reasons[str(record_id)]


def test_source_file_is_never_modified(source):
    before = source.read_bytes()
    sample_international(source)
    dry_run(source)
    assert source.read_bytes() == before


def test_real_source_is_never_modified():
    """The real VERIFIED source must remain byte-identical."""
    if not REAL_SOURCE.is_file():
        pytest.skip("real international source not available")
    import hashlib

    before = hashlib.sha256(REAL_SOURCE.read_bytes()).hexdigest()
    dry_run(REAL_SOURCE)
    after = hashlib.sha256(REAL_SOURCE.read_bytes()).hexdigest()
    assert before == after
    # Pin the known checksum from the VERIFIED manifest.
    assert before == "2a3435adcb5e5e8ffba44246dc529ecab4b9b24855f46849cf8d0fb3fe4252fd"


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_selects_nothing(source):
    report = dry_run(source)
    assert report.dry_run is True
    assert report.available_counts[TWEET_SOURCE] > 0


def test_dry_run_reports_required_fields(source):
    report = dry_run(source)
    assert report.available_counts
    assert report.length_bands
    assert report.requested_by_source
    assert report.available_by_stratum
    assert report.source_sha256


def test_dry_run_matches_real_run_plan(source):
    """A dry run must describe the same plan the real run executes."""
    dry = dry_run(source)
    _, real = sample_international(source)
    assert dry.available_counts == real.available_counts
    assert dry.requested_by_source == real.requested_by_source
    assert dry.length_bands == real.length_bands


# ---------------------------------------------------------------------------
# Scope guard: no South African sampling
# ---------------------------------------------------------------------------


def test_manifest_documents_international_only_scope(source):
    _, report = sample_international(source)
    manifest = build_selection_manifest(report)
    note = manifest["scope_note"].lower()
    assert "international" in note
    assert "south african" in note or "south africa" in note


def test_sampler_only_handles_international_sources(source):
    """The sampler must not silently sample South African records."""
    _, report = sample_international(source)
    assert set(report.selected_by_source) <= {TWEET_SOURCE, REVIEW_SOURCE}
    assert "south_african_bank_tweets" not in report.selected_by_source
