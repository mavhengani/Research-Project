"""Shared PyTorch training loop for the baseline models (KIRO_SPEC §17).

`training/loop.py` centralises the training-loop requirements common to the
BiLSTM (Req 35) and BERT (Req 36) baselines so they are implemented once:

- deterministic seeding at the start of training (Req 35.2 via `seed`),
- class-weighted `torch.nn.CrossEntropyLoss` on raw logits (Req 35.4),
- gradient clipping via `torch.nn.utils.clip_grad_norm_` (Req 35.6),
- per-epoch progress logging via `logging_utils.get_logger`,
- checkpointing by BEST validation macro-F1 (Req 36.5),
- early stopping on validation macro-F1 with configurable patience (Req 36.5),
- two explicit resume modes (Phase 3A Part 4):

  * ``warm_start`` — restore MODEL WEIGHTS ONLY; the optimiser, epoch counter,
    best score, and early-stopping counter all reset. This is a fresh training
    run initialised from prior weights, and is documented as such (it is NOT a
    continuation of a previous run).
  * ``full_resume`` — restore model weights, optimiser state, the epoch
    counter (training continues from ``epoch + 1``), the best validation
    macro-F1, the early-stopping counter, and RNG states where practical. This
    is a faithful continuation of an interrupted run.

Structured checkpoints (see :func:`build_checkpoint`) contain::

    {
      "model_state_dict": ...,
      "optimizer_state_dict": ...,
      "epoch": ...,
      "best_validation_macro_f1": ...,
      "epochs_without_improvement": ...,
      "training_config": ...,
      "label_mapping": ...,
      "rng_state": ...,
    }

Old *weight-only* checkpoints (a bare ``state_dict``) remain loadable as a
``warm_start``; attempting a ``full_resume`` from one raises a helpful
compatibility error rather than silently pretending to continue.

The loop is deliberately framework-agnostic: the model is supplied by the
caller, and a `forward_fn(model, batch) -> (logits, labels)` decouples the
loop from any specific model/task. `train_batches`/`val_batches` are
caller-provided iterables of already-collated batches.

**The TEST split is NEVER consulted** for checkpoint selection or early
stopping (Req 36.6). This is made explicit in the interface: `train_model`
accepts only train and validation batches and has no parameter through which
test data could be passed.

Dependency-light: torch only. Macro-F1 is implemented directly so no sklearn
dependency is required.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import torch
from torch import nn

from banking_tasci import seed as seed_module
from banking_tasci.config import Config
from banking_tasci.logging_utils import get_logger

# A batch is opaque to the loop; only `forward_fn` knows its structure.
Batch = Any
# Turns a model + batch into (logits[N, C], labels[N]) on the training device.
ForwardFn = Callable[[nn.Module, Batch], "tuple[torch.Tensor, torch.Tensor]"]


@dataclass
class TrainConfig:
    """Training-loop knobs (subset of the §17 config surface).

    Attributes:
        epochs: maximum number of epochs to run.
        learning_rate: optimiser learning rate.
        weight_decay: optimiser L2 weight decay.
        grad_clip: max gradient norm for `clip_grad_norm_`; ``None`` disables.
        early_stopping_patience: stop after this many consecutive epochs
            without an improvement in validation macro-F1. ``0`` or negative
            disables early stopping (train the full `epochs`).
        class_weights: optional per-class weights for cross-entropy; ``None``
            means unweighted.
        device: torch device string, e.g. ``"cpu"`` or ``"cuda"``.
        seed: deterministic seed applied at the start of training.
    """

    epochs: int
    learning_rate: float = 1e-3
    weight_decay: float = 0.0
    grad_clip: float | None = None
    early_stopping_patience: int = 0
    class_weights: list[float] | None = None
    device: str = "cpu"
    seed: int = 42


@dataclass
class TrainResult:
    """Outcome of a training run.

    Attributes:
        best_val_macro_f1: highest validation macro-F1 observed.
        best_epoch: 1-indexed epoch at which `best_val_macro_f1` occurred
            (``0`` if no epoch ran).
        best_state_dict: deep-copied model ``state_dict`` captured at the
            best epoch (CPU tensors), suitable for reload.
        history: per-epoch records ``{epoch, train_loss, val_macro_f1}``.
        stopped_early: ``True`` if early stopping halted training before
            `TrainConfig.epochs` epochs completed.
    """

    best_val_macro_f1: float
    best_epoch: int
    best_state_dict: dict
    history: list[dict] = field(default_factory=list)
    stopped_early: bool = False
    last_epoch: int = 0
    epochs_without_improvement: int = 0
    last_state_dict: dict = field(default_factory=dict)
    best_optimizer_state_dict: dict | None = None
    last_optimizer_state_dict: dict | None = None


def macro_f1(y_true: list[int], y_pred: list[int], num_classes: int) -> float:
    """Return the macro-averaged F1 score (unweighted mean of per-class F1).

    Pure Python implementation (no sklearn dependency). For each class ``c``
    in ``range(num_classes)`` the F1 is computed from true positives, false
    positives, and false negatives; a class with a zero denominator (no
    predictions and no gold instances contributing) contributes an F1 of 0.
    The macro score is the arithmetic mean across all ``num_classes`` classes.

    Args:
        y_true: gold label ids.
        y_pred: predicted label ids (same length as `y_true`).
        num_classes: number of classes; averaging is over exactly these.

    Raises:
        ValueError: if `y_true` and `y_pred` differ in length or
            `num_classes` < 1.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"y_true and y_pred must have equal length, got "
            f"{len(y_true)} and {len(y_pred)}"
        )
    if num_classes < 1:
        raise ValueError(f"num_classes must be >= 1, got {num_classes}")

    tp = [0] * num_classes
    fp = [0] * num_classes
    fn = [0] * num_classes

    for gold, pred in zip(y_true, y_pred):
        if pred == gold:
            if 0 <= gold < num_classes:
                tp[gold] += 1
        else:
            if 0 <= pred < num_classes:
                fp[pred] += 1
            if 0 <= gold < num_classes:
                fn[gold] += 1

    f1_sum = 0.0
    for c in range(num_classes):
        denom = 2 * tp[c] + fp[c] + fn[c]
        if denom == 0:
            # No gold or predicted instances for this class: F1 undefined,
            # counted as 0 in the macro average.
            f1_sum += 0.0
        else:
            f1_sum += (2 * tp[c]) / denom

    return f1_sum / num_classes


