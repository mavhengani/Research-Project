"""Tests for the reproducibility writer
(src/banking_tasci/training/reproducibility.py).

Covers KIRO_SPEC §22 / Req 37.5 / Req 29.2 / Req 29.3:
- `new_run_dir` returns a fresh directory and two successive calls never
  collide (different paths, never overwriting a prior run).
- `write_run` with a full RunArtifacts writes every §22 artifact and returns
  a success map marking the written files True; environment.txt records a
  python version and no obvious secret.
- A partial-failure test: a non-existent split_dir makes the manifest copies
  fail (recorded False) while the other artifacts are still written True and
  `write_run` does not raise (Req 37.5).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pytest  # noqa: E402
import yaml  # noqa: E402

from banking_tasci.training.reproducibility import (  # noqa: E402
    CHECKPOINT_FILE,
    CONFIG_FILE,
    ENVIRONMENT_FILE,
    GIT_COMMIT_FILE,
    LABEL_MAPS_FILE,
    METRICS_FILE,
    PREDICTIONS_FILE,
    TEST_MANIFEST_FILE,
    TRAIN_MANIFEST_FILE,
    TRAINING_LOG_FILE,
    VALIDATION_MANIFEST_FILE,
    RunArtifacts,
    new_run_dir,
    write_run,
)

try:  # torch is installed (CPU) per the plan, but degrade gracefully.
    import torch  # noqa: F401

    _HAS_TORCH = True
except Exception:  # pragma: no cover - torch absence path
    _HAS_TORCH = False


_MANIFESTS = (TRAIN_MANIFEST_FILE, VALIDATION_MANIFEST_FILE, TEST_MANIFEST_FILE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_split_dir(root: Path) -> Path:
    """Create a split dir with the three manifests and return its path."""
    split_dir = root / "split"
    split_dir.mkdir(parents=True, exist_ok=True)
    for name in _MANIFESTS:
        (split_dir / name).write_text(
            "record_id,text\nr1,hello\n", encoding="utf-8"
        )
    return split_dir


def _full_artifacts(split_dir: "Path | None") -> RunArtifacts:
    return RunArtifacts(
        config={"seed": 42, "model": "svm", "task": "intent"},
        label_maps={"intent": {"complaint": 0, "praise": 1}},
        metrics={"note": "synthetic - not a research metric"},
        best_state_dict={"weight": torch.zeros(2, 2)} if _HAS_TORCH else {"weight": [0, 0]},
        predictions=[{"record_id": "r1", "pred": "complaint"}],
        training_log="epoch 1: ok\nepoch 2: ok\n",
        split_dir=str(split_dir) if split_dir is not None else None,
        seed=42,
        source_checksums={"bank_reviews3.csv": "abc123"},
    )


# ---------------------------------------------------------------------------
# new_run_dir
# ---------------------------------------------------------------------------


def test_new_run_dir_returns_fresh_existing_directory(tmp_path: Path) -> None:
    run_dir = new_run_dir(tmp_path / "runs")
    assert run_dir.is_dir()
    assert run_dir.parent == tmp_path / "runs"


def test_new_run_dir_two_calls_never_collide(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    first = new_run_dir(runs_root)
    second = new_run_dir(runs_root)
    assert first != second
    assert first.is_dir() and second.is_dir()


def test_new_run_dir_does_not_overwrite_prior_run(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    first = new_run_dir(runs_root)
    (first / "sentinel.txt").write_text("keep me", encoding="utf-8")

    second = new_run_dir(runs_root)
    # The prior run's contents are untouched.
    assert (first / "sentinel.txt").read_text(encoding="utf-8") == "keep me"
    assert second != first


# ---------------------------------------------------------------------------
# write_run - full artifacts
# ---------------------------------------------------------------------------


def test_write_run_full_writes_all_artifacts(tmp_path: Path) -> None:
    split_dir = _make_split_dir(tmp_path)
    run_dir = new_run_dir(tmp_path / "runs")

    results = write_run(_full_artifacts(split_dir), run_dir)

    # Always-written artifacts.
    for name in (
        CONFIG_FILE,
        ENVIRONMENT_FILE,
        GIT_COMMIT_FILE,
        LABEL_MAPS_FILE,
        METRICS_FILE,
        TRAINING_LOG_FILE,
        PREDICTIONS_FILE,
        *_MANIFESTS,
    ):
        assert results[name] is True, f"expected {name} to be written"
        assert (run_dir / name).is_file()

    # Checkpoint depends on torch availability.
    if _HAS_TORCH:
        assert results[CHECKPOINT_FILE] is True
        assert (run_dir / CHECKPOINT_FILE).is_file()
    else:  # pragma: no cover - torch is expected present in CI
        assert results[CHECKPOINT_FILE] is False
        assert not (run_dir / CHECKPOINT_FILE).exists()


def test_write_run_config_and_label_maps_roundtrip(tmp_path: Path) -> None:
    split_dir = _make_split_dir(tmp_path)
    run_dir = new_run_dir(tmp_path / "runs")
    artifacts = _full_artifacts(split_dir)

    write_run(artifacts, run_dir)

    loaded_config = yaml.safe_load((run_dir / CONFIG_FILE).read_text(encoding="utf-8"))
    assert loaded_config == artifacts.config

    import json

    loaded_maps = json.loads((run_dir / LABEL_MAPS_FILE).read_text(encoding="utf-8"))
    assert loaded_maps == artifacts.label_maps


def test_environment_txt_has_python_version_and_no_secret(tmp_path: Path) -> None:
    split_dir = _make_split_dir(tmp_path)
    run_dir = new_run_dir(tmp_path / "runs")

    write_run(_full_artifacts(split_dir), run_dir)

    env_text = (run_dir / ENVIRONMENT_FILE).read_text(encoding="utf-8")
    # A python version is recorded.
    assert "python_version:" in env_text
    import platform

    assert platform.python_version() in env_text
    # The seed and a source checksum are recorded (Req 29.3).
    assert "seed: 42" in env_text
    assert "abc123" in env_text
    # No obvious secret material leaks into the environment record.
    lowered = env_text.lower()
    for forbidden in ("password", "secret", "api_key", "api-key", "token", "private key", "begin rsa"):
        assert forbidden not in lowered


def test_predictions_jsonl_is_one_object_per_line(tmp_path: Path) -> None:
    split_dir = _make_split_dir(tmp_path)
    run_dir = new_run_dir(tmp_path / "runs")

    write_run(_full_artifacts(split_dir), run_dir)

    import json

    lines = (run_dir / PREDICTIONS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"record_id": "r1", "pred": "complaint"}


# ---------------------------------------------------------------------------
# write_run - partial failure (Req 37.5)
# ---------------------------------------------------------------------------


def test_write_run_partial_failure_continues(tmp_path: Path) -> None:
    """A non-existent split_dir makes manifest copies fail, but the run still
    completes and the other artifacts are written (Req 37.5, Req 29.2)."""
    missing_split = tmp_path / "does_not_exist"
    assert not missing_split.exists()
    run_dir = new_run_dir(tmp_path / "runs")

    # Must not raise despite the missing manifest sources.
    results = write_run(_full_artifacts(missing_split), run_dir)

    # Manifests are marked False and were not written.
    for name in _MANIFESTS:
        assert results[name] is False
        assert not (run_dir / name).exists()

    # Other artifacts are still written True.
    for name in (
        CONFIG_FILE,
        ENVIRONMENT_FILE,
        GIT_COMMIT_FILE,
        LABEL_MAPS_FILE,
        METRICS_FILE,
        TRAINING_LOG_FILE,
        PREDICTIONS_FILE,
    ):
        assert results[name] is True
        assert (run_dir / name).is_file()


def test_write_run_missing_optionals_marked_false_not_raised(tmp_path: Path) -> None:
    """Absent optional artifacts (metrics, checkpoint, predictions, log) are
    marked False without raising; required config/label_maps still True."""
    run_dir = new_run_dir(tmp_path / "runs")
    artifacts = RunArtifacts(
        config={"seed": 1},
        label_maps={"intent": {"a": 0}},
    )

    results = write_run(artifacts, run_dir)

    assert results[CONFIG_FILE] is True
    assert results[LABEL_MAPS_FILE] is True
    assert results[ENVIRONMENT_FILE] is True
    assert results[GIT_COMMIT_FILE] is True
    # No source for these optionals -> recorded False, never raised.
    assert results[METRICS_FILE] is False
    assert results[CHECKPOINT_FILE] is False
    assert results[TRAINING_LOG_FILE] is False
    assert results[PREDICTIONS_FILE] is False
    for name in _MANIFESTS:
        assert results[name] is False
