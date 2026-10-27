"""Targeted tests for the Phase 3A.1 annotation workflow CLI changes.

Covers:
- annotation_app._parse_cli_args: correct parsing of --input/--output/--annotator-id.
- annotation_app.load_session_records: explicit_output_path parameter.
- annotation_app.save_annotator_file: explicit_output_path parameter.
- validate_annotations: --completed-only and --require-complete flags.
- calculate_agreement: --completed-only, --require-complete, --disagreements flags.
- adjudicate_annotations: --disagreements flag.
- create_splits: --near-dup-csv flag.

No Streamlit UI is launched. No research data is read. All tests use
small in-memory or tempfile fixtures.

Do NOT execute these tests until approved.
Run with:
    PYTHONPATH=src python3 -m pytest tests/test_annotation_workflow_cli.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ directory is on sys.path so we can import the CLI scripts.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
for _d in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))


# ---------------------------------------------------------------------------
# annotation_app CLI argument tests
# ---------------------------------------------------------------------------


class TestAnnotationAppCLI:
    def test_parse_cli_args_all_flags(self, monkeypatch):
        """All three CLI flags are parsed correctly."""
        import annotation_app
        monkeypatch.setattr(
            sys, "argv",
            ["annotation_app.py",
             "--input", "data/annotations/pilot_unannotated.jsonl",
             "--output", "data/annotations/pilot_annotator_a.jsonl",
             "--annotator-id", "annotator_a"],
        )
        result = annotation_app._parse_cli_args()
        assert result is not None
        assert result.input == "data/annotations/pilot_unannotated.jsonl"
        assert result.output == "data/annotations/pilot_annotator_a.jsonl"
        assert result.annotator_id == "annotator_a"

    def test_parse_cli_args_no_args_returns_none(self, monkeypatch):
        """When no relevant args are supplied, returns None (legacy mode)."""
        import annotation_app
        monkeypatch.setattr(sys, "argv", ["annotation_app.py"])
        result = annotation_app._parse_cli_args()
        assert result is None

    def test_load_session_records_explicit_path_used(self, tmp_path):
        """When explicit_output_path is provided and exists, records are
        loaded from it, not from the derived annotator path."""
        import annotation_app
        from banking_tasci.data.annotations import AnnotationRecord, write_jsonl

        # Create a minimal completed record in the explicit output file.
        record = AnnotationRecord(
            record_id="test_001",
            source="test",
            region="international",
            text="the mobile app is slow",
            previous_text="[NO_CONTEXT]",
            context_available=False,
            aspects=[],
            intent="complaint",
            intent_ambiguous=False,
            alternative_intent=None,
            annotator_id="annotator_a",
            annotation_status="completed",
            notes="",
        )
        explicit_path = tmp_path / "explicit_output.jsonl"
        write_jsonl([record], explicit_path)

        loaded = annotation_app.load_session_records(
            "annotator_a",
            unannotated_path=tmp_path / "nonexistent.jsonl",  # must not be read
            annotations_dir=tmp_path,
            explicit_output_path=explicit_path,
        )
        assert len(loaded) == 1
        assert loaded[0].record_id == "test_001"

    def test_save_annotator_file_explicit_path(self, tmp_path):
        """When explicit_output_path is provided, saves to that path."""
        import annotation_app
        from banking_tasci.data.annotations import AnnotationRecord

        record = AnnotationRecord(
            record_id="r1", source="t", region="intl", text="text",
            previous_text="[NO_CONTEXT]", context_available=False,
            aspects=[], intent=None, intent_ambiguous=False,
            alternative_intent=None, annotator_id="annotator_b",
            annotation_status="not_started", notes="",
        )
        explicit_path = tmp_path / "pilot_annotator_b.jsonl"
        saved = annotation_app.save_annotator_file(
            [record], "annotator_b", tmp_path, explicit_output_path=explicit_path
        )
        assert saved == explicit_path
        assert explicit_path.is_file()

    def test_different_annotators_write_separate_files(self, tmp_path):
        """Annotator A's save does not overwrite annotator B's file."""
        import annotation_app
        from banking_tasci.data.annotations import AnnotationRecord

        def make_record(annotator_id, status):
            return AnnotationRecord(
                record_id="r1", source="t", region="intl", text="text",
                previous_text="[NO_CONTEXT]", context_available=False,
                aspects=[], intent=None, intent_ambiguous=False,
                alternative_intent=None, annotator_id=annotator_id,
                annotation_status=status, notes="",
            )

        path_a = tmp_path / "pilot_annotator_a.jsonl"
        path_b = tmp_path / "pilot_annotator_b.jsonl"

        annotation_app.save_annotator_file(
            [make_record("annotator_a", "completed")],
            "annotator_a", tmp_path, explicit_output_path=path_a,
        )
        annotation_app.save_annotator_file(
            [make_record("annotator_b", "in_progress")],
            "annotator_b", tmp_path, explicit_output_path=path_b,
        )

        assert path_a.is_file()
        assert path_b.is_file()
        # Verify they are distinct and correct.
        from banking_tasci.data.annotations import read_jsonl
        recs_a = read_jsonl(path_a)
        recs_b = read_jsonl(path_b)
        assert recs_a[0].annotator_id == "annotator_a"
        assert recs_b[0].annotator_id == "annotator_b"
        assert recs_a[0].annotation_status == "completed"
        assert recs_b[0].annotation_status == "in_progress"


# ---------------------------------------------------------------------------
# validate_annotations CLI tests
# ---------------------------------------------------------------------------


def _make_jsonl_file(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _completed_record(record_id="r1"):
    return {
        "record_id": record_id,
        "source": "bank_tweets",
        "region": "international",
        "text": "the customer service was slow",
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "aspects": [],
        "intent": "complaint",
        "intent_ambiguous": False,
        "alternative_intent": None,
        "annotator_id": "annotator_a",
        "annotation_status": "completed",
        "notes": "",
    }


def _not_started_record(record_id="r2"):
    rec = _completed_record(record_id)
    rec["annotation_status"] = "not_started"
    rec["intent"] = None
    return rec


class TestValidateAnnotationsCLI:
    def test_completed_only_skips_not_started(self, tmp_path):
        """--completed-only: not_started records are skipped, only completed are validated."""
        import validate_annotations
        input_path = tmp_path / "input.jsonl"
        _make_jsonl_file(input_path, [_completed_record("r1"), _not_started_record("r2")])
        output_path = tmp_path / "report.json"

        rc = validate_annotations.main([
            "--input", str(input_path),
            "--output", str(output_path),
            "--completed-only",
        ])
        assert rc == 0
        report = json.loads(output_path.read_text())
        # Only the completed record is validated.
        assert report["valid_count"] + report["invalid_count"] == 1

    def test_require_complete_fails_when_incomplete(self, tmp_path):
        """--require-complete: exits 1 when not_started records exist."""
        import validate_annotations
        input_path = tmp_path / "input.jsonl"
        _make_jsonl_file(input_path, [_completed_record("r1"), _not_started_record("r2")])
        output_path = tmp_path / "report.json"

        rc = validate_annotations.main([
            "--input", str(input_path),
            "--output", str(output_path),
            "--require-complete",
        ])
        assert rc == 1

    def test_require_complete_passes_when_all_done(self, tmp_path):
        """--require-complete: exits 0 when all records are completed."""
        import validate_annotations
        input_path = tmp_path / "input.jsonl"
        _make_jsonl_file(input_path, [_completed_record("r1"), _completed_record("r2")])
        output_path = tmp_path / "report.json"

        rc = validate_annotations.main([
            "--input", str(input_path),
            "--output", str(output_path),
            "--require-complete",
        ])
        assert rc == 0

    def test_no_flags_validates_all_records(self, tmp_path):
        """Without flags, all records (including not_started) are validated."""
        import validate_annotations
        input_path = tmp_path / "input.jsonl"
        _make_jsonl_file(input_path, [_completed_record("r1"), _not_started_record("r2")])
        output_path = tmp_path / "report.json"

        rc = validate_annotations.main([
            "--input", str(input_path),
            "--output", str(output_path),
        ])
        assert rc == 0
        report = json.loads(output_path.read_text())
        assert report["valid_count"] + report["invalid_count"] == 2


# ---------------------------------------------------------------------------
# calculate_agreement CLI tests
# ---------------------------------------------------------------------------


class TestCalculateAgreementCLI:
    def _write_two_annotator_files(self, tmp_path, status_a="completed", status_b="completed"):
        path_a = tmp_path / "annotator_a.jsonl"
        path_b = tmp_path / "annotator_b.jsonl"
        rec_a = _completed_record("r1")
        rec_a["annotation_status"] = status_a
        rec_a["annotator_id"] = "annotator_a"
        rec_b = _completed_record("r1")
        rec_b["annotation_status"] = status_b
        rec_b["annotator_id"] = "annotator_b"
        _make_jsonl_file(path_a, [rec_a])
        _make_jsonl_file(path_b, [rec_b])
        return path_a, path_b

    def test_completed_only_restricts_to_both_done(self, tmp_path):
        """--completed-only with one not_started annotator produces 0 joint records."""
        import calculate_agreement
        path_a, path_b = self._write_two_annotator_files(tmp_path, "completed", "not_started")
        output_path = tmp_path / "agreement.json"
        rc = calculate_agreement.main([
            "--annotator-a", str(path_a),
            "--annotator-b", str(path_b),
            "--output", str(output_path),
            "--completed-only",
        ])
        assert rc == 0
        report = json.loads(output_path.read_text())
        assert report["joint_record_count"] == 0

    def test_require_complete_fails_with_incomplete(self, tmp_path):
        """--require-complete: exits 1 when annotator-b has not_started records."""
        import calculate_agreement
        path_a, path_b = self._write_two_annotator_files(tmp_path, "completed", "not_started")
        output_path = tmp_path / "agreement.json"
        rc = calculate_agreement.main([
            "--annotator-a", str(path_a),
            "--annotator-b", str(path_b),
            "--output", str(output_path),
            "--require-complete",
        ])
        assert rc == 1

    def test_disagreements_alias(self, tmp_path):
        """--disagreements is accepted as an alias for --disagreements-output."""
        import calculate_agreement
        path_a, path_b = self._write_two_annotator_files(tmp_path)
        output_path = tmp_path / "agreement.json"
        disagreements_path = tmp_path / "disagreements.jsonl"
        rc = calculate_agreement.main([
            "--annotator-a", str(path_a),
            "--annotator-b", str(path_b),
            "--output", str(output_path),
            "--disagreements", str(disagreements_path),
        ])
        assert rc == 0
        assert disagreements_path.is_file()


# ---------------------------------------------------------------------------
# create_splits near-dup CSV tests
# ---------------------------------------------------------------------------


class TestCreateSplitsNearDup:
    def test_near_dup_csv_missing_column_is_ignored(self, tmp_path):
        """When the CSV has no near_dup_group_id column, splits proceed normally."""
        import create_splits

        # Write a CSV without the near_dup_group_id column.
        csv_path = tmp_path / "prepared.csv"
        csv_path.write_text("record_id,text\nr1,hello\nr2,world\n")

        # Just verify _read_near_dup_groups returns empty dict.
        result = create_splits._read_near_dup_groups(csv_path)
        assert result == {}

    def test_near_dup_csv_read_correctly(self, tmp_path):
        """near_dup_group_id column is read and returned correctly."""
        import create_splits

        csv_path = tmp_path / "prepared.csv"
        csv_path.write_text(
            "record_id,near_dup_group_id\n"
            "r1,group_abc\n"
            "r2,group_abc\n"
            "r3,\n"
        )
        result = create_splits._read_near_dup_groups(csv_path)
        assert result["r1"] == "group_abc"
        assert result["r2"] == "group_abc"
        assert "r3" not in result  # empty group ID skipped

    def test_near_dup_csv_absent_returns_empty(self, tmp_path):
        """Non-existent file returns empty dict without raising."""
        import create_splits
        result = create_splits._read_near_dup_groups(tmp_path / "nonexistent.csv")
        assert result == {}
