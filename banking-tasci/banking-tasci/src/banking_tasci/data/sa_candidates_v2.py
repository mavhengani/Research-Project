"""Canonical v2 evidence-based South African candidate selection.

**This module is the single authoritative implementation of the v2 candidate
selection** used by historical reproduction, materialisation, tests, and
documentation. Requirements Section 9's "do not duplicate independent category
lists across scripts" applies equally to selection rules.

Why this module exists
----------------------

The v2 selection that produced the authoritative **100,768** count was
implemented *inline* inside ``scripts.resample_south_africa_v2.build_reservoir``
as vectorised pandas keyword masks. The September 2026 run log records exactly
that path::

    Applying evidence-based candidate filter (vectorised keyword matching)...
    Candidates: 100768, Zero-aspect: 1842771

Two hazards made extraction necessary rather than optional:

1. ``src/banking_tasci/data/sa_candidate_filter.py`` contains **duplicate
   definitions** of ``classify_candidate`` (lines 198 and 757), ``CandidateResult``
   (189, 748), ``is_potential_zero_aspect`` (313, 892) and ``_any`` (353, 375).
   The later definitions shadow the earlier ones, so the *live*
   ``classify_candidate`` is the regex-based variant at line 757 - the same
   duplicate-definition hazard as finding R41.

2. That live row-wise ``classify_candidate`` **does not agree** with the
   vectorised mask logic that produced 100,768. Measured on a 40,000-row sample
   of the real parent source: 1,838 vectorised candidates versus 2,592 row-wise
   candidates, **756 disagreements (1.89%)**. The row-wise path is more
   permissive.

Calling ``classify_candidate`` would therefore *not* reproduce 100,768. This
module extracts the vectorised logic verbatim so there is exactly one
authoritative selection function, without altering
``scripts/resample_south_africa_v2.py`` (whose completed outputs are preserved)
and without touching the legacy ``sa_candidate_filter`` duplicates.

Selection rules (Requirements Section 6.4)
------------------------------------------

===== ====================================================
Rule  Condition
===== ====================================================
F     specific banking issue phrase
A     banking aspect + problem expression
B     banking aspect + request expression
C     first-person + banking aspect
D     positive sentiment + positive service context
E     (suggestion | warning | churn) + banking reference
===== ====================================================

All rules additionally require: not an unrelated-bank match, text length
>= ``MIN_TEXT_LENGTH``, and not promotional-without-personal-experience.
A record is a candidate when it matches at least one rule and additionally
falls inside the study year range and is not a possible official account.

Rule attribution uses the documented precedence F > A > B > C > D > E, which is
what produces the historical per-rule breakdown.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from banking_tasci.data.sa_candidate_filter import (
    BANKING_ASPECT_KW,
    BANKING_REFERENCE_KW,
    CHURN_KW,
    FIRST_PERSON_KW,
    MIN_TEXT_LENGTH,
    POSITIVE_CONTEXT_KW,
    POSITIVE_KW,
    PROBLEM_KW,
    PROMOTIONAL_KW,
    REQUEST_KW,
    SPECIFIC_ISSUE_KW,
    SUGGESTION_KW,
    UNRELATED_BANK_KW,
    WARNING_KW,
)

__all__ = [
    "SELECTION_VERSION",
    "YEAR_MIN",
    "YEAR_MAX",
    "RULE_PRECEDENCE",
    "EXPECTED_TOTAL",
    "EXPECTED_RULE_COUNTS",
    "REQUIRED_SOURCE_COLUMNS",
    "SelectionResult",
    "select_v2_candidates",
]

SELECTION_VERSION = "sa_candidates_v2"

# Study-scope year range (documented in outputs/south_africa_data_report.json
# as a study-scope decision, not a cleaning error).
YEAR_MIN = 2018
YEAR_MAX = 2022

# Documented attribution precedence; order is load-bearing for rule counts.
RULE_PRECEDENCE = ("F", "A", "B", "C", "D", "E")

# The authoritative expectations, from the September 2026 run log and
# docs/south_africa_resampling_report.md. Used for verification only - never
# to coerce, truncate, or pad a result.
EXPECTED_TOTAL = 100_768
EXPECTED_RULE_COUNTS = {
    "C": 38_185,
    "A": 33_360,
    "B": 18_428,
    "D": 6_380,
    "E": 2_880,
    "F": 1_535,
}

# Minimum columns the parent source must provide for selection.
REQUIRED_SOURCE_COLUMNS = (
    "record_id",
    "text",
    "created_at",
    "possible_official_account",
)


@dataclass
class SelectionResult:
    """Outcome of a v2 candidate selection pass."""

    mask: Any = None
    rule_labels: Any = None
    total: int = 0
    rule_counts: dict[str, int] = field(default_factory=dict)
    parent_row_count: int = 0
    selection_version: str = SELECTION_VERSION
    year_min: int = YEAR_MIN
    year_max: int = YEAR_MAX
    min_text_length: int = MIN_TEXT_LENGTH

    def to_dict(self) -> dict:
        payload = asdict(self)
        # The boolean/label Series are large; they are not part of the report.
        payload.pop("mask", None)
        payload.pop("rule_labels", None)
        return payload


def _keyword_mask(padded_lower: "pd.Series", keywords: "list[str]") -> "pd.Series":
    """Vectorised space-padded substring match, verbatim from the v2 path.

    Padding both the text and each keyword with single spaces prevents short
    tokens such as ``app`` matching inside unrelated words such as ``happy``.
    """
    combined = "|".join(re.escape(f" {kw.lower()} ") for kw in keywords)
    return padded_lower.str.contains(combined, regex=True)


def select_v2_candidates(frame: "pd.DataFrame") -> SelectionResult:
    """Apply the canonical v2 evidence-based candidate selection.

    Args:
        frame: the parent South African prepared dataset. Must contain
            :data:`REQUIRED_SOURCE_COLUMNS`.

    Returns:
        A :class:`SelectionResult` whose ``mask`` is a boolean Series aligned to
        ``frame.index`` and whose ``rule_labels`` gives the attributed rule for
        each selected row.

    Raises:
        ValueError: if a required column is absent.

    This function only reads ``frame``; it never mutates it, and it never
    samples, truncates, or pads to reach any target count.
    """
    missing = [c for c in REQUIRED_SOURCE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            f"parent source is missing required column(s): {', '.join(missing)}"
        )

    texts = frame["text"].fillna("").astype(str)
    padded = " " + texts.str.lower() + " "

    has_aspect = _keyword_mask(padded, BANKING_ASPECT_KW)
    has_problem = _keyword_mask(padded, PROBLEM_KW)
    has_request = _keyword_mask(padded, REQUEST_KW)
    has_first_person = _keyword_mask(padded, FIRST_PERSON_KW)
    has_positive = _keyword_mask(padded, POSITIVE_KW)
    has_positive_context = _keyword_mask(padded, POSITIVE_CONTEXT_KW)
    has_suggestion = _keyword_mask(padded, SUGGESTION_KW)
    has_warning = _keyword_mask(padded, WARNING_KW)
    has_churn = _keyword_mask(padded, CHURN_KW)
    has_specific = _keyword_mask(padded, SPECIFIC_ISSUE_KW)
    is_promotional = _keyword_mask(padded, PROMOTIONAL_KW)
    has_bank_reference = _keyword_mask(padded, BANKING_REFERENCE_KW)
    is_unrelated = _keyword_mask(padded, UNRELATED_BANK_KW)
    too_short = texts.str.len() < MIN_TEXT_LENGTH

    rule_f = has_specific & ~is_unrelated
    rule_a = has_aspect & has_problem & ~is_unrelated
    rule_b = has_aspect & has_request & ~is_unrelated
    rule_c = has_first_person & has_aspect & ~is_unrelated
    rule_d = has_positive & has_positive_context & ~is_unrelated
    rule_e = (has_suggestion | has_warning | has_churn) & has_bank_reference & ~is_unrelated

    # Promotional precedence: a promotional record is excluded unless it also
    # carries a first-person experience, a problem expression, or a specific
    # banking issue - so a genuine complaint mentioning a competition is kept.
    promotional_exclude = is_promotional & ~(has_first_person | has_problem | has_specific)

    matches_any_rule = (rule_f | rule_a | rule_b | rule_c | rule_d | rule_e)
    rule_eligible = matches_any_rule & ~too_short & ~promotional_exclude

    year = frame["created_at"].fillna("").astype(str).str[:4]
    in_year_range = year.isin([str(y) for y in range(YEAR_MIN, YEAR_MAX + 1)])

    not_official = ~frame["possible_official_account"].fillna(False).astype(bool)

    mask = rule_eligible & in_year_range & not_official

    # Rule attribution under the documented precedence F > A > B > C > D > E.
    rules = {"F": rule_f, "A": rule_a, "B": rule_b, "C": rule_c, "D": rule_d, "E": rule_e}
    labels = pd.Series("none", index=frame.index, dtype=object)
    already = pd.Series(False, index=frame.index)
    for name in RULE_PRECEDENCE:
        current = rules[name] & ~already
        labels[current] = name
        already = already | rules[name]

    selected_labels = labels[mask]
    rule_counts = {
        str(key): int(value)
        for key, value in selected_labels.value_counts().to_dict().items()
    }

    return SelectionResult(
        mask=mask,
        rule_labels=labels,
        total=int(mask.sum()),
        rule_counts=dict(sorted(rule_counts.items())),
        parent_row_count=int(len(frame)),
    )
