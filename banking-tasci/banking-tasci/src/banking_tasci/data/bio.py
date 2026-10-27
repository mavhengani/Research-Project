"""Deterministic BIO conversion (BIO_Converter) for the banking-tasci
annotation pipeline.

This module converts between character-offset aspect spans and token-level
BIO labels (`B-ASP`, `I-ASP`, `O`) and reconstructs character spans from
predicted BIO labels. It is deliberately **tokenizer-agnostic**: it never
imports `transformers` or any specific tokenizer. Instead, the caller
injects a tokenizer callable and passes plain `Token = (text, start, end)`
tuples, so the same logic works with a trivial whitespace tokenizer in
tests and a real subword tokenizer in a later phase.

Requirements:
- 20.1: `offsets_to_word_bio` — one BIO label per word-level token.
- 20.2: `word_bio_to_subword_bio` — word-level BIO to subword-level BIO,
  with `B-ASP` only on the first subword of a span-beginning token.
- 20.3: `apply_ignore_mask` — `-100` for special/padding positions.
- 20.4: `bio_to_offsets` — reconstruct (start, end) character spans from
  predicted BIO labels.
- 20.5: `round_trip` — offsets -> word BIO -> subword BIO -> offsets is an
  identity on the aspect (start, end) set when tokenisation aligns.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from banking_tasci.data.annotations import AspectSpan

# A token is a (text, start, end) tuple with half-open character offsets
# [start, end) into the originating `text`. Word- or subword-level.
Token = tuple[str, int, int]

B_ASP = "B-ASP"
I_ASP = "I-ASP"
O = "O"
IGNORE_INDEX = -100


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _aspect_bounds(aspects: "list[AspectSpan]") -> list[tuple[int, int]]:
    """Extract (start, end) integer bounds from aspect spans, rejecting
    overlaps defensively (Req 20.6 invalid-overlap scenario).

    Raises ValueError if any two aspects overlap. Two half-open spans
    [a_start, a_end) and [b_start, b_end) overlap when
    `a_start < b_end and b_start < a_end`.
    """
    bounds = [(int(a.start), int(a.end)) for a in aspects]
    ordered = sorted(bounds)
    for i in range(1, len(ordered)):
        prev_start, prev_end = ordered[i - 1]
        cur_start, cur_end = ordered[i]
        if cur_start < prev_end and prev_start < cur_end:
            raise ValueError(
                f"Overlapping aspect spans are not allowed: "
                f"[{prev_start}:{prev_end}] and [{cur_start}:{cur_end}]"
            )
    return bounds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def offsets_to_word_bio(
    text: str, aspects: "list[AspectSpan]", tokens: list[Token]
) -> list[str]:
    """Return one BIO label per token in `tokens` (Req 20.1).

    A token `(t, s, e)` is labelled:
    - ``B-ASP`` if its start offset equals some aspect span's start;
    - ``I-ASP`` if it falls inside an aspect span (``s >= aspect.start`` and
      ``e <= aspect.end``) but is not that span's first token;
    - ``O`` otherwise.

    Raises ValueError if two aspects in the input overlap each other
    (defensive rejection of the invalid partial-overlap scenario, Req 20.6),
    even though overlaps should already have been rejected upstream by the
    Annotation_Validator.
    """
    bounds = _aspect_bounds(aspects)
    starts = {b[0] for b in bounds}

    labels: list[str] = []
    for _text, start, end in tokens:
        if start in starts:
            labels.append(B_ASP)
            continue
        inside = any(
            a_start <= start and end <= a_end for a_start, a_end in bounds
        )
        labels.append(I_ASP if inside else O)
    return labels


def word_bio_to_subword_bio(
    word_tokens: list[Token], word_bio: list[str], subword_tokens: list[Token]
) -> list[str]:
    """Project word-level BIO labels onto a subword tokenization (Req 20.2).

    Each subword is assigned the label of the word token it falls within.
    The first subword of a word labelled ``B-ASP`` gets ``B-ASP``; subsequent
    subwords of that same word get ``I-ASP``. All subwords of an ``I-ASP``
    word get ``I-ASP``. All subwords of an ``O`` word get ``O``.

    A subword that does not fall within any word token (e.g. a special
    token spanning no word) is labelled ``O``.
    """
    if len(word_tokens) != len(word_bio):
        raise ValueError(
            "word_tokens and word_bio must have the same length "
            f"({len(word_tokens)} != {len(word_bio)})"
        )

    seen_word: set[int] = set()
    labels: list[str] = []
    for _text, start, end in subword_tokens:
        word_idx = _owning_word_index(word_tokens, start, end)
        if word_idx is None:
            labels.append(O)
            continue

        word_label = word_bio[word_idx]
        if word_label == O:
            labels.append(O)
        elif word_label == B_ASP:
            if word_idx in seen_word:
                labels.append(I_ASP)
            else:
                labels.append(B_ASP)
        else:  # I_ASP word — every subword is a continuation
            labels.append(I_ASP)
        seen_word.add(word_idx)
    return labels


def _owning_word_index(
    word_tokens: list[Token], start: int, end: int
) -> int | None:
    """Return the index of the word token that fully contains the subword
    span [start, end), or None if no word token contains it."""
    for idx, (_text, w_start, w_end) in enumerate(word_tokens):
        if w_start <= start and end <= w_end:
            return idx
    return None


def apply_ignore_mask(
    subword_bio: list[str], is_special_or_padding: list[bool]
) -> list[int | str]:
    """Return a per-position label list where position ``i`` is the integer
    ``-100`` when ``is_special_or_padding[i]`` is True (Req 20.3), and the
    original BIO string label otherwise.

    ``-100`` is the ignore sentinel used during loss computation for
    ``[CLS]``/``[SEP]``/padding (and any position the caller marks as
    special). The caller resolves the retained BIO strings to integer ids
    via its own label map.
    """
    if len(subword_bio) != len(is_special_or_padding):
        raise ValueError(
            "subword_bio and is_special_or_padding must have the same length "
            f"({len(subword_bio)} != {len(is_special_or_padding)})"
        )
    return [
        IGNORE_INDEX if ignored else label
        for label, ignored in zip(subword_bio, is_special_or_padding)
    ]


def bio_to_offsets(
    subword_tokens: list[Token], predicted_bio: list[str]
) -> list[tuple[int, int]]:
    """Reconstruct (start, end) character spans from predicted BIO labels
    over tokens with known character offsets (Req 20.4).

    A ``B-ASP`` starts a new span; following ``I-ASP`` tokens extend it; ``O``
    ends the current span. Each reconstructed span's start is the ``B-ASP``
    token's start offset and its end is the end offset of the last
    contiguous ``I-ASP`` token (or the ``B-ASP`` token itself if none
    follow). A leading ``I-ASP`` with no active span defensively begins a new
    span so predictions are never silently dropped.
    """
    if len(subword_tokens) != len(predicted_bio):
        raise ValueError(
            "subword_tokens and predicted_bio must have the same length "
            f"({len(subword_tokens)} != {len(predicted_bio)})"
        )

    spans: list[tuple[int, int]] = []
    cur_start: int | None = None
    cur_end: int | None = None

    for (_text, start, end), label in zip(subword_tokens, predicted_bio):
        if label == B_ASP:
            if cur_start is not None:
                spans.append((cur_start, cur_end))  # type: ignore[arg-type]
            cur_start, cur_end = start, end
        elif label == I_ASP:
            if cur_start is None:
                cur_start, cur_end = start, end
            else:
                cur_end = end
        else:  # O or any non-aspect label
            if cur_start is not None:
                spans.append((cur_start, cur_end))  # type: ignore[arg-type]
                cur_start, cur_end = None, None

    if cur_start is not None:
        spans.append((cur_start, cur_end))  # type: ignore[arg-type]
    return spans


def round_trip(
    text: str,
    aspects: "list[AspectSpan]",
    tokenizer_fn: Callable[[str], list[Token]],
) -> bool:
    """Return True when a full offsets -> BIO -> offsets round trip
    reproduces the input aspects' (start, end) set exactly (Req 20.5).

    The injected ``tokenizer_fn`` tokenizes ``text`` into ``Token`` tuples;
    those tokens are treated as their own subwords (identity subword
    tokenization) so this exercises `offsets_to_word_bio`,
    `word_bio_to_subword_bio`, and `bio_to_offsets` together.
    """
    tokens = tokenizer_fn(text)
    word_bio = offsets_to_word_bio(text, aspects, tokens)
    subword_bio = word_bio_to_subword_bio(tokens, word_bio, tokens)
    reconstructed = bio_to_offsets(tokens, subword_bio)

    expected = {(int(a.start), int(a.end)) for a in aspects}
    return set(reconstructed) == expected