def _resolve_class_weights(
    class_weights: list[float] | None, device: torch.device
) -> torch.Tensor | None:
    if class_weights is None:
        return None
    return torch.tensor(class_weights, dtype=torch.float32, device=device)


def _evaluate_macro_f1(
    model: nn.Module,
    val_batches: Iterable[Batch],
    forward_fn: ForwardFn,
    num_classes: int,
) -> float:
    """Run `model` over `val_batches` and return macro-F1 (no gradients)."""
    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []
    with torch.no_grad():
        for batch in val_batches:
            logits, labels = forward_fn(model, batch)
            preds = torch.argmax(logits, dim=-1)
            y_pred.extend(int(p) for p in preds.reshape(-1).tolist())
            y_true.extend(int(t) for t in labels.reshape(-1).tolist())
    return macro_f1(y_true, y_pred, num_classes)


def _cpu_state_dict(model: nn.Module) -> dict:
    """Deep-copy the model state_dict onto CPU for safe checkpointing."""
    return copy.deepcopy(
        {k: v.detach().cpu() for k, v in model.state_dict().items()}
    )


# ---------------------------------------------------------------------------
# Resume modes + structured checkpoints (Phase 3A Part 4)
# ---------------------------------------------------------------------------

WARM_START = "warm_start"
FULL_RESUME = "full_resume"

