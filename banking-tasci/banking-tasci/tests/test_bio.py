"""Tests for the BIO_Converter (src/banking_tasci/data/bio.py).

Covers the ten scenarios enumerated in Requirement 20.6, each as an
explicit example plus (where applicable) a round-trip assertion:

 1. one-token aspect
 2. multi-token aspect
 3. two aspects in one text
 4. aspect adjacent to punctuation
 5. repeated aspect term appearing twice (only annotated occurrences tagged)
 6. text with no aspects (all O)
 7. subword tokenisation splitting a single word into multiple subwords
 8. attempted invalid partial-overlap input (rejected with ValueError)
 9. Unicode text (char offsets in Python string indices)
10. aspect at the very beginning or very end of the text

Validates: Requirements 20.1, 20.2, 20.3, 20.4, 20.5, 20.6
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import AspectSpan  # noqa: E402
from banking_tasci.data.bio import (  # noqa: E402
    IGNORE_INDEX,
    Token,
    apply_ignore_mask,
    bio_to_offsets,
    offsets_to_word_bio,
    round_trip,
    word_bio_to_subword_bio,
)


# ---------------------------------------------------------------------------
# Tokenizer helpers injected into the BIO_Converter (never imported by it).
# ---------------------------------------------------------------------------


def whitespace_tokenizer(text: str) -> list[Token]:
    """Return (word, start, end) tuples by scanning non-space runs.

    A "word" is a maximal run of non-whitespace characters; offsets are
    half-open [start, end) Python string indices.
    """
    tokens: list[Token] = []
    start = None
    for i, ch in enumerate(text):
        if ch.isspace():
            if start is not None:
                tokens.append((text[start:i], start, i))
                start = None
        elif start is None:
            start = i
    if start is not None:
        tokens.append((text[start:len(text)], start, len(text)))
    return tokens


def fixed_width_subword_tokenizer(word_tokens: list[Token], size: int = 3) -> list[Token]:
    """Synthetic subword tokenizer: split each word token into contiguous
    pieces of at most `size` characters, preserving correct char offsets.
    """
    subwords: list[Token] = []
    for text, start, end in word_tokens:
        pos = start
        while pos < end:
            piece_end = min(pos + size, end)
            subwords.append((text[pos - start:piece_end - start], pos, piece_end))
            pos = piece_end
    return subwords


def _span(text: str, start: int, end: int, category: str = "cards",
          sentiment: str = "neutral") -> AspectSpan:
    return AspectSpan(term=text[start:end], start=start, end=end,
                      category=category, sentiment=sentiment)


# ---------------------------------------------------------------------------
# Scenario 1: one-token aspect
# ---------------------------------------------------------------------------


def test_one_token_aspect():
    text = "the app crashed"
    tokens = whitespace_tokenizer(text)
    aspects = [_span(text, 4, 7)]  # "app"

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "B-ASP", "O"]
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 2: multi-token aspect
# ---------------------------------------------------------------------------


def test_multi_token_aspect():
    text = "the mobile app is slow"
    tokens = whitespace_tokenizer(text)
    aspects = [_span(text, 4, 14)]  # "mobile app"

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "B-ASP", "I-ASP", "O", "O"]
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 3: two aspects in one text
# ---------------------------------------------------------------------------


def test_two_aspects():
    text = "the app and the fees"
    tokens = whitespace_tokenizer(text)
    aspects = [_span(text, 4, 7), _span(text, 16, 20)]  # "app", "fees"

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "B-ASP", "O", "O", "B-ASP"]
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 4: aspect adjacent to punctuation
# ---------------------------------------------------------------------------


def test_aspect_adjacent_to_punctuation():
    # "app" is followed immediately by a comma; the whitespace token is
    # "app," so we annotate the whole token span to keep alignment.
    text = "the app, really"
    tokens = whitespace_tokenizer(text)
    assert tokens[1] == ("app,", 4, 8)
    aspects = [_span(text, 4, 8)]  # "app,"

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "B-ASP", "O"]
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 5: repeated aspect term appearing twice
# ---------------------------------------------------------------------------


def test_repeated_term_only_annotated_occurrence_tagged():
    text = "app good app bad"
    tokens = whitespace_tokenizer(text)
    # Only the SECOND "app" (offset 9-12) is annotated.
    aspects = [_span(text, 9, 12)]

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "O", "B-ASP", "O"]
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 6: text with no aspects
# ---------------------------------------------------------------------------


def test_no_aspects_all_O():
    text = "nothing to see here"
    tokens = whitespace_tokenizer(text)
    aspects: list[AspectSpan] = []

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "O", "O", "O"]
    assert bio_to_offsets(tokens, bio) == []
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 7: subword tokenisation splitting a single word
# ---------------------------------------------------------------------------


def test_subword_split_single_word():
    text = "the application works"
    word_tokens = whitespace_tokenizer(text)
    aspects = [_span(text, 4, 15)]  # "application"
    word_bio = offsets_to_word_bio(text, aspects, word_tokens)
    assert word_bio == ["O", "B-ASP", "O"]

    subword_tokens = fixed_width_subword_tokenizer(word_tokens, size=3)
    subword_bio = word_bio_to_subword_bio(word_tokens, word_bio, subword_tokens)

    # "application" (11 chars) splits into 4 subwords: B-ASP then 3 I-ASP.
    app_labels = [
        lbl for tok, lbl in zip(subword_tokens, subword_bio) if 4 <= tok[1] < 15
    ]
    assert app_labels == ["B-ASP", "I-ASP", "I-ASP", "I-ASP"]

    # Reconstruction from the subword labels recovers the original span.
    assert bio_to_offsets(subword_tokens, subword_bio) == [(4, 15)]


def test_apply_ignore_mask_marks_special_positions():
    subword_bio = ["O", "B-ASP", "I-ASP", "O"]
    is_special = [True, False, False, True]  # e.g. [CLS] ... [SEP]

    masked = apply_ignore_mask(subword_bio, is_special)
    assert masked == [IGNORE_INDEX, "B-ASP", "I-ASP", IGNORE_INDEX]


# ---------------------------------------------------------------------------
# Scenario 8: attempted invalid partial-overlap input
# ---------------------------------------------------------------------------


def test_invalid_partial_overlap_raises():
    text = "the mobile app crashed"
    tokens = whitespace_tokenizer(text)
    # Two spans that partially overlap: [4:14] "mobile app" and [11:14] "app".
    aspects = [_span(text, 4, 14), _span(text, 11, 14)]

    with pytest.raises(ValueError):
        offsets_to_word_bio(text, aspects, tokens)


# ---------------------------------------------------------------------------
# Scenario 9: Unicode text
# ---------------------------------------------------------------------------


def test_unicode_text_offsets():
    # Accented + non-Latin characters; offsets are Python string indices.
    text = "le café était naïve über"
    tokens = whitespace_tokenizer(text)
    # "café" occupies indices 3-7.
    assert text[3:7] == "café"
    aspects = [_span(text, 3, 7)]

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio[1] == "B-ASP"
    assert round_trip(text, aspects, whitespace_tokenizer)


# ---------------------------------------------------------------------------
# Scenario 10: aspect at the very beginning or very end of the text
# ---------------------------------------------------------------------------


def test_aspect_at_beginning():
    text = "cards are great"
    tokens = whitespace_tokenizer(text)
    aspects = [_span(text, 0, 5)]  # "cards"

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["B-ASP", "O", "O"]
    assert round_trip(text, aspects, whitespace_tokenizer)


def test_aspect_at_end():
    text = "great customer support"
    tokens = whitespace_tokenizer(text)
    aspects = [_span(text, 6, 22)]  # "customer support"

    bio = offsets_to_word_bio(text, aspects, tokens)
    assert bio == ["O", "B-ASP", "I-ASP"]
    assert round_trip(text, aspects, whitespace_tokenizer)
