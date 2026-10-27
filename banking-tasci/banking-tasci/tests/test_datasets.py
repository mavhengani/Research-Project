"""Property-based and example tests for the supervised-learning data loaders
(src/banking_tasci/data/datasets.py), Phase 3A (Requirements 32 and 38).

Property tests (hypothesis, >=100 examples each):
- Property 2: Intent loader preserves context flag and label identity.
- Property 3: Sentiment loader emits exactly one instance per gold aspect.
- Property 4: BIO alignment round-trips and masks ignored positions with -100.
- Property 5: Truncation reports every removed aspect and never emits an
  invalid span.
- Property 6: Aspect marking is span-exact and reversible.

Example tests:
- Gold-only guard (Req 32.8): not_started / empty-intent records yield zero
  intent and zero sentiment examples.

All fixtures are tiny synthetic in-memory records constructed within the
tests; no gold data, no network, CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import (  # noqa: E402
    ASPECT_SENTIMENTS,
    INTENT_LABELS,
    AnnotationRecord,
    AspectSpan,
)
from banking_tasci.data import bio  # noqa: E402
from banking_tasci.data.bio import IGNORE_INDEX, Token, bio_to_offsets  # noqa: E402
from banking_tasci.data.datasets import (  # noqa: E402
    ASP_CLOSE,
    ASP_OPEN,
    BioExample,
    build_bio_examples,
    build_bio_label_map,
    build_intent_examples,
    build_intent_label_map,
    build_sentiment_examples,
    build_sentiment_label_map,
    mark_aspect,
)


# ---------------------------------------------------------------------------
# Whitespace tokenizer_fn — returns (token_text, char_start, char_end) tuples
# with correct half-open [start, end) character offsets. Defined in the test
# so datasets.py never depends on transformers (tokenizer_fn is injected).
# ---------------------------------------------------------------------------


def whitespace_tokenizer(text: str) -> list[Token]:
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


# ---------------------------------------------------------------------------
# Helpers to build synthetic records.
# ---------------------------------------------------------------------------


def _record(
    *,
    record_id: str = "rec",
    text: str = "the app is slow",
    previous_text: str = "[NO_CONTEXT]",
    context_available: bool = False,
    aspects: list[AspectSpan] | None = None,
    intent: str | None = "complaint",
    annotation_status: str = "completed",
) -> AnnotationRecord:
    return AnnotationRecord(
        record_id=record_id,
        source="bank_reviews",
        region="local",
        text=text,
        previous_text=previous_text,
        context_available=context_available,
        aspects=aspects if aspects is not None else [],
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="annotator_a",
        annotation_status=annotation_status,
        notes="",
    )


# ---------------------------------------------------------------------------
# Strategy: build a text made of whitespace-separated word tokens plus a set
# of non-overlapping aspect spans aligned to whole tokens.
# ---------------------------------------------------------------------------

# The alphabet is deliberately broad (printable ASCII punctuation through the
# Latin Extended-B block, Unicode boundary cases) so the property still
# exercises real edge cases. The two square-bracket characters are excluded
# because aspect terms are never the reserved control markers themselves:
# mark_aspect is only defined for text that does not already contain the
# reserved substrings "[ASP]" / "[/ASP]" (a documented precondition). Without
# this, Hypothesis could synthesise a span whose content *is* the literal
# marker, spuriously breaking the marker-count and reversibility assertions.
_WORD = st.text(
    alphabet=st.characters(
        min_codepoint=0x21,
        max_codepoint=0x24F,
        blacklist_categories=("Zs",),
        blacklist_characters="[]",
    ),
    min_size=1,
    max_size=6,
).filter(lambda w: not any(c.isspace() for c in w))


@st.composite
def _text_with_token_aspects(draw, min_words=1, max_words=8):
    words = draw(st.lists(_WORD, min_size=min_words, max_size=max_words))
    text = " ".join(words)
    tokens = whitespace_tokenizer(text)

    # Choose a subset of token indices as single-token aspects (non-overlap
    # is automatic since each aspect is exactly one distinct token).
    n = len(tokens)
    chosen = draw(
        st.lists(st.integers(min_value=0, max_value=max(0, n - 1)), min_size=0, max_size=n, unique=True)
    ) if n else []

    aspects: list[AspectSpan] = []
    for idx in sorted(set(chosen)):
        term, start, end = tokens[idx]
        sentiment = draw(st.sampled_from(ASPECT_SENTIMENTS))
        aspects.append(AspectSpan(term=term, start=start, end=end, category="cards", sentiment=sentiment))
    return text, aspects


# ===========================================================================
# Property 2
# ===========================================================================
# Feature: banking-tasci-phase-3a, Property 2: Intent loader preserves context flag and label identity
# Validates: Requirements 32.1
@settings(max_examples=150)
@given(
    intent=st.sampled_from(INTENT_LABELS),
    context_available=st.booleans(),
    previous_text=st.text(min_size=1, max_size=20),
    text=st.text(min_size=1, max_size=30),
)
def test_property_intent_loader_preserves_context_and_label(intent, context_available, previous_text, text):
    label_map = build_intent_label_map()
    prev = previous_text if context_available else "[NO_CONTEXT]"
    record = _record(
        text=text,
        previous_text=prev,
        context_available=context_available,
        intent=intent,
        annotation_status="completed",
    )

    examples = build_intent_examples([record], label_map)

    assert len(examples) == 1
    ex = examples[0]
    # Label identity: encoded id round-trips to the gold intent.
    assert ex.label_id == label_map[intent]
    # Context flag preserved.
    assert ex.context_available == context_available
    # previous_text carried ONLY when context is available (Req 32.1).
    if context_available:
        assert ex.previous_text == prev
    else:
        assert ex.previous_text is None
    assert ex.text == text
    assert ex.record_id == record.record_id


# ===========================================================================
# Property 3
# ===========================================================================
# Feature: banking-tasci-phase-3a, Property 3: Sentiment loader emits exactly one instance per gold aspect
# Validates: Requirements 32.2
@settings(max_examples=150)
@given(data=_text_with_token_aspects())
def test_property_sentiment_loader_one_instance_per_aspect(data):
    text, aspects = data
    label_map = build_sentiment_label_map()
    record = _record(text=text, aspects=aspects, annotation_status="completed")

    examples = build_sentiment_examples([record], label_map)

    # Exactly one instance per gold aspect.
    assert len(examples) == len(aspects)
    for ex, aspect in zip(examples, aspects):
        assert ex.aspect_start == aspect.start
        assert ex.aspect_end == aspect.end
        assert ex.term == aspect.term
        assert ex.category == aspect.category
        assert ex.label_id == label_map[aspect.sentiment]
        assert ex.record_id == record.record_id
        # marked_text marks exactly this one span.
        assert ex.marked_text == mark_aspect(text, aspect.start, aspect.end)
        # aspect_mask is character-level with 1s exactly on the span.
        assert len(ex.aspect_mask) == len(text)
        assert all(ex.aspect_mask[i] == 1 for i in range(aspect.start, aspect.end))
        assert sum(ex.aspect_mask) == aspect.end - aspect.start


def test_sentiment_loader_three_aspects_yields_three_instances():
    text = "app fees staff"
    aspects = [
        AspectSpan(term="app", start=0, end=3, category="digital_banking", sentiment="negative"),
        AspectSpan(term="fees", start=4, end=8, category="fees", sentiment="negative"),
        AspectSpan(term="staff", start=9, end=14, category="branch_service", sentiment="positive"),
    ]
    record = _record(text=text, aspects=aspects)
    examples = build_sentiment_examples([record])
    assert len(examples) == 3


# ===========================================================================
# Property 4
# ===========================================================================
# Feature: banking-tasci-phase-3a, Property 4: BIO alignment round-trips and masks ignored positions with -100
# Validates: Requirements 32.3, 32.4, 32.5


def _reconstruct_offsets(example: BioExample, id_to_tag: dict[int, str]) -> list[tuple[int, int]]:
    """Reconstruct character spans from a BioExample: drop -100 positions,
    map ids back to BIO tags, and delegate to bio.bio_to_offsets over the
    real (non-padding) tokens (Req 32.5)."""
    real_tokens: list[Token] = []
    real_bio: list[str] = []
    for (start, end), label_id in zip(example.offset_mapping, example.bio_labels):
        if label_id == IGNORE_INDEX:
            continue
        real_tokens.append(("", start, end))
        real_bio.append(id_to_tag[label_id])
    return bio_to_offsets(real_tokens, real_bio)


@settings(max_examples=150)
@given(data=_text_with_token_aspects(min_words=1, max_words=8))
def test_property_bio_roundtrip_and_masking(data):
    text, aspects = data
    label_map = build_bio_label_map()
    id_to_tag = {v: k for k, v in label_map.items()}
    record = _record(text=text, aspects=aspects)

    n_tokens = len(whitespace_tokenizer(text))
    # Generous window so nothing is truncated here (truncation is Property 5).
    max_seq_length = n_tokens + 3

    result = build_bio_examples([record], whitespace_tokenizer, max_seq_length, label_map)
    assert len(result.examples) == 1
    assert result.dropped_aspects == []
    ex = result.examples[0]

    # Every position is exactly max_seq_length long.
    assert len(ex.bio_labels) == max_seq_length
    assert len(ex.offset_mapping) == max_seq_length
    assert len(ex.attention_mask) == max_seq_length

    # Padding positions are masked with -100 and attention 0 (Req 32.4).
    for i in range(n_tokens, max_seq_length):
        assert ex.bio_labels[i] == IGNORE_INDEX
        assert ex.attention_mask[i] == 0
    # Real positions are never -100.
    for i in range(n_tokens):
        assert ex.bio_labels[i] != IGNORE_INDEX
        assert ex.attention_mask[i] == 1

    # Exact reconstruction of gold spans that survived tokenisation (Req 32.5).
    expected = {(a.start, a.end) for a in aspects}
    assert set(_reconstruct_offsets(ex, id_to_tag)) == expected


def test_bio_subword_split_masking_and_roundtrip():
    """Subword-splitting case: a subword tokenizer that splits words into
    fixed-width pieces still round-trips and masks padding with -100."""

    def subword_tokenizer(text: str, size: int = 3) -> list[Token]:
        subwords: list[Token] = []
        for _t, start, end in whitespace_tokenizer(text):
            pos = start
            while pos < end:
                piece_end = min(pos + size, end)
                subwords.append((text[pos:piece_end], pos, piece_end))
                pos = piece_end
        return subwords

    text = "the application works"
    aspects = [AspectSpan(term="application", start=4, end=15, category="digital_banking", sentiment="neutral")]
    record = _record(text=text, aspects=aspects)
    label_map = build_bio_label_map()
    id_to_tag = {v: k for k, v in label_map.items()}

    n_sub = len(subword_tokenizer(text))
    result = build_bio_examples([record], subword_tokenizer, n_sub + 2, label_map)
    ex = result.examples[0]
    assert set(_reconstruct_offsets(ex, id_to_tag)) == {(4, 15)}
    assert ex.bio_labels[-1] == IGNORE_INDEX  # padding masked


def test_bio_unicode_and_boundary_of_text():
    text = "café über naïve"
    tokens = whitespace_tokenizer(text)
    # Boundary-of-text aspects: first and last token.
    first = tokens[0]
    last = tokens[-1]
    aspects = [
        AspectSpan(term=first[0], start=first[1], end=first[2], category="cards", sentiment="positive"),
        AspectSpan(term=last[0], start=last[1], end=last[2], category="cards", sentiment="negative"),
    ]
    record = _record(text=text, aspects=aspects)
    label_map = build_bio_label_map()
    id_to_tag = {v: k for k, v in label_map.items()}
    result = build_bio_examples([record], whitespace_tokenizer, len(tokens) + 1, label_map)
    ex = result.examples[0]
    assert set(_reconstruct_offsets(ex, id_to_tag)) == {
        (first[1], first[2]),
        (last[1], last[2]),
    }


# ===========================================================================
# Property 5
# ===========================================================================
# Feature: banking-tasci-phase-3a, Property 5: Truncation reports every removed aspect and never emits an invalid span
# Validates: Requirements 32.6
@settings(max_examples=150)
@given(
    data=_text_with_token_aspects(min_words=2, max_words=10),
    max_seq_length=st.integers(min_value=1, max_value=10),
)
def test_property_truncation_reports_removed_and_never_invalid(data, max_seq_length):
    text, aspects = data
    label_map = build_bio_label_map()
    id_to_tag = {v: k for k, v in label_map.items()}
    record = _record(text=text, aspects=aspects)

    tokens = whitespace_tokenizer(text)
    kept_tokens = tokens[:max_seq_length]
    window_end_char = kept_tokens[-1][2] if kept_tokens else 0
    window_start_char = kept_tokens[0][1] if kept_tokens else 0

    result = build_bio_examples([record], whitespace_tokenizer, max_seq_length, label_map)
    assert len(result.examples) == 1
    ex = result.examples[0]

    # Partition gold aspects into survived vs dropped by the window.
    survived = {
        (a.start, a.end)
        for a in aspects
        if kept_tokens and a.start >= window_start_char and a.end <= window_end_char
    }
    dropped = {(a.start, a.end) for a in aspects} - survived

    reported_dropped = {(d["start"], d["end"]) for d in result.dropped_aspects if d["record_id"] == record.record_id}
    # Every removed aspect is reported (Req 32.6).
    assert dropped <= reported_dropped
    # Nothing spurious reported.
    assert reported_dropped <= dropped | {(a.start, a.end) for a in aspects}

    # Reconstructed spans are exactly the survivors — never a partial/invalid
    # span (Req 32.6).
    reconstructed = set(_reconstruct_offsets(ex, id_to_tag))
    assert reconstructed == survived
    # Every reconstructed span is well-formed and within the retained window.
    for s, e in reconstructed:
        assert 0 <= s < e <= window_end_char


# ===========================================================================
# Property 6
# ===========================================================================
# Feature: banking-tasci-phase-3a, Property 6: Aspect marking is span-exact and reversible
# Validates: Requirements 38.1, 38.2, 38.3
@settings(max_examples=150)
@given(data=_text_with_token_aspects(min_words=1, max_words=8))
def test_property_aspect_marking_span_exact_and_reversible(data):
    text, aspects = data
    # Only exercise marking when there is at least one aspect.
    if not aspects:
        assert mark_aspect  # nothing to mark; function exists
        return

    open_prefix = ASP_OPEN + " "  # inserted immediately before the span start
    close_suffix = " " + ASP_CLOSE  # inserted immediately after the span end
    for aspect in aspects:
        marked = mark_aspect(text, aspect.start, aspect.end)
        # Markers present exactly once each (marks exactly one target span).
        # Guaranteed by the generator excluding the reserved marker literals.
        assert marked.count(ASP_OPEN) == 1
        assert marked.count(ASP_CLOSE) == 1
        # The marked term sits between the markers.
        segment = marked.split(ASP_OPEN, 1)[1].split(ASP_CLOSE, 1)[0]
        assert segment.strip() == text[aspect.start:aspect.end]
        # Reversible: reconstruct the original by removing the inserted
        # markers at their KNOWN insertion points (position-based, not a
        # fragile global replace). "[ASP] " is inserted at aspect.start and
        # " [/ASP]" immediately after the span, so their positions in the
        # marked string are deterministic (Req 38.3 — no other char changed).
        open_at = aspect.start
        close_at = aspect.start + len(open_prefix) + (aspect.end - aspect.start)
        assert marked[open_at:open_at + len(open_prefix)] == open_prefix
        assert marked[close_at:close_at + len(close_suffix)] == close_suffix
        restored = (
            marked[:open_at]
            + marked[open_at + len(open_prefix):close_at]
            + marked[close_at + len(close_suffix):]
        )
        assert restored == text


def test_mark_aspect_leaves_other_aspects_unmarked():
    text = "app and fees"
    # Mark only "app"; "fees" must remain unmarked (Req 38.2).
    marked = mark_aspect(text, 0, 3)
    assert marked == "[ASP] app [/ASP] and fees"
    assert marked.count(ASP_OPEN) == 1
    assert "fees" in marked


def test_mark_aspect_precondition_text_without_reserved_markers():
    """``mark_aspect`` is a pure positional insert and is only defined for
    text that does not itself contain the reserved control markers
    ``[ASP]``/``[/ASP]`` (a documented precondition; real annotation text
    never contains them). For such text it is span-exact — inserting the
    markers around exactly the target span and preserving every other
    character — and marks exactly one span.
    """
    text = "the mobile app is slow"
    # Span covers "mobile app".
    start, end = 4, 14
    assert text[start:end] == "mobile app"
    marked = mark_aspect(text, start, end)
    assert marked == "the [ASP] mobile app [/ASP] is slow"
    assert marked.count(ASP_OPEN) == 1
    assert marked.count(ASP_CLOSE) == 1
    # Position-based reversal restores the original exactly.
    open_prefix, close_suffix = ASP_OPEN + " ", " " + ASP_CLOSE
    close_at = start + len(open_prefix) + (end - start)
    restored = (
        marked[:start]
        + marked[start + len(open_prefix):close_at]
        + marked[close_at + len(close_suffix):]
    )
    assert restored == text


# ===========================================================================
# Gold-only guard (Req 32.8)
# ===========================================================================


def test_not_started_and_empty_intent_records_produce_zero_examples():
    """not_started / empty-intent records must yield ZERO intent and ZERO
    sentiment examples — the guard that prevents accidental training on the
    unannotated pilot (Req 32.8)."""
    # Mirror the current pilot: not_started, null intent, empty aspects.
    unannotated = _record(
        record_id="pilot_1",
        text="the mobile app keeps crashing",
        intent=None,
        annotation_status="not_started",
        aspects=[],
    )
    # An in-progress record with an empty-string intent and some spans.
    empty_intent = _record(
        record_id="pilot_2",
        text="the fees are high",
        intent="",
        annotation_status="in_progress",
        aspects=[AspectSpan(term="fees", start=4, end=8, category="fees", sentiment="negative")],
    )

    records = [unannotated, empty_intent]

    assert build_intent_examples(records) == []
    assert build_sentiment_examples(records) == []
    bio_result = build_bio_examples(records, whitespace_tokenizer, 16)
    # Non-completed records contribute no gold aspects, so no BIO aspects and
    # no dropped aspects are produced from them.
    assert bio_result.dropped_aspects == []
    for ex in bio_result.examples:
        # Any labels present are all O or -100 (no B-ASP/I-ASP from non-gold).
        assert all(v in (IGNORE_INDEX, build_bio_label_map()[bio.O]) for v in ex.bio_labels)
