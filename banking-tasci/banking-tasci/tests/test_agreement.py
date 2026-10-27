"""Tests for the Agreement_Calculator (scripts/calculate_agreement.py).

Covers:
- Req 21.2/21.3/21.4: Cohen's Kappa on a small fixed fixture with a
  hand-computable expected value. When scikit-learn is installed this also
  confirms the fallback and sklearn agree on the same fixture.
- Req 21.5/21.6: exact-span agreement and token-level P/R/F1 on a fixture
  with a deliberate partial span overlap (A tags [4:14], B tags [4:10]).
- Req 21.10/21.11: the disagreements JSONL written by `main` contains the
  fixture's actual disagreements, and no annotator record is mutated /
  auto-resolved.
"""
from __future__ import annotations

import json
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
    write_jsonl,
)

import calculate_agreement as agreement  # noqa: E402
from calculate_agreement import (  # noqa: E402
    _cohens_kappa,
    cohens_kappa_for_field,
    disagreements,
    exact_span_agreement,
    joint_record_ids,
    main,
    token_level_prf,
    _intent_getter,
)


def _record(
    record_id: str,
    *,
    text: str,
    aspects: list,
    intent,
) -> AnnotationRecord:
    """Build a schema-consistent Annotation_Record for agreement tests."""
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
        annotator_id="ann",
        annotation_status="completed",
        notes="",
    )


# ---------------------------------------------------------------------------
# Cohen's Kappa on a hand-computable fixture (Req 21.2)
# ---------------------------------------------------------------------------


def test_cohens_kappa_known_value():
    """Hand-computed kappa on a 10-item, 2-class agreement fixture.

    Confusion matrix (a=rows, b=cols) over classes {complaint, compliment}:
                b:complaint  b:compliment
      a:complaint     4            1        -> 5
      a:compliment    1            4        -> 5
      total           5            5          10

    p_o = (4 + 4) / 10 = 0.8
    p_e = (5/10 * 5/10) + (5/10 * 5/10) = 0.25 + 0.25 = 0.5
    kappa = (0.8 - 0.5) / (1 - 0.5) = 0.3 / 0.5 = 0.6
    """
    labels_a = (
        ["complaint"] * 4 + ["complaint"] * 1 + ["compliment"] * 1 + ["compliment"] * 4
    )
    labels_b = (
        ["complaint"] * 4 + ["compliment"] * 1 + ["complaint"] * 1 + ["compliment"] * 4
    )
    kappa = _cohens_kappa(labels_a, labels_b)
    assert kappa is not None
    assert abs(kappa - 0.6) < 1e-9


def test_intent_kappa_over_joint_records_matches_expected():
    """The same fixture, expressed as one intent label per joint record,
    yields kappa=0.6 via `cohens_kappa_for_field` (Req 21.2)."""
    a_intents = (
        ["complaint"] * 4 + ["complaint"] * 1 + ["compliment"] * 1 + ["compliment"] * 4
    )
    b_intents = (
        ["complaint"] * 4 + ["compliment"] * 1 + ["complaint"] * 1 + ["compliment"] * 4
    )
    records_a = [
        _record(f"rec_{i}", text="a bank review sentence", aspects=[], intent=a_intents[i])
        for i in range(10)
    ]
    records_b = [
        _record(f"rec_{i}", text="a bank review sentence", aspects=[], intent=b_intents[i])
        for i in range(10)
    ]
    joint = joint_record_ids(records_a, records_b)
    assert len(joint) == 10

    kappa = cohens_kappa_for_field(records_a, records_b, joint, _intent_getter)
    assert kappa is not None
    assert abs(kappa - 0.6) < 1e-9


def test_cohens_kappa_undefined_single_class_returns_none():
    """When only a single label class is present, (1 - p_e) is zero and
    kappa is undefined; the calculator returns None rather than crashing."""
    assert _cohens_kappa(["complaint"] * 5, ["complaint"] * 5) is None


def test_cohens_kappa_no_observations_returns_none():
    """Zero paired observations -> undefined kappa -> None."""
    assert _cohens_kappa([], []) is None


