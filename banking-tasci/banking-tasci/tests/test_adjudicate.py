"""Tests for the Adjudication_Tool (scripts/adjudicate_annotations.py).

Covers the pure, stdin-free logic (Req 22.1, 22.3, 22.5, 22.6):
- `find_disagreements` detects intent, span, category, and sentiment
  disagreements on a small fixture.
- `merge_adjudicated`, driven by a synthetic `decisions` structure, produces
  adjudicated records whose final field values match the decisions AND whose
  per-field `adjudication` sub-object preserves both annotators' original
  values plus the adjudicator id and notes (Req 22.5, 22.6).
- Agreed records pass through carrying the agreed value with no
  `adjudication` sub-object.
- No input record is mutated by `merge_adjudicated`.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
for _dir in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from banking_tasci.data.annotations import (  # noqa: E402
    AnnotationRecord,
    AspectSpan,
)

import adjudicate_annotations as adj  # noqa: E402
from adjudicate_annotations import (  # noqa: E402
    find_disagreements,
    merge_adjudicated,
    _write_adjudicated,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _record(
    record_id: str,
    *,
    text: str,
    aspects: list,
    intent,
    annotator_id: str = "ann",
) -> AnnotationRecord:
    return AnnotationRecord(
        record_id=record_id,
        source="bank_reviews",
        region="international",
        text=text,
        previous_text="[NO_CONTEXT]",
        context_available=False,
        aspects=aspects,
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id=annotator_id,
        annotation_status="completed",
        notes="",
    )


# text: "The mobile app is slow but customer support was helpful."
#        0123456789...
_TEXT = "The mobile app is slow but customer support was helpful."
_MOBILE = AspectSpan("mobile app", 4, 14, "digital_banking", "negative")
_SUPPORT = AspectSpan("customer support", 27, 43, "customer_support", "positive")


# ---------------------------------------------------------------------------
# find_disagreements (Req 22.1)
# ---------------------------------------------------------------------------


def test_find_disagreements_detects_intent_and_aspect_disputes():
    """Intent, span, category, and sentiment disagreements are all surfaced."""
    # r_intent: intent differs only.
    a_intent = _record("r_intent", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b_intent = _record("r_intent", text=_TEXT, aspects=[_MOBILE], intent="general_feedback")

    # r_span: annotator B tagged an extra span (span-set disagreement).
    a_span = _record("r_span", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b_span = _record("r_span", text=_TEXT, aspects=[_MOBILE, _SUPPORT], intent="complaint")

    # r_cat: same span, different category.
    a_cat = _record("r_cat", text=_TEXT,
                    aspects=[AspectSpan("mobile app", 4, 14, "digital_banking", "negative")],
                    intent="complaint")
    b_cat = _record("r_cat", text=_TEXT,
                    aspects=[AspectSpan("mobile app", 4, 14, "general_service", "negative")],
                    intent="complaint")

    # r_sent: same span+category, different sentiment.
    a_sent = _record("r_sent", text=_TEXT,
                     aspects=[AspectSpan("mobile app", 4, 14, "digital_banking", "negative")],
                     intent="complaint")
    b_sent = _record("r_sent", text=_TEXT,
                     aspects=[AspectSpan("mobile app", 4, 14, "digital_banking", "positive")],
                     intent="complaint")

    # r_agree: fully identical -> no disagreement.
    a_agree = _record("r_agree", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b_agree = _record("r_agree", text=_TEXT, aspects=[_MOBILE], intent="complaint")

    records_a = [a_intent, a_span, a_cat, a_sent, a_agree]
    records_b = [b_intent, b_span, b_cat, b_sent, b_agree]

    entries = find_disagreements(records_a, records_b)
    by_id = {e["record_id"]: e for e in entries}

    # The agreed record produces no disagreement entry.
    assert "r_agree" not in by_id
    assert set(by_id) == {"r_intent", "r_span", "r_cat", "r_sent"}

    # Intent dispute exposes the `intent` adjudicable field with both values.
    assert "intent" in by_id["r_intent"]["fields"]
    assert by_id["r_intent"]["fields"]["intent"]["annotator_a"] == "complaint"
    assert by_id["r_intent"]["fields"]["intent"]["annotator_b"] == "general_feedback"

    # Span / category / sentiment disputes all collapse to the `aspects`
    # adjudicable field.
    for rid in ("r_span", "r_cat", "r_sent"):
        assert "aspects" in by_id[rid]["fields"], rid
        assert "intent" not in by_id[rid]["fields"], rid

    # The granular detail preserves the underlying disagreement types.
    detail_types = {d["type"] for d in by_id["r_span"]["detail"]}
    assert "span" in detail_types
    assert {d["type"] for d in by_id["r_cat"]["detail"]} == {"category"}
    assert {d["type"] for d in by_id["r_sent"]["detail"]} == {"sentiment"}


# ---------------------------------------------------------------------------
# merge_adjudicated: final values + preserved originals (Req 22.3, 22.5, 22.6)
# ---------------------------------------------------------------------------


def test_merge_adjudicated_choice_a_and_b_preserve_both_originals():
    """Choosing 'a' for intent and 'b' for aspects yields those final values
    while the `adjudication` sub-object preserves BOTH annotators' originals
    plus adjudicator id and notes."""
    a = _record("r1", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b = _record("r1", text=_TEXT, aspects=[_MOBILE, _SUPPORT], intent="general_feedback")

    decisions = {
        "r1": {
            "intent": {"choice": "a", "value": None, "notes": "A's intent is right",
                       "adjudicator_id": "lead"},
            "aspects": {"choice": "b", "value": None, "notes": "B caught the extra aspect",
                        "adjudicator_id": "lead"},
        }
    }

    merged = merge_adjudicated([a], [b], decisions)
    assert len(merged) == 1
    rec = merged[0]

    # Final field values follow the decisions.
    assert rec.intent == "complaint"          # chose A
    assert len(rec.aspects) == 2              # chose B (mobile + support)

    adjudication = getattr(rec, "adjudication")
    # Intent: both originals + final + adjudicator + notes preserved.
    assert adjudication["intent"]["annotator_a_value"] == "complaint"
    assert adjudication["intent"]["annotator_b_value"] == "general_feedback"
    assert adjudication["intent"]["final_value"] == "complaint"
    assert adjudication["intent"]["adjudicator_id"] == "lead"
    assert adjudication["intent"]["notes"] == "A's intent is right"

    # Aspects: both originals preserved as serialised span lists.
    assert len(adjudication["aspects"]["annotator_a_value"]) == 1
    assert len(adjudication["aspects"]["annotator_b_value"]) == 2
    assert len(adjudication["aspects"]["final_value"]) == 2
    assert adjudication["aspects"]["annotator_a_value"][0]["term"] == "mobile app"


def test_merge_adjudicated_new_intent_value():
    """A typed new final intent value is applied and recorded, with both
    original annotator intents still preserved (Req 22.3, 22.5)."""
    a = _record("r1", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b = _record("r1", text=_TEXT, aspects=[_MOBILE], intent="warning")

    decisions = {
        "r1": {
            "intent": {"choice": "new", "value": "churn_signal",
                       "notes": "both missed the churn cue", "adjudicator_id": "lead"},
        }
    }

    merged = merge_adjudicated([a], [b], decisions)
    rec = merged[0]

    assert rec.intent == "churn_signal"
    adjudication = getattr(rec, "adjudication")
    assert adjudication["intent"]["annotator_a_value"] == "complaint"
    assert adjudication["intent"]["annotator_b_value"] == "warning"
    assert adjudication["intent"]["final_value"] == "churn_signal"
    assert adjudication["intent"]["notes"] == "both missed the churn cue"


def test_agreed_records_pass_through_without_adjudication():
    """A jointly-annotated record with no decision passes through carrying
    the agreed value and gains NO `adjudication` sub-object."""
    a = _record("r_agree", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b = _record("r_agree", text=_TEXT, aspects=[_MOBILE], intent="complaint")

    merged = merge_adjudicated([a], [b], decisions={})
    assert len(merged) == 1
    rec = merged[0]
    assert rec.intent == "complaint"
    assert len(rec.aspects) == 1
    assert getattr(rec, "adjudication", None) is None


def test_merge_adjudicated_does_not_mutate_inputs():
    """merge_adjudicated is pure: neither input record is modified."""
    a = _record("r1", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b = _record("r1", text=_TEXT, aspects=[_MOBILE, _SUPPORT], intent="general_feedback")

    a_before = copy.deepcopy(a)
    b_before = copy.deepcopy(b)

    decisions = {
        "r1": {
            "intent": {"choice": "b", "value": None, "notes": "", "adjudicator_id": "lead"},
            "aspects": {"choice": "a", "value": None, "notes": "", "adjudicator_id": "lead"},
        }
    }
    merge_adjudicated([a], [b], decisions)

    assert a.intent == a_before.intent
    assert b.intent == b_before.intent
    assert [asp.term for asp in a.aspects] == [asp.term for asp in a_before.aspects]
    assert [asp.term for asp in b.aspects] == [asp.term for asp in b_before.aspects]
    assert not hasattr(a, "adjudication")
    assert not hasattr(b, "adjudication")


def test_write_adjudicated_output_is_readable_and_carries_adjudication(tmp_path):
    """The written JSONL is readable by annotations.read_jsonl for the
    standard fields (Req 22.4) and carries the extra `adjudication` key on
    disputed records (Req 22.5)."""
    import json

    from banking_tasci.data import annotations as ann

    a = _record("r1", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b = _record("r1", text=_TEXT, aspects=[_MOBILE], intent="warning")
    a2 = _record("r2", text=_TEXT, aspects=[_MOBILE], intent="complaint")
    b2 = _record("r2", text=_TEXT, aspects=[_MOBILE], intent="complaint")

    decisions = {
        "r1": {"intent": {"choice": "a", "value": None, "notes": "n", "adjudicator_id": "lead"}}
    }
    merged = merge_adjudicated([a, a2], [b, b2], decisions)

    out = tmp_path / "pilot_adjudicated.jsonl"
    _write_adjudicated(merged, out)

    # Standard fields still round-trip through read_jsonl.
    read_back = ann.read_jsonl(out)
    assert {r.record_id for r in read_back} == {"r1", "r2"}

    lines = [json.loads(line) for line in out.read_text().splitlines()]
    by_id = {d["record_id"]: d for d in lines}
    assert "adjudication" in by_id["r1"]            # disputed
    assert "adjudication" not in by_id["r2"]        # agreed
    assert by_id["r1"]["adjudication"]["intent"]["adjudicator_id"] == "lead"
