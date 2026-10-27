"""Tests for the BiLSTM baseline (src/banking_tasci/models/bilstm_baseline.py),
Phase 3A Part 9.

Infrastructure / architecture checks only, on tiny synthetic CPU fixtures. No
research metric is reported and no gold data is used.

Covers:
- forward pass shapes (intent + aspect-sentiment with aspect mask);
- a tiny-batch overfit (the model can memorise a trivially separable set);
- checkpoint reload prediction-equivalence via the shared loop's structured
  checkpoint (build_checkpoint / save_checkpoint / load_checkpoint).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import torch  # noqa: E402

from banking_tasci.models.bilstm_baseline import (  # noqa: E402
    INTENT_TASK,
    SENTIMENT_TASK,
    BiLSTMClassifier,
    BiLSTMConfig,
    build_vocab,
    collate_intent_batch,
    collate_sentiment_batch,
    encode,
    make_forward_fn,
)
from banking_tasci.training.loop import (  # noqa: E402
    FULL_RESUME,
    TrainConfig,
    build_checkpoint,
    load_checkpoint,
    macro_f1,
    save_checkpoint,
    train_model,
)


def _intent_fixture():
    texts = [
        "app crashing terrible slow broken",
        "awful fees unfair angry broken",
        "excellent friendly staff wonderful great",
        "amazing helpful support lovely great",
    ]
    labels = [0, 0, 1, 1]
    vocab = build_vocab(texts)
    seqs = [encode(t, vocab) for t in texts]
    return vocab, seqs, labels


def test_intent_forward_pass_shapes():
    vocab, seqs, labels = _intent_fixture()
    cfg = BiLSTMConfig(vocab_size=len(vocab) + 1, num_classes=2, embedding_dim=16, hidden_dim=16)
    model = BiLSTMClassifier(cfg)
    batch = collate_intent_batch(seqs, labels)
    logits, y = make_forward_fn(INTENT_TASK)(model, batch)
    assert logits.shape == (4, 2)
    assert y.tolist() == labels


def test_sentiment_forward_pass_with_aspect_mask():
    texts = ["the fees are terrible", "the staff are great"]
    labels = [0, 1]
    vocab = build_vocab(texts)
    seqs = [encode(t, vocab) for t in texts]
    # Mark the aspect token ("fees" idx 1, "staff" idx 1).
    aspect_masks = [[0, 1, 0, 0], [0, 1, 0, 0]]
    cfg = BiLSTMConfig(
        vocab_size=len(vocab) + 1, num_classes=3, embedding_dim=16, hidden_dim=16,
        use_aspect_pooling=True,
    )
    model = BiLSTMClassifier(cfg)
    batch = collate_sentiment_batch(seqs, labels, aspect_masks)
    logits, y = make_forward_fn(SENTIMENT_TASK)(model, batch)
    assert logits.shape == (2, 3)
    assert y.tolist() == labels


def test_bilstm_tiny_batch_overfit():
    """A tiny BiLSTM should be able to memorise a trivially separable set,
    confirming the architecture + loop wire together (not a research metric)."""
    torch.manual_seed(0)
    vocab, seqs, labels = _intent_fixture()
    cfg = BiLSTMConfig(vocab_size=len(vocab) + 1, num_classes=2, embedding_dim=24, hidden_dim=24)
    model = BiLSTMClassifier(cfg)
    batch = collate_intent_batch(seqs, labels)
    batches = [batch]

    train_cfg = TrainConfig(epochs=60, learning_rate=0.05, grad_clip=1.0, device="cpu", seed=0)
    result = train_model(
        model, batches, batches, num_classes=2, cfg=train_cfg,
        forward_fn=make_forward_fn(INTENT_TASK),
    )
    # On 4 separable examples the model should reach perfect training macro-F1.
    assert result.best_val_macro_f1 == pytest.approx(1.0)


def test_bilstm_checkpoint_reload_prediction_equivalence(tmp_path):
    torch.manual_seed(0)
    vocab, seqs, labels = _intent_fixture()
    cfg = BiLSTMConfig(vocab_size=len(vocab) + 1, num_classes=2, embedding_dim=24, hidden_dim=24)
    model = BiLSTMClassifier(cfg)
    batch = collate_intent_batch(seqs, labels)
    forward_fn = make_forward_fn(INTENT_TASK)

    train_cfg = TrainConfig(epochs=30, learning_rate=0.05, device="cpu", seed=0)
    result = train_model(model, [batch], [batch], num_classes=2, cfg=train_cfg, forward_fn=forward_fn)

    # Predictions from the trained (best) weights.
    model.load_state_dict(result.best_state_dict)
    model.eval()
    with torch.no_grad():
        before = torch.argmax(model(batch["input_ids"], batch["lengths"]), dim=-1).tolist()

    # Save a structured checkpoint and reload into a fresh model.
    ckpt = build_checkpoint(
        model=model, optimizer=None, epoch=result.last_epoch,
        best_validation_macro_f1=result.best_val_macro_f1,
        epochs_without_improvement=result.epochs_without_improvement,
        training_config=train_cfg, label_mapping={"neg": 0, "pos": 1},
    )
    path = tmp_path / "bilstm.pt"
    save_checkpoint(ckpt, path)
    reloaded_ckpt = load_checkpoint(path)

    fresh = BiLSTMClassifier(cfg)
    fresh.load_state_dict(reloaded_ckpt["model_state_dict"])
    fresh.eval()
    with torch.no_grad():
        after = torch.argmax(fresh(batch["input_ids"], batch["lengths"]), dim=-1).tolist()

    assert before == after


def test_bilstm_full_resume_continues_epochs(tmp_path):
    torch.manual_seed(0)
    vocab, seqs, labels = _intent_fixture()
    cfg = BiLSTMConfig(vocab_size=len(vocab) + 1, num_classes=2, embedding_dim=16, hidden_dim=16)
    model = BiLSTMClassifier(cfg)
    batch = collate_intent_batch(seqs, labels)
    fwd = make_forward_fn(INTENT_TASK)

    ckpt = build_checkpoint(
        model=model, optimizer=torch.optim.Adam(model.parameters()),
        epoch=4, best_validation_macro_f1=0.5, epochs_without_improvement=0,
        training_config=TrainConfig(epochs=4, device="cpu", seed=0),
        label_mapping={"neg": 0, "pos": 1},
    )
    fresh = BiLSTMClassifier(cfg)
    result = train_model(
        fresh, [batch], [batch], num_classes=2,
        cfg=TrainConfig(epochs=6, learning_rate=0.05, device="cpu", seed=0),
        forward_fn=fwd, resume_from=ckpt, resume_mode=FULL_RESUME,
    )
    assert [h["epoch"] for h in result.history] == [5, 6]

