"""Tests for the baseline training CLI + runner (scripts/train_baselines.py,
src/banking_tasci/training/baseline_runner.py), Phase 3A Part 11.

- Every (model, task) command stops with the exact blocked message while the
  pilot is unannotated (no gold, no manifests).
- With a TEMPORARY synthetic gold fixture + leakage-safe manifests, the SVM and
  BiLSTM intent paths actually run, select on validation, evaluate on test
  AFTER selection, and write run artifacts (predictions + metrics + label maps).

The synthetic fixture is a TEST fixture only — never research data.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import AnnotationRecord, AspectSpan, write_jsonl  # noqa: E402
from banking_tasci.training.supervised_gate import SUPERVISED_BLOCKED_MESSAGE  # noqa: E402


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "train_baselines_cli", _ROOT / "scripts" / "train_baselines.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = _load_cli()


_COMBOS = [
    ("svm", "intent", "svm_intent"),
    ("svm", "sentiment", "svm_sentiment"),
    ("bilstm", "intent", "bilstm_intent"),
    ("bilstm", "sentiment", "bilstm_sentiment"),
    ("bert", "aspect", "bert_aspect"),
    ("bert", "intent", "bert_intent"),
    ("bert", "sentiment", "bert_sentiment"),
]


@pytest.mark.parametrize("model,task,cfg_name", _COMBOS)
def test_cli_blocks_without_gold(model, task, cfg_name, tmp_path, capsys):
    # Point at empty annotations/splits so the gate blocks.
    split_dir = tmp_path / "processed"
    split_dir.mkdir()
    rc = CLI.main([
        "--model", model, "--task", task,
        "--config", str(_ROOT / "configs" / "baselines" / f"{cfg_name}.yaml"),
        "--annotations", str(tmp_path / "annotations" / "pilot_adjudicated.jsonl"),
        "--split-dir", str(split_dir),
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert SUPERVISED_BLOCKED_MESSAGE in err


# ---------------------------------------------------------------------------
# Synthetic gold fixture (test-only) to exercise the real training paths.
# ---------------------------------------------------------------------------


def _rec(rid, text, term, sentiment, intent):
    start = text.index(term)
    return AnnotationRecord(
        record_id=rid, source="bank_reviews", region="local", text=text,
        previous_text="[NO_CONTEXT]", context_available=False,
        aspects=[AspectSpan(term=term, start=start, end=start + len(term),
                            category="fees", sentiment=sentiment)],
        intent=intent, intent_ambiguous=False, alternative_intent=None,
        annotator_id="lead", annotation_status="completed", notes="",
    )


def _write_manifest(path, ids):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["record_id"])
        for i in ids:
            w.writerow([i])


def _gold_fixture(base: Path):
    ann_dir = base / "annotations"
    split_dir = base / "processed"
    ann_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)

    records = [
        _rec("t1", "the fees are terrible and unfair", "fees", "negative", "complaint"),
        _rec("t2", "awful fees far too high and broken", "fees", "negative", "complaint"),
        _rec("t3", "the staff are excellent and kind", "staff", "positive", "compliment"),
        _rec("t4", "wonderful helpful staff great branch", "staff", "positive", "compliment"),
        _rec("v1", "the fees felt horrible and excessive", "fees", "negative", "complaint"),
        _rec("v2", "friendly staff great and lovely", "staff", "positive", "compliment"),
        _rec("e1", "the fees are unfair and painful", "fees", "negative", "complaint"),
        _rec("e2", "the staff were kind and wonderful", "staff", "positive", "compliment"),
    ]
    ann_path = ann_dir / "pilot_adjudicated.jsonl"
    write_jsonl(records, ann_path)

    _write_manifest(split_dir / "train_manifest.csv", ["t1", "t2", "t3", "t4"])
    _write_manifest(split_dir / "validation_manifest.csv", ["v1", "v2"])
    _write_manifest(split_dir / "test_manifest.csv", ["e1", "e2"])
    return ann_path, split_dir


def _latest_run_dir(runs_root: Path) -> Path:
    runs = sorted(p for p in runs_root.iterdir() if p.is_dir())
    assert runs, "no run directory created"
    return runs[-1]


def test_cli_svm_intent_end_to_end(tmp_path):
    pytest.importorskip("sklearn")
    ann_path, split_dir = _gold_fixture(tmp_path)
    runs_root = tmp_path / "runs"

    rc = CLI.main([
        "--model", "svm", "--task", "intent",
        "--config", str(_ROOT / "configs" / "baselines" / "svm_intent.yaml"),
        "--annotations", str(ann_path), "--split-dir", str(split_dir),
        "--runs-root", str(runs_root),
    ])
    assert rc == 0

    run_dir = _latest_run_dir(runs_root)
    # Artifacts written.
    assert (run_dir / "svm" / "model.joblib").exists()
    assert (run_dir / "svm" / "extractor.json").exists()
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert "test" in metrics and "macro_f1" in metrics["test"]
    label_maps = json.loads((run_dir / "label_maps.json").read_text())
    assert "intent" in label_maps
    # Predictions written for the test split (2 records).
    preds = [json.loads(l) for l in (run_dir / "predictions.jsonl").read_text().splitlines()]
    assert len(preds) == 2


def test_cli_bilstm_intent_end_to_end(tmp_path):
    ann_path, split_dir = _gold_fixture(tmp_path)
    runs_root = tmp_path / "runs"

    rc = CLI.main([
        "--model", "bilstm", "--task", "intent",
        "--config", str(_ROOT / "configs" / "baselines" / "bilstm_intent.yaml"),
        "--annotations", str(ann_path), "--split-dir", str(split_dir),
        "--runs-root", str(runs_root),
    ])
    assert rc == 0

    run_dir = _latest_run_dir(runs_root)
    assert (run_dir / "best_checkpoint.pt").exists()
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert "test" in metrics
    assert "best_val_macro_f1" in metrics



# ---------------------------------------------------------------------------
# Regression tests for the duplicate-definition bug in
# src/banking_tasci/training/baseline_runner.py
#
# Two definitions of `_write_bilstm_posthoc_artifacts` existed in that module.
# The second shadowed the first and declared an extra leading `model`
# parameter it never used, so the 8-argument call site in `_train_bilstm`
# bound `splits` into `metrics` and left `splits` unfilled, raising:
#
#   TypeError: _write_bilstm_posthoc_artifacts() missing 1 required
#              positional argument: 'splits'
#
# These tests pin the contract so the duplicate cannot silently return.
# ---------------------------------------------------------------------------


def test_bilstm_posthoc_writer_is_defined_exactly_once():
    """A re-introduced duplicate definition would silently shadow the real one."""
    source = (
        _ROOT / "src" / "banking_tasci" / "training" / "baseline_runner.py"
    ).read_text(encoding="utf-8")
    definitions = [
        line
        for line in source.splitlines()
        if line.startswith("def _write_bilstm_posthoc_artifacts")
    ]
    assert len(definitions) == 1, (
        f"expected exactly 1 definition, found {len(definitions)}: {definitions}"
    )


def test_bilstm_posthoc_writer_signature_matches_call_site():
    """The call site passes 8 positional arguments; the signature must accept
    exactly those, with `splits` last and no unused leading `model`."""
    import inspect

    from banking_tasci.training import baseline_runner

    params = list(
        inspect.signature(baseline_runner._write_bilstm_posthoc_artifacts).parameters
    )
    assert params == [
        "run_dir",
        "task",
        "label_map",
        "test_examples",
        "gold",
        "preds",
        "metrics",
        "splits",
    ]
    # `splits` must stay REQUIRED - making it optional would mask the bug
    # rather than fix it.
    signature = inspect.signature(baseline_runner._write_bilstm_posthoc_artifacts)
    assert signature.parameters["splits"].default is inspect.Parameter.empty


def test_bilstm_run_writes_all_posthoc_artifacts(tmp_path):
    """The posthoc writer must actually produce its artifacts, not be skipped."""
    ann_path, split_dir = _gold_fixture(tmp_path)
    runs_root = tmp_path / "runs"

    rc = CLI.main([
        "--model", "bilstm", "--task", "intent",
        "--config", str(_ROOT / "configs" / "baselines" / "bilstm_intent.yaml"),
        "--annotations", str(ann_path), "--split-dir", str(split_dir),
        "--runs-root", str(runs_root),
    ])
    assert rc == 0

    run_dir = _latest_run_dir(runs_root)
    for name in (
        "validation_metrics.json",
        "test_metrics.json",
        "confusion_matrix.csv",
        "subgroup_metrics.json",
        "cluster_job_metadata.json",
    ):
        assert (run_dir / name).exists(), f"missing posthoc artifact: {name}"


def test_bilstm_posthoc_subgroups_resolve_from_test_split(tmp_path):
    """`splits` must reach the writer intact: subgroup metrics are derived by
    looking test examples up in splits["test"], so a missing/empty splits
    argument would yield no subgroups at all."""
    ann_path, split_dir = _gold_fixture(tmp_path)
    runs_root = tmp_path / "runs"

    assert CLI.main([
        "--model", "bilstm", "--task", "intent",
        "--config", str(_ROOT / "configs" / "baselines" / "bilstm_intent.yaml"),
        "--annotations", str(ann_path), "--split-dir", str(split_dir),
        "--runs-root", str(runs_root),
    ]) == 0

    run_dir = _latest_run_dir(runs_root)
    subgroups = json.loads((run_dir / "subgroup_metrics.json").read_text())

    assert subgroups["task"] == "intent"
    # The fixture's test records are source=bank_reviews, region=local,
    # context_available=False -> these subgroups must be present.
    assert "combined" in subgroups["groups"]
    assert "reviews" in subgroups["groups"]
    assert "no_context" in subgroups["groups"]
    assert "south_africa" in subgroups["groups"]  # region != "international"


def test_bilstm_split_identities_are_preserved(tmp_path):
    """Train/validation/test identities must survive into the run artifacts:
    predictions must cover exactly the test manifest, and no more."""
    ann_path, split_dir = _gold_fixture(tmp_path)
    runs_root = tmp_path / "runs"

    assert CLI.main([
        "--model", "bilstm", "--task", "intent",
        "--config", str(_ROOT / "configs" / "baselines" / "bilstm_intent.yaml"),
        "--annotations", str(ann_path), "--split-dir", str(split_dir),
        "--runs-root", str(runs_root),
    ]) == 0

    run_dir = _latest_run_dir(runs_root)
    predicted_ids = {
        json.loads(line)["record_id"]
        for line in (run_dir / "predictions.jsonl").read_text().splitlines()
        if line.strip()
    }
    # Exactly the test manifest - never the train or validation records.
    assert predicted_ids == {"e1", "e2"}
    assert not predicted_ids & {"t1", "t2", "t3", "t4"}
    assert not predicted_ids & {"v1", "v2"}


def test_bilstm_selection_uses_validation_not_test(tmp_path):
    """Model selection must be driven by validation macro-F1. Test records must
    not influence checkpoint selection (Requirements Section 15.1)."""
    ann_path, split_dir = _gold_fixture(tmp_path)
    runs_root = tmp_path / "runs"

    assert CLI.main([
        "--model", "bilstm", "--task", "intent",
        "--config", str(_ROOT / "configs" / "baselines" / "bilstm_intent.yaml"),
        "--annotations", str(ann_path), "--split-dir", str(split_dir),
        "--runs-root", str(runs_root),
    ]) == 0

    run_dir = _latest_run_dir(runs_root)
    validation = json.loads((run_dir / "validation_metrics.json").read_text())

    # Selection metadata comes from the validation stream only.
    assert "best_val_macro_f1" in validation
    assert "best_epoch" in validation
    assert "history" in validation
    for row in validation["history"]:
        # Each epoch records a validation score; no test score is consulted
        # during selection.
        assert "val_macro_f1" in row
        assert "test_macro_f1" not in row
