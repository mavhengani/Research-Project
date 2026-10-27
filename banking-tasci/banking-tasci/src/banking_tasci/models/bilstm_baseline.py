"""BiLSTM baselines for intent and aspect-sentiment classification
(Phase 3A, Part 9).

This module provides a compact, well-documented bidirectional-LSTM baseline
that plugs into the shared training loop (``banking_tasci.training.loop``) via a
task-specific ``forward_fn``. It supports two tasks:

1. **Intent classification.** A mask-aware mean pool over the BiLSTM outputs of
   the current text feeds a linear classification head. Raw logits are returned
   for ``CrossEntropyLoss`` (class weights + gradient clipping are handled by
   the training loop).

2. **Aspect-level sentiment classification.** The target aspect is identified
   with an **aspect mask** (a 0/1 token mask marking the aspect tokens). The
   model pools the BiLSTM outputs **over the aspect tokens** (falling back to a
   full mask-aware mean when a row has no aspect tokens), so the prediction is
   conditioned on the specific aspect. This is the documented aspect-injection
   strategy for this baseline (aspect *mask* + pooled aspect representation).

Design guardrails:
- **Raw logits only.** The head returns logits; loss/weighting live in the loop.
- **Mask-aware / packed sequences.** Padding never contributes to pooling; the
  LSTM runs over ``pack_padded_sequence`` with ``enforce_sorted=False``.
- **CPU and CUDA.** The module is device-agnostic; tensors follow the model's
  device inside ``forward``.
- **No metadata leakage.** Only token ids (+ the aspect mask for sentiment) are
  consumed — never ``rating``/``region``/``source``/``bank``/``title``.
- **Synthetic-only fixtures in tests.** Nothing here fabricates research data;
  tiny synthetic vocabularies/batches are used exclusively inside tests.

Checkpointing, warm start, and full resume are provided by the shared loop's
:func:`banking_tasci.training.loop.build_checkpoint` /
``save_checkpoint`` / ``load_checkpoint`` and the ``resume_mode`` argument of
:func:`banking_tasci.training.loop.train_model`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

# Reserved id 0 for padding by convention (kept out of the learned vocabulary).
PAD_ID = 0

INTENT_TASK = "intent"
SENTIMENT_TASK = "sentiment"


@dataclass
class BiLSTMConfig:
    """Architecture hyper-parameters for :class:`BiLSTMClassifier`."""

    vocab_size: int
    num_classes: int
    embedding_dim: int = 64
    hidden_dim: int = 64
    num_layers: int = 1
    dropout: float = 0.1
    padding_idx: int = PAD_ID
    use_aspect_pooling: bool = False


class BiLSTMClassifier(nn.Module):
    """Embedding -> BiLSTM -> dropout -> linear head producing raw logits.

    ``forward(input_ids, lengths, aspect_mask=None)`` returns ``[N, num_classes]``
    logits. Pooling is mask-aware: for intent, the mean is over valid (non-pad)
    tokens; for sentiment (``use_aspect_pooling=True``), the mean is over the
    aspect-masked tokens, falling back to the valid-token mean when a row marks
    no aspect tokens.
    """

    def __init__(self, cfg: BiLSTMConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.embedding = nn.Embedding(
            cfg.vocab_size, cfg.embedding_dim, padding_idx=cfg.padding_idx
        )
        self.lstm = nn.LSTM(
            input_size=cfg.embedding_dim,
            hidden_size=cfg.hidden_dim,
            num_layers=cfg.num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=cfg.dropout if cfg.num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(cfg.dropout)
        self.head = nn.Linear(2 * cfg.hidden_dim, cfg.num_classes)

    def forward(
        self,
        input_ids: torch.Tensor,
        lengths: torch.Tensor,
        aspect_mask: "torch.Tensor | None" = None,
    ) -> torch.Tensor:
        device = self.head.weight.device
        input_ids = input_ids.to(device)
        # pack_padded_sequence requires CPU int64 lengths.
        lengths_cpu = lengths.detach().to("cpu").clamp(min=1)

        embedded = self.embedding(input_ids)  # [N, T, E]
        packed = pack_padded_sequence(
            embedded, lengths_cpu, batch_first=True, enforce_sorted=False
        )
        packed_out, _ = self.lstm(packed)
        outputs, _ = pad_packed_sequence(packed_out, batch_first=True)  # [N, T, 2H]

        T = outputs.size(1)
        # Valid-token mask from lengths.
        arange = torch.arange(T, device=device).unsqueeze(0)  # [1, T]
        valid_mask = (arange < lengths.to(device).unsqueeze(1)).float()  # [N, T]

        if self.cfg.use_aspect_pooling and aspect_mask is not None:
            aspect_mask = aspect_mask.to(device).float()[:, :T]
            pool_mask = aspect_mask * valid_mask
            # Rows with no aspect tokens fall back to the valid-token mean.
            empty = pool_mask.sum(dim=1, keepdim=True) == 0
            pool_mask = torch.where(empty, valid_mask, pool_mask)
        else:
            pool_mask = valid_mask

        denom = pool_mask.sum(dim=1, keepdim=True).clamp(min=1.0)
        pooled = (outputs * pool_mask.unsqueeze(-1)).sum(dim=1) / denom  # [N, 2H]
        return self.head(self.dropout(pooled))


# ---------------------------------------------------------------------------
# Batch collation + forward_fn factories for the shared training loop.
# ---------------------------------------------------------------------------

Batch = dict


def collate_intent_batch(
    token_id_seqs: "list[list[int]]", labels: "list[int]"
) -> Batch:
    """Right-pad variable-length token-id sequences into an intent batch dict."""
    return _collate(token_id_seqs, labels, aspect_masks=None)


def collate_sentiment_batch(
    token_id_seqs: "list[list[int]]",
    labels: "list[int]",
    aspect_masks: "list[list[int]]",
) -> Batch:
    """Right-pad token-id sequences + per-token aspect masks into a batch dict."""
    return _collate(token_id_seqs, labels, aspect_masks=aspect_masks)


def _collate(token_id_seqs, labels, aspect_masks) -> Batch:
    if not token_id_seqs:
        raise ValueError("cannot collate an empty batch")
    max_len = max(len(seq) for seq in token_id_seqs)
    n = len(token_id_seqs)
    input_ids = torch.full((n, max_len), PAD_ID, dtype=torch.long)
    lengths = torch.zeros(n, dtype=torch.long)
    for i, seq in enumerate(token_id_seqs):
        input_ids[i, : len(seq)] = torch.tensor(seq, dtype=torch.long)
        lengths[i] = max(len(seq), 1)
    batch: Batch = {
        "input_ids": input_ids,
        "lengths": lengths,
        "labels": torch.tensor(labels, dtype=torch.long),
    }
    if aspect_masks is not None:
        mask = torch.zeros((n, max_len), dtype=torch.long)
        for i, m in enumerate(aspect_masks):
            mask[i, : len(m)] = torch.tensor(m, dtype=torch.long)
        batch["aspect_mask"] = mask
    return batch


ForwardFn = Callable[[nn.Module, Batch], "tuple[torch.Tensor, torch.Tensor]"]


def make_forward_fn(task: str) -> ForwardFn:
    """Return a ``forward_fn(model, batch) -> (logits, labels)`` for the loop.

    For ``sentiment`` the batch's ``aspect_mask`` is passed through so the
    prediction is conditioned on the target aspect.
    """
    if task not in (INTENT_TASK, SENTIMENT_TASK):
        raise ValueError(f"unknown task '{task}'; expected 'intent' or 'sentiment'")

    def forward_fn(model: nn.Module, batch: Batch):
        labels = batch["labels"].to(model.head.weight.device)
        aspect_mask = batch.get("aspect_mask") if task == SENTIMENT_TASK else None
        logits = model(batch["input_ids"], batch["lengths"], aspect_mask=aspect_mask)
        return logits, labels

    return forward_fn


# ---------------------------------------------------------------------------
# Tiny convenience vocab (used by tests; safe for any whitespace text).
# ---------------------------------------------------------------------------


def build_vocab(texts: "list[str]", min_id: int = 1) -> "dict[str, int]":
    """Build a ``token -> id`` vocab (ids start at ``min_id``; 0 is padding)."""
    vocab: dict[str, int] = {}
    next_id = min_id
    for text in texts:
        for token in text.split():
            if token not in vocab:
                vocab[token] = next_id
                next_id += 1
    return vocab


def encode(text: str, vocab: "dict[str, int]", unk_id: int = PAD_ID) -> "list[int]":
    """Encode whitespace tokens to ids; unknown tokens map to ``unk_id``."""
    return [vocab.get(tok, unk_id) for tok in text.split()]

