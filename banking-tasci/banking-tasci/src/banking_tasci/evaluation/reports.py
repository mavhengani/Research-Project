"""Report serialisation and formatting utilities for the banking-tasci
evaluation pipeline.

All functions are pure formatters.  They accept already-computed metric
dicts and return strings or write files.  They never recompute metrics,
fabricate values, or modify input dicts.

Output formats
--------------
- JSON (machine-readable)      → ``write_metrics_json``
- Markdown summary table       → ``write_classification_report_md``
- CSV confusion matrix         → ``write_confusion_matrix_csv``
- JSONL error export           → ``write_errors_jsonl``
- JSONL prediction export      → ``write_predictions_jsonl``
- Plain-text ablation summary  → ``write_ablation_summary_md``
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# JSON metrics
# ---------------------------------------------------------------------------


def write_metrics_json(
    metrics: "dict[str, Any]",
    path: "str | Path",
    indent: int = 2,
) -> None:
    """Write ``metrics`` as a pretty-printed JSON file at ``path``.

    Parent directories are created automatically.  Existing files are
    overwritten.

    Parameters
    ----------
    metrics:
        Any JSON-serialisable dict.
    path:
        Destination file path.
    indent:
        JSON indentation width.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=indent, ensure_ascii=False, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Markdown classification report
# ---------------------------------------------------------------------------


def _fmt(v: Any, decimals: int = 4) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def write_classification_report_md(
    metrics: "dict[str, Any]",
    path: "str | Path",
    title: str = "Classification Report",
) -> None:
    """Write a Markdown classification report from a ``classification_metrics``
    dict (as produced by
    :func:`banking_tasci.evaluation.metrics.classification_metrics`).

    Parameters
    ----------
    metrics:
        Dict with keys ``accuracy``, ``macro_precision``, ``macro_recall``,
        ``macro_f1``, ``weighted_f1``, ``per_class``, ``n``.
    path:
        Output Markdown file path.
    title:
        H2-level heading for the report.
    """
    lines = [f"## {title}", ""]
    lines.append(f"**n = {metrics.get('n', '?')}**")
    lines.append("")
    lines.append(f"- Accuracy:        {_fmt(metrics.get('accuracy'))}")
    lines.append(f"- Macro Precision: {_fmt(metrics.get('macro_precision'))}")
    lines.append(f"- Macro Recall:    {_fmt(metrics.get('macro_recall'))}")
    lines.append(f"- Macro F1:        {_fmt(metrics.get('macro_f1'))}")
    lines.append(f"- Weighted F1:     {_fmt(metrics.get('weighted_f1'))}")
    lines.append("")

    per_class = metrics.get("per_class", {})
    if per_class:
        lines.append("### Per-class metrics")
        lines.append("")
        lines.append("| Label | Precision | Recall | F1 | Support |")
        lines.append("|-------|-----------|--------|----|---------|")
        for label, pc in sorted(per_class.items()):
            lines.append(
                f"| {label} "
                f"| {_fmt(pc.get('precision'))} "
                f"| {_fmt(pc.get('recall'))} "
                f"| {_fmt(pc.get('f1'))} "
                f"| {pc.get('support', '?')} |"
            )
        lines.append("")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CSV confusion matrix
# ---------------------------------------------------------------------------


def write_confusion_matrix_csv(
    confusion_matrix: "list[list[int]]",
    labels: "list[str]",
    path: "str | Path",
) -> None:
    """Write a confusion matrix as a CSV file.

    Row = gold label, column = predicted label.

    Parameters
    ----------
    confusion_matrix:
        ``n_classes × n_classes`` list of counts.
    labels:
        Class label strings, same order as the matrix rows/columns.
    path:
        Output CSV file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        # Header row: empty corner then predicted labels
        writer.writerow(["gold \\ pred"] + list(labels))
        for label, row in zip(labels, confusion_matrix):
            writer.writerow([label] + list(row))


# ---------------------------------------------------------------------------
# JSONL exports
# ---------------------------------------------------------------------------


def write_errors_jsonl(
    errors: "list[dict[str, Any]]",
    path: "str | Path",
) -> None:
    """Write one JSON object per error record to a JSONL file.

    Parameters
    ----------
    errors:
        List of dicts describing error cases (e.g. false positives,
        false negatives, boundary errors).  Each must be JSON-serialisable.
    path:
        Output JSONL file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for error in errors:
            fh.write(json.dumps(error, ensure_ascii=False, default=str) + "\n")


def write_predictions_jsonl(
    predictions: "list[dict[str, Any]]",
    path: "str | Path",
) -> None:
    """Write one JSON object per prediction record to a JSONL file.

    Parameters
    ----------
    predictions:
        List of prediction dicts.  Each should include at minimum
        ``record_id``, ``intent``, and ``aspects``.  Must be
        JSON-serialisable.
    path:
        Output JSONL file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for pred in predictions:
            fh.write(json.dumps(pred, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Ablation Markdown summary
# ---------------------------------------------------------------------------


def write_ablation_summary_md(
    rows: "list[dict[str, Any]]",
    path: "str | Path",
    title: str = "Ablation Summary",
    metric_columns: "list[str] | None" = None,
) -> None:
    """Write a Markdown ablation summary table.

    Parameters
    ----------
    rows:
        List of row dicts as returned by
        :func:`banking_tasci.evaluation.ablation.comparison_table`.
    path:
        Output Markdown file path.
    title:
        H2-level heading.
    metric_columns:
        Columns to include in the table (excluding ``condition`` and
        ``status``).  When ``None``, all columns from the first row
        (except ``condition`` and ``status``) are included in sorted order.
    """
    if not rows:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"## {title}\n\nNo conditions to report.\n", encoding="utf-8")
        return

    if metric_columns is None:
        all_keys = sorted(k for k in rows[0] if k not in ("condition", "status"))
        metric_columns = all_keys

    header = ["Condition", "Status"] + metric_columns
    lines = [f"## {title}", ""]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    for row in rows:
        cells = [str(row.get("condition", "")), str(row.get("status", ""))]
        for col in metric_columns:
            cells.append(_fmt(row.get(col)))
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")

    # Append warnings if any rows have missing status
    missing = [r["condition"] for r in rows if r.get("status") == "missing"]
    if missing:
        lines.append("> **Note:** The following conditions have no recorded "
                     f"metrics and are excluded from delta calculations: {', '.join(missing)}")
        lines.append("")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
