"""Tests for the Anonymisation_Module (src/banking_tasci/data/anonymise.py).

Covers:
- Req 6.1-6.6: fixed-example smoke tests for each replacement token, plus
  Property 5 (sensitive-pattern replacement completeness/consistency).
- Req 6.7: negation/intensifier words preserved (Property 6).
- Req 6.8: hashtag bodies survive without the leading `#` (Property 7).
- Req 6.9: audit reports counts only, never original values (Property 8).
- Req 6.10: a replacement failure halts processing and raises
  AnonymisationError without returning partially-anonymised text.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import Config, load_config  # noqa: E402
from banking_tasci.data.anonymise import (  # noqa: E402
    INTENSIFIER_WORDS,
    NEGATION_WORDS,
    REPLACEMENT_TOKENS,
    AnonymisationAudit,
    AnonymisationError,
    anonymise_batch,
    anonymise_text,
)

_BASE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "base.yaml"


def _make_cfg(replace_amounts: bool = False) -> Config:
    """Build a real `Config` from `configs/base.yaml`, optionally toggling
    `anonymise.replace_amounts`."""
    return load_config(_BASE_CONFIG_PATH, overrides={"anonymise": {"replace_amounts": replace_amounts}})


# ---------------------------------------------------------------------------
# Unit tests: one fixed-example smoke test per replacement token (Req 6.6.x)
# ---------------------------------------------------------------------------

def test_smoke_email_replaced_with_token() -> None:
    text, audit = anonymise_text("Contact me at jane.doe@example.com please", _make_cfg())
    assert text == "Contact me at [EMAIL] please"
    assert audit.to_dict()["email"] == 1


def test_smoke_url_replaced_with_token() -> None:
    text, audit = anonymise_text("See https://example.com/path for details", _make_cfg())
    assert text == "See [URL] for details"
    assert audit.to_dict()["url"] == 1


def test_smoke_mention_replaced_with_token() -> None:
    text, audit = anonymise_text("Thanks @jsmith for the help", _make_cfg())
    assert text == "Thanks [USER] for the help"
    assert audit.to_dict()["mention"] == 1


def test_smoke_account_or_reference_replaced_with_token() -> None:
    text, audit = anonymise_text("My account number is 123456789 thanks", _make_cfg())
    assert text == "My account number is [ACCOUNT_OR_REFERENCE] thanks"
    assert audit.to_dict()["account_or_reference"] == 1


def test_smoke_phone_replaced_with_token() -> None:
    text, audit = anonymise_text("Call me on 1234567 today", _make_cfg())
    assert text == "Call me on [PHONE] today"
    assert audit.to_dict()["phone"] == 1


# ---------------------------------------------------------------------------
# Req 11.1-11.5: positive tests for each corrected phone format.
# ---------------------------------------------------------------------------

def test_phone_hyphen_separated_replaced_with_token() -> None:
    text, audit = anonymise_text("Call 555-123-4567 now", _make_cfg())
    assert text == "Call [PHONE] now"
    assert audit.to_dict()["phone"] == 1


def test_phone_space_separated_replaced_with_token() -> None:
    text, audit = anonymise_text("Call 555 123 4567 now", _make_cfg())
    assert text == "Call [PHONE] now"
    assert audit.to_dict()["phone"] == 1


def test_phone_international_space_separated_replaced_with_token() -> None:
    text, audit = anonymise_text("Call +27 82 123 4567 now", _make_cfg())
    assert text == "Call [PHONE] now"
    assert audit.to_dict()["phone"] == 1


def test_phone_international_hyphen_separated_replaced_with_token() -> None:
    text, audit = anonymise_text("Call +27-82-123-4567 now", _make_cfg())
    assert text == "Call [PHONE] now"
    assert audit.to_dict()["phone"] == 1


def test_phone_parenthesised_area_code_replaced_with_token() -> None:
    text, audit = anonymise_text("Call (011) 123 4567 now", _make_cfg())
    assert text == "Call [PHONE] now"
    assert audit.to_dict()["phone"] == 1


def test_phone_unbroken_digit_run_is_anonymised() -> None:
    # 0821234567 is a 10-digit unbroken run. It also satisfies the
    # existing `account_reference_pattern` (`\b\d{9,}\b`), which is applied
    # before `phone` in the fixed replacement order, so it is anonymised as
    # [ACCOUNT_OR_REFERENCE] rather than [PHONE]. Either way, the raw
    # digits never reach annotators unredacted.
    text, audit = anonymise_text("Call 0821234567 now", _make_cfg())
    assert text == "Call [ACCOUNT_OR_REFERENCE] now"
    assert audit.to_dict()["account_or_reference"] == 1
    assert audit.to_dict()["phone"] == 0


# ---------------------------------------------------------------------------
# Req 11.7: negative tests confirming amounts and ISO dates are not
# misclassified as [PHONE].
# ---------------------------------------------------------------------------

def test_currency_amount_not_replaced_with_phone_when_amounts_disabled() -> None:
    text, audit = anonymise_text("It cost $1,250.00 total", _make_cfg(replace_amounts=False))
    assert text == "It cost $1,250.00 total"
    assert audit.to_dict()["phone"] == 0
    assert audit.to_dict()["amount"] == 0


def test_currency_amount_replaced_with_amount_token_not_phone_when_enabled() -> None:
    text, audit = anonymise_text("It cost $1,250.00 total", _make_cfg(replace_amounts=True))
    assert text == "It cost [AMOUNT] total"
    assert audit.to_dict()["phone"] == 0
    assert audit.to_dict()["amount"] == 1


def test_iso_date_not_replaced_with_phone() -> None:
    text, audit = anonymise_text("Signed on 2020-03-21 by the customer", _make_cfg())
    assert text == "Signed on 2020-03-21 by the customer"
    assert audit.to_dict()["phone"] == 0


def test_iso_date_not_replaced_with_phone_when_amounts_enabled() -> None:
    text, audit = anonymise_text("Signed on 2020-03-21 by the customer", _make_cfg(replace_amounts=True))
    assert text == "Signed on 2020-03-21 by the customer"
    assert audit.to_dict()["phone"] == 0
    assert audit.to_dict()["amount"] == 0


def test_smoke_amount_replaced_with_token_when_enabled() -> None:
    text, audit = anonymise_text("It cost $42.50 in total", _make_cfg(replace_amounts=True))
    assert text == "It cost [AMOUNT] in total"
    assert audit.to_dict()["amount"] == 1


def test_amount_not_replaced_when_disabled() -> None:
    text, audit = anonymise_text("It cost $42.50 in total", _make_cfg(replace_amounts=False))
    assert text == "It cost $42.50 in total"
    assert audit.to_dict()["amount"] == 0


def test_hashtag_body_retained_without_hash_symbol() -> None:
    text, _ = anonymise_text("Loving the #NewApp update", _make_cfg())
    assert text == "Loving the NewApp update"


def test_negation_and_intensifier_words_untouched() -> None:
    text, _ = anonymise_text("This is not very good, email me at a@b.com", _make_cfg())
    assert "not" in text.split()
    assert "very" in text.split()


# ---------------------------------------------------------------------------
# Req 6.10: replacement-failure edge case (mocked) halts processing and
# raises AnonymisationError without returning partially-anonymised text.
# ---------------------------------------------------------------------------

def test_replacement_failure_raises_anonymisation_error_without_partial_result() -> None:
    with patch(
        "banking_tasci.data.anonymise._apply_replacement",
        side_effect=RuntimeError("simulated replacement failure"),
    ):
        with pytest.raises(AnonymisationError):
            anonymise_text("Contact me at jane.doe@example.com please", _make_cfg())


def test_replacement_failure_in_batch_halts_that_text() -> None:
    cfg = _make_cfg()
    with patch(
        "banking_tasci.data.anonymise._apply_replacement",
        side_effect=RuntimeError("simulated replacement failure"),
    ):
        with pytest.raises(AnonymisationError):
            anonymise_batch(["hello world", "email a@b.com here"], cfg)


# ---------------------------------------------------------------------------
# AnonymisationAudit unit tests (merge/to_dict)
# ---------------------------------------------------------------------------

def test_audit_merge_sums_counts() -> None:
    a = AnonymisationAudit({"email": 1, "url": 2})
    b = AnonymisationAudit({"email": 3, "phone": 1})
    merged = a.merge(b)
    assert merged.to_dict()["email"] == 4
    assert merged.to_dict()["url"] == 2
    assert merged.to_dict()["phone"] == 1


def test_anonymise_batch_combines_audits() -> None:
    cfg = _make_cfg()
    texts = ["a@b.com hi", "another a2@b.com hi", "no sensitive content here"]
    anonymised, audit = anonymise_batch(texts, cfg)
    assert anonymised[0] == "[EMAIL] hi"
    assert anonymised[1] == "another [EMAIL] hi"
    assert anonymised[2] == "no sensitive content here"
    assert audit.to_dict()["email"] == 2


# ---------------------------------------------------------------------------
# Strategies for embedding valid sensitive-pattern instances.
# ---------------------------------------------------------------------------

_safe_word = st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu")), min_size=1, max_size=6)
_safe_surrounding = st.lists(_safe_word, min_size=0, max_size=4).map(lambda words: " ".join(words))


_ascii_lower = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6)


def _email_strategy():
    local = _ascii_lower
    domain = _ascii_lower
    tld = st.sampled_from(["com", "org", "net", "co"])
    return st.tuples(local, domain, tld).map(lambda t: f"{t[0]}@{t[1]}.{t[2]}")


def _url_strategy():
    domain = _ascii_lower
    tld = st.sampled_from(["com", "org", "net"])
    path = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=0, max_size=6)
    return st.tuples(domain, tld, path).map(lambda t: f"https://{t[0]}.{t[1]}/{t[2]}" if t[2] else f"https://{t[0]}.{t[1]}")


def _mention_strategy():
    handle = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=8)
    return handle.map(lambda h: f"@{h}")


def _account_reference_strategy():
    # account_reference_pattern in configs/base.yaml: \b\d{9,}\b
    return st.text(alphabet="0123456789", min_size=9, max_size=15)


def _phone_strategy():
    # phone_pattern in configs/base.yaml also matches bare 7-10 digit runs;
    # restrict to 7-8 digits here so this doesn't also satisfy the
    # account/reference pattern (>=9 digits), which is applied first.
    return st.text(alphabet="0123456789", min_size=7, max_size=8)


def _amount_strategy():
    symbol = st.sampled_from(["$", "£", "€"])
    whole = st.integers(min_value=1, max_value=999999).map(str)
    cents = st.integers(min_value=0, max_value=99).map(lambda c: f".{c:02d}")
    has_cents = st.booleans()
    return st.tuples(symbol, whole, cents, has_cents).map(
        lambda t: f"{t[0]}{t[1]}{t[2] if t[3] else ''}"
    )


_PATTERN_STRATEGIES = {
    "email": _email_strategy(),
    "url": _url_strategy(),
    "mention": _mention_strategy(),
    "account_or_reference": _account_reference_strategy(),
    "phone": _phone_strategy(),
    "amount": _amount_strategy(),
}


def _embed(instance: str, prefix: str, suffix: str) -> str:
    parts = [p for p in (prefix, instance, suffix) if p]
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Property 5: Sensitive-pattern replacement is complete and token-consistent.
# Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    pattern_key=st.sampled_from(list(_PATTERN_STRATEGIES.keys())),
    prefix=_safe_surrounding,
    suffix=_safe_surrounding,
    data=st.data(),
)
# Feature: banking-tasci-pipeline, Property 5: Sensitive-pattern replacement is complete and token-consistent
def test_property_sensitive_pattern_replacement_complete_and_consistent(pattern_key, prefix, suffix, data) -> None:
    instance = data.draw(_PATTERN_STRATEGIES[pattern_key])
    text = _embed(instance, prefix, suffix)
    cfg = _make_cfg(replace_amounts=True)

    anonymised, audit = anonymise_text(text, cfg)

    token = REPLACEMENT_TOKENS[pattern_key]
    assert token in anonymised
    assert instance not in anonymised
    assert audit.to_dict()[pattern_key] >= 1


# ---------------------------------------------------------------------------
# Property 6: Negation and intensifier words are preserved verbatim.
# Validates: Requirements 6.7
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    word=st.sampled_from(NEGATION_WORDS + INTENSIFIER_WORDS),
    pattern_key=st.sampled_from(list(_PATTERN_STRATEGIES.keys())),
    data=st.data(),
)
# Feature: banking-tasci-pipeline, Property 6: Negation and intensifier words are preserved verbatim
def test_property_negation_and_intensifier_words_preserved(word, pattern_key, data) -> None:
    instance = data.draw(_PATTERN_STRATEGIES[pattern_key])
    text = f"{word} {instance}"
    cfg = _make_cfg(replace_amounts=True)

    anonymised, _ = anonymise_text(text, cfg)

    assert word in anonymised.split()


# ---------------------------------------------------------------------------
# Property 7: Hashtag bodies survive anonymisation without the `#`.
# Validates: Requirements 6.8
# ---------------------------------------------------------------------------

_hashtag_body = st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=10)


@settings(max_examples=100)
@given(body=_hashtag_body, prefix=_safe_surrounding, suffix=_safe_surrounding)
# Feature: banking-tasci-pipeline, Property 7: Hashtag bodies survive anonymisation without the #
def test_property_hashtag_body_survives_without_hash(body, prefix, suffix) -> None:
    hashtag = f"#{body}"
    text = _embed(hashtag, prefix, suffix)
    cfg = _make_cfg()

    anonymised, _ = anonymise_text(text, cfg)

    assert body in anonymised.split()
    assert f"#{body}" not in anonymised


# ---------------------------------------------------------------------------
# Property 8: Anonymisation audit reports counts only, never original values.
# Validates: Requirements 6.9
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    pattern_key=st.sampled_from(list(_PATTERN_STRATEGIES.keys())),
    instances=st.lists(st.integers(min_value=1, max_value=3), min_size=1, max_size=5),
    data=st.data(),
)
# Feature: banking-tasci-pipeline, Property 8: Anonymisation audit reports counts only, never original values
def test_property_audit_counts_only_no_original_values(pattern_key, instances, data) -> None:
    cfg = _make_cfg(replace_amounts=True)
    drawn_instances = [data.draw(_PATTERN_STRATEGIES[pattern_key]) for _ in instances]
    texts = [f"text {i}: {inst} end" for i, inst in enumerate(drawn_instances)]

    anonymised_texts, audit = anonymise_batch(texts, cfg)

    assert audit.to_dict()[pattern_key] == len(drawn_instances)

    serialized = repr(audit.to_dict())
    for inst in drawn_instances:
        assert inst not in serialized
        assert all(inst not in text for text in anonymised_texts)
