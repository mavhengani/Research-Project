"""Tests for the Annotation_Sampler (scripts/create_annotation_sample.py).

Covers:
- Req 17.2: same seed + same input produces the identical sampled record
  set on two separate calls to `stratified_sample`.
- Req 17.6: the sample report contains all required fields.
- Req 17.4: the sampler never reads/uses any gold-label field when
  building the pool or drawing the sample.
- Req 17.3: the sample reflects source/region diversity where the input
  pool supports it.
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

import pandas as pd  # noqa: E402

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.ingest import CANONICAL_COLUMNS  # noqa: E402

from create_annotation_sample import (  # noqa: E402
    build_annotatable_pool,
    stratified_sample,
    to_unannotated_records,
    write_sample_report,
)

_BASE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "base.yaml"


def _cfg():
    return load_config(_BASE_CONFIG_PATH)


def _canonical_row(
    record_id: str,
    source: str,
    region: str = "international",
    text: str = "Great service overall",
    rating=None,
    bank=None,
) -> dict:
    row = {col: None for col in CANONICAL_COLUMNS}
    row.update(
        record_id=record_id,
        source=source,
        region=region,
        bank=bank,
        rating=rating,
        title="",
        text=text,
        previous_text="[NO_CONTEXT]",
        context_available=False,
        thread_id=None,
        created_at=None,
        split=None,
    )
    return row


def _mixed_prepared_df(cfg) -> pd.DataFrame:
    reviews_source = cfg.data.reviews_source_name
    tweets_source = cfg.data.tweets_source_name

    rows = [
        _canonical_row(
            "rev1",
            reviews_source,
            region="south_africa",
            text="Waited an hour. The teller was rude. Never coming back.",
            rating=1,
            bank="SBI",
        ),
        _canonical_row(
            "rev2",
            reviews_source,
            region="international",
            text="Great service overall.",
            rating=5,
            bank="ABC",
        ),
        _canonical_row(
            "rev3",
            reviews_source,
            region="south_africa",
            text="The mobile app is slow. But support was helpful.",
            rating=3,
            bank="SBI",
        ),
        _canonical_row("tw1", tweets_source, region="international", text="My card got blocked"),
        _canonical_row("tw2", tweets_source, region="international", text="Any update on my complaint?"),
        _canonical_row("tw3", tweets_source, region="international", text="Thanks for the quick help!"),
    ]
    return pd.DataFrame(rows)[CANONICAL_COLUMNS]


# ---------------------------------------------------------------------------
# Req 17.2: determinism
# ---------------------------------------------------------------------------


def test_stratified_sample_is_deterministic_for_same_seed_and_input():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)

    sample_a = stratified_sample(pool, size=4, seed=42)
    sample_b = stratified_sample(pool, size=4, seed=42)

    ids_a = [item["record_id"] for item in sample_a]
    ids_b = [item["record_id"] for item in sample_b]
    assert ids_a == ids_b


def test_stratified_sample_differs_for_different_seed():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)

    sample_a = stratified_sample(pool, size=4, seed=1)
    sample_b = stratified_sample(pool, size=4, seed=2)

    ids_a = [item["record_id"] for item in sample_a]
    ids_b = [item["record_id"] for item in sample_b]
    # Not a hard guarantee for every possible pool, but true for this
    # fixture; documents that the seed actually drives selection.
    assert ids_a != ids_b or len(pool) <= 4


# ---------------------------------------------------------------------------
# Req 17.6: sample report fields
# ---------------------------------------------------------------------------


def test_write_sample_report_contains_all_required_fields(tmp_path):
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)
    sample = stratified_sample(pool, size=5, seed=42)

    report_path = tmp_path / "report.json"
    write_sample_report(sample, seed=42, path=report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))

    for field_name in (
        "seed",
        "sample_size",
        "counts_by_source",
        "counts_by_region",
        "context_available_true_count",
        "context_available_false_count",
        "text_length_distribution",
        "rating_distribution",
        "multi_sentence_review_count",
    ):
        assert field_name in report

    assert report["seed"] == 42
    for key in ("min", "max", "mean", "q1", "median", "q3"):
        assert key in report["text_length_distribution"]


def test_multi_sentence_review_count_reflects_sample_composition(tmp_path):
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)
    # Take the whole pool so both sentences of the multi-sentence reviews
    # are guaranteed to be present.
    sample = stratified_sample(pool, size=len(pool), seed=42)

    report_path = tmp_path / "report.json"
    write_sample_report(sample, seed=42, path=report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # rev1 and rev3 are both two-sentence reviews.
    assert report["multi_sentence_review_count"] == 2


# ---------------------------------------------------------------------------
# Req 17.4: no gold-label field is ever read/used
# ---------------------------------------------------------------------------


def test_pool_dicts_have_no_gold_label_fields():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)

    assert len(pool) > 0
    for item in pool:
        assert "aspects" not in item
        assert "intent" not in item
        assert "annotation_status" not in item


def test_unannotated_records_have_empty_gold_labels():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)
    sample = stratified_sample(pool, size=3, seed=42)
    records = to_unannotated_records(sample)

    assert len(records) == 3
    for record in records:
        assert record.aspects == []
        assert record.intent is None
        assert record.intent_ambiguous is False
        assert record.alternative_intent is None
        assert record.annotator_id == ""
        assert record.annotation_status == "not_started"
        assert record.notes == ""


# ---------------------------------------------------------------------------
# Req 17.3: source/region diversity preserved where the pool supports it
# ---------------------------------------------------------------------------


def test_sample_reflects_source_diversity_when_size_allows():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)

    sample = stratified_sample(pool, size=6, seed=42)
    sources_in_sample = {item["source"] for item in sample}

    assert cfg.data.reviews_source_name in sources_in_sample
    assert cfg.data.tweets_source_name in sources_in_sample


def test_sample_size_larger_than_pool_returns_whole_pool():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)

    sample = stratified_sample(pool, size=1000, seed=42)
    assert len(sample) == len(pool)


def test_sample_size_zero_returns_empty():
    cfg = _cfg()
    df = _mixed_prepared_df(cfg)
    pool = build_annotatable_pool(df, cfg)

    assert stratified_sample(pool, size=0, seed=42) == []
