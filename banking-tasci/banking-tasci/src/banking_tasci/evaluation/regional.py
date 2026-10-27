"""Regional and subset evaluation for the banking-tasci pipeline.

Groups metric-ready records by ``region``, ``source``, or
``context_available`` and applies a caller-supplied metric function to
each subset.  Returns an explicit insufficient-sample sentinel for groups
that fall below a configurable minimum size rather than silently omitting
or filling them with zeros.

Design constraints
------------------
- Never invents metrics for a missing group.
- Never silently omits a small group — always records it with
  ``status = "insufficient_samples"``.
- Never modifies the input records or metric dicts.
- The caller supplies the metric function so this module has no dependency
  on specific model architectures or metric implementations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

INSUFFICIENT = "insufficient_samples"
OK = "ok"


@dataclass
class SubsetResult:
    """Result for one evaluation subset.

    Attributes:
        group_key:      The grouping value (e.g. ``"international"``).
        group_by:       The field used for grouping (e.g. ``"region"``).
        status:         ``"ok"`` or ``"insufficient_samples"``.
        n:              Number of records in this subset.
        min_required:   Minimum required sample size from config.
        metrics:        Metrics dict returned by the metric function, or
                        ``None`` when ``status == "insufficient_samples"``.
    """

    group_key: str
    group_by: str
    status: str
    n: int
    min_required: int
    metrics: "dict[str, Any] | None" = None

    def to_dict(self) -> dict:
        return {
            "group_key": self.group_key,
            "group_by": self.group_by,
            "status": self.status,
            "n": self.n,
            "min_required": self.min_required,
            "metrics": self.metrics,
        }


@dataclass
class RegionalEvalResult:
    """Aggregate result of a regional/subset evaluation run.

    Attributes:
        group_by:       The field used for grouping.
        subsets:        One :class:`SubsetResult` per unique group key.
        n_ok:           Subsets with sufficient samples.
        n_insufficient: Subsets with fewer records than ``min_required``.
    """

    group_by: str
    subsets: "list[SubsetResult]" = field(default_factory=list)

    @property
    def n_ok(self) -> int:
        return sum(1 for s in self.subsets if s.status == OK)

    @property
    def n_insufficient(self) -> int:
        return sum(1 for s in self.subsets if s.status == INSUFFICIENT)

    def to_dict(self) -> dict:
        return {
            "group_by": self.group_by,
            "n_ok": self.n_ok,
            "n_insufficient": self.n_insufficient,
            "subsets": [s.to_dict() for s in self.subsets],
        }


# ---------------------------------------------------------------------------
# Core grouping logic
# ---------------------------------------------------------------------------


def _get_field(record: "dict[str, Any]", field_name: str) -> str:
    """Extract a grouping key from a record dict, normalising to a string.

    Returns ``"<unknown>"`` when the field is absent or None so every
    record is accounted for in exactly one group.
    """
    value = record.get(field_name)
    if value is None:
        return "<unknown>"
    return str(value)


def _group_records(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
    group_by: str,
) -> "dict[str, tuple[list, list]]":
    """Partition (gold, pred) pairs by the value of ``group_by`` in gold.

    Returns ``{group_key: (gold_subset, pred_subset)}``.
    """
    groups: dict[str, tuple[list, list]] = {}
    for gold, pred in zip(gold_records, pred_records):
        key = _get_field(gold, group_by)
        if key not in groups:
            groups[key] = ([], [])
        groups[key][0].append(gold)
        groups[key][1].append(pred)
    return groups


def evaluate_by_group(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
    metric_fn: "Callable[[list[dict], list[dict]], dict[str, Any]]",
    group_by: str = "region",
    min_samples: int = 10,
) -> RegionalEvalResult:
    """Evaluate ``metric_fn`` separately for each value of ``group_by``.

    Parameters
    ----------
    gold_records:
        List of gold structured-output dicts.  Each must contain the field
        named by ``group_by``.
    pred_records:
        List of predicted structured-output dicts, same length as
        ``gold_records``.
    metric_fn:
        A callable that accepts ``(gold_subset, pred_subset)`` and returns
        a ``dict`` of metric names to scalar values.  Must not raise when
        both lists are non-empty.
    group_by:
        Field name to group by.  Typical values: ``"region"``,
        ``"source"``, ``"context_available"``.
    min_samples:
        Groups with fewer records than this value are marked
        ``"insufficient_samples"`` and ``metric_fn`` is NOT called for
        them.  Set to 1 to evaluate all groups.

    Returns
    -------
    RegionalEvalResult
        Contains one :class:`SubsetResult` per unique group key.
        Groups below ``min_samples`` have ``metrics = None`` and
        ``status = "insufficient_samples"`` — they are never silently
        omitted.

    Raises
    ------
    ValueError
        When ``gold_records`` and ``pred_records`` differ in length, or
        ``min_samples < 1``.
    """
    if len(gold_records) != len(pred_records):
        raise ValueError(
            f"gold_records and pred_records must have the same length, "
            f"got {len(gold_records)} and {len(pred_records)}"
        )
    if min_samples < 1:
        raise ValueError(f"min_samples must be >= 1, got {min_samples}")

    groups = _group_records(gold_records, pred_records, group_by)
    result = RegionalEvalResult(group_by=group_by)

    for key in sorted(groups):
        gold_subset, pred_subset = groups[key]
        n = len(gold_subset)
        if n < min_samples:
            result.subsets.append(SubsetResult(
                group_key=key,
                group_by=group_by,
                status=INSUFFICIENT,
                n=n,
                min_required=min_samples,
                metrics=None,
            ))
        else:
            metrics = metric_fn(gold_subset, pred_subset)
            result.subsets.append(SubsetResult(
                group_key=key,
                group_by=group_by,
                status=OK,
                n=n,
                min_required=min_samples,
                metrics=metrics,
            ))

    return result


# ---------------------------------------------------------------------------
# Convenience wrappers for the three standard groupings
# ---------------------------------------------------------------------------


def evaluate_by_region(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
    metric_fn: "Callable[[list[dict], list[dict]], dict[str, Any]]",
    min_samples: int = 10,
) -> RegionalEvalResult:
    """Evaluate ``metric_fn`` per ``region`` value.

    See :func:`evaluate_by_group` for parameter details.
    """
    return evaluate_by_group(
        gold_records, pred_records, metric_fn,
        group_by="region", min_samples=min_samples,
    )


def evaluate_by_source(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
    metric_fn: "Callable[[list[dict], list[dict]], dict[str, Any]]",
    min_samples: int = 10,
) -> RegionalEvalResult:
    """Evaluate ``metric_fn`` per ``source`` value.

    See :func:`evaluate_by_group` for parameter details.
    """
    return evaluate_by_group(
        gold_records, pred_records, metric_fn,
        group_by="source", min_samples=min_samples,
    )


def evaluate_by_context_availability(
    gold_records: "list[dict[str, Any]]",
    pred_records: "list[dict[str, Any]]",
    metric_fn: "Callable[[list[dict], list[dict]], dict[str, Any]]",
    min_samples: int = 10,
) -> RegionalEvalResult:
    """Evaluate ``metric_fn`` separately for context-available and no-context
    records.

    Groups on the boolean ``context_available`` field.  Both ``True`` and
    ``False`` subsets are always reported (with
    ``"insufficient_samples"`` when below ``min_samples``), so evaluation
    cannot accidentally confuse them.

    See :func:`evaluate_by_group` for parameter details.
    """
    return evaluate_by_group(
        gold_records, pred_records, metric_fn,
        group_by="context_available", min_samples=min_samples,
    )
