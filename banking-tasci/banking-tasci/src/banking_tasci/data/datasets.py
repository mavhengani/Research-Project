"""Common supervised-learning data loaders for the banking-tasci baselines
(Phase 3A, Requirements 32 and 38).

This module turns validated gold ``AnnotationRecord``s (produced by
``annotations.read_jsonl`` + ``annotations.validate_all``) into model-ready
examples for each task:

- ``build_intent_examples`` — one example per gold-labelled record, carrying
  the current text, optional ``previous_text`` (only when
  ``context_available`` is True), a ``context_available`` flag, the encoded
  gold ``intent`` id, and the originating ``record_id`` (Req 32.1).
- ``build_sentiment_examples`` — exactly one instance per gold ``AspectSpan``
  (a 3-aspect record yields 3 instances), each carrying the full text, the
  exact gold span offsets, the term, category, a ``[ASP]``/``[/ASP]``-marked
  text, an aspect mask, the encoded gold ``sentiment`` id, and the
  originating ``record_id`` (Req 32.2, 38).
- ``build_bio_examples`` — token ids, attention mask, BIO labels aligned to
  (sub)word tokens via ``bio.py`` with ``-100`` on padding/ignored positions,
  offset mappings, and the originating ``record_id``; single-window
  right-truncation to ``max_seq_length`` with removed aspects reported in
  ``dropped_aspects`` (Req 32.3-32.6).

Design guardrails:
- Labels are derived ONLY from explicit gold fields; records lacking a gold
  label are skipped, so the loaders can never be "accidentally" trained on
  the unannotated pilot (Req 32.8).
- This module MUST NOT import ``transformers``. A tokenizer callable
  ``tokenizer_fn`` is injected by the caller (a whitespace tokenizer in
  tests; a subword tokenizer with offset mapping in the BERT path).
- All BIO logic is delegated to ``bio.py`` — this module never re-implements
  BIO alignment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from banking_tasci.data.annotations import (
    ASPECT_SENTIMENTS,
    INTENT_LABELS,
    AnnotationRecord,
    AspectSpan,
)
from banking_tasci.data import bio
from banking_tasci.data.bio import IGNORE_INDEX, Token

# A tokenizer callable returns a list of (token_text, char_start, char_end)
# tuples with half-open [start, end) character offsets into the input text.
TokenizerFn = Callable[[str], list[Token]]

# Aspect-marking convention (Req 38.1).
ASP_OPEN = "[ASP]"
ASP_CLOSE = "[/ASP]"

# Intent input rendering modes (Req 32.1, Part 7). ``current_only`` feeds just
# the current text; ``previous_plus_current`` prepends the genuine previous
# turn (only when the record actually has context available) — it never uses
# the previous CSV row as context.
INTENT_MODE_CURRENT_ONLY = "current_only"
INTENT_MODE_PREVIOUS_PLUS_CURRENT = "previous_plus_current"
INTENT_MODES = (INTENT_MODE_CURRENT_ONLY, INTENT_MODE_PREVIOUS_PLUS_CURRENT)

# Sentinel used when a previous turn is absent (mirrors the ingestion layer).
NO_CONTEXT = "[NO_CONTEXT]"

# Fixed BIO tag -> id map (Req 32.4 / 20.x). Shared, stable label space.
BIO_LABEL_MAP: dict[str, int] = {bio.O: 0, bio.B_ASP: 1, bio.I_ASP: 2}


# ---------------------------------------------------------------------------
# Label maps built from the fixed constants in annotations.py
# ---------------------------------------------------------------------------


def build_intent_label_map() -> dict[str, int]:
    """Return the fixed ``intent -> id`` map from ``INTENT_LABELS`` (stable,
    shared label space)."""
    return {label: idx for idx, label in enumerate(INTENT_LABELS)}


def build_sentiment_label_map() -> dict[str, int]:
    """Return the fixed ``sentiment -> id`` map from ``ASPECT_SENTIMENTS``."""
    return {label: idx for idx, label in enumerate(ASPECT_SENTIMENTS)}


def build_bio_label_map() -> dict[str, int]:
    """Return the fixed BIO ``tag -> id`` map ``{O: 0, B-ASP: 1, I-ASP: 2}``."""
    return dict(BIO_LABEL_MAP)


# ---------------------------------------------------------------------------
# Aspect marking (Requirement 38)
# ---------------------------------------------------------------------------


def mark_aspect(text: str, start: int, end: int) -> str:
    """Return ``text`` with ``'[ASP] '`` inserted immediately before ``start``
    and ``' [/ASP]'`` inserted immediately after ``end``, marking exactly the
    one target span and preserving every other character (Req 38.1, 38.3).

    Raises ``ValueError`` for out-of-bounds or inverted offsets so callers
    never emit a silently corrupt marked text.
    """
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool):
        raise ValueError("start and end must be integers")
    if start < 0 or end > len(text) or start >= end:
        raise ValueError(
            f"mark_aspect got an out-of-bounds or invalid span [{start}:{end}] "
            f"for text of length {len(text)}"
        )
    return f"{text[:start]}{ASP_OPEN} {text[start:end]} {ASP_CLOSE}{text[end:]}"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IntentExample:
    record_id: str
    text: str
    previous_text: str | None
    context_available: bool
    label_id: int


def render_intent_text(example: "IntentExample", mode: str = INTENT_MODE_CURRENT_ONLY) -> str:
    """Render the model-input string for an ``IntentExample`` under ``mode``.

    - ``current_only`` returns just the current text (Req 32.1).
    - ``previous_plus_current`` prepends the genuine previous turn when the
      record has context available, otherwise the ``[NO_CONTEXT]`` sentinel.
      It NEVER fabricates context from an unrelated (e.g. previous CSV) row —
      ``previous_text`` is only populated by the loader when
      ``context_available`` is True.

    Raises ``ValueError`` for an unknown mode so a typo can never silently fall
    back to current-only.
    """
    if mode == INTENT_MODE_CURRENT_ONLY:
        return example.text
    if mode == INTENT_MODE_PREVIOUS_PLUS_CURRENT:
        previous = example.previous_text if example.context_available else None
        if not previous:
            previous = NO_CONTEXT
        return f"{previous} {example.text}"
    raise ValueError(
        f"unknown intent mode '{mode}'; expected one of {INTENT_MODES}"
    )


@dataclass
class SentimentExample:
    record_id: str
    text: str
    marked_text: str
    aspect_start: int
    aspect_end: int
    term: str
    category: str
    aspect_mask: list[int]
    label_id: int


@dataclass
class BioExample:
    record_id: str
    token_ids: list[int]
    attention_mask: list[int]
    bio_labels: list[int]  # -100 on ignored/padding positions
    offset_mapping: list[tuple[int, int]]


@dataclass
class BioBatchResult:
    examples: list[BioExample] = field(default_factory=list)
    dropped_aspects: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gold-label guards (Req 32.8)
# ---------------------------------------------------------------------------


def _has_gold_intent(record: AnnotationRecord) -> bool:
    """True only when the record is an explicitly completed gold record with
    a known non-empty intent (Req 32.8). This is the guard that prevents
    training on the unannotated pilot (``annotation_status="not_started"``,
    ``intent=None``)."""
    status = getattr(record, "annotation_status", None)
    intent = getattr(record, "intent", None)
    return (
        status == "completed"
        and isinstance(intent, str)
        and intent in INTENT_LABELS
    )


def _gold_aspects(record: AnnotationRecord) -> list[AspectSpan]:
    """Return the record's gold aspect spans that carry a known sentiment,
    or an empty list when the record has no usable gold aspects. Only
    completed records contribute gold aspects (Req 32.8)."""
    if getattr(record, "annotation_status", None) != "completed":
        return []
    aspects = getattr(record, "aspects", None)
    if not isinstance(aspects, list):
        return []
    usable: list[AspectSpan] = []
    for aspect in aspects:
        if not isinstance(aspect, AspectSpan):
            continue
        if not isinstance(aspect.start, int) or isinstance(aspect.start, bool):
            continue
        if not isinstance(aspect.end, int) or isinstance(aspect.end, bool):
            continue
        if aspect.sentiment not in ASPECT_SENTIMENTS:
            continue
        usable.append(aspect)
    return usable


# ---------------------------------------------------------------------------
# Intent loader (Req 32.1, 32.8)
# ---------------------------------------------------------------------------


def build_intent_examples(
    records: list[AnnotationRecord],
    label_map: dict[str, int] | None = None,
    tokenizer_fn: TokenizerFn | None = None,
) -> list[IntentExample]:
    """Build one ``IntentExample`` per gold-labelled record (Req 32.1).

    ``previous_text`` is carried ONLY when ``context_available`` is True;
    otherwise it is ``None`` (Req 32.1). Records without a gold intent are
    skipped (Req 32.8). ``tokenizer_fn`` is accepted for interface
    compatibility with the BERT path but is not required for the pure
    example construction verified here.
    """
    if label_map is None:
        label_map = build_intent_label_map()

    examples: list[IntentExample] = []
    for record in records:
        if not _has_gold_intent(record):
            continue
        intent = record.intent
        if intent not in label_map:
            continue
        context_available = getattr(record, "context_available", False) is True
        previous_text = record.previous_text if context_available else None
        examples.append(
            IntentExample(
                record_id=record.record_id,
                text=record.text,
                previous_text=previous_text,
                context_available=context_available,
                label_id=label_map[intent],
            )
        )
    return examples


# ---------------------------------------------------------------------------
# Sentiment loader (Req 32.2, 38)
# ---------------------------------------------------------------------------


def _char_aspect_mask(text: str, start: int, end: int) -> list[int]:
    """Return a character-level 0/1 mask over ``text`` (length == len(text))
    with 1s on ``[start, end)`` marking the target aspect span."""
    mask = [0] * len(text)
    for i in range(start, min(end, len(text))):
        mask[i] = 1
    return mask


def build_sentiment_examples(
    records: list[AnnotationRecord],
    label_map: dict[str, int] | None = None,
) -> list[SentimentExample]:
    """Emit exactly ONE ``SentimentExample`` per gold ``AspectSpan`` (a
    3-aspect record yields 3 instances, Req 32.2).

    Each instance carries the full ``text``, the exact gold ``(start, end)``
    offsets, the ``term`` and ``category``, ``marked_text`` produced by
    ``mark_aspect`` (Req 38), a character-level ``aspect_mask``, the encoded
    gold ``sentiment`` id, and the originating ``record_id``. Records without
    usable gold aspects/sentiments are skipped (Req 32.8).
    """
    if label_map is None:
        label_map = build_sentiment_label_map()

    examples: list[SentimentExample] = []
    for record in records:
        text = record.text
        if not isinstance(text, str):
            continue
        for aspect in _gold_aspects(record):
            if aspect.sentiment not in label_map:
                continue
            start, end = aspect.start, aspect.end
            if start < 0 or end > len(text) or start >= end:
                continue
            examples.append(
                SentimentExample(
                    record_id=record.record_id,
                    text=text,
                    marked_text=mark_aspect(text, start, end),
                    aspect_start=start,
                    aspect_end=end,
                    term=aspect.term,
                    category=aspect.category,
                    # Character-level aspect mask over the original text.
                    aspect_mask=_char_aspect_mask(text, start, end),
                    label_id=label_map[aspect.sentiment],
                )
            )
    return examples


# ---------------------------------------------------------------------------
# BIO loader (Req 32.3-32.6)
# ---------------------------------------------------------------------------


def build_bio_examples(
    records: list[AnnotationRecord],
    tokenizer_fn: TokenizerFn,
    max_seq_length: int,
    label_map: dict[str, int] | None = None,
) -> BioBatchResult:
    """Convert each gold record's ``text`` + gold aspect spans into a
    ``BioExample`` (Req 32.3).

    Alignment is delegated entirely to ``bio.py``:
    ``offsets_to_word_bio`` -> ``word_bio_to_subword_bio`` (identity subword
    mapping over the injected tokens) -> ``apply_ignore_mask``. Padding and
    ignored positions carry ``-100`` (Req 32.4). The aligned BIO labels
    reconstruct gold spans exactly via ``bio.bio_to_offsets`` (Req 32.5).

    Windowing is a documented single-window RIGHT-TRUNCATION to
    ``max_seq_length`` tokens: any gold aspect whose span falls wholly or
    partly beyond the retained window is DROPPED from the example and
    recorded in ``dropped_aspects`` (record_id + original start/end), never
    emitted as a partial/invalid span (Req 32.6). Aspects entirely within the
    window reconstruct exactly.
    """
    if label_map is None:
        label_map = build_bio_label_map()
    if max_seq_length <= 0:
        raise ValueError("max_seq_length must be positive")

    result = BioBatchResult()

    for record in records:
        text = record.text
        if not isinstance(text, str):
            continue
        gold_aspects = _gold_aspects(record)

        all_tokens = tokenizer_fn(text)
        # Single-window right-truncation to max_seq_length tokens.
        kept_tokens = all_tokens[:max_seq_length]

        # Determine which gold aspects survive the window fully. An aspect
        # survives only when every one of its tokens is within the retained
        # window; if any part is truncated, it is dropped and reported.
        surviving: list[AspectSpan] = []
        if kept_tokens:
            window_end_char = kept_tokens[-1][2]
        else:
            window_end_char = 0

        for aspect in gold_aspects:
            # An aspect is fully retained iff its character span end is within
            # the last kept token's end offset and its start is within the
            # window. Any aspect touching truncated tokens is dropped.
            if kept_tokens and aspect.start >= kept_tokens[0][1] and aspect.end <= window_end_char:
                surviving.append(aspect)
            else:
                result.dropped_aspects.append(
                    {
                        "record_id": record.record_id,
                        "start": aspect.start,
                        "end": aspect.end,
                    }
                )

        # Align surviving gold spans to BIO over the kept tokens via bio.py.
        word_bio = bio.offsets_to_word_bio(text, surviving, kept_tokens)
        # Identity subword mapping (kept tokens act as their own subwords).
        subword_bio = bio.word_bio_to_subword_bio(kept_tokens, word_bio, kept_tokens)

        # Right-pad to max_seq_length. Real (kept) token positions are not
        # special; padding positions ARE, so apply_ignore_mask assigns them
        # -100 — the single source of -100 masking (Req 32.4).
        n_pad = max_seq_length - len(kept_tokens)
        padded_bio = list(subword_bio) + [bio.O] * n_pad
        is_special_or_padding = [False] * len(kept_tokens) + [True] * n_pad
        masked = bio.apply_ignore_mask(padded_bio, is_special_or_padding)

        bio_label_ids: list[int] = [
            IGNORE_INDEX if value == IGNORE_INDEX else label_map[value]
            for value in masked
        ]

        # Token ids here are positional placeholders (a real subword
        # tokenizer supplies vocabulary ids); the loader's contract is the
        # alignment + masking + reconstruction, not a specific vocabulary.
        # Padding positions use pad id 0 and attention 0.
        token_ids = list(range(1, len(kept_tokens) + 1)) + [0] * n_pad
        attention_mask = [1] * len(kept_tokens) + [0] * n_pad
        offset_mapping = [(start, end) for _text, start, end in kept_tokens] + [(0, 0)] * n_pad

        result.examples.append(
            BioExample(
                record_id=record.record_id,
                token_ids=token_ids,
                attention_mask=attention_mask,
                bio_labels=bio_label_ids,
                offset_mapping=offset_mapping,
            )
        )

    return result
