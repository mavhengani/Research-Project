"""Tests for the `new_pipeline_v1` record/opinion schema and validator.

Covers the schema half of this session's Step 5 checklist: explicit
target-offset rules, implicit target null-field rules, zero-opinion records,
multi-opinion records, canonical category composition enforcement, valid
entity-attribute pair enforcement, approved label spaces, and `[NO_CONTEXT]`
handling.

Every test builds records by hand. No repository data file is read, so these
tests are fast, hermetic, and do not depend on the unresolved South African
count question (gap-analysis finding R3).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.new_pipeline_schema import (  # noqa: E402
    NO_CONTEXT,
    PRIMARY_INTENTS,
    SENTIMENT_LABELS,
    NewPipelineRecord,
    Opinion,
    load_taxonomy,
    read_jsonl,
    record_from_dict,
    record_to_dict,
    validate_all,
    validate_record,
    write_jsonl,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = (
    PROJECT_ROOT / "configs" / "taxonomies" / "banking_entity_attribute_v1.yaml"
)

TEXT = "The banking app keeps crashing and the card fees are too high."


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy(TAXONOMY_PATH)


def _errors(issues):
    return [i for i in issues if i.severity == "error"]


def _rule_ids(issues):
    return {i.rule_id for i in issues}


def _explicit_opinion(**overrides) -> Opinion:
    """An opinion whose offsets genuinely match TEXT: 'banking app'."""
    start = TEXT.index("banking app")
    base = dict(
        target="banking app",
        target_start=start,
        target_end=start + len("banking app"),
        target_type="explicit",
        entity="APP",
        attribute="RELIABILITY",
        category="APP#RELIABILITY",
        opinion_phrase=None,
        opinion_start=None,
        opinion_end=None,
        sentiment="negative",
        annotation_notes=None,
    )
    base.update(overrides)
    return Opinion(**base)


def _implicit_opinion(**overrides) -> Opinion:
    base = dict(
        target=None,
        target_start=None,
        target_end=None,
        target_type="implicit",
        entity="BANK",
        attribute="OVERALL_SERVICE",
        category="BANK#OVERALL_SERVICE",
        opinion_phrase=None,
        opinion_start=None,
        opinion_end=None,
        sentiment="negative",
        annotation_notes=None,
    )
    base.update(overrides)
    return Opinion(**base)


def _record(**overrides) -> NewPipelineRecord:
    base = dict(
        record_id="sa_0001",
        source="south_african_bank_tweets",
        region="south_africa",
        bank="FNB",
        review_id=None,
        thread_id=None,
        conversation_id=None,
        publish_year=2021,
        text=TEXT,
        previous_text=None,
        context_available=False,
        duplicate_group=None,
        leakage_group=None,
        privacy_status="anonymised",
        primary_intent="complaint",
        public_warning=False,
        opinions=[],
        annotation_status="completed",
        annotation_version="v1",
        annotation_notes=None,
    )
    base.update(overrides)
    return NewPipelineRecord(**base)


# ---------------------------------------------------------------------------
# Baseline validity
# ---------------------------------------------------------------------------


def test_minimal_valid_record_passes(taxonomy):
    assert _errors(validate_record(_record(), taxonomy)) == []


def test_valid_explicit_opinion_record_passes(taxonomy):
    record = _record(opinions=[_explicit_opinion()])
    assert _errors(validate_record(record, taxonomy)) == []


def test_valid_implicit_opinion_record_passes(taxonomy):
    record = _record(opinions=[_implicit_opinion()])
    assert _errors(validate_record(record, taxonomy)) == []


# ---------------------------------------------------------------------------
# Zero-opinion records (Requirements 8.6)
# ---------------------------------------------------------------------------


def test_zero_opinion_record_is_valid(taxonomy):
    record = _record(opinions=[])
    assert _errors(validate_record(record, taxonomy)) == []


def test_zero_opinion_record_survives_round_trip(taxonomy):
    record = _record(opinions=[])
    restored = record_from_dict(record_to_dict(record))
    assert restored.opinions == []
    assert _errors(validate_record(restored, taxonomy)) == []


def test_opinions_must_be_a_list(taxonomy):
    record = _record(opinions="not a list")
    assert "opinions_not_a_list" in _rule_ids(validate_record(record, taxonomy))


# ---------------------------------------------------------------------------
# Multi-opinion records (Requirements 8.7)
# ---------------------------------------------------------------------------


def test_multi_opinion_record_is_valid(taxonomy):
    card_start = TEXT.index("card fees")
    second = _explicit_opinion(
        target="card fees",
        target_start=card_start,
        target_end=card_start + len("card fees"),
        entity="CARD",
        attribute="FEES",
        category="CARD#FEES",
        sentiment="negative",
    )
    record = _record(opinions=[_explicit_opinion(), second])
    assert _errors(validate_record(record, taxonomy)) == []


def test_multi_opinion_record_supports_differing_sentiments(taxonomy):
    """Requirements 8.7: one document-level sentiment must not overwrite
    target-level sentiment, including opposing sentiments in one record."""
    card_start = TEXT.index("card fees")
    positive = _explicit_opinion(
        target="card fees",
        target_start=card_start,
        target_end=card_start + len("card fees"),
        entity="CARD",
        attribute="FEES",
        category="CARD#FEES",
        sentiment="positive",
    )
    record = _record(opinions=[_explicit_opinion(sentiment="negative"), positive])
    assert _errors(validate_record(record, taxonomy)) == []
    assert {o.sentiment for o in record.opinions} == {"negative", "positive"}


def test_multi_opinion_mixes_explicit_and_implicit(taxonomy):
    record = _record(opinions=[_explicit_opinion(), _implicit_opinion()])
    assert _errors(validate_record(record, taxonomy)) == []


def test_conflict_sentiment_is_accepted(taxonomy):
    record = _record(opinions=[_explicit_opinion(sentiment="conflict")])
    assert _errors(validate_record(record, taxonomy)) == []


# ---------------------------------------------------------------------------
# Explicit target offsets (Requirements 8.3)
# ---------------------------------------------------------------------------


def test_explicit_target_offset_mismatch_is_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(target="mobile app")])
    assert "explicit_target_offset_mismatch" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_explicit_target_offsets_out_of_bounds_are_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(target_end=len(TEXT) + 50)])
    assert "explicit_target_offsets_out_of_bounds" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_explicit_target_negative_offset_is_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(target_start=-1)])
    assert "explicit_target_offsets_out_of_bounds" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_explicit_target_inverted_offsets_are_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(target_start=20, target_end=10)])
    assert "explicit_target_offsets_out_of_bounds" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_explicit_target_requires_integer_offsets(taxonomy):
    record = _record(opinions=[_explicit_opinion(target_start="4")])
    assert "explicit_target_offsets_not_integers" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_explicit_target_rejects_boolean_offsets(taxonomy):
    """`bool` subclasses `int`; it must not satisfy the offset type check."""
    record = _record(opinions=[_explicit_opinion(target_start=True)])
    assert "explicit_target_offsets_not_integers" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_explicit_target_requires_target_text(taxonomy):
    record = _record(opinions=[_explicit_opinion(target=None)])
    assert "explicit_target_missing_text" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_offsets_are_end_exclusive(taxonomy):
    """Requirements 8.3: start inclusive, end exclusive."""
    start = TEXT.index("banking app")
    end = start + len("banking app")
    assert TEXT[start:end] == "banking app"
    record = _record(
        opinions=[_explicit_opinion(target_start=start, target_end=end)]
    )
    assert _errors(validate_record(record, taxonomy)) == []
    # An inclusive-end reading would be off by one and must fail.
    bad = _record(opinions=[_explicit_opinion(target_end=end - 1)])
    assert "explicit_target_offset_mismatch" in _rule_ids(validate_record(bad, taxonomy))


# ---------------------------------------------------------------------------
# Implicit target null fields (Requirements 8.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name,value",
    [("target", "banking app"), ("target_start", 4), ("target_end", 15)],
)
def test_implicit_target_rejects_non_null_target_fields(taxonomy, field_name, value):
    record = _record(opinions=[_implicit_opinion(**{field_name: value})])
    issues = validate_record(record, taxonomy)
    assert "implicit_target_field_not_null" in _rule_ids(issues)


def test_implicit_target_retains_entity_attribute_and_sentiment(taxonomy):
    """Requirements 8.4: these remain annotated for implicit targets."""
    opinion = _implicit_opinion()
    record = _record(opinions=[opinion])
    assert _errors(validate_record(record, taxonomy)) == []
    assert opinion.entity == "BANK"
    assert opinion.attribute == "OVERALL_SERVICE"
    assert opinion.sentiment == "negative"


def test_implicit_target_may_still_carry_explicit_opinion_phrase(taxonomy):
    """Requirements 8.4: "any explicit opinion phrase remain[s] annotated"."""
    phrase_start = TEXT.index("too high")
    opinion = _implicit_opinion(
        opinion_phrase="too high",
        opinion_start=phrase_start,
        opinion_end=phrase_start + len("too high"),
    )
    record = _record(opinions=[opinion])
    assert _errors(validate_record(record, taxonomy)) == []


def test_unknown_target_type_is_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(target_type="inferred")])
    assert "target_type_not_allowed" in _rule_ids(validate_record(record, taxonomy))


# ---------------------------------------------------------------------------
# Opinion phrase offsets (Requirements 8.5)
# ---------------------------------------------------------------------------


def test_valid_opinion_phrase_offsets_pass(taxonomy):
    start = TEXT.index("crashing")
    record = _record(
        opinions=[
            _explicit_opinion(
                opinion_phrase="crashing",
                opinion_start=start,
                opinion_end=start + len("crashing"),
            )
        ]
    )
    assert _errors(validate_record(record, taxonomy)) == []


def test_opinion_phrase_offset_mismatch_is_rejected(taxonomy):
    start = TEXT.index("crashing")
    record = _record(
        opinions=[
            _explicit_opinion(
                opinion_phrase="exploding",
                opinion_start=start,
                opinion_end=start + len("crashing"),
            )
        ]
    )
    assert "opinion_phrase_offset_mismatch" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_all_null_opinion_phrase_is_valid(taxonomy):
    """Requirements 8.5 allows null phrase and offsets together."""
    record = _record(
        opinions=[
            _explicit_opinion(
                opinion_phrase=None, opinion_start=None, opinion_end=None
            )
        ]
    )
    assert _errors(validate_record(record, taxonomy)) == []


def test_partially_populated_opinion_phrase_is_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(opinion_phrase="crashing")])
    assert "opinion_phrase_partially_populated" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_opinion_phrase_out_of_bounds_is_rejected(taxonomy):
    record = _record(
        opinions=[
            _explicit_opinion(
                opinion_phrase="crashing",
                opinion_start=0,
                opinion_end=len(TEXT) + 10,
            )
        ]
    )
    assert "opinion_phrase_offsets_out_of_bounds" in _rule_ids(
        validate_record(record, taxonomy)
    )


# ---------------------------------------------------------------------------
# Category composition and entity-attribute validity (Requirements 9, 14)
# ---------------------------------------------------------------------------


def test_category_composition_mismatch_is_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(category="APP#USABILITY")])
    assert "category_composition_mismatch" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_invalid_entity_attribute_pair_is_rejected(taxonomy):
    record = _record(
        opinions=[
            _explicit_opinion(
                entity="APP", attribute="WAITING_TIME", category="APP#WAITING_TIME"
            )
        ]
    )
    issues = _rule_ids(validate_record(record, taxonomy))
    assert "entity_attribute_pair_not_allowed" in issues


def test_unknown_entity_is_rejected(taxonomy):
    record = _record(
        opinions=[
            _explicit_opinion(
                entity="CHATBOT", attribute="GENERAL", category="CHATBOT#GENERAL"
            )
        ]
    )
    assert "entity_not_allowed" in _rule_ids(validate_record(record, taxonomy))


def test_legacy_flat_category_is_rejected(taxonomy):
    """A legacy-shaped category must not validate under the new schema."""
    record = _record(
        opinions=[
            _explicit_opinion(entity="APP", attribute="RELIABILITY", category="digital_banking")
        ]
    )
    issues = _rule_ids(validate_record(record, taxonomy))
    assert "category_composition_mismatch" in issues
    assert "category_not_in_taxonomy" in issues


def test_general_attribute_raises_a_monitoring_warning(taxonomy):
    """Requirements 9.14: GENERAL is allowed but must be monitored."""
    record = _record(
        opinions=[
            _explicit_opinion(entity="APP", attribute="GENERAL", category="APP#GENERAL")
        ]
    )
    issues = validate_record(record, taxonomy)
    assert _errors(issues) == []  # permitted
    warnings = [i for i in issues if i.severity == "warning"]
    assert "general_attribute_used" in {i.rule_id for i in warnings}


# ---------------------------------------------------------------------------
# Sentiment and intent label spaces (Requirements 10, 11)
# ---------------------------------------------------------------------------


def test_unknown_sentiment_is_rejected(taxonomy):
    record = _record(opinions=[_explicit_opinion(sentiment="very_negative")])
    assert "sentiment_not_allowed" in _rule_ids(validate_record(record, taxonomy))


@pytest.mark.parametrize("sentiment", SENTIMENT_LABELS)
def test_every_approved_sentiment_is_accepted(taxonomy, sentiment):
    record = _record(opinions=[_explicit_opinion(sentiment=sentiment)])
    assert _errors(validate_record(record, taxonomy)) == []


@pytest.mark.parametrize("intent", PRIMARY_INTENTS)
def test_every_approved_intent_is_accepted(taxonomy, intent):
    assert _errors(validate_record(_record(primary_intent=intent), taxonomy)) == []


def test_warning_as_primary_intent_is_rejected(taxonomy):
    """Requirements 11.7 and Section 27: warning is not a primary intent."""
    issues = validate_record(_record(primary_intent="warning"), taxonomy)
    assert "intent_not_allowed" in _rule_ids(issues)
    guidance = " ".join(i.fix_guidance for i in issues)
    assert "public_warning" in guidance


@pytest.mark.parametrize("legacy", ["compliment", "suggestion", "churn_signal"])
def test_legacy_intent_labels_are_rejected(taxonomy, legacy):
    assert "intent_not_allowed" in _rule_ids(
        validate_record(_record(primary_intent=legacy), taxonomy)
    )


def test_public_warning_true_with_complaint_intent_is_valid(taxonomy):
    """The flag preserves warnings while intent stays dominant (Req 11.7)."""
    record = _record(primary_intent="complaint", public_warning=True)
    assert _errors(validate_record(record, taxonomy)) == []


def test_public_warning_must_be_boolean(taxonomy):
    assert "public_warning_not_boolean" in _rule_ids(
        validate_record(_record(public_warning="yes"), taxonomy)
    )


def test_completed_record_requires_primary_intent(taxonomy):
    record = _record(annotation_status="completed", primary_intent=None)
    assert "completed_without_intent" in _rule_ids(validate_record(record, taxonomy))


def test_incomplete_record_may_omit_primary_intent(taxonomy):
    record = _record(annotation_status="not_started", primary_intent=None)
    assert "completed_without_intent" not in _rule_ids(
        validate_record(record, taxonomy)
    )


# ---------------------------------------------------------------------------
# Context fields (Requirements 12)
# ---------------------------------------------------------------------------


def test_no_context_token_is_accepted(taxonomy):
    record = _record(context_available=False, previous_text=NO_CONTEXT)
    assert _errors(validate_record(record, taxonomy)) == []


def test_null_previous_text_is_accepted_when_no_context(taxonomy):
    record = _record(context_available=False, previous_text=None)
    assert _errors(validate_record(record, taxonomy)) == []


def test_genuine_context_is_accepted(taxonomy):
    record = _record(
        context_available=True,
        previous_text="I have been a customer for ten years.",
        review_id="rev_1",
    )
    assert _errors(validate_record(record, taxonomy)) == []


def test_context_available_with_no_context_token_is_rejected(taxonomy):
    record = _record(context_available=True, previous_text=NO_CONTEXT)
    assert "context_available_without_text" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_context_available_with_null_text_is_rejected(taxonomy):
    record = _record(context_available=True, previous_text=None)
    assert "context_available_without_text" in _rule_ids(
        validate_record(record, taxonomy)
    )


def test_no_context_with_real_text_is_rejected(taxonomy):
    record = _record(context_available=False, previous_text="Some earlier sentence.")
    assert "no_context_with_text" in _rule_ids(validate_record(record, taxonomy))


def test_context_available_must_be_boolean(taxonomy):
    record = _record(context_available="true")
    assert "context_available_not_boolean" in _rule_ids(
        validate_record(record, taxonomy)
    )


# ---------------------------------------------------------------------------
# Record-level structure and privacy
# ---------------------------------------------------------------------------


def test_missing_mandatory_key_is_reported(taxonomy):
    data = record_to_dict(_record())
    del data["privacy_status"]
    record = record_from_dict(data)
    assert "missing_mandatory_key" in _rule_ids(validate_record(record, taxonomy))


def test_null_valued_optional_field_is_not_a_missing_key(taxonomy):
    """Requirements 8.1: unavailable source fields may be null."""
    record = _record(bank=None, review_id=None, thread_id=None, publish_year=None)
    assert "missing_mandatory_key" not in _rule_ids(validate_record(record, taxonomy))


@pytest.mark.parametrize("field_name", ["record_id", "source", "region", "text"])
def test_required_non_null_fields_are_enforced(taxonomy, field_name):
    record = _record(**{field_name: None})
    assert "required_field_null" in _rule_ids(validate_record(record, taxonomy))


def test_unknown_privacy_status_is_rejected(taxonomy):
    assert "privacy_status_not_allowed" in _rule_ids(
        validate_record(_record(privacy_status="maybe"), taxonomy)
    )


def test_unknown_annotation_status_is_rejected(taxonomy):
    assert "annotation_status_not_allowed" in _rule_ids(
        validate_record(_record(annotation_status="done"), taxonomy)
    )


def test_validator_never_mutates_the_record(taxonomy):
    record = _record(opinions=[_explicit_opinion()])
    before = record_to_dict(record)
    validate_record(record, taxonomy)
    assert record_to_dict(record) == before


def test_issues_never_leak_record_text(taxonomy):
    """Validation output must not echo potentially sensitive field values."""
    secret = "my account number is 123456789 and I am furious"
    record = _record(text=secret, primary_intent="warning", privacy_status="bogus")
    for issue in validate_record(record, taxonomy):
        assert secret not in issue.message
        assert secret not in issue.fix_guidance


def test_every_issue_carries_rule_id_and_fix_guidance(taxonomy):
    """Requirements Section 14 requires rule identifiers and fix guidance."""
    record = _record(primary_intent="warning", opinions=[_explicit_opinion(sentiment="bad")])
    issues = validate_record(record, taxonomy)
    assert issues
    for issue in issues:
        assert issue.rule_id
        assert issue.fix_guidance
        assert issue.severity in {"error", "warning"}
        assert issue.to_dict()["rule_id"] == issue.rule_id


# ---------------------------------------------------------------------------
# Corpus-level validation
# ---------------------------------------------------------------------------


def test_duplicate_record_ids_are_reported(taxonomy):
    records = [_record(record_id="dup"), _record(record_id="dup")]
    _, _, corpus_issues = validate_all(records, taxonomy)
    assert "duplicate_record_id" in {i.rule_id for i in corpus_issues}


def test_unique_record_ids_produce_no_corpus_issues(taxonomy):
    records = [_record(record_id="a"), _record(record_id="b")]
    valid, invalid, corpus_issues = validate_all(records, taxonomy)
    assert len(valid) == 2
    assert invalid == {}
    assert corpus_issues == []


def test_validate_all_separates_valid_from_invalid(taxonomy):
    records = [_record(record_id="ok"), _record(record_id="bad", primary_intent="warning")]
    valid, invalid, _ = validate_all(records, taxonomy)
    assert [r.record_id for r in valid] == ["ok"]
    assert "bad" in invalid


def test_warning_only_record_is_still_valid(taxonomy):
    """A GENERAL-attribute warning must not fail the record."""
    record = _record(
        record_id="general",
        opinions=[
            _explicit_opinion(entity="APP", attribute="GENERAL", category="APP#GENERAL")
        ],
    )
    valid, invalid, _ = validate_all([record], taxonomy)
    assert len(valid) == 1
    assert invalid == {}


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_record_round_trip_preserves_all_fields(taxonomy):
    record = _record(opinions=[_explicit_opinion(), _implicit_opinion()])
    restored = record_from_dict(record_to_dict(record))
    assert record_to_dict(restored) == record_to_dict(record)
    assert _errors(validate_record(restored, taxonomy)) == []


def test_serialised_record_contains_every_schema_key():
    data = record_to_dict(_record())
    for key in (
        "record_id",
        "source",
        "region",
        "bank",
        "review_id",
        "thread_id",
        "conversation_id",
        "publish_year",
        "text",
        "previous_text",
        "context_available",
        "duplicate_group",
        "leakage_group",
        "privacy_status",
        "primary_intent",
        "public_warning",
        "opinions",
        "annotation_status",
        "annotation_version",
        "annotation_notes",
    ):
        assert key in data


def test_serialised_opinion_contains_every_schema_key():
    data = record_to_dict(_record(opinions=[_explicit_opinion()]))
    opinion = data["opinions"][0]
    for key in (
        "target",
        "target_start",
        "target_end",
        "target_type",
        "entity",
        "attribute",
        "category",
        "opinion_phrase",
        "opinion_start",
        "opinion_end",
        "sentiment",
        "annotation_notes",
    ):
        assert key in opinion


def test_opinions_key_is_used_not_aspects():
    """The new schema must emit `opinions`, never the legacy `aspects`."""
    data = record_to_dict(_record(opinions=[_explicit_opinion()]))
    assert "opinions" in data
    assert "aspects" not in data


def test_jsonl_round_trip(tmp_path, taxonomy):
    records = [
        _record(record_id="a", opinions=[]),
        _record(record_id="b", opinions=[_explicit_opinion()]),
        _record(record_id="c", opinions=[_implicit_opinion(), _explicit_opinion()]),
    ]
    path = tmp_path / "records.jsonl"
    write_jsonl(records, path)

    restored = read_jsonl(path)
    assert len(restored) == 3
    assert [r.record_id for r in restored] == ["a", "b", "c"]
    assert len(restored[2].opinions) == 2

    valid, invalid, corpus_issues = validate_all(restored, taxonomy)
    assert len(valid) == 3
    assert invalid == {}
    assert corpus_issues == []


def test_write_jsonl_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "deeper" / "records.jsonl"
    write_jsonl([_record()], path)
    assert path.is_file()