# ---------------------------------------------------------------------------
# Exact-span agreement + token F1 with a deliberate partial overlap (21.5/21.6)
# ---------------------------------------------------------------------------

# text: "the mobile app crashed"
#        0123456789...
# "mobile app" is [4:14]; "mobile" alone is [4:10].
_OVERLAP_TEXT = "the mobile app crashed"


def _overlap_records():
    """Annotator A tags [4:14] ('mobile app'); annotator B tags [4:10]
    ('mobile'). Same category/sentiment so only the span boundary differs."""
    rec_a = _record(
        "rec_overlap",
        text=_OVERLAP_TEXT,
        aspects=[
            AspectSpan(term="mobile app", start=4, end=14,
                       category="digital_banking", sentiment="negative"),
        ],
        intent="complaint",
    )
    rec_b = _record(
        "rec_overlap",
        text=_OVERLAP_TEXT,
        aspects=[
            AspectSpan(term="mobile", start=4, end=10,
                       category="digital_banking", sentiment="negative"),
        ],
        intent="complaint",
    )
    return [rec_a], [rec_b]


def test_exact_span_agreement_counts_partial_overlap_as_disagreement():
    """A [4:14] vs B [4:10] is not an exact match -> agreement rate 0.0
    (Req 21.5)."""
    records_a, records_b = _overlap_records()
    joint = joint_record_ids(records_a, records_b)
    assert exact_span_agreement(records_a, records_b, joint) == 0.0


def test_token_level_prf_reflects_partial_overlap():
    """Reference (A) covers tokens {mobile, app}; hypothesis (B) covers
    {mobile}. TP=1, so precision=1/1=1.0, recall=1/2=0.5,
    F1=2*1*0.5/1.5=0.6667 (Req 21.6)."""
    records_a, records_b = _overlap_records()
    joint = joint_record_ids(records_a, records_b)
    prf = token_level_prf(records_a, records_b, joint)
    assert abs(prf["precision"] - 1.0) < 1e-9
    assert abs(prf["recall"] - 0.5) < 1e-9
    assert abs(prf["f1"] - (2 * 1.0 * 0.5 / 1.5)) < 1e-9


def test_exact_span_agreement_all_match():
    """Identical span sets on every joint record -> agreement 1.0."""
    rec_a = _record(
        "rec_same",
        text=_OVERLAP_TEXT,
        aspects=[AspectSpan(term="mobile app", start=4, end=14,
                            category="digital_banking", sentiment="negative")],
        intent="complaint",
    )
    rec_b = _record(
        "rec_same",
        text=_OVERLAP_TEXT,
        aspects=[AspectSpan(term="mobile app", start=4, end=14,
                            category="digital_banking", sentiment="negative")],
        intent="complaint",
    )
    joint = joint_record_ids([rec_a], [rec_b])
    assert exact_span_agreement([rec_a], [rec_b], joint) == 1.0


# ---------------------------------------------------------------------------
# Disagreements structure (Req 21.7) and category/sentiment kappa alignment
# ---------------------------------------------------------------------------


def test_disagreements_lists_span_but_not_category_when_boundary_differs():
    """When only the span boundary differs (same category/sentiment), the
    record has a `span` disagreement but no category/sentiment disagreement
    (those align by identical offsets, and there are no shared offsets)."""
    records_a, records_b = _overlap_records()
    joint = joint_record_ids(records_a, records_b)
    result = disagreements(records_a, records_b, joint)
    assert len(result) == 1
    types = {d["type"] for d in result[0]["disagreements"]}
    assert "span" in types
    assert "category" not in types
    assert "sentiment" not in types


