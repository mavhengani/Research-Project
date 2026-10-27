"""Reproducibility writer for Phase 3A baseline training (KIRO_SPEC §22).

Every training run writes a *fresh* artifact directory under
``outputs/runs/<run-id>/`` that captures enough information to reproduce the
run: the effective config, the environment, the git commit, label maps, the
three split manifests, metrics, the best checkpoint, the training log, and
the model predictions.

Two guarantees shape this module:

* **Never overwrite a prior run.** :func:`new_run_dir` mints a unique
  ``<run-id>`` (timestamp + short uuid suffix) and, in the unlikely event of
  a collision, keeps trying until it finds an unused directory. It never
  reuses or clobbers an existing run directory (Req 37.5, §22).

* **Log and continue on partial failure.** :func:`write_run` attempts every
  §22 artifact independently. If a subset fails to write -- a manifest source
  is missing, ``torch`` is unavailable for the checkpoint, etc. -- the
  failure is logged via :func:`banking_tasci.logging_utils.get_logger` and
  the run is still considered complete. It returns a per-artifact success map
  rather than aborting (Req 37.5, Req 29.2).

Credential handling (Req 29.3, §22): the environment record captures the
Python version, PyTorch version (when importable), platform, installed
package versions, the seed value, and source-data checksums. It NEVER
records SSH passwords, private keys, API tokens, or other raw sensitive
values -- only benign version/metadata strings and caller-supplied checksums.
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from banking_tasci.logging_utils import get_logger

# The §22 run-artifact filenames, kept as module constants so callers and
# tests can reference them without hard-coding strings.
CONFIG_FILE = "config.yaml"
ENVIRONMENT_FILE = "environment.txt"
GIT_COMMIT_FILE = "git_commit.txt"
LABEL_MAPS_FILE = "label_maps.json"
TRAIN_MANIFEST_FILE = "train_manifest.csv"
VALIDATION_MANIFEST_FILE = "validation_manifest.csv"
TEST_MANIFEST_FILE = "test_manifest.csv"
METRICS_FILE = "metrics.json"
CHECKPOINT_FILE = "best_checkpoint.pt"
TRAINING_LOG_FILE = "training_log.txt"
PREDICTIONS_FILE = "predictions.jsonl"

# The manifests are copied from the split directory; map artifact filename ->
# source filename in the split dir (they share names here, but the mapping
# keeps the intent explicit).
_MANIFEST_FILES = (
    TRAIN_MANIFEST_FILE,
    VALIDATION_MANIFEST_FILE,
    TEST_MANIFEST_FILE,
)

# A small allow-list of packages whose versions are useful and safe to record
# in environment.txt. Absent packages are simply skipped (never fatal).
_ENV_PACKAGES = (
    "numpy",
    "pandas",
    "scikit-learn",
    "sklearn",
    "transformers",
    "seqeval",
    "hypothesis",
    "pyyaml",
    "yaml",
)


@dataclass
class RunArtifacts:
    """Everything :func:`write_run` needs to materialise a §22 run directory.

    Only ``config`` and ``label_maps`` are required; every other field is
    optional and simply skipped (and marked accordingly in the success map)
    when absent.

    Attributes:
        config: the effective run configuration, written as ``config.yaml``.
        label_maps: task -> {label: id} mappings, written as
            ``label_maps.json``.
        metrics: optional metrics dict, written as ``metrics.json``.
        best_state_dict: optional model ``state_dict``, saved via
            ``torch.save`` as ``best_checkpoint.pt`` (skipped when torch is
            unavailable).
        predictions: optional list of prediction records, written one JSON
            object per line as ``predictions.jsonl``.
        training_log: optional training log text, written as
            ``training_log.txt``.
        split_dir: optional directory to copy the three manifests from.
        seed: optional seed value recorded in ``environment.txt``.
        source_checksums: optional mapping of source-data name -> checksum,
            recorded in ``environment.txt`` (Req 29.3).
    """

    config: dict
    label_maps: dict
    metrics: "dict | None" = None
    best_state_dict: "dict | None" = None
    predictions: "list[dict] | None" = None
    training_log: "str | None" = None
    split_dir: "str | Path | None" = None
    seed: "int | None" = None
    source_checksums: "dict | None" = field(default=None)


def new_run_dir(runs_root: "str | Path" = "outputs/runs") -> Path:
    """Create and return a fresh, non-colliding ``outputs/runs/<run-id>/`` dir.

    ``<run-id>`` is a timestamp (microsecond precision) plus a short uuid
    suffix, which makes practical collisions vanishingly unlikely. Should one
    still occur, a new id is generated until an unused directory is found --
    an existing run directory is never reused or overwritten (Req 37.5, §22).

    The directory (and any missing parents) is created before it is returned.
    """
    runs_root = Path(runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)

    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        suffix = uuid.uuid4().hex[:8]
        run_dir = runs_root / f"{timestamp}_{suffix}"
        try:
            # exist_ok=False makes this fail loudly on the (improbable)
            # collision, so we loop and pick a new id rather than overwrite.
            run_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:  # pragma: no cover - collision is improbable
            continue
        return run_dir


def _package_version(name: str) -> "str | None":
    """Return the installed version of ``name`` or None when unavailable.

    Uses :mod:`importlib.metadata` and never raises; a missing or
    unresolvable package simply yields None.
    """
    try:
        from importlib import metadata

        return metadata.version(name)
    except Exception:
        return None


def _torch_version() -> "str | None":
    """Return the installed ``torch`` version, or None when not importable."""
    try:
        import torch

        return str(torch.__version__)
    except Exception:
        return None


def _build_environment_text(artifacts: RunArtifacts) -> str:
    """Compose the ``environment.txt`` body.

    Records only benign version/metadata strings, the seed, and
    caller-supplied source-data checksums. Never emits credentials or raw
    sensitive values (Req 29.3, §22).
    """
    lines: list[str] = []
    lines.append("# banking-tasci run environment (no credentials, no raw sensitive values)")
    lines.append(f"generated_at: {datetime.now().isoformat()}")
    lines.append(f"python_version: {platform.python_version()}")
    lines.append(f"python_implementation: {platform.python_implementation()}")
    lines.append(f"platform: {platform.platform()}")
    lines.append(f"machine: {platform.machine()}")

    torch_version = _torch_version()
    lines.append(f"torch_version: {torch_version if torch_version else 'not installed'}")

    seen: set[str] = set()
    lines.append("packages:")
    for name in _ENV_PACKAGES:
        if name in seen:
            continue
        seen.add(name)
        version = _package_version(name)
        if version is not None:
            lines.append(f"  {name}: {version}")

    seed_value = artifacts.seed
    lines.append(f"seed: {seed_value if seed_value is not None else 'unspecified'}")

    lines.append("source_data_checksums:")
    checksums = artifacts.source_checksums or {}
    if checksums:
        for key in sorted(checksums):
            lines.append(f"  {key}: {checksums[key]}")
    else:
        lines.append("  (none provided)")

    return "\n".join(lines) + "\n"


def _read_git_commit() -> str:
    """Return the current git commit hash, or a clear marker when unavailable.

    Runs ``git rev-parse HEAD`` and never crashes: if git is not installed,
    this is not a git repository, or the command otherwise fails, a
    descriptive marker string is returned instead (Req 37.5).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return "unknown (git not available)"
    except Exception as exc:  # pragma: no cover - defensive
        return f"unknown (git error: {exc})"

    if result.returncode != 0:
        return "unknown (not a git repository)"

    commit = result.stdout.strip()
    return commit if commit else "unknown (empty commit)"


