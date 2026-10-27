"""Evaluation metrics for the banking-tasci tasks (Phase 3A, Part 12).

Pure-Python metric implementations (no sklearn dependency) covering the three
task families. These functions compute metrics from provided predictions and
gold labels only — they NEVER fabricate labels or scores. When no gold data is
available (the current stage), they are simply not called with any real data.

Task coverage:
- Classification (intent, aspect sentiment): accuracy, macro precision/recall/F1,
  weighted-F1, per-class metrics, and a confusion matrix.
- BIO aspect extraction: token precision/recall/F1, exact-span
  precision/recall/F1, and boundary-error examples.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Classification metrics (intent + aspect sentiment)
# ---------------------------------------------------------------------------


def _prf(tp: int, fp: int, fn: int) -> "tuple[float, float, float]":
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def classification_metrics(
    y_true: "list[int]",
    y_pred: "list[int]",
    num_classes: int,
    id_to_label: "dict[int, str] | None" = None,
) -> dict:
    """Return a full classification metrics dict.

    Includes accuracy, macro precision/recall/F1 (unweighted mean over all
    ``num_classes`` classes), support-weighted F1, per-class precision/recall/
    F1/support, and a ``num_classes x num_classes`` confusion matrix
    (``confusion_matrix[t][p]`` = count of gold ``t`` predicted ``p``).
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have equal length")
    if num_classes < 1:
        raise ValueError("num_classes must be >= 1")

    tp = [0] * num_classes
    fp = [0] * num_classes
    fn = [0] * num_classes
    support = [0] * num_classes
    confusion = [[0] * num_classes for _ in range(num_classes)]

    correct = 0
    for t, p in zip(y_true, y_pred):
        support[t] += 1
        confusion[t][p] += 1
        if t == p:
            correct += 1
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1

    n = len(y_true)
    accuracy = correct / n if n else 0.0

    per_class: dict[str, dict] = {}
    macro_p = macro_r = macro_f1 = 0.0
    weighted_f1 = 0.0
    for c in range(num_classes):
        p, r, f1 = _prf(tp[c], fp[c], fn[c])
        macro_p += p
        macro_r += r
        macro_f1 += f1
        weighted_f1 += f1 * support[c]
        label = id_to_label.get(c, str(c)) if id_to_label else str(c)
        per_class[label] = {
            "precision": p, "recall": r, "f1": f1, "support": support[c],
        }

    macro_p /= num_classes
    macro_r /= num_classes
    macro_f1 /= num_classes
    weighted_f1 = weighted_f1 / n if n else 0.0

    return {
        "accuracy": accuracy,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "labels": [id_to_label.get(c, str(c)) if id_to_label else str(c) for c in range(num_classes)],
        "n": n,
    }


# ---------------------------------------------------------------------------
# BIO aspect-extraction metrics
# ---------------------------------------------------------------------------


def bio_token_metrics(
    y_true_tags: "list[list[str]]",
    y_pred_tags: "list[list[str]]",
    positive_tags: "tuple[str, ...]" = ("B-ASP", "I-ASP"),
) -> dict:
    """Token-level precision/recall/F1 over aspect tokens (micro-averaged).

    A token counts as a positive when its tag is in ``positive_tags``. TP is a
    position that is positive in both gold and prediction; FP is positive in
    prediction but not gold; FN is positive in gold but not prediction. ``O``
    positions that match contribute to neither.
    """
    tp = fp = fn = 0
    positive = set(positive_tags)
    for gold_seq, pred_seq in zip(y_true_tags, y_pred_tags):
        if len(gold_seq) != len(pred_seq):
            raise ValueError("gold and pred tag sequences must align in length")
        for g, p in zip(gold_seq, pred_seq):
            g_pos = g in positive
            p_pos = p in positive
            if g_pos and p_pos:
                tp += 1
            elif p_pos and not g_pos:
                fp += 1
            elif g_pos and not p_pos:
                fn += 1
    precision, recall, f1 = _prf(tp, fp, fn)
    return {
        "token_precision": precision,
        "token_recall": recall,
        "token_f1": f1,
        "tp": tp, "fp": fp, "fn": fn,
    }


@dataclass
class SpanMetrics:
    exact_span_precision: float
    exact_span_recall: float
    exact_span_f1: float
    tp: int
    fp: int
    fn: int
    boundary_errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "exact_span_precision": self.exact_span_precision,
            "exact_span_recall": self.exact_span_recall,
            "exact_span_f1": self.exact_span_f1,
            "tp": self.tp, "fp": self.fp, "fn": self.fn,
            "boundary_errors": self.boundary_errors,
        }


def bio_span_metrics(
    true_spans_per_doc: "list[list[tuple[int, int]]]",
    pred_spans_per_doc: "list[list[tuple[int, int]]]",
    record_ids: "list[str] | None" = None,
    max_boundary_examples: int = 20,
) -> SpanMetrics:
    """Exact-span precision/recall/F1 plus boundary-error examples.

    A predicted span is a true positive iff it exactly matches a gold span
    (same start AND end). ``boundary_errors`` collects up to
    ``max_boundary_examples`` cases where a predicted span OVERLAPS a gold span
    but does not match its boundaries (a partial/boundary error), each recorded
    as ``{record_id, predicted, gold}``.
    """
    tp = fp = fn = 0
    boundary_errors: list[dict] = []

    for idx, (gold_spans, pred_spans) in enumerate(zip(true_spans_per_doc, pred_spans_per_doc)):
        gold_set = set(gold_spans)
        pred_set = set(pred_spans)
        tp += len(gold_set & pred_set)
        unmatched_pred = pred_set - gold_set
        unmatched_gold = gold_set - pred_set
        fp += len(unmatched_pred)
        fn += len(unmatched_gold)

        rid = record_ids[idx] if record_ids else str(idx)
        for pstart, pend in sorted(unmatched_pred):
            for gstart, gend in sorted(unmatched_gold):
                if pstart < gend and gstart < pend:  # overlap but not exact
                    if len(boundary_errors) < max_boundary_examples:
                        boundary_errors.append(
                            {"record_id": rid, "predicted": [pstart, pend], "gold": [gstart, gend]}
                        )
                    break

    precision, recall, f1 = _prf(tp, fp, fn)
    return SpanMetrics(
        exact_span_precision=precision,
        exact_span_recall=recall,
        exact_span_f1=f1,
        tp=tp, fp=fp, fn=fn,
        boundary_errors=boundary_errors,
    )


def label_distribution(y: "list[int]", id_to_label: "dict[int, str] | None" = None) -> dict:
    """Return a count distribution for a label list (diagnostics helper)."""
    counts = Counter(y)
    if id_to_label:
        return {id_to_label.get(k, str(k)): v for k, v in sorted(counts.items())}
    return {str(k): v for k, v in sorted(counts.items())}