# The keys that distinguish a structured checkpoint from a bare weight-only
# ``state_dict``. A dict carrying ``model_state_dict`` is treated as structured.
_STRUCTURED_KEYS = (
    "model_state_dict",
    "optimizer_state_dict",
    "epoch",
    "best_validation_macro_f1",
    "epochs_without_improvement",
    "training_config",
    "label_mapping",
    "rng_state",
)


def capture_rng_state() -> dict:
    """Capture RNG states for Python, NumPy, and torch (CPU + CUDA) where
    practical. Missing back-ends are simply omitted; capture never raises."""
    state: dict = {}
    try:
        import random as _random

        state["python"] = _random.getstate()
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        import numpy as _np

        state["numpy"] = _np.random.get_state()
    except Exception:  # pragma: no cover - numpy optional
        pass
    try:
        state["torch_cpu"] = torch.get_rng_state()
        if torch.cuda.is_available():
            state["torch_cuda"] = torch.cuda.get_rng_state_all()
    except Exception:  # pragma: no cover - defensive
        pass
    return state


def restore_rng_state(state: "dict | None") -> None:
    """Restore RNG states captured by :func:`capture_rng_state`. Unknown or
    missing back-ends are skipped; restoration never raises on a partial
    state (Req: RNG states where practical)."""
    if not state:
        return
    try:
        import random as _random

        if "python" in state:
            _random.setstate(state["python"])
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        import numpy as _np

        if "numpy" in state:
            _np.random.set_state(state["numpy"])
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        if "torch_cpu" in state:
            cpu_state = state["torch_cpu"]
            if not isinstance(cpu_state, torch.Tensor):
                cpu_state = torch.as_tensor(cpu_state, dtype=torch.uint8)
            torch.set_rng_state(cpu_state.to(torch.uint8))
        if "torch_cuda" in state and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(state["torch_cuda"])
    except Exception:  # pragma: no cover - defensive
        pass


def build_checkpoint(
    model: nn.Module,
    optimizer: "torch.optim.Optimizer | None",
    epoch: int,
    best_validation_macro_f1: float,
    epochs_without_improvement: int,
    training_config: "TrainConfig | dict | None",
    label_mapping: "dict | None" = None,
    rng_state: "dict | None" = None,
) -> dict:
    """Assemble a structured checkpoint dict (see module docstring).

    ``training_config`` accepts a :class:`TrainConfig` (stored as its ``__dict__``)
    or a plain dict. ``rng_state`` defaults to a fresh capture when omitted.
    """
    if isinstance(training_config, TrainConfig):
        cfg_dict = dict(training_config.__dict__)
    else:
        cfg_dict = training_config
    return {
        "model_state_dict": _cpu_state_dict(model),
        "optimizer_state_dict": optimizer.state_dict() if optimizer is not None else None,
        "epoch": int(epoch),
        "best_validation_macro_f1": float(best_validation_macro_f1),
        "epochs_without_improvement": int(epochs_without_improvement),
        "training_config": cfg_dict,
        "label_mapping": label_mapping,
        "rng_state": rng_state if rng_state is not None else capture_rng_state(),
    }


def is_structured_checkpoint(obj: "dict | None") -> bool:
    """True when ``obj`` looks like a structured checkpoint (has
    ``model_state_dict``), as opposed to a bare weight-only ``state_dict``."""
    return isinstance(obj, dict) and "model_state_dict" in obj


def save_checkpoint(checkpoint: dict, path: "str | Path") -> None:
    """Persist a structured checkpoint with ``torch.save``."""
    from pathlib import Path as _Path

    p = _Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, p)


def load_checkpoint(path: "str | Path") -> dict:
    """Load a checkpoint written by :func:`save_checkpoint`.

    Uses ``weights_only=False`` because our checkpoints intentionally embed
    Python RNG state and config metadata, not just tensors.
    """
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        # Older torch without the weights_only kwarg.
        return torch.load(path, map_location="cpu")