def write_run(artifacts: RunArtifacts, run_dir: "str | Path") -> "dict[str, bool]":
    """Write every §22 artifact into ``run_dir``; return a per-artifact map.

    Each artifact is attempted independently. On any individual failure the
    error is logged via :func:`get_logger` and that artifact is marked
    ``False`` in the returned map; the remaining artifacts are still written
    and the run is still considered complete. This function does not raise on
    an individual artifact failure (Req 37.5, Req 29.2).

    The returned map is keyed by artifact filename (the module ``*_FILE``
    constants), with ``True`` for a successful write and ``False`` for a
    logged failure or a skipped-because-absent optional artifact.
    """
    logger = get_logger("banking_tasci.training.reproducibility")
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, bool] = {}

    def _attempt(filename: str, writer) -> None:
        """Run ``writer`` guarded; log+record failure instead of raising."""
        try:
            writer()
            results[filename] = True
        except Exception as exc:
            logger.warning(
                "failed to write run artifact '%s' in '%s': %s",
                filename,
                run_dir,
                exc,
            )
            results[filename] = False

    # config.yaml (required field) ------------------------------------------
    def _write_config() -> None:
        with (run_dir / CONFIG_FILE).open("w", encoding="utf-8") as fh:
            yaml.safe_dump(artifacts.config, fh, default_flow_style=False, sort_keys=True)

    _attempt(CONFIG_FILE, _write_config)

    # environment.txt --------------------------------------------------------
    def _write_environment() -> None:
        text = _build_environment_text(artifacts)
        (run_dir / ENVIRONMENT_FILE).write_text(text, encoding="utf-8")

    _attempt(ENVIRONMENT_FILE, _write_environment)

    # git_commit.txt ---------------------------------------------------------
    def _write_git_commit() -> None:
        commit = _read_git_commit()
        (run_dir / GIT_COMMIT_FILE).write_text(commit + "\n", encoding="utf-8")

    _attempt(GIT_COMMIT_FILE, _write_git_commit)

    # label_maps.json (required field) --------------------------------------
    def _write_label_maps() -> None:
        with (run_dir / LABEL_MAPS_FILE).open("w", encoding="utf-8") as fh:
            json.dump(artifacts.label_maps, fh, indent=2, ensure_ascii=False, sort_keys=True)

    _attempt(LABEL_MAPS_FILE, _write_label_maps)

    # the three manifests (copied from split_dir) ---------------------------
    for manifest_name in _MANIFEST_FILES:
        def _copy_manifest(name: str = manifest_name) -> None:
            if artifacts.split_dir is None:
                raise FileNotFoundError(
                    f"no split_dir provided; cannot copy manifest '{name}'"
                )
            source = Path(artifacts.split_dir) / name
            if not source.is_file():
                raise FileNotFoundError(f"manifest source not found: '{source}'")
            shutil.copyfile(source, run_dir / name)

        _attempt(manifest_name, _copy_manifest)

    # metrics.json -----------------------------------------------------------
    def _write_metrics() -> None:
        if artifacts.metrics is None:
            raise ValueError("no metrics provided")
        with (run_dir / METRICS_FILE).open("w", encoding="utf-8") as fh:
            json.dump(artifacts.metrics, fh, indent=2, ensure_ascii=False, sort_keys=True)

    _attempt(METRICS_FILE, _write_metrics)

    # best_checkpoint.pt (requires torch) -----------------------------------
    def _write_checkpoint() -> None:
        if artifacts.best_state_dict is None:
            raise ValueError("no best_state_dict provided")
        import torch  # imported lazily so torch's absence is non-fatal

        torch.save(artifacts.best_state_dict, run_dir / CHECKPOINT_FILE)

    _attempt(CHECKPOINT_FILE, _write_checkpoint)

    # training_log.txt -------------------------------------------------------
    def _write_training_log() -> None:
        if artifacts.training_log is None:
            raise ValueError("no training_log provided")
        (run_dir / TRAINING_LOG_FILE).write_text(artifacts.training_log, encoding="utf-8")

    _attempt(TRAINING_LOG_FILE, _write_training_log)

    # predictions.jsonl ------------------------------------------------------
    def _write_predictions() -> None:
        if artifacts.predictions is None:
            raise ValueError("no predictions provided")
        with (run_dir / PREDICTIONS_FILE).open("w", encoding="utf-8") as fh:
            for row in artifacts.predictions:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    _attempt(PREDICTIONS_FILE, _write_predictions)

    ok = sum(1 for v in results.values() if v)
    logger.info(
        "wrote run artifacts to '%s': %d/%d succeeded",
        run_dir,
        ok,
        len(results),
    )

    return results
