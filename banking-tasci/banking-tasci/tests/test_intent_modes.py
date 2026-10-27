"""Tests for explicit intent input modes (Phase 3A, Part 7).

Verifies:
- ``current_only`` renders just the current text;
- ``previous_plus_current`` prepends the genuine previous turn only when the
  record has context available, otherwise the ``[NO_CONTEXT]`` sentinel;
- the loader never assigns an unrelated previous row as context;
- an unknown mode raises.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import AnnotationRecord  # noqa: E402
from banking_tasci.data.datasets import (  # noqa: E402
    INTENT_MODE_CURRENT_ONLY,
    INTENT_MODE_PREVIOUS_PLUS_CURRENT,
    NO_CONTEXT,
    build_intent_examples,
    render_intent_text,
)


def _record(rid, text, previous_text, context_available, intent="complaint"):
    return AnnotationRecord(
        record_id=rid,
        source="bank_reviews",
        region="local",
        text=text,
        previous_text=previous_text,
        context_available=context_available,
        aspects=[],
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="a",
        annotation_status="completed",
        notes="",
    )


def test_current_only_mode_uses_current_text():
    rec = _record("r1", "the app is slow", "earlier turn", True)
    ex = build_intent_examples([rec])[0]
    assert render_intent_text(ex, INTENT_MODE_CURRENT_ONLY) == "the app is slow"


def test_previous_plus_current_prepends_genuine_context():
    rec = _record("r1", "the app is slow", "the app was fine yesterday", True)
    ex = build_intent_examples([rec])[0]
    rendered = render_intent_text(ex, INTENT_MODE_PREVIOUS_PLUS_CURRENT)
    assert rendered == "the app was fine yesterday the app is slow"


def test_previous_plus_current_uses_sentinel_when_no_context():
    rec = _record("r1", "the app is slow", NO_CONTEXT, False)
    ex = build_intent_examples([rec])[0]
    # previous_text must be dropped by the loader when context is unavailable.
    assert ex.previous_text is None
    rendered = render_intent_text(ex, INTENT_MODE_PREVIOUS_PLUS_CURRENT)
    assert rendered == f"{NO_CONTEXT} the app is slow"


def test_loader_never_assigns_unrelated_previous_row_as_context():
    # A record with context_available=False must never carry previous_text,
    # even if the raw record had some non-sentinel previous_text set.
    rec = _record("r1", "current text", "leaked previous row", False)
    ex = build_intent_examples([rec])[0]
    assert ex.previous_text is None
    assert render_intent_text(ex, INTENT_MODE_PREVIOUS_PLUS_CURRENT) == f"{NO_CONTEXT} current text"


def test_unknown_intent_mode_raises():
    rec = _record("r1", "text", NO_CONTEXT, False)
    ex = build_intent_examples([rec])[0]
    with pytest.raises(ValueError):
        render_intent_text(ex, "bogus_mode")

