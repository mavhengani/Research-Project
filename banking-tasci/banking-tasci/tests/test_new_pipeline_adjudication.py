from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from banking_tasci.data.new_pipeline_adjudication import (  # noqa: E402
    AdjudicationError,
    apply_adjudication,
    compare_submissions,
)

_CLI_SPEC = importlib.util.spec_from_file_location(
    "adjudicate_new_pipeline_annotations", ROOT / "scripts/adjudicate_new_pipeline_annotations.py"
)
_CLI = importlib.util.module_from_spec(_CLI_SPEC)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
_CLI_SPEC.loader.exec_module(_CLI)


def _record(*, intent="complaint", public_warning=False, text="The app is bad."):
    return {
        "record_id": "south_africa_tweet::record-1",
        "source_record_id": "record-1",
        "source": "south_africa_tweet",
        "region": "south_africa",
        "bank": "FNB",
        "review_id": None,
        "thread_id": None,
        "conversation_id": None,
        "publish_year": 2020,
        "text": text,
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "duplicate_group": None,
        "leakage_group": "leak-1",
        "privacy_status": "anonymised",
        "primary_intent": intent,
        "public_warning": public_warning,
        "opinions": [],
        "annotation_status": "completed",
        "annotation_version": "new_pipeline_v1",
        "annotation_notes": None,
    }


def test_compare_reports_only_human_label_disagreements_and_input_hashes():
    left = [_record()]
    right = [_record(intent="request_for_assistance", public_warning=True)]
    result = compare_submissions(left, right)
    assert result["record_count"] == 1
    assert result["disagreement_count"] == 2
    assert result["immutable_mismatches"] == []
    assert result["annotator_a_checksum"] != result["annotator_b_checksum"]
    assert set(result["disagreements"][0]["fields"]) == {"primary_intent", "public_warning"}


def test_adjudication_requires_explicit_resolution_and_never_infers():
    left = [_record()]
    right = [_record(intent="request_for_assistance")]
    result = apply_adjudication(left, right, {}, adjudicator="Reviewer")
    assert result["complete"] is False
    assert result["records"] == []
    assert result["pending_review"] == [{"record_id": left[0]["record_id"], "field": "primary_intent"}]


def test_adjudication_preserves_both_values_in_separate_audit():
    left = [_record()]
    right = [_record(intent="request_for_assistance")]
    result = apply_adjudication(
        left, right,
        {left[0]["record_id"]: {"primary_intent": {"choice": "b", "rationale": "The record explicitly asks for corrective action."}}},
        adjudicator="Human Reviewer",
    )
    assert result["complete"] is True
    assert result["records"][0]["primary_intent"] == "request_for_assistance"
    assert "adjudication" not in result["records"][0]
    audit = result["audit_records"][0]["fields"]["primary_intent"]
    assert audit["annotator_a"] == "complaint"
    assert audit["annotator_b"] == "request_for_assistance"
    assert audit["adjudicator"] == "Human Reviewer"
    assert "customer" not in str(result["audit_records"])


def test_new_value_is_validated_by_canonical_schema():
    left = [_record()]
    right = [_record(intent="request_for_assistance")]
    with pytest.raises(AdjudicationError, match="invalid"):
        apply_adjudication(
            left, right,
            {left[0]["record_id"]: {"primary_intent": {"choice": "new", "value": "warning", "rationale": "Invalid legacy label."}}},
            adjudicator="Reviewer",
        )


def test_immutable_source_mismatch_refuses_adjudication():
    left = [_record()]
    right = [_record(text="different immutable text")]
    with pytest.raises(AdjudicationError, match="immutable"):
        apply_adjudication(left, right, {}, adjudicator="Reviewer")


def test_missing_or_duplicate_records_refuse_comparison():
    left = [_record()]
    with pytest.raises(AdjudicationError, match="IDs differ"):
        compare_submissions(left, [])
    with pytest.raises(AdjudicationError, match="duplicate"):
        compare_submissions(left + [copy.deepcopy(left[0])], left)


def test_decisions_require_rationale_and_must_match_disputed_fields():
    left = [_record()]
    right = [_record(intent="request_for_assistance")]
    with pytest.raises(AdjudicationError, match="rationale"):
        apply_adjudication(
            left, right,
            {left[0]["record_id"]: {"primary_intent": {"choice": "a", "rationale": " "}}},
            adjudicator="Reviewer",
        )
    with pytest.raises(AdjudicationError, match="without disagreements"):
        apply_adjudication(left, [_record()], {"unrelated": {}}, adjudicator="Reviewer")


def test_decision_template_contains_only_record_ids_and_disputed_fields(tmp_path, capsys):
    left = [_record()]
    right = [_record(intent="request_for_assistance")]
    a_path, b_path = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a_path.write_text(json.dumps(left[0]) + "\n")
    b_path.write_text(json.dumps(right[0]) + "\n")
    output = tmp_path / "decisions.jsonl"
    assert _CLI.main(["template", "--annotator-a", str(a_path), "--annotator-b", str(b_path), "--output", str(output)]) == 0
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["writes"] == 0
    assert _CLI.main(["template", "--annotator-a", str(a_path), "--annotator-b", str(b_path), "--output", str(output), "--write"]) == 0
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows == [{"record_id": left[0]["record_id"], "field": "primary_intent"}]
    assert "The app is bad" not in output.read_text()
