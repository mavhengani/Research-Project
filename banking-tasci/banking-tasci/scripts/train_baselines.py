"""train_baselines.py — unified baseline training CLI (Phase 3A, Part 11).

Usage:
    python scripts/train_baselines.py --model svm    --task intent    --config configs/baselines/svm_intent.yaml
    python scripts/train_baselines.py --model svm    --task sentiment --config configs/baselines/svm_sentiment.yaml
    python scripts/train_baselines.py --model bilstm --task intent    --config configs/baselines/bilstm_intent.yaml
    python scripts/train_baselines.py --model bilstm --task sentiment --config configs/baselines/bilstm_sentiment.yaml
    python scripts/train_baselines.py --model bert   --task aspect    --config configs/baselines/bert_aspect.yaml
    python scripts/train_baselines.py --model bert   --task intent    --config configs/baselines/bert_intent.yaml
    python scripts/train_baselines.py --model bert   --task sentiment --config configs/baselines/bert_sentiment.yaml

Every invocation:
 1. loads and validates the configuration;
 2. runs the supervised-training readiness gate (Part 6) FIRST — refusing to
    train on unannotated / incomplete data;
 3. loads the SAME split manifests for all models;
 4. records the seed and environment;
 5. writes to a unique run directory under outputs/runs/<run-id>/;
 6. saves label mappings, checkpoints, and (only after REAL training)
    predictions and metrics.

At the current project stage the pilot is UNANNOTATED, so step 2 stops every
command with the exact blocked message and NOTHING is trained or fabricated.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.logging_utils import get_logger  # noqa: E402
from banking_tasci.seed import SeedError, set_seed_from_config  # noqa: E402
from banking_tasci.training.supervised_gate import (  # noqa: E402
    SUPERVISED_BLOCKED_MESSAGE,
    assert_supervised_ready,
)

# Valid (model, task) combinations.
_VALID_COMBOS = {
    ("svm", "intent"),
    ("svm", "sentiment"),
    ("bilstm", "intent"),
    ("bilstm", "sentiment"),
    ("bert", "aspect"),
    ("bert", "intent"),
    ("bert", "sentiment"),
}

DEFAULT_ANNOTATIONS = "data/annotations/pilot_adjudicated.jsonl"
DEFAULT_SPLIT_DIR = "data/processed"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="train_baselines.py",
        description="Train a Phase 3A baseline (svm/bilstm/bert) on the adjudicated gold splits.",
    )
    parser.add_argument("--model", required=True, choices=["svm", "bilstm", "bert"])
    parser.add_argument("--task", required=True, choices=["intent", "sentiment", "aspect"])
    parser.add_argument("--config", required=True, help="Path to the baseline YAML config.")
    parser.add_argument("--annotations", default=None, help="Override adjudicated gold JSONL path.")
    parser.add_argument("--split-dir", default=None, help="Override split-manifest directory.")
    parser.add_argument("--runs-root", default="outputs/runs", help="Root for run directories.")
    return parser


def _cfg_get(cfg, dotted: str, default=None):
    """Read a dotted key from a Config/dict-like, returning default if absent."""
    cur = cfg
    for part in dotted.split("."):
        try:
            if part in cur:
                cur = cur[part]
                continue
        except TypeError:
            pass
        cur = getattr(cur, part, None)
        if cur is None:
            return default
    return default if cur is None else cur


def main(argv: "list[str] | None" = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # 1. Validate the (model, task) combination.
    if (args.model, args.task) not in _VALID_COMBOS:
        print(
            f"error: unsupported combination --model {args.model} --task {args.task}. "
            f"Valid combinations: {sorted(_VALID_COMBOS)}",
            file=sys.stderr,
        )
        return 2

    # 1. Load + validate configuration.
    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        return 2
    cfg = load_config(config_path)

    annotations_path = args.annotations or _cfg_get(cfg, "data.annotations", DEFAULT_ANNOTATIONS)
    split_dir = args.split_dir or _cfg_get(cfg, "data.split_dir", DEFAULT_SPLIT_DIR)

    logger = get_logger("banking_tasci.train_baselines", cfg)
    logger.info("Preparing %s/%s baseline from %s", args.model, args.task, config_path)

    # 2 + 3. Readiness gate FIRST — refuse unannotated / incomplete input.
    try:
        assert_supervised_ready(annotations_path, split_dir)
    except RuntimeError as exc:
        # Expected at the current stage: the pilot is unannotated.
        logger.error("Readiness gate failed: %s", exc)
        print(SUPERVISED_BLOCKED_MESSAGE, file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Post-readiness training path. Only reached once adjudicated gold +
    # leakage-safe manifests exist. Never fabricates data.
    # ------------------------------------------------------------------
    try:
        set_seed_from_config(cfg)
    except SeedError:
        if args.model != "svm":
            raise
        logger.warning("Torch seeding failed; continuing with Python/NumPy seeding for SVM.")
    from banking_tasci.training.baseline_runner import run_baseline  # local import

    return run_baseline(
        model=args.model,
        task=args.task,
        cfg=cfg,
        annotations_path=annotations_path,
        split_dir=split_dir,
        runs_root=args.runs_root,
        logger=logger,
    )


if __name__ == "__main__":
    raise SystemExit(main())

