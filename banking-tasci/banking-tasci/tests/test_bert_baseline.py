"""Tests for the BERT baseline (src/banking_tasci/models/bert_baseline.py),
Phase 3A Part 10.

The BIO alignment + reconstruction logic is PURE PYTHON and tested without
``transformers``. A transformers-gated smoke test exercises offline model
loading + a forward pass using a tiny LOCAL BERT config; it is skipped when
``transformers`` is not installed and never downloads anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.bio import IGNORE_INDEX  # noqa: E402
from banking_tasci.data.datasets import BIO_LABEL_MAP  # noqa: E402
from banking_tasci.models.bert_baseline import (  # noqa: E402
    align_bio_to_subwords,
    marked_sentiment_text,
    predictions_to_char_spans,
)


# ---------------------------------------------------------------------------
# Pure-Python BIO alignment (no transformers needed).
# ---------------------------------------------------------------------------


def test_align_bio_uses_minus_100_for_special_and_continuation():
    word_bio = ["O", "B-ASP", "I-ASP", "O"]
    # [CLS] w0 w1a w1b w2 w3 [SEP]
    word_ids = [None, 0, 1, 1, 2, 3, None]
    labels = align_bio_to_subwords(word_bio, word_ids, dict(BIO_LABEL_MAP))
    assert labels == [
        IGNORE_INDEX,           # [CLS]
        BIO_LABEL_MAP["O"],     # w0
        BIO_LABEL_MAP["B-ASP"], # w1 first subword
        IGNORE_INDEX,           # w1 continuation
        BIO_LABEL_MAP["I-ASP"], # w2 first subword
        BIO_LABEL_MAP["O"],     # w3
        IGNORE_INDEX,           # [SEP]
    ]


def test_align_bio_all_special_positions_are_ignored():
    labels = align_bio_to_subwords(["O"], [None, None], dict(BIO_LABEL_MAP))
    assert labels == [IGNORE_INDEX, IGNORE_INDEX]


def test_predictions_to_char_spans_reconstructs_aspect():
    # "the fees app"; word1 "fees" (4-8) is the aspect.
    offset_mapping = [(0, 0), (0, 3), (4, 6), (6, 8), (9, 12), (0, 0)]
    word_ids = [None, 0, 1, 1, 2, None]
    id_to_label = {v: k for k, v in BIO_LABEL_MAP.items()}
    # First subword of word1 predicted B-ASP; continuation/others O.
    pred = [
        BIO_LABEL_MAP["O"],
        BIO_LABEL_MAP["O"],
        BIO_LABEL_MAP["B-ASP"],
        BIO_LABEL_MAP["O"],   # continuation position (ignored by first-subword rule)
        BIO_LABEL_MAP["O"],
        BIO_LABEL_MAP["O"],
    ]
    spans = predictions_to_char_spans(offset_mapping, pred, word_ids, id_to_label)
    assert spans == [(4, 8)]


def test_predictions_to_char_spans_multiword_aspect():
    # "mobile app is slow"; aspect = "mobile app" (0-10) as B-ASP, I-ASP.
    offset_mapping = [(0, 0), (0, 6), (7, 10), (11, 13), (14, 18), (0, 0)]
    word_ids = [None, 0, 1, 2, 3, None]
    id_to_label = {v: k for k, v in BIO_LABEL_MAP.items()}
    pred = [
        BIO_LABEL_MAP["O"],
        BIO_LABEL_MAP["B-ASP"],  # mobile
        BIO_LABEL_MAP["I-ASP"],  # app
        BIO_LABEL_MAP["O"],
        BIO_LABEL_MAP["O"],
        BIO_LABEL_MAP["O"],
    ]
    spans = predictions_to_char_spans(offset_mapping, pred, word_ids, id_to_label)
    assert spans == [(0, 10)]


def test_marked_sentiment_text_marks_target_aspect():
    text = "the mobile app is slow"
    marked = marked_sentiment_text(text, 4, 14)
    assert marked == "the [ASP] mobile app [/ASP] is slow"


# ---------------------------------------------------------------------------
# Transformers-gated offline smoke test (skips without transformers).
# ---------------------------------------------------------------------------


def test_bert_offline_forward_pass_with_tiny_local_config(tmp_path):
    transformers = pytest.importorskip("transformers")
    import torch

    from banking_tasci.models.bert_baseline import (
        BIO_TASK,
        BertBaselineConfig,
        build_model,
        encode_bio_example,
        load_tokenizer,
    )
    from banking_tasci.data.annotations import AspectSpan

    # Build a TINY BERT locally and save it to a local dir (no download).
    config = transformers.BertConfig(
        vocab_size=64, hidden_size=16, num_hidden_layers=1,
        num_attention_heads=2, intermediate_size=32, max_position_embeddings=64,
        num_labels=len(BIO_LABEL_MAP),
    )
    model = transformers.BertForTokenClassification(config)
    local_dir = tmp_path / "tiny-bert"
    model.save_pretrained(local_dir)

    # A tiny WordPiece tokenizer saved locally too.
    from transformers import BertTokenizerFast

    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "the", "fees", "app", "slow", "is"]
    vocab_file = tmp_path / "vocab.txt"
    vocab_file.write_text("\n".join(vocab) + "\n", encoding="utf-8")
    tok = BertTokenizerFast(vocab_file=str(vocab_file))
    tok.save_pretrained(local_dir)

    cfg = BertBaselineConfig(
        pretrained_path=str(local_dir), task=BIO_TASK,
        num_labels=len(BIO_LABEL_MAP), max_seq_length=32, local_files_only=True,
    )
    tokenizer = load_tokenizer(cfg)
    bert = build_model(cfg, tokenizer)

    def whitespace_tokens(text):
        out = []
        start = None
        for i, ch in enumerate(text):
            if ch.isspace():
                if start is not None:
                    out.append((text[start:i], start, i)); start = None
            elif start is None:
                start = i
        if start is not None:
            out.append((text[start:], start, len(text)))
        return out

    text = "the fees app is slow"
    aspects = [AspectSpan(term="fees", start=4, end=8, category="fees", sentiment="negative")]
    enc = encode_bio_example(tokenizer, text, aspects, whitespace_tokens, cfg)

    input_ids = torch.tensor([enc.input_ids])
    attention = torch.tensor([enc.attention_mask])
    with torch.no_grad():
        out = bert(input_ids=input_ids, attention_mask=attention)
    assert out.logits.shape[-1] == len(BIO_LABEL_MAP)
    # Labels are aligned 1:1 with the tokenized sequence.
    assert len(enc.labels) == len(enc.input_ids)