class CheckpointCompatibilityError(RuntimeError):
    """Raised when a full_resume is requested from a checkpoint that lacks the
    structured state needed to faithfully continue a run."""


def train_model(
    model: nn.Module,
    train_batches: Iterable[Batch],
    val_batches: Iterable[Batch],
    num_classes: int,
    cfg: TrainConfig,
    forward_fn: ForwardFn,
    resume_state_dict: dict | None = None,
    resume_from: "dict | None" = None,
    resume_mode: str = FULL_RESUME,
    label_mapping: "dict | None" = None,
) -> TrainResult:
    """Train `model` with the shared loop, selecting on validation macro-F1.

    For each epoch the loop runs `forward_fn(model, batch) -> (logits, labels)`
    over `train_batches`, computes class-weighted cross-entropy on the raw
    logits, back-propagates, clips gradients (when `cfg.grad_clip` is set),
    and steps the optimiser. It then evaluates macro-F1 over `val_batches`,
    checkpoints the model when validation macro-F1 improves, and early-stops
    after `cfg.early_stopping_patience` epochs without improvement.

    The TEST split is never touched here (Req 36.6): only `train_batches` and
    `val_batches` are accepted, and the interface exposes no test-data
    parameter.

    Resume behaviour (Part 4):
        resume_state_dict: LEGACY warm start — a bare model ``state_dict``
            loaded as initial weights only (optimiser/epoch/best all reset).
        resume_from: a checkpoint (structured dict from :func:`build_checkpoint`
            or a bare ``state_dict``) to resume from, interpreted per
            ``resume_mode``.
        resume_mode: ``"warm_start"`` restores weights only and starts a fresh
            run; ``"full_resume"`` restores weights + optimiser + epoch + best
            score + early-stopping counter + RNG, continuing from ``epoch + 1``.
            A ``full_resume`` from a bare weight-only checkpoint raises
            :class:`CheckpointCompatibilityError`.
        label_mapping: optional label map echoed into structured checkpoints by
            callers; not otherwise used by the loop.

    Returns:
        TrainResult with the best validation macro-F1, the epoch and
        state_dict that achieved it, and the per-epoch history.
    """
    logger = get_logger("banking_tasci.training.loop")

    # Deterministic seeding at the very start of training (Req 35.2). Use the
    # config-driven helper so the seed is never a hard-coded literal.
    seed_module.set_seed_from_config(Config({"seed": cfg.seed}))

    device = torch.device(cfg.device)
    model.to(device)

    # ---- resume state initialisation -------------------------------------
    start_epoch = 1
    resumed_best_val = float("-inf")
    resumed_best_epoch = 0
    resumed_epochs_without_improvement = 0
    resumed_optimizer_state: dict | None = None
    restore_rng_after_seed: dict | None = None

    if resume_state_dict is not None:
        # Legacy weight-only warm start.
        model.load_state_dict(resume_state_dict)
        logger.info("Warm start: loaded model weights from resume_state_dict (optimiser/epoch reset)")

    if resume_from is not None:
        if resume_mode == WARM_START:
            weights = resume_from["model_state_dict"] if is_structured_checkpoint(resume_from) else resume_from
            model.load_state_dict(weights)
            logger.info("Warm start: restored model weights only; optimiser and epoch state reset")
        elif resume_mode == FULL_RESUME:
            if not is_structured_checkpoint(resume_from):
                raise CheckpointCompatibilityError(
                    "full_resume requires a structured checkpoint with "
                    "'model_state_dict'/'optimizer_state_dict'/'epoch'. This "
                    "looks like an old weight-only checkpoint; load it with "
                    "resume_mode='warm_start' instead (weights only, fresh run)."
                )
            model.load_state_dict(resume_from["model_state_dict"])
            resumed_optimizer_state = resume_from.get("optimizer_state_dict")
            start_epoch = int(resume_from.get("epoch", 0)) + 1
            resumed_best_val = float(resume_from.get("best_validation_macro_f1", float("-inf")))
            resumed_best_epoch = int(resume_from.get("epoch", 0))
            resumed_epochs_without_improvement = int(resume_from.get("epochs_without_improvement", 0))
            restore_rng_after_seed = resume_from.get("rng_state")
            logger.info(
                "Full resume: continuing from epoch %d (best_val_macro_f1=%.6f, "
                "epochs_without_improvement=%d)",
                start_epoch,
                resumed_best_val,
                resumed_epochs_without_improvement,
            )
        else:
            raise ValueError(
                f"unknown resume_mode '{resume_mode}'; expected "
                f"'{WARM_START}' or '{FULL_RESUME}'"
            )

    weight = _resolve_class_weights(cfg.class_weights, device)
    criterion = nn.CrossEntropyLoss(weight=weight)
    optimiser = torch.optim.Adam(
        model.parameters(),
        lr=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
    )
    if resumed_optimizer_state is not None:
        optimiser.load_state_dict(resumed_optimizer_state)

    # For a full_resume, continue the RNG stream from where it stopped (after
    # the deterministic re-seed above, which we deliberately override).
    if restore_rng_after_seed is not None:
        restore_rng_state(restore_rng_after_seed)

    best_val_macro_f1 = resumed_best_val
    best_epoch = resumed_best_epoch
    best_state_dict: dict = _cpu_state_dict(model)
    best_optimizer_state_dict: dict | None = None
    history: list[dict] = []
    epochs_without_improvement = resumed_epochs_without_improvement
    stopped_early = False

    patience = cfg.early_stopping_patience

    last_epoch = start_epoch - 1
    for epoch in range(start_epoch, cfg.epochs + 1):
        last_epoch = epoch
        model.train()
        total_loss = 0.0
        num_batches = 0

        for batch in train_batches:
            optimiser.zero_grad()
            logits, labels = forward_fn(model, batch)
            loss = criterion(logits, labels)
            loss.backward()
            if cfg.grad_clip is not None:
                nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            optimiser.step()
            total_loss += float(loss.detach())
            num_batches += 1

        train_loss = total_loss / num_batches if num_batches else 0.0
        val_macro_f1 = _evaluate_macro_f1(
            model, val_batches, forward_fn, num_classes
        )

        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_macro_f1": val_macro_f1,
            }
        )
        logger.info(
            "epoch %d | train_loss=%.6f | val_macro_f1=%.6f",
            epoch,
            train_loss,
            val_macro_f1,
        )

        if val_macro_f1 > best_val_macro_f1:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            best_state_dict = _cpu_state_dict(model)
            best_optimizer_state_dict = copy.deepcopy(optimiser.state_dict())
            epochs_without_improvement = 0
            logger.info(
                "New best validation macro-F1=%.6f at epoch %d (checkpointed)",
                best_val_macro_f1,
                best_epoch,
            )
        else:
            epochs_without_improvement += 1
            if patience and epochs_without_improvement >= patience:
                stopped_early = True
                logger.info(
                    "Early stopping at epoch %d after %d epoch(s) without "
                    "improvement (patience=%d)",
                    epoch,
                    epochs_without_improvement,
                    patience,
                )
                break

    if best_epoch == 0:
        # No epoch ran (epochs <= 0); report a defined score rather than -inf.
        best_val_macro_f1 = 0.0

    return TrainResult(
        best_val_macro_f1=best_val_macro_f1,
        best_epoch=best_epoch,
        best_state_dict=best_state_dict,
        history=history,
        stopped_early=stopped_early,
        last_epoch=last_epoch,
        epochs_without_improvement=epochs_without_improvement,
        last_state_dict=_cpu_state_dict(model),
        best_optimizer_state_dict=best_optimizer_state_dict,
        last_optimizer_state_dict=copy.deepcopy(optimiser.state_dict()),
    )
