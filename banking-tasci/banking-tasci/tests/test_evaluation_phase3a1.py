"""Tests for the Phase 3A.1 evaluation modules.

Covers:
- banking_tasci.evaluation.end_to_end
- banking_tasci.evaluation.regional
- banking_tasci.evaluation.ablation
- banking_tasci.evaluation.reports

All tests use small in-memory fixtures.  No models are run, no files on
disk are read, and no research data is generated.

Run with:
    pytest tests/test_evaluation_phase3a1.py -v
"""
from __future__ import annotations

import json
import csv
import tempfile
from pathlib import Path

import pytest

from banking_tasci.evaluation.end_to_end import (
    span_sentiment_metrics,
    span_category_sentiment_metrics,
    span_sentiment_intent_metrics,
    all_tuple_metrics,
)
from banking_tasci.evaluation.regional import (
    evaluate_by_group,
    evaluate_by_region,
    evaluate_by_source,
    evaluate_by_context_availability,
    INSUFFICIENT,
    OK,
)
from banking_tasci.evaluation.ablation import (
    build_ablation_report,
    comparison_table,
    FULL_MODEL,
    NO_INTENT,
    CURRENT_ONLY,
    STATUS_MISSING,
    STATUS_OK,
)
from banking_tasci.evaluation.reports import (
    write_metrics_json,
    write_classification_report_md,
    write_confusion_matrix_csv,
    write_errors_jsonl,
    write_predictions_jsonl,
    write_ablation_summary_md,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(aspects, intent="complaint", region="international",
                 source="bank_tweets", context_available=False):
    return {
        "record_id": "r1",
        "region": region,
        "source": source,
        "context_available": context_available,
        "intent": {"label": intent},
        "aspects": aspects,
    }


def _asp(start, end, sentiment="negative", category="customer_support"):
    return {"start": start, "end": end, "sentiment": sentiment, "category": category}


# ---------------------------------------------------------------------------
# end_to_end: span+sentiment
# ---------------------------------------------------------------------------


def test_span_sentiment_perfect_match():
    gold = [_make_record([_asp(0, 5)])]
    pred = [_make_record([_asp(0, 5)])]
    r = span_sentiment_metrics(gold, pred)
    assert r.f1 == 1.0
    assert r.tp == 1
    assert r.fp == 0
    assert r.fn == 0


def test_span_sentiment_all_wrong_span():
    gold = [_make_record([_asp(0, 5)])]
    pred = [_make_record([_asp(0, 6)])]  # wrong end offset
    r = span_sentiment_metrics(gold, pred)
    assert r.tp == 0
    assert r.fp == 1
    assert r.fn == 1


def test_span_sentiment_wrong_label():
    gold = [_make_record([_asp(0, 5, sentiment="negative")])]
    pred = [_make_record([_asp(0, 5, sentiment="positive")])]
    r = span_sentiment_metrics(gold, pred)
    assert r.tp == 0


def test_span_sentiment_no_aspects_both():
    gold = [_make_record([])]
    pred = [_make_record([])]
    r = span_sentiment_metrics(gold, pred)
    assert r.tp == 0 and r.fp == 0 and r.fn == 0
    assert r.records_all_correct == 1


def test_span_sentiment_extra_prediction():
    gold = [_make_record([])]
    pred = [_make_record([_asp(0, 5)])]
    r = span_sentiment_metrics(gold, pred)
    assert r.fp == 1 and r.fn == 0


def test_span_sentiment_missing_prediction():
    gold = [_make_record([_asp(0, 5)])]
    pred = [_make_record([])]
    r = span_sentiment_metrics(gold, pred)
    assert r.fn == 1 and r.fp == 0


def test_span_sentiment_duplicate_gold_tuple_counted():
    # Gold has the same span twice; prediction has it once → 1 TP, 1 FN
    gold = [_make_record([_asp(0, 5), _asp(0, 5)])]
    pred = [_make_record([_asp(0, 5)])]
    r = span_sentiment_metrics(gold, pred)
    assert r.tp == 1
    assert r.fn == 1


def test_span_sentiment_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        span_sentiment_metrics([_make_record([])], [])


def test_all_tuple_metrics_keys():
    gold = [_make_record([_asp(0, 5)])]
    pred = [_make_record([_asp(0, 5)])]
    result = all_tuple_metrics(gold, pred)
    assert "span+sentiment" in result
    assert "span+category+sentiment" in result
    assert "span+sentiment+intent" in result


def test_span_category_sentiment_wrong_category():
    gold = [_make_record([_asp(0, 5, category="cards")])]
    pred = [_make_record([_asp(0, 5, category="fees")])]
    r = span_category_sentiment_metrics(gold, pred)
    assert r.tp == 0


def test_span_sentiment_intent_wrong_intent():
    gold = [_make_record([_asp(0, 5)], intent="complaint")]
    pred = [_make_record([_asp(0, 5)], intent="compliment")]
    r = span_sentiment_intent_metrics(gold, pred)
    assert r.tp == 0


def test_records_all_correct_percentage():
    gold = [_make_record([_asp(0, 5)]), _make_record([])]
    pred = [_make_record([_asp(0, 5)]), _make_record([])]
    r = span_sentiment_metrics(gold, pred)
    assert r.records_all_correct == 2
    assert r.records_all_correct_pct == 100.0


# ---------------------------------------------------------------------------
# regional
# ---------------------------------------------------------------------------

def _simple_metric_fn(gold, pred):
    return {"n": len(gold), "dummy_f1": 1.0}


def test_evaluate_by_group_basic():
    gold = [
        _make_record([], region="international"),
        _make_record([], region="international"),
        _make_record([], region="south_africa"),
    ]
    pred = gold[:]  # same records as prediction for this test
    result = evaluate_by_region(gold, pred, _simple_metric_fn, min_samples=1)
    keys = {s.group_key for s in result.subsets}
    assert "international" in keys
    assert "south_africa" in keys


def test_evaluate_by_group_insufficient_sample():
    gold = [
        _make_record([], region="international"),
        _make_record([], region="international"),
        _make_record([], region="rare"),  # only 1 record
    ]
    pred = gold[:]
    result = evaluate_by_region(gold, pred, _simple_metric_fn, min_samples=2)
    rare = next(s for s in result.subsets if s.group_key == "rare")
    assert rare.status == INSUFFICIENT
    assert rare.metrics is None


def test_evaluate_by_group_all_sufficient():
    gold = [_make_record([], region="intl") for _ in range(5)]
    pred = gold[:]
    result = evaluate_by_region(gold, pred, _simple_metric_fn, min_samples=3)
    assert result.n_ok == 1
    assert result.n_insufficient == 0


def test_evaluate_by_context_availability_groups():
    gold = [
        _make_record([], context_available=True),
        _make_record([], context_available=True),
        _make_record([], context_available=False),
    ]
    pred = gold[:]
    result = evaluate_by_context_availability(gold, pred, _simple_metric_fn, min_samples=1)
    keys = {s.group_key for s in result.subsets}
    assert "True" in keys
    assert "False" in keys


def test_evaluate_by_group_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        evaluate_by_region([_make_record([])], [], _simple_metric_fn)


def test_evaluate_by_group_min_samples_below_one_raises():
    gold = [_make_record([])]
    with pytest.raises(ValueError, match="min_samples"):
        evaluate_by_region(gold, gold, _simple_metric_fn, min_samples=0)


def test_evaluate_by_group_unknown_region():
    gold = [{"aspects": [], "intent": {"label": "complaint"}}]  # no region key
    pred = gold[:]
    result = evaluate_by_region(gold, pred, _simple_metric_fn, min_samples=1)
    keys = {s.group_key for s in result.subsets}
    assert "<unknown>" in keys


# ---------------------------------------------------------------------------
# ablation
# ---------------------------------------------------------------------------


def test_ablation_all_missing():
    report = build_ablation_report({})
    assert report.n_missing == len(report.conditions)
    assert report.n_ok == 0


def test_ablation_full_model_present():
    metrics = {"macro_f1": 0.75}
    report = build_ablation_report({FULL_MODEL: metrics})
    cr = report.get(FULL_MODEL)
    assert cr is not None
    assert cr.status == STATUS_OK
    assert cr.metrics["macro_f1"] == 0.75


def test_ablation_missing_condition_status():
    report = build_ablation_report({FULL_MODEL: {"macro_f1": 0.75}})
    cr = report.get(NO_INTENT)
    assert cr is not None
    assert cr.status == STATUS_MISSING
    assert cr.metrics is None


def test_ablation_delta_ok():
    metrics = {
        FULL_MODEL: {"macro_f1": 0.80},
        NO_INTENT: {"macro_f1": 0.70},
    }
    report = build_ablation_report(metrics)
    delta = report.delta("macro_f1", NO_INTENT)
    assert delta is not None
    assert abs(delta - (-0.10)) < 1e-9


def test_ablation_delta_missing_condition_returns_none():
    report = build_ablation_report({FULL_MODEL: {"macro_f1": 0.80}})
    delta = report.delta("macro_f1", CURRENT_ONLY)
    assert delta is None


def test_ablation_delta_missing_metric_returns_none():
    metrics = {
        FULL_MODEL: {"macro_f1": 0.80},
        NO_INTENT: {"accuracy": 0.70},  # no macro_f1
    }
    report = build_ablation_report(metrics)
    delta = report.delta("macro_f1", NO_INTENT)
    assert delta is None


def test_ablation_comparison_table_columns():
    metrics = {
        FULL_MODEL: {"macro_f1": 0.80},
        NO_INTENT: {"macro_f1": 0.70},
    }
    report = build_ablation_report(metrics)
    table = comparison_table(report, ["macro_f1"])
    assert len(table) == len(report.conditions)
    for row in table:
        assert "condition" in row
        assert "status" in row
        assert "macro_f1" in row
        assert "delta_macro_f1" in row


def test_ablation_to_dict_structure():
    report = build_ablation_report({FULL_MODEL: {"macro_f1": 0.80}})
    d = report.to_dict()
    assert "conditions" in d
    assert "n_ok" in d
    assert "n_missing" in d


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------


def test_write_metrics_json_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "metrics.json"
        write_metrics_json({"macro_f1": 0.75}, path)
        assert path.is_file()
        loaded = json.loads(path.read_text())
        assert loaded["macro_f1"] == 0.75


def test_write_metrics_json_creates_parents():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sub" / "dir" / "metrics.json"
        write_metrics_json({"n": 10}, path)
        assert path.is_file()


def test_write_classification_report_md():
    metrics = {
        "n": 100,
        "accuracy": 0.80,
        "macro_precision": 0.79,
        "macro_recall": 0.78,
        "macro_f1": 0.785,
        "weighted_f1": 0.80,
        "per_class": {
            "complaint": {"precision": 0.8, "recall": 0.75, "f1": 0.77, "support": 50},
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "report.md"
        write_classification_report_md(metrics, path, title="Test Report")
        text = path.read_text()
        assert "Test Report" in text
        assert "complaint" in text
        assert "0.7700" in text


def test_write_confusion_matrix_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "cm.csv"
        write_confusion_matrix_csv([[10, 2], [1, 8]], ["class_a", "class_b"], path)
        rows = list(csv.reader(path.open()))
        assert rows[0][1] == "class_a"
        assert rows[1][0] == "class_a"
        assert rows[1][1] == "10"


def test_write_errors_jsonl():
    errors = [{"record_id": "r1", "type": "fp"}, {"record_id": "r2", "type": "fn"}]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "errors.jsonl"
        write_errors_jsonl(errors, path)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["record_id"] == "r1"


def test_write_predictions_jsonl():
    preds = [{"record_id": "r1", "intent": {"label": "complaint"}, "aspects": []}]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "preds.jsonl"
        write_predictions_jsonl(preds, path)
        loaded = json.loads(path.read_text().strip())
        assert loaded["record_id"] == "r1"


def test_write_ablation_summary_md_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ablation.md"
        write_ablation_summary_md([], path)
        text = path.read_text()
        assert "No conditions" in text


def test_write_ablation_summary_md_with_rows():
    rows = [
        {"condition": "full_model", "status": "ok", "macro_f1": 0.80, "delta_macro_f1": None},
        {"condition": "no_intent", "status": "ok", "macro_f1": 0.70, "delta_macro_f1": -0.10},
        {"condition": "current_only", "status": "missing", "macro_f1": None, "delta_macro_f1": None},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ablation.md"
        write_ablation_summary_md(rows, path, metric_columns=["macro_f1", "delta_macro_f1"])
        text = path.read_text()
        assert "full_model" in text
        assert "no_intent" in text
        assert "missing" in text