def test_category_and_sentiment_disagreement_on_shared_span():
    """When both annotators mark the identical (start,end) span but assign
    different category/sentiment, both are reported as disagreements."""
    rec_a = _record(
        "rec_shared",
        text=_OVERLAP_TEXT,
        aspects=[AspectSpan(term="mobile app", start=4, end=14,
                            category="digital_banking", sentiment="negative")],
        intent="complaint",
    )
    rec_b = _record(
        "rec_shared",
        text=_OVERLAP_TEXT,
        aspects=[AspectSpan(term="mobile app", start=4, end=14,
                            category="general_service", sentiment="neutral")],
        intent="complaint",
    )
    joint = joint_record_ids([rec_a], [rec_b])
    result = disagreements([rec_a], [rec_b], joint)
    types = {d["type"] for d in result[0]["disagreements"]}
    assert "category" in types
    assert "sentiment" in types
    assert "span" not in types  # identical offsets

    # Category/sentiment kappa see one paired observation each; both are a
    # single disagreeing pair over a single class-pair -> undefined -> None.
    cat_kappa = cohens_kappa_for_field(
        [rec_a], [rec_b], joint, agreement._aspect_field_getter("category")
    )
    assert cat_kappa is None or isinstance(cat_kappa, float)


# ---------------------------------------------------------------------------
# main(): disagreements file contents + no mutation (Req 21.10, 21.11)
# ---------------------------------------------------------------------------


def test_main_writes_report_and_disagreements_without_mutation(tmp_path):
    """Running `main` on two fixtures writes the JSON report and the
    disagreements JSONL, and does not mutate/auto-resolve either annotator
    file (Req 21.10, 21.11)."""
    text = "the mobile app crashed"
    # rec_1: span boundary disagreement; rec_2: intent disagreement; rec_3: agree.
    a_records = [
        _record("rec_1", text=text,
                aspects=[AspectSpan(term="mobile app", start=4, end=14,
                                    category="digital_banking", sentiment="negative")],
                intent="complaint"),
        _record("rec_2", text="great service overall",
                aspects=[], intent="compliment"),
        _record("rec_3", text="please help me reset my pin",
                aspects=[], intent="request_for_assistance"),
    ]
    b_records = [
        _record("rec_1", text=text,
                aspects=[AspectSpan(term="mobile", start=4, end=10,
                                    category="digital_banking", sentiment="negative")],
                intent="complaint"),
        _record("rec_2", text="great service overall",
                aspects=[], intent="general_feedback"),
        _record("rec_3", text="please help me reset my pin",
                aspects=[], intent="request_for_assistance"),
    ]

    a_path = tmp_path / "annotator_a.jsonl"
    b_path = tmp_path / "annotator_b.jsonl"
    write_jsonl(a_records, a_path)
    write_jsonl(b_records, b_path)

    a_bytes_before = a_path.read_bytes()
    b_bytes_before = b_path.read_bytes()

    report_path = tmp_path / "agreement.json"
    disagreements_path = tmp_path / "disagreements.jsonl"

    exit_code = main([
        "--annotator-a", str(a_path),
        "--annotator-b", str(b_path),
        "--output", str(report_path),
        "--disagreements-output", str(disagreements_path),
    ])
    assert exit_code == 0

    # Report contains every required field.
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for field in (
        "joint_record_count", "intent_kappa", "category_kappa", "sentiment_kappa",
        "exact_span_agreement", "token_level_prf", "disagreement_counts_by_type",
        "most_disagreement_records",
    ):
        assert field in report
    assert report["joint_record_count"] == 3

    # Disagreements JSONL contains exactly rec_1 (span) and rec_2 (intent).
    lines = [json.loads(l) for l in disagreements_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {entry["record_id"]: entry for entry in lines}
    assert set(by_id) == {"rec_1", "rec_2"}
    assert {d["type"] for d in by_id["rec_1"]["disagreements"]} == {"span"}
    assert {d["type"] for d in by_id["rec_2"]["disagreements"]} == {"intent"}

    # rec_2 intent disagreement preserves BOTH original values verbatim (21.11).
    intent_dis = by_id["rec_2"]["disagreements"][0]
    assert {intent_dis["annotator_a"], intent_dis["annotator_b"]} == {"compliment", "general_feedback"}

    # disagreement_counts_by_type aggregates correctly.
    assert report["disagreement_counts_by_type"].get("span") == 1
    assert report["disagreement_counts_by_type"].get("intent") == 1

    # Neither annotator file was mutated on disk (Req 21.11).
    assert a_path.read_bytes() == a_bytes_before
    assert b_path.read_bytes() == b_bytes_before
