"""Tests for the shared training loop (`banking_tasci.training.loop`).

Infrastructure sanity checks only (Req 35.2, 35.4, 35.6, 36.5, 36.6) on tiny
synthetic CPU fixtures. No research metric is reported.

Covers:
- `macro_f1` on known y_true/y_pred cases (perfect prediction = 1.0, plus a
  hand-computable partial case).
- A tiny end-to-end loop: a 1-linear-layer model on ~8 synthetic 2-class
  examples trains, captures a best_state_dict, and improves val macro-F1.
- Early stopping halts before max epochs when validation never improves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import torch  # noqa: E402
from torch import nn  # noqa: E402

from banking_tasci.training.loop import (  # noqa: E402
    FULL_RESUME,
    WARM_START,
    CheckpointCompatibilityError,
    TrainConfig,
    TrainResult,
    build_checkpoint,
    load_checkpoint,
    macro_f1,
    save_checkpoint,
    train_model,
)


# --------------------------------------------------------------------------
# macro_f1
# --------------------------------------------------------------------------
def test_macro_f1_perfect_prediction_is_one() -> None:
    y_true = [0, 1, 2, 1, 0]
    y_pred = [0, 1, 2, 1, 0]
    assert macro_f1(y_true, y_pred, num_classes=3) == pytest.approx(1.0)


def test_macro_f1_known_partial_case() -> None:
    # Two classes, one prediction wrong.
    #   y_true = [0, 0, 1, 1], y_pred = [0, 1, 1, 1]
    # Class 0: tp=1, fp=0, fn=1 -> F1 = 2*1/(2*1+0+1) = 2/3
    # Class 1: tp=2, fp=1, fn=0 -> F1 = 2*2/(2*2+1+0) = 4/5
    # macro = (2/3 + 4/5) / 2 = 0.7333...
    y_true = [0, 0, 1, 1]
    y_pred = [0, 1, 1, 1]
    expected = ((2 / 3) + (4 / 5)) / 2
    assert macro_f1(y_true, y_pred, num_classes=2) == pytest.approx(expected)


def test_macro_f1_all_wrong_is_zero() -> None:
    y_true = [0, 0, 0, 0]
    y_pred = [1, 1, 1, 1]
    # Class 0: tp=0 -> F1 0. Class 1: tp=0, fp=4 -> F1 0. macro = 0.
    assert macro_f1(y_true, y_pred, num_classes=2) == pytest.approx(0.0)


def test_macro_f1_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        macro_f1([0, 1], [0], num_classes=2)


def test_macro_f1_invalid_num_classes_raises() -> None:
    with pytest.raises(ValueError):
        macro_f1([0], [0], num_classes=0)


# --------------------------------------------------------------------------
# End-to-end loop
# --------------------------------------------------------------------------
class _TinyLinear(nn.Module):
    """Trivial 1-linear-layer classifier producing raw logits."""

    def __init__(self, in_features: int, num_classes: int) -> None:
        super().__init__()
        self.linear = nn.Linear(in_features, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x)


def _forward_fn(model: nn.Module, batch):
    features, labels = batch
    return model(features), labels


def _separable_batches() -> list:
    """8 synthetic, linearly-separable 2-class examples as a single batch."""
    features = torch.tensor(
        [
            [2.0, 0.0],
            [2.5, 0.1],
            [1.8, -0.2],
            [2.2, 0.3],
            [-2.0, 0.0],
            [-2.5, 0.1],
            [-1.8, -0.2],
            [-2.2, 0.3],
        ],
        dtype=torch.float32,
    )
    labels = torch.tensor([1, 1, 1, 1, 0, 0, 0, 0], dtype=torch.long)
    return [(features, labels)]


def test_train_model_learns_and_captures_best_checkpoint() -> None:
    torch.manual_seed(0)
    model = _TinyLinear(in_features=2, num_classes=2)
    batches = _separable_batches()

    cfg = TrainConfig(
        epochs=40,
        learning_rate=0.1,
        grad_clip=1.0,
        early_stopping_patience=0,  # disabled: run full schedule
        device="cpu",
        seed=123,
    )

    result = train_model(
        model=model,
        train_batches=batches,
        val_batches=batches,  # same separable data acts as validation here
        num_classes=2,
        cfg=cfg,
        forward_fn=_forward_fn,
    )

    assert isinstance(result, TrainResult)
    # The model should be able to perfectly separate this trivial data.
    assert result.best_val_macro_f1 == pytest.approx(1.0)
    assert result.best_epoch >= 1
    assert result.best_state_dict  # a checkpoint was captured
    assert len(result.history) == 40
    # First epoch macro-F1 should be no better than the best.
    assert result.history[0]["val_macro_f1"] <= result.best_val_macro_f1


def test_train_model_best_state_dict_reloads_to_best_score() -> None:
    torch.manual_seed(0)
    model = _TinyLinear(in_features=2, num_classes=2)
    batches = _separable_batches()

    cfg = TrainConfig(epochs=30, learning_rate=0.1, device="cpu", seed=7)
    result = train_model(
        model, batches, batches, num_classes=2, cfg=cfg, forward_fn=_forward_fn
    )

    # Reload the captured best checkpoint into a fresh model and confirm it
    # reproduces the recorded best validation macro-F1 (checkpoint is valid).
    reloaded = _TinyLinear(in_features=2, num_classes=2)
    reloaded.load_state_dict(result.best_state_dict)
    reloaded.eval()
    with torch.no_grad():
        features, labels = batches[0]
        preds = torch.argmax(reloaded(features), dim=-1)
    assert macro_f1(
        labels.tolist(), preds.tolist(), num_classes=2
    ) == pytest.approx(result.best_val_macro_f1)


def test_train_model_early_stops_when_validation_never_improves() -> None:
    torch.manual_seed(0)
    model = _TinyLinear(in_features=2, num_classes=2)
    train_batches = _separable_batches()

    # Validation data on which macro-F1 stays constant regardless of the
    # model: a single class present, so predictions can never raise the
    # unweighted macro-F1 across epochs -> no improvement after epoch 1.
    const_features = torch.zeros((4, 2), dtype=torch.float32)
    const_labels = torch.zeros(4, dtype=torch.long)
    val_batches = [(const_features, const_labels)]

    patience = 3
    cfg = TrainConfig(
        epochs=50,
        learning_rate=0.1,
        early_stopping_patience=patience,
        device="cpu",
        seed=1,
    )

    result = train_model(
        model,
        train_batches,
        val_batches,
        num_classes=2,
        cfg=cfg,
        forward_fn=_forward_fn,
    )

    assert result.stopped_early is True
    # Best is found at epoch 1, then `patience` epochs pass without improving.
    assert len(result.history) < cfg.epochs
    assert len(result.history) <= result.best_epoch + patience


def test_train_model_resume_from_checkpoint_loads_state() -> None:
    torch.manual_seed(0)
    trained = _TinyLinear(in_features=2, num_classes=2)
    batches = _separable_batches()
    cfg = TrainConfig(epochs=20, learning_rate=0.1, device="cpu", seed=3)
    first = train_model(
        trained, batches, batches, num_classes=2, cfg=cfg, forward_fn=_forward_fn
    )

    # Resume a fresh model from the captured checkpoint and train 0 further
    # would be degenerate; instead confirm resume loads the weights by
    # running one epoch and checking it starts from the good checkpoint.
    fresh = _TinyLinear(in_features=2, num_classes=2)
    resumed = train_model(
        fresh,
        batches,
        batches,
        num_classes=2,
        cfg=TrainConfig(epochs=1, learning_rate=0.1, device="cpu", seed=3),
        forward_fn=_forward_fn,
        resume_state_dict=first.best_state_dict,
    )
    # Starting from an already-good checkpoint, the single epoch's validation
    # macro-F1 should already be strong (near-perfect on separable data).
    assert resumed.history[0]["val_macro_f1"] >= 0.5


# --------------------------------------------------------------------------
# Part 4 — warm_start vs full_resume + structured checkpoints
# --------------------------------------------------------------------------
def _structured_checkpoint_at_epoch(epoch: int, best: float = 0.5, ewi: int = 1):
    model = _TinyLinear(in_features=2, num_classes=2)
    optim = torch.optim.Adam(model.parameters(), lr=0.1)
    cfg = TrainConfig(epochs=epoch, learning_rate=0.1, device="cpu", seed=3)
    return build_checkpoint(
        model=model,
        optimizer=optim,
        epoch=epoch,
        best_validation_macro_f1=best,
        epochs_without_improvement=ewi,
        training_config=cfg,
        label_mapping={"neg": 0, "pos": 1},
    )


def test_build_checkpoint_has_required_structure() -> None:
    ckpt = _structured_checkpoint_at_epoch(5)
    for key in (
        "model_state_dict",
        "optimizer_state_dict",
        "epoch",
        "best_validation_macro_f1",
        "epochs_without_improvement",
        "training_config",
        "label_mapping",
        "rng_state",
    ):
        assert key in ckpt
    assert ckpt["epoch"] == 5
    assert ckpt["label_mapping"] == {"neg": 0, "pos": 1}


def test_save_and_load_checkpoint_roundtrip(tmp_path) -> None:
    ckpt = _structured_checkpoint_at_epoch(7, best=0.8, ewi=2)
    path = tmp_path / "ckpt.pt"
    save_checkpoint(ckpt, path)
    loaded = load_checkpoint(path)
    assert loaded["epoch"] == 7
    assert loaded["best_validation_macro_f1"] == 0.8
    assert loaded["epochs_without_improvement"] == 2
    assert loaded["label_mapping"] == {"neg": 0, "pos": 1}


def test_full_resume_continues_from_correct_epoch() -> None:
    ckpt = _structured_checkpoint_at_epoch(5, best=0.5, ewi=1)
    batches = _separable_batches()
    fresh = _TinyLinear(in_features=2, num_classes=2)

    result = train_model(
        fresh,
        batches,
        batches,
        num_classes=2,
        cfg=TrainConfig(epochs=8, learning_rate=0.1, device="cpu", seed=3),
        forward_fn=_forward_fn,
        resume_from=ckpt,
        resume_mode=FULL_RESUME,
    )

    # Training continues from epoch 6..8 (not 1..8).
    assert [h["epoch"] for h in result.history] == [6, 7, 8]
    assert result.last_epoch == 8


def test_full_resume_past_max_epochs_runs_no_further_epochs() -> None:
    ckpt = _structured_checkpoint_at_epoch(5, best=0.5, ewi=1)
    batches = _separable_batches()
    fresh = _TinyLinear(in_features=2, num_classes=2)

    result = train_model(
        fresh,
        batches,
        batches,
        num_classes=2,
        cfg=TrainConfig(epochs=5, learning_rate=0.1, device="cpu", seed=3),
        forward_fn=_forward_fn,
        resume_from=ckpt,
        resume_mode=FULL_RESUME,
    )
    # Nothing to do: epoch 5 already reached. Best score/epoch preserved.
    assert result.history == []
    assert result.best_epoch == 5
    assert result.best_val_macro_f1 == pytest.approx(0.5)


def test_warm_start_resets_epoch_and_optimiser() -> None:
    ckpt = _structured_checkpoint_at_epoch(5, best=0.9, ewi=3)
    batches = _separable_batches()
    fresh = _TinyLinear(in_features=2, num_classes=2)

    result = train_model(
        fresh,
        batches,
        batches,
        num_classes=2,
        cfg=TrainConfig(epochs=3, learning_rate=0.1, device="cpu", seed=3),
        forward_fn=_forward_fn,
        resume_from=ckpt,
        resume_mode=WARM_START,
    )
    # Warm start is a FRESH run: epochs are numbered from 1 again, and the
    # resumed best score (0.9) does NOT carry over as prior state.
    assert [h["epoch"] for h in result.history] == [1, 2, 3]
    assert result.last_epoch == 3


def test_full_resume_from_weight_only_checkpoint_raises_compatibility_error() -> None:
    trained = _TinyLinear(in_features=2, num_classes=2)
    bare_state_dict = trained.state_dict()  # old-style, weight-only
    batches = _separable_batches()

    with pytest.raises(CheckpointCompatibilityError):
        train_model(
            _TinyLinear(in_features=2, num_classes=2),
            batches,
            batches,
            num_classes=2,
            cfg=TrainConfig(epochs=2, device="cpu", seed=3),
            forward_fn=_forward_fn,
            resume_from=bare_state_dict,
            resume_mode=FULL_RESUME,
        )


def test_warm_start_accepts_weight_only_checkpoint() -> None:
    trained = _TinyLinear(in_features=2, num_classes=2)
    bare_state_dict = trained.state_dict()
    batches = _separable_batches()

    # A bare weight-only checkpoint must remain loadable as a warm start.
    result = train_model(
        _TinyLinear(in_features=2, num_classes=2),
        batches,
        batches,
        num_classes=2,
        cfg=TrainConfig(epochs=1, device="cpu", seed=3),
        forward_fn=_forward_fn,
        resume_from=bare_state_dict,
        resume_mode=WARM_START,
    )
    assert result.last_epoch == 1


