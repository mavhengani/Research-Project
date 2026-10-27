"""Tests for the evaluation metrics (src/banking_tasci/evaluation/metrics.py),
Phase 3A Part 12. Pure, deterministic checks on hand-computable cases. No gold
data and no fabricated metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.evaluation.metrics import (  # noqa: E402
    bio_span_metrics,
    bio_token_metrics,
    classification_metrics,
)


def test_classification_metrics_perfect():
    m = classification_metrics([0, 1, 2, 1], [0, 1, 2, 1], num_classes=3,
                               id_to_label={0: "a", 1: "b", 2: "c"})
    assert m["accuracy"] == pytest.approx(1.0)
    assert m["macro_f1"] == pytest.approx(1.0)
    assert m["weighted_f1"] == pytest.approx(1.0)
    assert m["per_class"]["b"]["support"] == 2
    # Diagonal confusion matrix.
    assert m["confusion_matrix"] == [[1, 0, 0], [0, 2, 0], [0, 0, 1]]


def test_classification_metrics_known_partial():
    # y_true=[0,0,1,1], y_pred=[0,1,1,1]
    # class0: tp1 fp0 fn1 -> P1 R.5 F1 2/3 ; class1: tp2 fp1 fn0 -> P2/3 R1 F1 0.8
    m = classification_metrics([0, 0, 1, 1], [0, 1, 1, 1], num_classes=2)
    assert m["accuracy"] == pytest.approx(0.75)
    assert m["macro_f1"] == pytest.approx(((2 / 3) + 0.8) / 2)
    # weighted by support (2 each) equals the macro here.
    assert m["weighted_f1"] == pytest.approx(((2 / 3) * 2 + 0.8 * 2) / 4)
    assert m["confusion_matrix"] == [[1, 1], [0, 2]]


def test_bio_token_metrics_counts():
    gold = [["O", "B-ASP", "I-ASP", "O"]]
    pred = [["O", "B-ASP", "O", "O"]]
    m = bio_token_metrics(gold, pred)
    # positives gold: idx1,2 ; pred: idx1 -> tp1, fp0, fn1
    assert m["tp"] == 1 and m["fp"] == 0 and m["fn"] == 1
    assert m["token_precision"] == pytest.approx(1.0)
    assert m["token_recall"] == pytest.approx(0.5)


def test_bio_span_metrics_exact_and_boundary():
    gold = [[(4, 8)], [(0, 10)]]
    pred = [[(4, 8)], [(0, 6)]]  # doc0 exact; doc1 boundary error (overlap, not exact)
    sm = bio_span_metrics(gold, pred, record_ids=["d0", "d1"])
    assert sm.tp == 1  # (4,8) exact
    assert sm.fp == 1  # (0,6) unmatched pred
    assert sm.fn == 1  # (0,10) unmatched gold
    assert sm.exact_span_precision == pytest.approx(0.5)
    assert sm.exact_span_recall == pytest.approx(0.5)
    # Boundary error recorded for the overlapping-but-not-exact pair.
    assert sm.boundary_errors == [{"record_id": "d1", "predicted": [0, 6], "gold": [0, 10]}]


def test_bio_span_metrics_no_predictions():
    sm = bio_span_metrics([[(1, 3)]], [[]])
    assert sm.tp == 0 and sm.fn == 1 and sm.fp == 0
    assert sm.exact_span_f1 == pytest.approx(0.0)

