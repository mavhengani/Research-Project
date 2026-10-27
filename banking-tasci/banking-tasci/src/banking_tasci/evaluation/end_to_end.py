"""End-to-end evaluation metrics for the full banking-tasci pipeline.

Computes tuple-level correctness between gold and predicted structured
outputs.  All functions are pure: they accept lists of dicts and return
dicts of scalar metrics.  They never fabricate labels, scores, or results.

Offset convention
-----------------
All span offsets follow the half-open convention used throughout the
codebase:  ``start`` is inclusive, ``end`` is exclusive, so
``text[start:end]`` yields the aspect term.

Tuple definitions
-----------------
The three supported tuple granularities are:

1. ``(start, end, sentiment)``
   Exact-aspect-and-sentiment: a predicted span is a true positive only
   when its character offsets **exactly** match a gold span AND the
   predicted sentiment matches the gold sentiment.

2. ``(start, end, category, sentiment)``
   Full aspect tuple: additionally requires the aspect category to match.

3. ``(start, end, sentiment, intent)``
   Intent-integrated tuple: additionally requires the record-level intent
   to match.  The intent is taken from the record-level prediction, not
   the aspect level.

Records with no gold aspects
-----------------------------
A record that has zero gold aspects but zero predicted aspects is a
**true negative** — it contributes 0 TP, 0 FP, 0 FN.  A record with
zero gold aspects but at least one predicted aspect contributes FP for
each spurious prediction.  A record with at least one gold aspect but
zero predicted aspects contributes FN for each missed gold aspect.  This
matches the behaviour of standard span-level F1 evaluation.

Records with no predicted aspects
-----------------------------------
Handled symmetrically as described above.

Duplicate tuple handling
-------------------------
Within a single record, tuples are compared as **multisets** (counts
matter).  If gold contains the same tuple twice and prediction contains
it once, one TP and one FN are recorded.  This prevents gaming the metric
by predicting a single correct span many times.

All-tuples-correct (record-level)
----------------------------------
A record is "all tuples correct" when:
  - the multiset of predicted tuples exactly equals the multiset of gold
    tuples for that record (no missing, no extra, no wrong tuples).
Records with zero gold aspects and zero predictions are counted as correct.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _aspect_tuples_span_sentiment(
    aspects: "list[dict[str, Any]]",
    intent: "str | None" = None,
    include_intent: bool = False,
    include_category: bool = False,
) -> "list[tuple]":
    """Extract sortable tuples from a list of aspect dicts.

    Each dict must contain ``start``, ``end``, and ``sentiment``.
    Optionally includes ``category`` and/or ``intent``.
    Silently skips aspects that are missing required fields.
    """
    tuples = []
    for asp in aspects:
        start = asp.get("start")
        end = asp.get("end")
        sentiment = asp.get("sentiment")
        category = asp.get("category")
        if start is None or end is None or sentiment is None:
            continue
        t: tuple
        if include_intent and include_category:
            t = (int(start), int(end), str(category) if category else "", str(sentiment), str(intent) if intent else "")
        elif include_category:
            t = (int(start), int(end), str(category) if category else "", str(sentiment))
        elif include_intent:
            t = (int(start), int(end), str(sentiment), str(intent) if intent else "")
        else:
            t = (int(start), int(end), str(sentiment))
        tuples.append(t)
    return tuples


def _prf_from_counts(tp: int, fp: int, fn: int) -> "tuple[float, float, float]":
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _multiset_prf(
    gold_tuples: "list[tuple]",
    pred_tuples: "list[tuple]",
) -> "tuple[int, int, int]":
    """Return (tp, fp, fn) for two multisets of tuples.

    Comparison is count-aware: predicting the same tuple twice when gold
    has it once yields 1 TP and 1 FP, not 2 TP.
    """
    gold_counts = Counter(gold_tuples)
    pred_counts = Counter(pred_tuples)
    tp = sum(min(gold_counts[t], pred_counts[t]) for t in gold_counts)
    fp = sum(max(0, pred_counts[t] - gold_counts.get(t, 0)) for t in pred_counts)
    fn = sum(max(0, gold_counts[t] - pred_counts.get(t, 0)) for t in gold_counts)
    return tp, fp, fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class EndToEndResult:
    """Aggregate end-to-end evaluation result.

    Attributes:
        precision, recall, f1:   Micro-averaged over all records.
        tp, fp, fn:              Raw tuple counts.
        records_all_correct:     Number of records where every gold tuple
                                 is matched exactly (no extra predictions,
                                 no missing ones).
        records_all_correct_pct: Percentage of records where all tuples
                                 are correct.  0.0 when ``n_records == 0``.
        n_records:               Total records evaluated.
        n_gold_aspects:          Total gold aspect instances.
        n_pred_aspects:          Total predicted aspect instances.
        tuple_type:              Human-readable name of the tuple type used.
    """

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    records_all_correct: int
    records_all_correct_pct: float
    n_records: int
    n_gold_aspects: int
    n_pred_aspects: int
    tuple_type: str

    def to_dict(self) -> dict:
        return {
            "tuple_type": self.tuple_type,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "records_all_correct": self.records_all_correct,
            "records_all_correct_pct": self.records_all_correct_pct,
            "n_records": self.n_records,
            "n_gold_aspects": self.n_gold_aspects,
            "n_pred_aspects": self.n_pred_aspects,
        }


def _evaluate_tuples(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
    *,
    include_category: bool,
    include_intent: bool,
    tuple_type_name: str,
) -> EndToEndResult:
    """Shared implementation for all three tuple granularities."""
    if len(gold_records) != len(pred_records):
        raise ValueError(
            f"gold_records and pred_records must have the same length, "
            f"got {len(gold_records)} and {len(pred_records)}"
        )

    total_tp = total_fp = total_fn = 0
    records_all_correct = 0
    n_gold_aspects = 0
    n_pred_aspects = 0
    n_records = len(gold_records)

    for gold, pred in zip(gold_records, pred_records):
        gold_intent = gold.get("intent", {})
        if isinstance(gold_intent, dict):
            gold_intent_label = gold_intent.get("label")
        else:
            gold_intent_label = gold_intent

        pred_intent = pred.get("intent", {})
        if isinstance(pred_intent, dict):
            pred_intent_label = pred_intent.get("label")
        else:
            pred_intent_label = pred_intent

        gold_aspects = gold.get("aspects") or []
        pred_aspects = pred.get("aspects") or []

        gold_tuples = _aspect_tuples_span_sentiment(
            gold_aspects, gold_intent_label,
            include_intent=include_intent,
            include_category=include_category,
        )
        pred_tuples = _aspect_tuples_span_sentiment(
            pred_aspects, pred_intent_label,
            include_intent=include_intent,
            include_category=include_category,
        )

        tp, fp, fn = _multiset_prf(gold_tuples, pred_tuples)
        total_tp += tp
        total_fp += fp
        total_fn += fn

        n_gold_aspects += len(gold_tuples)
        n_pred_aspects += len(pred_tuples)

        if fp == 0 and fn == 0:
            records_all_correct += 1

    precision, recall, f1 = _prf_from_counts(total_tp, total_fp, total_fn)
    records_all_correct_pct = (
        100.0 * records_all_correct / n_records if n_records else 0.0
    )

    return EndToEndResult(
        precision=precision,
        recall=recall,
        f1=f1,
        tp=total_tp,
        fp=total_fp,
        fn=total_fn,
        records_all_correct=records_all_correct,
        records_all_correct_pct=records_all_correct_pct,
        n_records=n_records,
        n_gold_aspects=n_gold_aspects,
        n_pred_aspects=n_pred_aspects,
        tuple_type=tuple_type_name,
    )


def span_sentiment_metrics(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
) -> EndToEndResult:
    """Exact-span + correct-sentiment evaluation.

    A predicted aspect is a TP only when its (start, end) exactly matches
    a gold span AND the predicted sentiment matches the gold sentiment.

    Parameters
    ----------
    gold_records:
        List of gold structured outputs.  Each dict must have an ``aspects``
        list where each element has ``start``, ``end``, and ``sentiment``.
    pred_records:
        List of predicted structured outputs in the same format.

    Returns
    -------
    EndToEndResult
        Micro-averaged precision, recall, F1 and record-level all-correct
        percentage.
    """
    return _evaluate_tuples(
        gold_records, pred_records,
        include_category=False,
        include_intent=False,
        tuple_type_name="span+sentiment",
    )


def span_category_sentiment_metrics(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
) -> EndToEndResult:
    """Exact-span + correct-category + correct-sentiment evaluation.

    A TP requires the predicted (start, end, category, sentiment) tuple
    to exactly match the gold tuple.

    Parameters
    ----------
    gold_records / pred_records:
        Same format as :func:`span_sentiment_metrics`, but each aspect
        dict must also include ``category``.
    """
    return _evaluate_tuples(
        gold_records, pred_records,
        include_category=True,
        include_intent=False,
        tuple_type_name="span+category+sentiment",
    )


def span_sentiment_intent_metrics(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
) -> EndToEndResult:
    """Exact-span + correct-sentiment + correct-record-intent evaluation.

    A TP requires the predicted (start, end, sentiment, intent) tuple to
    exactly match the gold tuple.  ``intent`` is the record-level intent
    label taken from ``record["intent"]["label"]`` (structured output) or
    ``record["intent"]`` (flat string).

    Parameters
    ----------
    gold_records / pred_records:
        Structured output dicts with ``aspects`` and ``intent`` fields.
    """
    return _evaluate_tuples(
        gold_records, pred_records,
        include_category=False,
        include_intent=True,
        tuple_type_name="span+sentiment+intent",
    )


def all_tuple_metrics(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
) -> "dict[str, EndToEndResult]":
    """Compute all three tuple granularities in one call.

    Returns a dict with keys ``"span+sentiment"``,
    ``"span+category+sentiment"``, and ``"span+sentiment+intent"``.
    """
    return {
        "span+sentiment": span_sentiment_metrics(gold_records, pred_records),
        "span+category+sentiment": span_category_sentiment_metrics(gold_records, pred_records),
        "span+sentiment+intent": span_sentiment_intent_metrics(gold_records, pred_records),
    }
