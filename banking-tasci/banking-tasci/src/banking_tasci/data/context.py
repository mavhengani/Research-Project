"""Context_Builder: constructs `previous_text`/`context_available` for
annotation records (Requirement 16).

This module is a pure data-transformation layer invoked by
`scripts/create_annotation_sample.py` while it expands `data/interim/
prepared.csv` rows into annotatable units. It never inspects CSV row
adjacency and never links context across unrelated reviews, threads, or
records — the only two legitimate sources of `previous_text` are:

1. The immediately preceding sentence *within the same* multi-sentence
   `bank_reviews` record (Req 16.1-16.3).
2. An explicit, caller-supplied `thread_map` entry for a tweet record
   (Req 16.4-16.6) — never inferred from adjacent rows.

Requirements:
- 16.1: multi-sentence `bank_reviews` records are split into one
  Annotation_Record per sentence, each retaining the original review's
  `record_id`.
- 16.2: non-first sentences get `previous_text` set to the immediately
  preceding sentence from the same review and `context_available=True`.
- 16.3: the first sentence of any review gets `previous_text=
  "[NO_CONTEXT]"` and `context_available=False`.
- 16.4: tweet records get genuine thread context only when an explicit
  reply-to relationship is supplied via `thread_map`; otherwise
  `[NO_CONTEXT]`/`False`.
- 16.5: the previous row of the source CSV is never used as
  `previous_text`.
- 16.6: an unrelated tweet or unrelated review's sentence is never used
  as `previous_text`.
"""
from __future__ import annotations

import re

NO_CONTEXT = "[NO_CONTEXT]"

# Common abbreviations that should not be treated as sentence boundaries
# even though they end with a period. Matched case-sensitively at a word
# boundary immediately before the terminal period.
_ABBREVIATIONS = (
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Prof",
    "Sr",
    "Jr",
    "St",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "U.S",
    "U.K",
)

# Sentence-terminal punctuation: one or more of . ! ? followed by
# whitespace or end-of-string. Captured so the terminator can be
# reattached to the sentence it closes.
_SENTENCE_SPLIT_RE = re.compile(r"([.!?]+)(?:\s+|$)")


def split_into_sentences(text: str) -> list[str]:
    """Deterministic, regex-based sentence segmentation.

    Splits `text` on `.`/`!`/`?` boundaries followed by whitespace or
    end-of-string, with a simple guard against common abbreviations
    (e.g. "Mr.", "Dr.", "e.g.") so those periods are not treated as
    sentence boundaries. No external NLP dependency is used.

    Returns a list of trimmed, non-empty sentence strings. Returns an
    empty list for empty/whitespace-only input.
    """
    if text is None:
        return []
    stripped = text.strip()
    if not stripped:
        return []

    sentences: list[str] = []
    pos = 0
    current_start = 0

    for match in _SENTENCE_SPLIT_RE.finditer(stripped):
        boundary_end = match.end()
        terminator_start = match.start()

        # Guard against common abbreviations: if the word immediately
        # preceding the terminator is a known abbreviation, this is not
        # a real sentence boundary — skip splitting here.
        preceding = stripped[current_start:terminator_start]
        word_match = re.search(r"(\w+(?:\.\w+)*)$", preceding)
        if word_match and word_match.group(1) in _ABBREVIATIONS:
            continue

        candidate = stripped[current_start:boundary_end].strip()
        if candidate:
            sentences.append(candidate)
        current_start = boundary_end
        pos = boundary_end

    remainder = stripped[current_start:].strip()
    if remainder:
        sentences.append(remainder)

    return sentences


def build_review_sentence_records(review_canonical_record: dict) -> list[dict]:
    """Split a `bank_reviews` Canonical_Record's `text` into sentences and
    emit one Annotation-ready dict per sentence.

    Each emitted dict is a copy of `review_canonical_record`'s fields
    except:
    - `record_id`: a new, deterministic per-sentence identifier derived
      from the original review's `record_id` and the sentence's index
      (`f"{original_record_id}_s{idx}"`), so every emitted sentence-level
      record has its own distinct, stable identifier.
    - `text`: that sentence's text.
    - `previous_text`: the immediately preceding sentence's text, or
      `"[NO_CONTEXT]"` for the first sentence (Req 16.2, 16.3).
    - `context_available`: `True` for non-first sentences, `False` for
      the first sentence.
    - `source_record_id`: the ORIGINAL review's `record_id`, so later
      split logic can group sentence-records back to their review
      (Req 16.1).

    If `text` yields zero sentences (empty/whitespace text), returns an
    empty list. If it yields exactly one sentence, returns a single
    record with `[NO_CONTEXT]`/`False` (there is no preceding sentence).
    """
    sentences = split_into_sentences(review_canonical_record.get("text", ""))
    original_record_id = review_canonical_record.get("record_id")

    records: list[dict] = []
    previous_sentence: str | None = None

    for idx, sentence in enumerate(sentences):
        record = dict(review_canonical_record)
        record["record_id"] = f"{original_record_id}_s{idx}"
        record["text"] = sentence
        record["source_record_id"] = original_record_id

        if previous_sentence is None:
            record["previous_text"] = NO_CONTEXT
            record["context_available"] = False
        else:
            record["previous_text"] = previous_sentence
            record["context_available"] = True

        records.append(record)
        previous_sentence = sentence

    return records


def build_tweet_record(tweet_canonical_record: dict, thread_map: dict | None = None) -> dict:
    """Build an Annotation-ready dict for a single tweet Canonical_Record.

    Sets `previous_text`/`context_available` from a genuine `thread_map`
    lookup ONLY when `thread_map` provides an explicit entry for this
    record's `record_id`; otherwise defaults to `[NO_CONTEXT]`/`False`
    (Req 16.4). `thread_map` defaults to `None` since the current tweet
    source carries no thread metadata — this never derives context from
    CSV row adjacency, because no such adjacency information is ever
    consulted here (Req 16.5, 16.6).
    """
    record = dict(tweet_canonical_record)
    record_id = tweet_canonical_record.get("record_id")

    if thread_map is not None and record_id in thread_map:
        record["previous_text"] = thread_map[record_id]
        record["context_available"] = True
    else:
        record["previous_text"] = NO_CONTEXT
        record["context_available"] = False

    return record
