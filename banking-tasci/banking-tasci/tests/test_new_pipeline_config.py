"""Tests for the `new_pipeline_v1` configuration and canonical taxonomy.

Covers the configuration/taxonomy half of this session's Step 5 checklist:
config loads, corpus counts match the specification, split ratios sum to 1.0,
annotation allocation totals 1,000, source-level 80/10/10 equals 800/100/100,
approved intent labels with `warning` excluded, approved sentiment labels,
approved target types, canonical category composition, valid entity-attribute
pairs, and `[NO_CONTEXT]` configuration.

These assert the configuration states the *required* values from
NEW_PIPELINE_REQUIREMENTS.md. They deliberately do NOT assert that the
underlying data satisfies those counts - that is the manifest generator's job
(see test_new_pipeline_manifest.py), and for the South African corpus it
currently does not (gap-analysis finding R3).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.new_pipeline_schema import (  # noqa: E402
    NO_CONTEXT,
    PRIMARY_INTENTS,
    SENTIMENT_LABELS,
    TARGET_TYPES,
    compose_category,
    load_taxonomy,
    split_category,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "new_pipeline_v1.yaml"
TAXONOMY_PATH = (
    PROJECT_ROOT / "configs" / "taxonomies" / "banking_entity_attribute_v1.yaml"
)


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy(TAXONOMY_PATH)


# ---------------------------------------------------------------------------
# Configuration loads
# ---------------------------------------------------------------------------


def test_config_file_exists():
    assert CONFIG_PATH.is_file(), f"missing {CONFIG_PATH}"


def test_config_loads_successfully(cfg):
    assert cfg is not None


def test_pipeline_version_is_new_pipeline_v1(cfg):
    assert cfg.pipeline_version == "new_pipeline_v1"


def test_config_inherits_base_seed(cfg):
    """`base: base.yaml` inheritance must still supply the shared seed."""
    assert cfg.seed == 42


# ---------------------------------------------------------------------------
# Corpus counts (Requirements Section 4)
# ---------------------------------------------------------------------------


def test_required_corpus_counts_match_specification(cfg):
    counts = cfg.counts
    assert counts.south_africa_candidates == 100_768
    assert counts.international_prepared == 10_847
    assert counts.combined_relevant == 111_615
    assert counts.gold_total == 1_000
    assert counts.unlabelled_total == 110_615


def test_combined_relevant_is_sum_of_sources(cfg):
    counts = cfg.counts
    assert (
        counts.south_africa_candidates + counts.international_prepared
        == counts.combined_relevant
    )


def test_unlabelled_total_excludes_gold(cfg):
    """Requirements 4.5: 111,615 - 1,000 = 110,615."""
    counts = cfg.counts
    assert counts.combined_relevant - counts.gold_total == counts.unlabelled_total


def test_provenance_only_count_is_not_a_modelling_count(cfg):
    """Requirements 4.1: the ~2.25M figure is provenance only.

    It must be recorded separately from `counts`, never inside it.
    """
    assert cfg.provenance_only_counts.south_africa_prepared_full == 2_250_776
    for value in cfg.counts.to_dict().values():
        assert value != 2_250_776


# ---------------------------------------------------------------------------
# Annotation allocation (Requirements Sections 4.4, 7, 13)
# ---------------------------------------------------------------------------


def test_source_annotation_allocation_totals_1000(cfg):
    annotation = cfg.annotation
    total = (
        annotation.south_africa_tweets
        + annotation.international_tweets
        + annotation.international_reviews
    )
    assert total == 1_000
    assert annotation.south_africa_tweets == 500
    assert annotation.international_tweets == 250
    assert annotation.international_reviews == 250


def test_regional_allocation_is_balanced(cfg):
    """Requirements 4.4: South African 500, international 500."""
    annotation = cfg.annotation
    international = annotation.international_tweets + annotation.international_reviews
    assert annotation.south_africa_tweets == international == 500


def test_calibration_size_is_50(cfg):
    assert cfg.annotation.calibration_size == 50


def test_batching_plan_totals_1000(cfg):
    """Requirements 13.3: 50 + (9 x 100) + 50 = 1,000, not 950."""
    batching = cfg.annotation.batching
    total = (
        batching.calibration_batch
        + batching.main_batch_size * batching.main_batch_count
        + batching.final_batch
    )
    assert total == 1_000
    # Guard against the specific arithmetic error the requirements call out.
    assert (
        batching.calibration_batch
        + batching.main_batch_size * batching.main_batch_count
        == 950
    )


def test_per_bank_allocation_covers_south_africa_sample(cfg):
    """Requirements 7.1: 5 banks x 100 = 500."""
    annotation = cfg.annotation
    banks = annotation.south_africa_banks
    assert len(banks) == 5
    assert len(banks) * annotation.per_bank_allocation == annotation.south_africa_tweets


def test_length_bands_use_source_specific_quantiles(cfg):
    """Requirements 7.4 forbids one arbitrary global character threshold."""
    bands = cfg.annotation.length_bands
    assert bands.method == "source_specific_quantile"
    assert len(bands.band_names) == 3
    assert len(bands.quantiles) == 2


# ---------------------------------------------------------------------------
# Split (Requirements Section 15)
# ---------------------------------------------------------------------------


def test_split_ratios_sum_to_one(cfg):
    split = cfg.split
    total = split.train_ratio + split.validation_ratio + split.test_ratio
    assert total == pytest.approx(1.0)


def test_split_ratios_are_80_10_10(cfg):
    split = cfg.split
    assert split.train_ratio == pytest.approx(0.80)
    assert split.validation_ratio == pytest.approx(0.10)
    assert split.test_ratio == pytest.approx(0.10)


def test_split_is_not_the_prohibited_70_15_15(cfg):
    """Requirements Section 27 explicitly prohibits 70/15/15."""
    split = cfg.split
    assert (split.train_ratio, split.validation_ratio, split.test_ratio) != (
        0.70,
        0.15,
        0.15,
    )


def test_split_seed_is_42(cfg):
    assert cfg.split.seed == 42


def test_split_is_group_aware_and_strict(cfg):
    assert cfg.split.group_aware is True
    assert cfg.split.strict_leakage_failure is True


def test_split_totals_are_800_100_100(cfg):
    totals = cfg.split.expected_totals
    assert totals.train == 800
    assert totals.validation == 100
    assert totals.test == 100
    assert totals.total == 1_000


def test_source_level_split_counts_equal_800_100_100(cfg):
    """Requirements Section 15 source-level allocation table."""
    allocation = cfg.split.expected_source_allocation.to_dict()

    assert allocation["south_african_tweets"] == {
        "train": 400,
        "validation": 50,
        "test": 50,
        "total": 500,
    }
    assert allocation["international_tweets"] == {
        "train": 200,
        "validation": 25,
        "test": 25,
        "total": 250,
    }
    assert allocation["international_reviews"] == {
        "train": 200,
        "validation": 25,
        "test": 25,
        "total": 250,
    }

    for key in ("train", "validation", "test", "total"):
        assert sum(row[key] for row in allocation.values()) == {
            "train": 800,
            "validation": 100,
            "test": 100,
            "total": 1000,
        }[key]


def test_source_allocation_rows_are_internally_consistent(cfg):
    for name, row in cfg.split.expected_source_allocation.to_dict().items():
        assert row["train"] + row["validation"] + row["test"] == row["total"], name


def test_split_ratios_applied_to_gold_total_give_expected_totals(cfg):
    """The ratios and the absolute counts must not drift apart."""
    gold = cfg.counts.gold_total
    split = cfg.split
    assert round(gold * split.train_ratio) == split.expected_totals.train
    assert round(gold * split.validation_ratio) == split.expected_totals.validation
    assert round(gold * split.test_ratio) == split.expected_totals.test


# ---------------------------------------------------------------------------
# Label spaces (Requirements Sections 10, 11)
# ---------------------------------------------------------------------------


def test_approved_intent_labels(cfg):
    expected = [
        "complaint",
        "request_for_assistance",
        "praise_or_appreciation",
        "suggestion_or_feature_request",
        "exit_or_switch_intention",
        "general_feedback",
    ]
    assert list(cfg.annotation.primary_intents) == expected
    assert list(PRIMARY_INTENTS) == expected


def test_exactly_six_primary_intents(cfg):
    assert len(cfg.annotation.primary_intents) == 6
    assert len(PRIMARY_INTENTS) == 6


def test_warning_excluded_from_primary_intents(cfg):
    """Requirements 11.7 and Section 27: warning is not a primary intent."""
    assert "warning" not in cfg.annotation.primary_intents
    assert "warning" not in PRIMARY_INTENTS
    assert "public_warning" not in cfg.annotation.primary_intents


def test_public_warning_is_a_separate_field(cfg):
    assert cfg.annotation.public_warning_field == "public_warning"


def test_legacy_intent_labels_are_absent_from_new_taxonomy(cfg):
    """The legacy 7-label vocabulary must not leak into the new config."""
    for legacy in ("compliment", "suggestion", "churn_signal"):
        assert legacy not in cfg.annotation.primary_intents


def test_approved_sentiment_labels(cfg):
    expected = ["positive", "neutral", "negative", "conflict"]
    assert list(cfg.annotation.sentiment_labels) == expected
    assert list(SENTIMENT_LABELS) == expected


def test_conflict_sentiment_is_present(cfg):
    """Requirements Section 10; absent from the legacy label set."""
    assert "conflict" in cfg.annotation.sentiment_labels
    assert "conflict" in SENTIMENT_LABELS


def test_approved_target_types(cfg):
    assert list(cfg.annotation.target_types) == ["explicit", "implicit"]
    assert list(TARGET_TYPES) == ["explicit", "implicit"]


# ---------------------------------------------------------------------------
# Context (Requirements Section 12)
# ---------------------------------------------------------------------------


def test_no_context_token_configuration(cfg):
    assert cfg.context.no_context_token == "[NO_CONTEXT]"
    assert NO_CONTEXT == "[NO_CONTEXT]"


def test_context_requires_verified_linkage(cfg):
    """Requirements Section 12 forbids unverified row-adjacency context."""
    assert cfg.context.require_verified_linkage is True


# ---------------------------------------------------------------------------
# Domain adaptation and evaluation (Requirements Sections 17, 24)
# ---------------------------------------------------------------------------


def test_domain_adaptation_defaults(cfg):
    da = cfg.domain_adaptation
    assert da.base_model == "bert-base-uncased"
    assert da.max_length == 128
    assert da.masking_probability == pytest.approx(0.15)
    assert da.exclude_all_gold_records is True
    assert da.expected_records == 110_615


def test_domain_adaptation_expected_records_matches_unlabelled_total(cfg):
    assert cfg.domain_adaptation.expected_records == cfg.counts.unlabelled_total


def test_evaluation_settings(cfg):
    assert cfg.evaluation.primary_metric == "macro_f1"
    assert cfg.evaluation.random_seeds == 5


# ---------------------------------------------------------------------------
# Taxonomy (Requirements Section 9)
# ---------------------------------------------------------------------------


def test_taxonomy_file_exists():
    assert TAXONOMY_PATH.is_file(), f"missing {TAXONOMY_PATH}"


def test_config_points_at_canonical_taxonomy(cfg):
    assert cfg.taxonomy.version == "banking_entity_attribute_v1"
    resolved = CONFIG_PATH.parent / cfg.taxonomy.path
    assert resolved.resolve() == TAXONOMY_PATH.resolve()


def test_taxonomy_loads_successfully(taxonomy):
    assert taxonomy.version == "banking_entity_attribute_v1"


def test_taxonomy_contains_all_required_entities(taxonomy):
    required = {
        "APP",
        "ONLINE_BANKING",
        "CARD",
        "ACCOUNT",
        "TRANSFER",
        "PAYMENT",
        "ATM",
        "SUPPORT",
        "BRANCH",
        "SECURITY",
        "FRAUD",
        "LOAN",
        "BANK",
    }
    assert set(taxonomy.entities) == required
    assert len(taxonomy.entities) == 13


@pytest.mark.parametrize(
    "category",
    [
        "APP#RELIABILITY",
        "CARD#FEES",
        "TRANSFER#SPEED",
        "SUPPORT#RESPONSIVENESS",
        "BRANCH#WAITING_TIME",
        "LOAN#INTEREST_RATE",
    ],
)
def test_required_example_categories_are_valid(taxonomy, category):
    """The exact examples named in the requirements must all resolve."""
    assert taxonomy.is_valid_category(category)


def test_canonical_category_composition(taxonomy):
    """Requirements Section 14: category == entity + '#' + attribute."""
    for category in taxonomy.categories:
        parts = split_category(category)
        assert parts is not None, category
        entity, attribute = parts
        assert compose_category(entity, attribute) == category
        assert taxonomy.is_valid_pair(entity, attribute)


def test_every_category_uses_the_canonical_separator(taxonomy):
    for category in taxonomy.categories:
        assert category.count("#") == 1


def test_valid_entity_attribute_pairs_are_accepted(taxonomy):
    assert taxonomy.is_valid_pair("APP", "RELIABILITY")
    assert taxonomy.is_valid_pair("LOAN", "INTEREST_RATE")
    assert taxonomy.is_valid_pair("BRANCH", "WAITING_TIME")


def test_invalid_entity_attribute_pairs_are_rejected(taxonomy):
    # Attribute belongs to a different entity.
    assert not taxonomy.is_valid_pair("APP", "WAITING_TIME")
    assert not taxonomy.is_valid_pair("LOAN", "DELIVERY")
    # Unknown entity and unknown attribute.
    assert not taxonomy.is_valid_pair("NOT_AN_ENTITY", "GENERAL")
    assert not taxonomy.is_valid_pair("APP", "NOT_AN_ATTRIBUTE")


def test_unknown_category_is_rejected(taxonomy):
    assert not taxonomy.is_valid_category("APP#NOT_REAL")
    assert not taxonomy.is_valid_category("cards")  # legacy flat form
    assert not taxonomy.is_valid_category("APP")
    assert not taxonomy.is_valid_category("APP#RELIABILITY#EXTRA")


def test_legacy_flat_categories_are_not_valid(taxonomy):
    """The legacy nine-value flat list must not be accepted here."""
    legacy = [
        "customer_support",
        "digital_banking",
        "transactions",
        "cards",
        "accounts",
        "fees",
        "fraud_security",
        "branch_service",
        "general_service",
    ]
    for category in legacy:
        assert not taxonomy.is_valid_category(category)


def test_every_entity_offers_a_general_attribute(taxonomy):
    """Requirements 9.14 permits GENERAL for every entity."""
    for entity, attributes in taxonomy.entities.items():
        assert taxonomy.general_attribute in attributes, entity


def test_semantic_mappings_match_requirements_examples(taxonomy):
    """Requirements Section 19 gives these three mappings explicitly."""
    assert taxonomy.semantic_for("APP#RELIABILITY") == "mobile application, reliability"
    assert taxonomy.semantic_for("CARD#FEES") == "card, fees"
    assert (
        taxonomy.semantic_for("SUPPORT#RESPONSIVENESS")
        == "customer support, responsiveness"
    )


def test_every_category_has_a_semantic_mapping(taxonomy):
    for category in taxonomy.categories:
        semantic = taxonomy.semantic_for(category)
        assert semantic, category
        assert "," in semantic


def test_split_category_rejects_malformed_input():
    assert split_category("APP") is None
    assert split_category("APP#A#B") is None
    assert split_category("#RELIABILITY") is None
    assert split_category("APP#") is None
    assert split_category(None) is None


# ---------------------------------------------------------------------------
# Legacy coexistence
# ---------------------------------------------------------------------------


def test_legacy_config_files_still_load():
    """Phase 1 must not disturb legacy configuration (Migration Principle 5)."""
    for name in ("base.yaml", "intent.yaml", "sentiment.yaml"):
        assert (PROJECT_ROOT / "configs" / name).is_file()
    assert load_config(PROJECT_ROOT / "configs" / "base.yaml").seed == 42


def test_legacy_annotation_constants_are_unchanged():
    """The legacy label spaces must remain intact for the 796-record corpus."""
    from banking_tasci.data import annotations as legacy

    assert "warning" in legacy.INTENT_LABELS
    assert len(legacy.INTENT_LABELS) == 7
    assert legacy.ASPECT_SENTIMENTS == ["positive", "negative", "neutral"]
    assert len(legacy.ASPECT_CATEGORIES) == 9


def test_new_and_legacy_schemas_are_independent():
    """The new schema must not re-export or mutate legacy constants."""
    from banking_tasci.data import annotations as legacy
    from banking_tasci.data import new_pipeline_schema as new

    assert set(new.PRIMARY_INTENTS) != set(legacy.INTENT_LABELS)
    assert set(new.SENTIMENT_LABELS) != set(legacy.ASPECT_SENTIMENTS)
