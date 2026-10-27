"""Tests for the Context_Builder (src/banking_tasci/data/context.py).

Covers:
- `split_into_sentences` on representative multi-sentence review text.
- Req 16.3: first sentence of a multi-sentence review gets
  `previous_text="[NO_CONTEXT]"`, `context_available=False`.
- Req 16.2: non-first sentences get `previous_text` equal to the
  immediately preceding sentence, `context_available=True`.
- Req 16.7: two sentence-records built from two DIFFERENT review dicts
  are never linked to each other (the critical anti-leakage invariant).
- Req 16.4-16.6: `build_tweet_record` with `thread_map=None` (or no entry
  for this record) defaults to `[NO_CONTEXT]`/`False`; an explicit
  `thread_map` entry is used correctly.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.context import (  # noqa: E402
    NO_CONTEXT,
    build_review_sentence_records,
    build_tweet_record,
    split_into_sentences,
)


def _review_record(record_id: str, text: str) -> dict:
    return {
        "record_id": record_id,
        "source": "bank_reviews",
        "region": "international",
        "bank": "SBI",
        "rating": 4,
        "title": "Nice",
        "text": text,
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "thread_id": None,
        "created_at": "2020-03-21",
        "split": None,
    }


def _tweet_record(record_id: str, text: str) -> dict:
    return {
        "record_id": record_id,
        "source": "international_bank_tweets",
        "region": "international",
        "bank": None,
        "rating": None,
        "title": "",
        "text": text,
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "thread_id": None,
        "created_at": None,
        "split": None,
    }


# ---------------------------------------------------------------------------
# split_into_sentences
# ---------------------------------------------------------------------------

def test_split_into_sentences_two_sentences() -> None:
    text = "The mobile app is slow. But the support agent was helpful."
    sentences = split_into_sentences(text)
    assert sentences == [
        "The mobile app is slow.",
        "But the support agent was helpful.",
    ]


def test_split_into_sentences_single_sentence() -> None:
    assert split_into_sentences("Great service overall") == ["Great service overall"]


def test_split_into_sentences_empty_text() -> None:
    assert split_into_sentences("") == []
    assert split_into_sentences("   ") == []


def test_split_into_sentences_abbreviation_guard() -> None:
    text = "I spoke with Dr. Smith and it was fine."
    sentences = split_into_sentences(text)
    assert sentences == ["I spoke with Dr. Smith and it was fine."]


def test_split_into_sentences_question_and_exclamation() -> None:
    text = "Why is this so slow? It is unacceptable! I want a refund."
    sentences = split_into_sentences(text)
    assert sentences == [
        "Why is this so slow?",
        "It is unacceptable!",
        "I want a refund.",
    ]


# ---------------------------------------------------------------------------
# build_review_sentence_records: first-sentence isolation (Req 16.3) and
# non-first-sentence linkage (Req 16.2).
# ---------------------------------------------------------------------------

def test_first_sentence_has_no_context() -> None:
    review = _review_record(
        "rev1", "The mobile app is slow. But the support agent was helpful."
    )
    records = build_review_sentence_records(review)

    assert len(records) == 2
    first = records[0]
    assert first["text"] == "The mobile app is slow."
    assert first["previous_text"] == NO_CONTEXT
    assert first["context_available"] is False
    assert first["source_record_id"] == "rev1"


def test_non_first_sentence_linked_to_immediate_predecessor() -> None:
    review = _review_record(
        "rev1", "The mobile app is slow. But the support agent was helpful."
    )
    records = build_review_sentence_records(review)

    second = records[1]
    assert second["text"] == "But the support agent was helpful."
    assert second["previous_text"] == "The mobile app is slow."
    assert second["context_available"] is True
    assert second["source_record_id"] == "rev1"


def test_three_sentence_review_chains_correctly() -> None:
    review = _review_record(
        "rev2",
        "Waited an hour. The teller was rude. Never coming back.",
    )
    records = build_review_sentence_records(review)

    assert len(records) == 3
    assert records[0]["previous_text"] == NO_CONTEXT
    assert records[0]["context_available"] is False
    assert records[1]["previous_text"] == "Waited an hour."
    assert records[1]["context_available"] is True
    assert records[2]["previous_text"] == "The teller was rude."
    assert records[2]["context_available"] is True
    assert all(r["source_record_id"] == "rev2" for r in records)


def test_single_sentence_review_has_no_context() -> None:
    review = _review_record("rev3", "Great service overall")
    records = build_review_sentence_records(review)

    assert len(records) == 1
    assert records[0]["previous_text"] == NO_CONTEXT
    assert records[0]["context_available"] is False


def test_sentence_records_get_distinct_deterministic_record_ids() -> None:
    review = _review_record(
        "rev2",
        "Waited an hour. The teller was rude. Never coming back.",
    )
    records_run1 = build_review_sentence_records(review)
    records_run2 = build_review_sentence_records(review)

    ids_run1 = [r["record_id"] for r in records_run1]
    ids_run2 = [r["record_id"] for r in records_run2]

    # Every emitted sentence-level record has its own distinct id.
    assert len(set(ids_run1)) == len(ids_run1) == 3
    # None of them collide with the original review's record_id.
    assert "rev2" not in ids_run1
    # Deterministic and stable across repeated runs on the same input.
    assert ids_run1 == ids_run2


# ---------------------------------------------------------------------------
# Req 16.7: the critical anti-leakage invariant — two records built from
# two DIFFERENT review dicts are never linked to each other.
# ---------------------------------------------------------------------------

def test_different_reviews_are_never_linked_as_context() -> None:
    review_a = _review_record(
        "revA", "This is review A first sentence. This is review A last sentence."
    )
    review_b = _review_record(
        "revB", "This is review B first sentence. This is review B last sentence."
    )

    records_a = build_review_sentence_records(review_a)
    records_b = build_review_sentence_records(review_b)

    review_b_first_sentence_record = records_b[0]

    # Review B's first sentence must never receive review A's last
    # sentence (or any of review A's text) as previous_text.
    assert review_b_first_sentence_record["previous_text"] == NO_CONTEXT
    assert review_b_first_sentence_record["context_available"] is False
    assert review_b_first_sentence_record["previous_text"] != records_a[-1]["text"]

    # Sanity: every record from B carries only B's record_id as
    # source_record_id, never A's.
    assert all(r["source_record_id"] == "revB" for r in records_b)
    assert all(r["source_record_id"] == "revA" for r in records_a)


# ---------------------------------------------------------------------------
# build_tweet_record: Req 16.4-16.6
# ---------------------------------------------------------------------------

def test_tweet_record_defaults_to_no_context_with_none_thread_map() -> None:
    tweet = _tweet_record("tw1", "My card got blocked")
    record = build_tweet_record(tweet, thread_map=None)

    assert record["previous_text"] == NO_CONTEXT
    assert record["context_available"] is False


def test_tweet_record_defaults_to_no_context_when_thread_map_has_no_entry() -> None:
    tweet = _tweet_record("tw1", "My card got blocked")
    thread_map = {"some_other_id": "An unrelated preceding message"}
    record = build_tweet_record(tweet, thread_map=thread_map)

    assert record["previous_text"] == NO_CONTEXT
    assert record["context_available"] is False


def test_tweet_record_uses_explicit_thread_map_entry() -> None:
    tweet = _tweet_record("tw2", "Any update on my complaint?")
    thread_map = {"tw2": "We are looking into your case."}
    record = build_tweet_record(tweet, thread_map=thread_map)

    assert record["previous_text"] == "We are looking into your case."
    assert record["context_available"] is True


def test_tweet_record_never_uses_unrelated_tweet_as_context() -> None:
    tweet_x = _tweet_record("twX", "Completely unrelated tweet content")
    tweet_y = _tweet_record("twY", "My transfer failed again")

    # No thread_map entry for twY; even though tweet_x exists elsewhere in
    # the dataset, build_tweet_record has no access to it and must not
    # invent a relationship.
    record_y = build_tweet_record(tweet_y, thread_map=None)

    assert record_y["previous_text"] == NO_CONTEXT
    assert record_y["previous_text"] != tweet_x["text"]
    assert record_y["context_available"] is False
