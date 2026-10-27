"""BERT baselines for the banking-tasci tasks (Phase 3A, Part 10).

Three heads are supported, all built on a configurable, **local** pretrained
model directory so cluster execution never needs internet access:

1. **BIO aspect extraction** — token classification (``B-ASP``/``I-ASP``/``O``)
   with tokenizer offset mapping used to align labels to sub-words.
2. **Intent** — sequence classification over the current text.
3. **Aspect sentiment** — sequence classification over ``[ASP] term [/ASP]``-
   marked text, so the target aspect is explicit in the input.

Offline / graceful-degradation guardrails:
- ``transformers`` is imported LAZILY. Importing this module never fails when
  ``transformers`` is absent; only actually building a model does, and with a
  clear message.
- ``from_pretrained(..., local_files_only=True)`` by default — models are
  loaded from a local directory (see :class:`BertBaselineConfig.pretrained_path`),
  never auto-downloaded.
- The label-alignment strategy is **pure Python** (:func:`align_bio_to_subwords`,
  :func:`predictions_to_char_spans`) and unit-testable without ``transformers``:
  special tokens and continuation sub-words use ``-100`` (the ignore index), so
  loss is computed only on the first sub-word of each word.

The test split is never consulted for checkpoint selection (that is enforced by
the shared training loop, which only accepts train/val batches).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from banking_tasci.data import bio
from banking_tasci.data.bio import IGNORE_INDEX, Token
from banking_tasci.data.datasets import BIO_LABEL_MAP, mark_aspect

BIO_TASK = "aspect"
INTENT_TASK = "intent"
SENTIMENT_TASK = "sentiment"

# Special additional tokens for the sentiment marker convention.
ASPECT_MARKER_TOKENS = ["[ASP]", "[/ASP]"]


@dataclass
class BertBaselineConfig:
    """Configuration for a BERT baseline.

    Attributes:
        pretrained_path: path to a LOCAL pretrained model directory (never a
            hub id that would trigger a download). Required for model building.
        task: one of ``"aspect"``, ``"intent"``, ``"sentiment"``.
        num_labels: number of output classes/tags.
        max_seq_length: tokenizer truncation length.
        local_files_only: pass-through to ``from_pretrained`` (default True →
            offline).
        add_marker_tokens: for the sentiment task, add ``[ASP]``/``[/ASP]`` as
            special tokens so they are not split by the tokenizer.
    """

    pretrained_path: str
    task: str
    num_labels: int
    max_seq_length: int = 128
    local_files_only: bool = True
    add_marker_tokens: bool = True


# ---------------------------------------------------------------------------
# Lazy transformers import (graceful degradation).
# ---------------------------------------------------------------------------


def _require_transformers():
    """Import and return the transformers symbols needed here, LAZILY."""
    try:
        from transformers import (
            AutoModelForSequenceClassification,
            AutoModelForTokenClassification,
            AutoTokenizer,
        )
    except ImportError as exc:  # pragma: no cover - exercised only w/o transformers
        raise ImportError(
            "transformers is required for the BERT baselines "
            "(banking_tasci.models.bert_baseline). Install it with "
            "`pip install transformers` and provide a LOCAL model directory."
        ) from exc
    return {
        "AutoTokenizer": AutoTokenizer,
        "AutoModelForTokenClassification": AutoModelForTokenClassification,
        "AutoModelForSequenceClassification": AutoModelForSequenceClassification,
    }


def load_tokenizer(cfg: BertBaselineConfig):
    """Load a tokenizer from the local pretrained directory (offline)."""
    tf = _require_transformers()
    tokenizer = tf["AutoTokenizer"].from_pretrained(
        cfg.pretrained_path, local_files_only=cfg.local_files_only, use_fast=True
    )
    if cfg.task == SENTIMENT_TASK and cfg.add_marker_tokens:
        tokenizer.add_special_tokens({"additional_special_tokens": list(ASPECT_MARKER_TOKENS)})
    return tokenizer


def build_model(cfg: BertBaselineConfig, tokenizer=None):
    """Build the task-appropriate BERT model from the local pretrained dir."""
    tf = _require_transformers()
    if cfg.task == BIO_TASK:
        model = tf["AutoModelForTokenClassification"].from_pretrained(
            cfg.pretrained_path, num_labels=cfg.num_labels,
            local_files_only=cfg.local_files_only,
        )
    elif cfg.task in (INTENT_TASK, SENTIMENT_TASK):
        model = tf["AutoModelForSequenceClassification"].from_pretrained(
            cfg.pretrained_path, num_labels=cfg.num_labels,
            local_files_only=cfg.local_files_only,
        )
    else:
        raise ValueError(f"unknown task '{cfg.task}'")
    # Resize embeddings if marker tokens were added to the tokenizer.
    if tokenizer is not None and cfg.task == SENTIMENT_TASK and cfg.add_marker_tokens:
        model.resize_token_embeddings(len(tokenizer))
    return model


# ---------------------------------------------------------------------------
# PURE-PYTHON BIO alignment + reconstruction (unit-testable w/o transformers).
# ---------------------------------------------------------------------------


def align_bio_to_subwords(
    word_bio: "list[str]",
    word_ids: "list[int | None]",
    label_map: "dict[str, int] | None" = None,
) -> "list[int]":
    """Align word-level BIO tags to sub-word token positions (the documented
    ``-100`` strategy).

    ``word_ids`` is the per-subword mapping produced by a fast tokenizer's
    ``BatchEncoding.word_ids()`` (``None`` for special tokens like
    ``[CLS]``/``[SEP]``/padding). For each sub-word position:

    - ``None`` (special/padding) -> ``-100`` (ignored in the loss);
    - the FIRST sub-word of a word -> the word's BIO tag id;
    - CONTINUATION sub-words of the same word -> ``-100`` (ignored), so loss is
      computed once per word.
    """
    if label_map is None:
        label_map = dict(BIO_LABEL_MAP)
    labels: list[int] = []
    previous_word_id: "int | None" = None
    for word_id in word_ids:
        if word_id is None:
            labels.append(IGNORE_INDEX)
        elif word_id != previous_word_id:
            labels.append(label_map[word_bio[word_id]])
        else:
            labels.append(IGNORE_INDEX)
        previous_word_id = word_id
    return labels


def predictions_to_char_spans(
    offset_mapping: "list[tuple[int, int]]",
    predicted_label_ids: "list[int]",
    word_ids: "list[int | None]",
    id_to_label: "dict[int, str]",
) -> "list[tuple[int, int]]":
    """Reconstruct character spans from sub-word BIO predictions.

    Takes the FIRST sub-word's prediction as each word's label, expands each
    word to its full character span (min start / max end across its
    sub-words), then delegates to :func:`bio.bio_to_offsets`. Special-token
    positions (``word_id is None``) are skipped. This proves BIO predictions
    are convertible back into character spans.
    """
    # Aggregate sub-words per word: char bounds + first-subword prediction.
    word_start: dict[int, int] = {}
    word_end: dict[int, int] = {}
    word_label: dict[int, str] = {}
    word_order: list[int] = []
    prev_word_id: "int | None" = None
    for (start, end), label_id, word_id in zip(offset_mapping, predicted_label_ids, word_ids):
        if word_id is None:
            prev_word_id = word_id
            continue
        if word_id not in word_start:
            word_start[word_id] = start
            word_end[word_id] = end
            word_order.append(word_id)
            if word_id != prev_word_id:
                word_label[word_id] = id_to_label.get(int(label_id), bio.O)
        else:
            word_end[word_id] = max(word_end[word_id], end)
        prev_word_id = word_id

    word_tokens: list[Token] = [
        ("", word_start[w], word_end[w]) for w in word_order
    ]
    word_bio = [word_label.get(w, bio.O) for w in word_order]
    return bio.bio_to_offsets(word_tokens, word_bio)


def marked_sentiment_text(text: str, start: int, end: int) -> str:
    """Return ``[ASP] term [/ASP]``-marked text for the sentiment input
    (delegates to :func:`banking_tasci.data.datasets.mark_aspect`)."""
    return mark_aspect(text, start, end)


# ---------------------------------------------------------------------------
# Transformers-backed encoding for BIO alignment (used in real training).
# ---------------------------------------------------------------------------


@dataclass
class BioEncoding:
    input_ids: list
    attention_mask: list
    labels: list
    offset_mapping: list
    word_ids: list
    dropped_aspects: list = field(default_factory=list)


def encode_bio_example(
    tokenizer,
    text: str,
    aspects,
    word_tokenizer_fn,
    cfg: BertBaselineConfig,
    label_map: "dict[str, int] | None" = None,
) -> BioEncoding:
    """Encode ``text`` + gold ``aspects`` into a BERT BIO training example.

    ``word_tokenizer_fn(text) -> list[Token]`` supplies word-level offsets
    (injected so this module never hard-codes a word tokenizer). Word-level BIO
    is computed via :mod:`banking_tasci.data.bio`, then aligned to sub-words
    using the fast tokenizer's ``word_ids`` with the ``-100`` strategy.

    Truncation never silently drops a labelled aspect: any aspect whose
    sub-words are cut off is reported in ``dropped_aspects`` rather than emitted
    as a partial span.
    """
    if label_map is None:
        label_map = dict(BIO_LABEL_MAP)

    word_tokens = word_tokenizer_fn(text)
    word_bio = bio.offsets_to_word_bio(text, list(aspects), word_tokens)

    encoding = tokenizer(
        [t for t, _s, _e in word_tokens],
        is_split_into_words=True,
        truncation=True,
        max_length=cfg.max_seq_length,
        return_offsets_mapping=True,
        return_attention_mask=True,
    )
    word_ids = encoding.word_ids()
    labels = align_bio_to_subwords(word_bio, word_ids, label_map)

    # Detect truncated aspects: a word that carries a B/I tag but no longer
    # appears in word_ids has been dropped by truncation.
    kept_word_indices = {w for w in word_ids if w is not None}
    dropped = []
    for idx, tag in enumerate(word_bio):
        if tag != bio.O and idx not in kept_word_indices:
            _term, s, e = word_tokens[idx]
            dropped.append({"start": s, "end": e})

    return BioEncoding(
        input_ids=encoding["input_ids"],
        attention_mask=encoding["attention_mask"],
        labels=labels,
        offset_mapping=encoding["offset_mapping"],
        word_ids=word_ids,
        dropped_aspects=dropped,
    )

