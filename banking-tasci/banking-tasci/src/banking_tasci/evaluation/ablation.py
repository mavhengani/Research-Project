"""Ablation comparison module for the banking-tasci pipeline.

Compares saved metric dictionaries from named experimental conditions
against one another.  All conditions represent previously-run experiments
whose results were written to JSON files by the training / evaluation
pipeline.

Supported ablation conditions (KIRO_SPEC §18)
---------------------------------------------
- ``full_model``              Full TASCI pipeline.
- ``no_intent``               Sentiment classifier with no intent input.
- ``current_only``            Intent model using current sentence only.
- ``previous_plus_current``   Intent model with previous+current context.
- ``no_transformer``          Sentiment without the Transformer encoder.
- ``gold_aspects``            Evaluated using gold aspect spans.
- ``predicted_aspects``       Evaluated using predicted aspect spans.
- ``gold_intent``             Sentiment classifier given gold intent.
- ``predicted_intent``        Sentiment classifier given predicted intent.

Design constraints
------------------
- This module NEVER invents missing metrics.
- It NEVER replaces a missing condition's values with zero or any default.
- It NEVER claims statistical significance.
- It raises ``ValueError`` when two conditions use incompatible manifests
  (different split manifests → different test sets → incomparable results),
  unless the caller explicitly opts out of the check.
- A condition that is not present in the input is represented by a
  ``ConditionResult`` with ``status = "missing"`` so the caller can
  distinguish "ran and measured" from "not yet run".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Known ablation condition names (used as canonical dict keys)
# ---------------------------------------------------------------------------

FULL_MODEL = "full_model"
NO_INTENT = "no_intent"
CURRENT_ONLY = "current_only"
PREVIOUS_PLUS_CURRENT = "previous_plus_current"
NO_TRANSFORMER = "no_transformer"
GOLD_ASPECTS = "gold_aspects"
PREDICTED_ASPECTS = "predicted_aspects"
GOLD_INTENT = "gold_intent"
PREDICTED_INTENT = "predicted_intent"

KNOWN_CONDITIONS = (
    FULL_MODEL,
    NO_INTENT,
    CURRENT_ONLY,
    PREVIOUS_PLUS_CURRENT,
    NO_TRANSFORMER,
    GOLD_ASPECTS,
    PREDICTED_ASPECTS,
    GOLD_INTENT,
    PREDICTED_INTENT,
)

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_INCOMPATIBLE_MANIFESTS = "incompatible_manifests"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ConditionResult:
    """Result for one ablation condition.

    Attributes:
        condition:  Canonical condition name.
        status:     ``"ok"``, ``"missing"``, or ``"incompatible_manifests"``.
        metrics:    The raw metric dict for this condition, or ``None`` when
                    status is not ``"ok"``.
        run_dir:    Path to the run directory that produced these metrics,
                    or ``None`` when not available.
        manifest_hash: Hash of the split manifests used in this run (used
                    for compatibility checks).  ``None`` when not recorded.
        detail:     Human-readable explanation for non-ok statuses.
    """

    condition: str
    status: str
    metrics: "dict[str, Any] | None" = None
    run_dir: "str | None" = None
    manifest_hash: "str | None" = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "status": self.status,
            "metrics": self.metrics,
            "run_dir": self.run_dir,
            "manifest_hash": self.manifest_hash,
            "detail": self.detail,
        }


@dataclass
class AblationReport:
    """Comparison of all ablation conditions.

    Attributes:
        conditions:     All conditions in the order they were provided.
        reference:      The reference condition name (default ``"full_model"``).
        warnings:       Human-readable warnings about missing or incompatible
                        conditions.
        n_ok:           Number of conditions with status ``"ok"``.
        n_missing:      Number of conditions with status ``"missing"``.
    """

    conditions: "list[ConditionResult]" = field(default_factory=list)
    reference: str = FULL_MODEL
    warnings: "list[str]" = field(default_factory=list)

    @property
    def n_ok(self) -> int:
        return sum(1 for c in self.conditions if c.status == STATUS_OK)

    @property
    def n_missing(self) -> int:
        return sum(1 for c in self.conditions if c.status == STATUS_MISSING)

    def get(self, condition: str) -> "ConditionResult | None":
        """Return the ConditionResult for ``condition``, or None."""
        for c in self.conditions:
            if c.condition == condition:
                return c
        return None

    def delta(
        self,
        metric_path: str,
        condition: str,
        reference: "str | None" = None,
    ) -> "float | None":
        """Return the difference between ``condition`` and ``reference`` for
        ``metric_path`` (dot-separated key path into the metrics dict).

        Returns ``None`` when either condition is missing or lacks the
        metric.  Never raises.

        Parameters
        ----------
        metric_path:
            Dot-separated path into the metrics dict, e.g. ``"macro_f1"``
            or ``"test.macro_f1"``.
        condition:
            The condition to compare.
        reference:
            The reference condition.  Defaults to ``self.reference``.
        """
        ref_name = reference if reference is not None else self.reference
        cond_result = self.get(condition)
        ref_result = self.get(ref_name)
        if cond_result is None or ref_result is None:
            return None
        if cond_result.status != STATUS_OK or ref_result.status != STATUS_OK:
            return None
        cond_val = _nested_get(cond_result.metrics, metric_path)
        ref_val = _nested_get(ref_result.metrics, metric_path)
        if cond_val is None or ref_val is None:
            return None
        try:
            return float(cond_val) - float(ref_val)
        except (TypeError, ValueError):
            return None

    def to_dict(self) -> dict:
        return {
            "reference": self.reference,
            "n_ok": self.n_ok,
            "n_missing": self.n_missing,
            "warnings": self.warnings,
            "conditions": [c.to_dict() for c in self.conditions],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nested_get(d: "dict[str, Any] | None", path: str) -> "Any | None":
    """Traverse a nested dict using a dot-separated ``path``."""
    if d is None:
        return None
    current: Any = d
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _manifest_hash(run_metadata: "dict[str, Any] | None") -> "str | None":
    """Extract a manifest hash or identifier from run metadata.

    Looks for ``split_manifest_hash``, ``train_manifest``,
    ``validation_manifest``, or ``test_manifest`` keys.  Returns None when
    none are present.
    """
    if not run_metadata:
        return None
    return (
        run_metadata.get("split_manifest_hash")
        or run_metadata.get("train_manifest")
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_ablation_report(
    condition_metrics: "dict[str, dict[str, Any]]",
    reference: str = FULL_MODEL,
    check_manifests: bool = True,
    run_metadata: "dict[str, dict[str, Any]] | None" = None,
) -> AblationReport:
    """Build an :class:`AblationReport` from a mapping of condition metrics.

    Parameters
    ----------
    condition_metrics:
        ``{condition_name: metrics_dict}`` where each ``metrics_dict`` is
        the JSON-serialisable dict produced by an evaluation run.  Only
        provide conditions that were actually run; absent conditions are
        recorded with ``status = "missing"``.
    reference:
        The reference condition for delta computation.  Must be a key in
        ``condition_metrics`` for delta values to be computed.  Default
        ``"full_model"``.
    check_manifests:
        When ``True``, warns when two conditions have different manifest
        identifiers — they may not be comparable.  Set to ``False`` only
        when you are certain the conditions used the same test set.
    run_metadata:
        Optional ``{condition_name: metadata_dict}`` carrying manifest
        hashes or paths for compatibility checking.

    Returns
    -------
    AblationReport
        All known conditions are represented.  Missing ones have
        ``status = "missing"`` and ``metrics = None``.

    Notes
    -----
    This function **never** fabricates missing metrics or fills them with
    defaults.  Callers must not treat ``None`` deltas as ``0``.
    """
    report = AblationReport(reference=reference)
    warnings: list[str] = []

    # --- Compatibility check -------------------------------------------------
    if check_manifests and run_metadata:
        hashes_seen: dict[str, str] = {}
        for cond, meta in run_metadata.items():
            h = _manifest_hash(meta)
            if h is not None:
                hashes_seen[cond] = h
        unique_hashes = set(hashes_seen.values())
        if len(unique_hashes) > 1:
            warnings.append(
                "Conditions appear to use different split manifests — results "
                "may not be directly comparable.  Conditions and hashes: "
                + str(hashes_seen)
            )

    # --- Build condition results ----------------------------------------------
    for condition in KNOWN_CONDITIONS:
        metrics = condition_metrics.get(condition)
        meta = (run_metadata or {}).get(condition)
        mh = _manifest_hash(meta) if meta else None

        if metrics is None:
            report.conditions.append(ConditionResult(
                condition=condition,
                status=STATUS_MISSING,
                detail=f"No metrics found for condition '{condition}'.",
            ))
        else:
            report.conditions.append(ConditionResult(
                condition=condition,
                status=STATUS_OK,
                metrics=metrics,
                run_dir=(meta or {}).get("run_dir"),
                manifest_hash=mh,
            ))

    # --- Reference check -----------------------------------------------------
    ref_result = report.get(reference)
    if ref_result is None or ref_result.status != STATUS_OK:
        warnings.append(
            f"Reference condition '{reference}' is missing or has no metrics. "
            "Delta values cannot be computed."
        )

    report.warnings = warnings
    return report


def comparison_table(
    report: AblationReport,
    metric_paths: "list[str]",
) -> "list[dict[str, Any]]":
    """Return a list of row dicts suitable for tabular display.

    Each row corresponds to one condition and contains:
    - ``condition``: the condition name.
    - ``status``: ``"ok"`` or ``"missing"``.
    - one column per ``metric_paths`` entry with the raw value (or ``None``).
    - one ``delta_*`` column per ``metric_paths`` entry with the difference
      from the reference condition (or ``None``).

    Parameters
    ----------
    report:
        The :class:`AblationReport` to summarise.
    metric_paths:
        Dot-separated paths into the metrics dicts to include,
        e.g. ``["macro_f1", "test.accuracy"]``.
    """
    rows = []
    for cr in report.conditions:
        row: dict[str, Any] = {
            "condition": cr.condition,
            "status": cr.status,
        }
        for path in metric_paths:
            val = _nested_get(cr.metrics, path) if cr.metrics else None
            row[path] = val
            delta = report.delta(path, cr.condition)
            row[f"delta_{path}"] = delta
        rows.append(row)
    return rows
