from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("activate_calibration_workspace", ROOT / "scripts/activate_calibration_workspace.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_authoritative_calibration_precheck_passes():
    records, metadata, approval = MODULE.precheck(ROOT)
    assert len(records) == len({row["record_id"] for row in records}) == 50
    assert metadata.batch_status == "generated"
    assert metadata.display_name == "Annotation Batch 1"
    assert metadata.workflow_role == "standard_manual_annotation_batch"
    assert approval["approval_status"] == "APPROVED"


def test_activation_creates_isolated_atomic_workspace(tmp_path):
    workspace = ROOT / ".pytest-calibration-workspace" / tmp_path.name
    try:
        progress = MODULE.activate(ROOT, workspace)
        assert progress["batch_status"] == "in_progress"
        assert progress["completed_record_count"] == 0
        assert progress["remaining_record_count"] == 50
        assert progress["display_name"] == "Annotation Batch 1"
        assert progress["workflow_role"] == "standard_manual_annotation_batch"
        assert progress["approved_membership_checksum"]
        assert progress["guide_version"]
        assert (workspace / "working_annotations.jsonl").is_file()
        assert len(list((workspace / "backups").glob("*.jsonl"))) == 1
        saved = json.loads((workspace / "progress_manifest.json").read_text())
        assert saved["audit_events"][0]["actor"] == "Rotondwa Mavhengani"
        assert saved["audit_events"][0]["reason"] == "Authorised 50-record calibration"
    finally:
        import shutil
        shutil.rmtree(ROOT / ".pytest-calibration-workspace", ignore_errors=True)


def test_activation_refuses_existing_workspace(tmp_path):
    workspace = tmp_path / "calibration_001"
    workspace.mkdir()
    try:
        MODULE.activate(ROOT, workspace)
    except FileExistsError:
        pass
    else:
        raise AssertionError("activation must refuse an existing workspace")
