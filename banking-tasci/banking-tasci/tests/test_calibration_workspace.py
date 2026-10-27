from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from banking_tasci.data.calibration_workspace import (  # noqa: E402
    HUMAN_DECISION_CODES,
    RESEARCHER_ACKNOWLEDGEMENT,
    WorkspaceError,
    apply_human_decisions,
    annotation_batch_display_name,
    create_annotation_workspace,
    exact_text_offsets,
    restore_checkpoint,
    save_checkpoint,
    verify_audit_chain,
    workspace_status,
)


def _record(record_id: str, *, status: str = "not_started") -> dict:
    return {
        "record_id": record_id,
        "source_record_id": record_id,
        "source": "south_africa_tweet",
        "region": "south_africa",
        "bank": "FNB",
        "review_id": None,
        "thread_id": None,
        "conversation_id": None,
        "publish_year": 2020,
        "text": "The app is bad.",
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "duplicate_group": None,
        "leakage_group": None,
        "privacy_status": "anonymised",
        "primary_intent": None,
        "public_warning": None,
        "opinions": [],
        "annotation_status": status,
        "annotation_version": "new_pipeline_v1",
        "annotation_notes": None,
    }


def _jsonl(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _workspace(tmp_path: Path):
    project = tmp_path / "project"
    workspace = project / "data/annotations/calibration_workspace/calibration_001"
    backups = workspace / "backups"
    backups.mkdir(parents=True)
    approved = project / "approved_calibration.jsonl"
    source = [_record(f"record-{index:02d}") for index in range(50)]
    source_bytes = _jsonl(source)
    approved.write_bytes(source_bytes)
    membership_bytes = _jsonl([{"record_id": row["record_id"], "batch_id": "calibration_001"} for row in source])
    membership_checksum = _sha(membership_bytes)
    frozen_dir = project / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2"
    frozen_dir.mkdir(parents=True)
    (frozen_dir / "approved_batch_membership.jsonl").write_bytes(membership_bytes)
    approval_path = project / "artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json"
    approval_path.parent.mkdir(parents=True)
    approval_bytes = json.dumps({"approval_status": "APPROVED", "candidate_number": 2}).encode()
    approval_path.write_bytes(approval_bytes)
    frozen_id_bytes = _jsonl([{"record_id": row["record_id"], "source_record_id": row["source_record_id"], "source": row["source"], "region": row["region"], "source_checksum": "synthetic"} for row in source])
    frozen_ids_path = frozen_dir / "gold_record_ids.jsonl"
    frozen_ids_path.write_bytes(frozen_id_bytes)
    (frozen_dir / "gold_sample_manifest.json").write_text(json.dumps({
        "immutable_status": "FROZEN", "candidate_number": 2,
        "approval_checksum": _sha(approval_bytes),
        "gold_id_checksum": _sha(frozen_id_bytes),
        "annotation_records_checksum": _sha(source_bytes),
        "approved_batch_manifest": {"membership_checksum": membership_checksum},
    }))
    frozen_ids_bytes = _jsonl([{"record_id": row["record_id"]} for row in source])
    (frozen_dir / "gold_record_ids.jsonl").write_bytes(frozen_ids_bytes)
    frozen_manifest = json.loads((frozen_dir / "gold_sample_manifest.json").read_text())
    frozen_manifest["gold_id_checksum"] = _sha(frozen_ids_bytes)
    (frozen_dir / "gold_sample_manifest.json").write_text(json.dumps(frozen_manifest))
    initial = backups / "initial.jsonl"
    initial.write_bytes(source_bytes)
    working = workspace / "working_annotations.jsonl"
    working.write_bytes(source_bytes)
    (workspace / "immutable_reference.json").write_text(json.dumps({
        "approved_source_path": "approved_calibration.jsonl",
        "approved_source_sha256": _sha(source_bytes),
        "approved_package_path": "approved_calibration.jsonl",
        "approved_package_sha256": _sha(source_bytes),
        "backup_path": str(initial.relative_to(project)),
        "backup_sha256": _sha(source_bytes),
        "record_count": 50,
    }))
    (workspace / "progress_manifest.json").write_text(json.dumps({
        "pipeline_version": "new_pipeline_v1",
        "batch_id": "calibration_001",
        "technical_batch_id": "calibration_001",
        "display_name": "Annotation Batch 1",
        "workflow_role": "standard_manual_annotation_batch",
        "source_checksum": _sha(source_bytes),
        "candidate_number": 2,
        "batch_status": "in_progress",
        "record_count": 50,
        "completed_record_count": 0,
        "remaining_record_count": 50,
        "working_checksum": _sha(source_bytes),
        "approved_membership_checksum": membership_checksum,
        "workspace_version": 1,
        "guide_version": "guide-v1",
        "annotation_guide_version": "guide-v1",
        "audit_events": [{"event": "batch_opened", "actor": "researcher", "reason": "synthetic fixture"}],
    }))
    candidate = project / "candidate.jsonl"
    edited = [dict(row) for row in source]
    edited[0].update(primary_intent="complaint", public_warning=False, annotation_status="completed")
    candidate.write_bytes(_jsonl(edited))
    return project, workspace, working, initial, candidate, source_bytes, candidate.read_bytes()


def test_checkpoint_dry_run_is_read_only(tmp_path):
    project, workspace, working, _initial, candidate, source_bytes, candidate_bytes = _workspace(tmp_path)
    result = save_checkpoint(
        workspace, candidate, project_root=project,
        expected_current_sha256=_sha(source_bytes), actor="Researcher", reason="synthetic test",
        expected_workspace_version=1, expected_guide_version="guide-v1",
        explicit_record_ids=["record-00"],
        researcher_acknowledgements={"record-00": RESEARCHER_ACKNOWLEDGEMENT},
        decision_actors={"record-00": "Researcher"},
    )
    assert result["result"] == "DRY_RUN_PASS"
    assert result["writes"] == 0
    assert working.read_bytes() == source_bytes
    assert not (workspace / "backups" / "working_annotations.jsonl").exists()


def test_checkpoint_save_backs_up_and_audits_human_submission(tmp_path):
    project, workspace, working, _initial, candidate, source_bytes, candidate_bytes = _workspace(tmp_path)
    result = save_checkpoint(
        workspace, candidate, project_root=project,
        expected_current_sha256=_sha(source_bytes), actor="Researcher", reason="save synthetic decisions",
        expected_workspace_version=1, expected_guide_version="guide-v1",
        explicit_record_ids=["record-00"],
        researcher_acknowledgements={"record-00": RESEARCHER_ACKNOWLEDGEMENT},
        decision_actors={"record-00": "Researcher"}, apply=True,
    )
    assert result["result"] == "CHECKPOINT_SAVED"
    assert working.read_bytes() == candidate_bytes
    assert (workspace / result["backup_path"]).read_bytes() == source_bytes
    status = workspace_status(workspace, project_root=project)
    assert status["completed_record_count"] == 1
    assert status["manifest_working_sha256_matches"] is True
    assert status["audit_chain"]["result"] == "PASS"


def test_restore_requires_registered_backup_and_preserves_pre_restore_copy(tmp_path):
    project, workspace, working, initial, candidate, source_bytes, _candidate_bytes = _workspace(tmp_path)
    saved = save_checkpoint(
        workspace, candidate, project_root=project,
        expected_current_sha256=_sha(source_bytes), actor="Researcher", reason="save",
        expected_workspace_version=1, expected_guide_version="guide-v1",
        explicit_record_ids=["record-00"],
        researcher_acknowledgements={"record-00": RESEARCHER_ACKNOWLEDGEMENT},
        decision_actors={"record-00": "Researcher"}, apply=True,
    )
    current_sha = _sha(working.read_bytes())
    result = restore_checkpoint(
        workspace, saved["backup_path"], project_root=project,
        expected_current_sha256=current_sha, actor="Researcher", reason="restore test",
        expected_workspace_version=2, expected_guide_version="guide-v1", apply=True,
    )
    assert result["result"] == "CHECKPOINT_RESTORED"
    assert working.read_bytes() == source_bytes
    assert (workspace / result["safety_backup_path"]).is_file()
    assert verify_audit_chain(workspace)["result"] == "PASS"
    assert initial.is_file()


def test_save_refuses_stale_checksum_and_invalid_immutable_fields(tmp_path):
    project, workspace, working, _initial, candidate, source_bytes, _candidate_bytes = _workspace(tmp_path)
    with pytest.raises(WorkspaceError, match="changed"):
        save_checkpoint(
            workspace, candidate, project_root=project,
            expected_current_sha256="stale", actor="Researcher", reason="test",
            expected_workspace_version=1, expected_guide_version="guide-v1", apply=True,
        )
    bad = json.loads(candidate.read_text().splitlines()[0])
    rows = [bad] + [json.loads(line) for line in candidate.read_text().splitlines()[1:]]
    rows[0]["text"] = "changed source text"
    candidate.write_bytes(_jsonl(rows))
    with pytest.raises(WorkspaceError, match="validation"):
        save_checkpoint(
            workspace, candidate, project_root=project,
            expected_current_sha256=_sha(source_bytes), actor="Researcher", reason="test",
            expected_workspace_version=1, expected_guide_version="guide-v1", apply=True,
        )
    assert working.read_bytes() == source_bytes


def test_restore_refuses_tampered_backup(tmp_path):
    project, workspace, working, initial, _candidate, source_bytes, _candidate_bytes = _workspace(tmp_path)
    initial.write_text("tampered\n")
    with pytest.raises(WorkspaceError, match="checksum"):
        restore_checkpoint(
            workspace, initial, project_root=project,
            expected_current_sha256=_sha(source_bytes), actor="Researcher", reason="test",
            expected_workspace_version=1, expected_guide_version="guide-v1", apply=True,
        )
    assert working.read_bytes() == source_bytes


def test_completed_calibration_record_requires_boolean_warning(tmp_path):
    project, workspace, working, _initial, candidate, source_bytes, _candidate_bytes = _workspace(tmp_path)
    rows = [json.loads(line) for line in candidate.read_text().splitlines()]
    rows[0]["public_warning"] = None
    candidate.write_bytes(_jsonl(rows))
    with pytest.raises(WorkspaceError, match="validation"):
        save_checkpoint(
            workspace, candidate, project_root=project,
            expected_current_sha256=_sha(source_bytes), actor="Researcher", reason="test",
            expected_workspace_version=1, expected_guide_version="guide-v1", apply=True,
        )
    assert working.read_bytes() == source_bytes


def test_batch_display_names_cover_all_technical_ids():
    assert annotation_batch_display_name("calibration_001") == "Annotation Batch 1"
    assert annotation_batch_display_name("main_001") == "Annotation Batch 2"
    assert annotation_batch_display_name("main_009") == "Annotation Batch 10"
    assert annotation_batch_display_name("final_001") == "Annotation Batch 11"


def test_human_decisions_fail_closed_and_only_accept_explicit_values():
    source = [_record("r1")]
    incomplete = [{"record_id": "r1", "actor": "R", "researcher_acknowledgement": RESEARCHER_ACKNOWLEDGEMENT}]
    with pytest.raises(WorkspaceError, match=HUMAN_DECISION_CODES["primary_intent"]):
        apply_human_decisions(source, incomplete, actor="R")
    decision = {
        "record_id": "r1", "actor": "R", "researcher_acknowledgement": RESEARCHER_ACKNOWLEDGEMENT,
        "primary_intent": "complaint", "public_warning": False, "opinions": [], "mark_completed": True,
    }
    edited, changed = apply_human_decisions(source, [decision], actor="R")
    assert changed == ["r1"]
    assert edited[0]["primary_intent"] == "complaint"
    assert edited[0]["opinions"] == []
    assert edited[0]["annotation_status"] == "completed"
    assert source[0]["annotation_status"] == "not_started"


def test_offset_resolution_requires_exact_unique_human_selection():
    assert exact_text_offsets("The app is bad", "app") == (4, 7)
    with pytest.raises(WorkspaceError, match="more than once"):
        exact_text_offsets("bad app, bad service", "bad")
    with pytest.raises(WorkspaceError, match="exact substring"):
        exact_text_offsets("The app is bad", "bad app")


def test_uniform_workspace_creation_is_dry_run_free_and_preserves_technical_id():
    assert annotation_batch_display_name("calibration_001") == "Annotation Batch 1"
