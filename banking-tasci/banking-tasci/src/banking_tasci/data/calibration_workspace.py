"""Safe, auditable save and restore operations for a uniform annotation batch.

This module never creates annotation labels. It only validates and checkpoints
records supplied by a human annotator. ``calibration_001`` remains the technical
ID, while user-facing metadata calls it Annotation Batch 1. Mutations require
an explicit ``apply`` flag and an observed current-workspace checksum.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .annotation_batches import (
    BATCH_SPECS,
    PIPELINE_VERSION,
    annotation_batch_display_name,
    annotation_records_checksum,
)
from .new_pipeline_annotation_validator import read_raw_jsonl, validate_records
from . import new_pipeline_schema as schema


class WorkspaceError(ValueError):
    """Raised when a calibration workspace operation is unsafe or invalid."""


RESEARCHER_ACKNOWLEDGEMENT = "I confirm these are my own human annotation decisions."
HUMAN_DECISION_CODES = {
    "decision": "HUMAN_DECISION_REQUIRED",
    "acknowledgement": "MISSING_RESEARCHER_ACKNOWLEDGEMENT",
    "primary_intent": "MISSING_PRIMARY_INTENT",
    "public_warning": "MISSING_PUBLIC_WARNING_DECISION",
    "opinions": "MISSING_OPINION_DECISION",
    "target": "MISSING_TARGET_DECISION",
    "sentiment": "MISSING_SENTIMENT_DECISION",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in records
    )


def create_annotation_workspace(
    project_root: str | Path,
    technical_batch_id: str,
    *,
    actor: str,
    reason: str,
    guide_version: str,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Create an isolated working copy for any approved technical batch.

    The protected source, frozen IDs, and approved membership are read-only.
    Existing workspaces are never replaced. ``calibration_001`` is displayed
    as Annotation Batch 1 but retains its technical filename/ID.
    """
    root = Path(project_root).resolve()
    if not actor.strip() or not reason.strip() or not guide_version.strip():
        raise WorkspaceError("actor, reason, and guide version are required to open a batch")
    record_count, display_name = _batch_policy(technical_batch_id)
    annotation_root = root / "data/annotations/new_pipeline_v1_candidate_2"
    manifest_path = root / "artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json"
    frozen_dir = root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2"
    approval_path = root / "artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json"
    frozen_manifest_path = frozen_dir / "gold_sample_manifest.json"
    ids_path = frozen_dir / "gold_record_ids.jsonl"
    membership_path = frozen_dir / "approved_batch_membership.jsonl"
    source_path = annotation_root / "batches" / f"{technical_batch_id}.jsonl"
    package_path = annotation_root / "annotation_records.jsonl"
    expected_batch_sha = _sha256_file(source_path) if source_path.is_file() else ""
    if not expected_batch_sha:
        raise WorkspaceError(f"approved source file is missing for {technical_batch_id}")
    manifest = _load_json(manifest_path)
    frozen_manifest = _load_json(frozen_manifest_path)
    approval = _load_json(approval_path)
    approval_checksum = frozen_manifest.get("approval_checksum")
    if (
        approval.get("approval_status") != "APPROVED"
        or approval.get("candidate_number") != 2
        or not isinstance(approval_checksum, str)
        or _sha256_file(approval_path) != approval_checksum
    ):
        raise WorkspaceError("Candidate 2 approval checksum/status validation failed")
    membership_checksum = frozen_manifest.get("approved_batch_manifest", {}).get("membership_checksum")
    if not isinstance(membership_checksum, str) or _sha256_file(membership_path) != membership_checksum:
        raise WorkspaceError("approved batch membership checksum mismatch")
    if frozen_manifest.get("immutable_status") != "FROZEN" or frozen_manifest.get("candidate_number") != 2:
        raise WorkspaceError("Freeze Revision 2 Candidate 2 manifest is not valid and frozen")
    expected_ids_checksum = frozen_manifest.get("gold_id_checksum")
    if not isinstance(expected_ids_checksum, str) or _sha256_file(ids_path) != expected_ids_checksum:
        raise WorkspaceError("frozen gold-ID checksum mismatch")
    item = manifest.get("batches", {}).get(technical_batch_id)
    if not isinstance(item, dict) or item.get("candidate_number") not in (None, 2):
        raise WorkspaceError("Candidate 2 batch metadata is missing or mismatched")
    if manifest.get("checksums", {}).get(technical_batch_id) != expected_batch_sha:
        raise WorkspaceError("approved annotation batch checksum mismatch")
    expected_package_checksum = frozen_manifest.get("annotation_records_checksum")
    if not isinstance(expected_package_checksum, str) or _sha256_file(package_path) != expected_package_checksum:
        raise WorkspaceError("approved label-hidden package checksum differs from Freeze Revision 2")
    if int(item.get("record_count", -1)) != record_count:
        raise WorkspaceError("approved annotation batch record count mismatch")

    batch_rows = read_raw_jsonl(source_path)
    package_rows = read_raw_jsonl(package_path)
    package_by_id = {str(row.get("record_id")): row for row in package_rows}
    ids = [str(row.get("record_id", "")) for row in batch_rows]
    frozen_ids = {json.loads(line)["record_id"] for line in ids_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    approved_rows = [json.loads(line) for line in membership_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    approved_ids = {row["record_id"] for row in approved_rows if row.get("batch_id") == technical_batch_id}
    if len(batch_rows) != record_count or len(set(ids)) != record_count or set(ids) - frozen_ids or set(ids) != approved_ids:
        raise WorkspaceError("batch IDs do not match frozen Candidate 2 membership")
    for row in batch_rows:
        original = package_by_id.get(row["record_id"])
        if original is None or any(row.get(field) != original.get(field) for field in (
            "record_id", "source_record_id", "source", "region", "bank", "review_id", "thread_id",
            "conversation_id", "publish_year", "text", "previous_text", "context_available",
            "duplicate_group", "leakage_group", "privacy_status",
        )):
            raise WorkspaceError(f"immutable source mismatch for {row['record_id']}")
    validation = validate_records(batch_rows, package_rows, {technical_batch_id: set(ids)})
    if validation["result"] != "PASS":
        raise WorkspaceError("approved label-hidden source batch failed validation")

    if workspace is not None:
        target = Path(workspace)
    elif technical_batch_id == "calibration_001":
        # Reuse the already-open historical workspace path; never fork a
        # second operational workspace for Annotation Batch 1.
        target = annotation_root / "calibration_workspace" / technical_batch_id
    else:
        target = annotation_root / "annotation_workspaces" / technical_batch_id
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if target.exists():
        if not all((target / name).is_file() for name in ("working_annotations.jsonl", "progress_manifest.json", "immutable_reference.json")):
            raise FileExistsError(f"annotation workspace already exists: {target}")
        status = workspace_status(target, project_root=root)
        if status.get("technical_batch_id") != technical_batch_id or status.get("source_checksum") != expected_batch_sha:
            raise WorkspaceError("existing workspace does not match the requested approved batch")
        status["workspace_reused_read_only"] = True
        return status
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{technical_batch_id}.", dir=target.parent))
    try:
        (staging / "backups").mkdir()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        initial_backup = staging / "backups" / f"{technical_batch_id}_initial_{timestamp}.jsonl"
        source_bytes = source_path.read_bytes()
        _atomic_write(initial_backup, source_bytes)
        _atomic_write(staging / "working_annotations.jsonl", source_bytes)
        reference = {
            "technical_batch_id": technical_batch_id,
            "display_name": display_name,
            "workflow_role": "standard_manual_annotation_batch",
            "approved_source_path": str(source_path.relative_to(root)),
            "approved_source_sha256": expected_batch_sha,
            "approved_package_path": str(package_path.relative_to(root)),
            "approved_package_sha256": expected_package_checksum,
            "approved_membership_path": str(membership_path.relative_to(root)),
            "approved_membership_checksum": membership_checksum,
            "freeze_manifest_checksum": _sha256_file(frozen_manifest_path),
            "frozen_ids_checksum": expected_ids_checksum,
            "batch_manifest_path": str(manifest_path.relative_to(root)),
            "batch_manifest_checksum": _sha256_file(manifest_path),
            "source_checksum": expected_batch_sha,
            "candidate_number": 2,
            "pipeline_version": PIPELINE_VERSION,
            "record_count": record_count,
            "initial_backup_path": str(initial_backup.relative_to(staging)),
            "initial_backup_checksum": _sha256_file(initial_backup),
        }
        _atomic_write(staging / "immutable_reference.json", _json_bytes(reference))
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        progress = {
            "technical_batch_id": technical_batch_id,
            "display_name": display_name,
            "workflow_role": "standard_manual_annotation_batch",
            "record_count": record_count,
            "source_checksum": expected_batch_sha,
            "candidate_number": 2,
            "pipeline_version": PIPELINE_VERSION,
            "approved_membership_checksum": membership_checksum,
            "current_status": "in_progress",
            "batch_status": "in_progress",
            "completed_count": 0,
            "completed_record_count": 0,
            "validated_count": 0,
            "failed_validation_count": 0,
            "remaining_count": record_count,
            "remaining_record_count": record_count,
            "main_batches_unlocked": True,
            "guide_version": guide_version.strip(),
            "annotation_guide_version": guide_version.strip(),
            "workspace_version": 1,
            "failed_validation_count": 0,
            "last_updated_at": now,
            "last_updated_by": actor.strip(),
            "working_checksum": expected_batch_sha,
            "created_at": now,
            "opened_at": now,
            "backup_registry": [{"path": str(initial_backup.relative_to(staging)), "sha256": _sha256_file(initial_backup), "created_by": actor.strip(), "created_at": now}],
            "audit_events": [{
                "event": "annotation_batch_workspace_opened",
                "technical_batch_id": technical_batch_id,
                "display_name": display_name,
                "actor": actor.strip(),
                "reason": reason.strip(),
                "timestamp": now,
                "source_checksum": expected_batch_sha,
                "approved_membership_checksum": membership_checksum,
            }],
        }
        _atomic_write(staging / "progress_manifest.json", _json_bytes(progress))
        readme = (
            f"# {display_name}\n\nTechnical ID: `{technical_batch_id}`\n\n"
            f"Workflow: uniform human-only manual annotation.\n\n"
            f"Records: {record_count}. Current guide version: `{guide_version.strip()}`.\n\n"
            "Every annotation decision must be supplied and acknowledged by the researcher. "
            "No model, source metadata, sampling rules, or prior labels may assign gold labels.\n"
        )
        _atomic_write(staging / "README.md", readme.encode("utf-8"))
        os.replace(staging, target)
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return progress


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"cannot read workspace metadata: {path}") from exc
    if not isinstance(value, dict):
        raise WorkspaceError(f"workspace metadata must be a JSON object: {path}")
    return value


def _workspace_files(workspace: str | Path) -> tuple[Path, Path, Path, Path]:
    root = Path(workspace).resolve()
    working = root / "working_annotations.jsonl"
    progress = root / "progress_manifest.json"
    reference = root / "immutable_reference.json"
    if not root.is_dir() or not all(path.is_file() for path in (working, progress, reference)):
        raise WorkspaceError("annotation workspace must contain working_annotations.jsonl, progress_manifest.json, and immutable_reference.json")
    return root, working, progress, reference


def _batch_policy(batch_id: str) -> tuple[int, str]:
    for technical_id, _legacy_type, size in BATCH_SPECS:
        if technical_id == batch_id:
            return size, annotation_batch_display_name(batch_id)
    raise WorkspaceError(f"unknown technical batch ID: {batch_id}")


def _membership_checksum(project_root: str | Path, reference: dict[str, Any], progress: dict[str, Any]) -> str:
    recorded = reference.get("approved_membership_checksum") or progress.get("approved_membership_checksum")
    root = Path(project_root)
    manifest_path = root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_sample_manifest.json"
    membership_path = root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/approved_batch_membership.jsonl"
    if not manifest_path.is_file() or not membership_path.is_file():
        raise WorkspaceError("approved Candidate 2 membership evidence is missing")
    manifest = _load_json(manifest_path)
    expected = manifest.get("approved_batch_manifest", {}).get("membership_checksum")
    if not isinstance(expected, str) or _sha256_file(membership_path) != expected:
        raise WorkspaceError("approved membership checksum does not match Freeze Revision 2")
    if recorded is not None and recorded != expected:
        raise WorkspaceError("workspace approved membership checksum mismatch")
    return expected


def _verify_freeze_approval(project_root: str | Path, reference: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_root)
    frozen_dir = root / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2"
    manifest_path = frozen_dir / "gold_sample_manifest.json"
    ids_path = frozen_dir / "gold_record_ids.jsonl"
    approval_path = root / "artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json"
    if not all(path.is_file() for path in (manifest_path, ids_path, approval_path)):
        raise WorkspaceError("Candidate 2 frozen identity or approval evidence is missing")
    manifest = _load_json(manifest_path)
    if manifest.get("immutable_status") != "FROZEN" or manifest.get("candidate_number") != 2:
        raise WorkspaceError("Freeze Revision 2 is not the frozen Candidate 2 authority")
    ids_checksum = manifest.get("gold_id_checksum")
    approval_checksum = manifest.get("approval_checksum")
    if not isinstance(ids_checksum, str) or _sha256_file(ids_path) != ids_checksum:
        raise WorkspaceError("frozen Candidate 2 ID checksum mismatch")
    if not isinstance(approval_checksum, str) or _sha256_file(approval_path) != approval_checksum:
        raise WorkspaceError("Candidate 2 approval artifact checksum mismatch")
    approval = _load_json(approval_path)
    if approval.get("approval_status") != "APPROVED" or approval.get("candidate_number") != 2:
        raise WorkspaceError("Candidate 2 package approval is not valid")
    if reference.get("freeze_manifest_checksum") not in (None, _sha256_file(manifest_path)):
        raise WorkspaceError("workspace Freeze Revision 2 manifest checksum mismatch")
    if reference.get("frozen_ids_checksum") not in (None, ids_checksum):
        raise WorkspaceError("workspace frozen-ID checksum reference mismatch")
    return manifest


def _workspace_metadata(root: Path, progress: dict[str, Any], reference: dict[str, Any], project_root: str | Path) -> dict[str, Any]:
    frozen_manifest = _verify_freeze_approval(project_root, reference)
    batch_id = str(progress.get("technical_batch_id") or progress.get("batch_id") or "")
    expected_count, display_name = _batch_policy(batch_id)
    source_checksum = reference.get("approved_source_sha256")
    membership_checksum = _membership_checksum(project_root, reference, progress)
    membership_path = Path(project_root) / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/approved_batch_membership.jsonl"
    source_path = Path(reference.get("approved_source_path", ""))
    if not source_path.is_absolute():
        source_path = Path(project_root) / source_path
    if not source_path.is_file() or _sha256_file(source_path) != source_checksum:
        raise WorkspaceError("approved source batch checksum mismatch")
    package_value = reference.get("approved_package_path")
    if not package_value and batch_id == "calibration_001":
        package_value = "data/annotations/new_pipeline_v1_candidate_2/annotation_records.jsonl"
    package_path = Path(package_value or "")
    if not package_path.is_absolute():
        package_path = Path(project_root) / package_path
    package_checksum = reference.get("approved_package_sha256") or frozen_manifest.get("annotation_records_checksum")
    if not package_path.is_file() or not isinstance(package_checksum, str) or _sha256_file(package_path) != package_checksum:
        raise WorkspaceError("approved label-hidden package checksum mismatch")
    actual_membership = {
        json.loads(line)["record_id"]
        for line in membership_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("batch_id") == batch_id
    }
    source_rows = read_raw_jsonl(source_path)
    source_ids = {str(row.get("record_id")) for row in source_rows}
    frozen_ids_path = Path(project_root) / "artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/gold_record_ids.jsonl"
    frozen_ids = {json.loads(line)["record_id"] for line in frozen_ids_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    if len(source_rows) != expected_count or len(source_ids) != expected_count or source_ids != actual_membership or not source_ids.issubset(frozen_ids):
        raise WorkspaceError("approved source batch IDs do not match immutable frozen membership")
    if not isinstance(source_checksum, str) or not source_checksum or not isinstance(membership_checksum, str) or not membership_checksum:
        raise WorkspaceError("workspace must pin source and approved-membership checksums")
    expected_fields = {
        "technical_batch_id": batch_id,
        "display_name": display_name,
        "workflow_role": "standard_manual_annotation_batch",
        "record_count": expected_count,
        "source_checksum": source_checksum,
        "candidate_number": 2,
        "pipeline_version": PIPELINE_VERSION,
        "approved_membership_checksum": membership_checksum,
    }
    for key, expected in expected_fields.items():
        actual = progress.get(key)
        if actual is None and key in {"technical_batch_id", "display_name", "workflow_role", "source_checksum", "candidate_number", "pipeline_version", "approved_membership_checksum"}:
            # Legacy active workspace can be read safely but is not silently
            # upgraded or mutated; new batch workspaces must be fully uniform.
            if batch_id == "calibration_001":
                continue
        if actual is not None and actual != expected:
            raise WorkspaceError(f"workspace metadata mismatch for {key}")
    if reference.get("record_count") != expected_count:
        raise WorkspaceError("immutable reference record count does not match the approved technical batch")
    return expected_fields


def _load_approved_source(reference: dict[str, Any], project_root: str | Path, *, verify_checksum: bool = True) -> tuple[list[dict], Path]:
    source_value = reference.get("approved_source_path")
    if not isinstance(source_value, str) or not source_value:
        raise WorkspaceError("immutable reference has no approved source path")
    source = Path(source_value)
    if not source.is_absolute():
        source = Path(project_root) / source
    source = source.resolve()
    if not source.is_file():
        raise WorkspaceError("approved calibration source is missing")
    expected = reference.get("approved_source_sha256")
    if not isinstance(expected, str) or (verify_checksum and _sha256_file(source) != expected):
        raise WorkspaceError("approved calibration source checksum mismatch")
    rows = read_raw_jsonl(source)
    if len(rows) != reference.get("record_count"):
        raise WorkspaceError("approved annotation batch source record count mismatch")
    return rows, source


def _load_source_package(reference: dict[str, Any], project_root: str | Path) -> list[dict[str, Any]]:
    package_value = reference.get("approved_package_path")
    if not package_value and reference.get("technical_batch_id", reference.get("batch_id")) == "calibration_001":
        package_value = "data/annotations/new_pipeline_v1_candidate_2/annotation_records.jsonl"
    if not isinstance(package_value, str) or not package_value:
        return []
    package = Path(package_value)
    if not package.is_absolute():
        package = Path(project_root) / package
    package = package.resolve()
    expected = reference.get("approved_package_sha256") or reference.get("package_sha256")
    if expected is None and package.is_file():
        expected = _sha256_file(package)
    if not package.is_file() or not isinstance(expected, str) or _sha256_file(package) != expected:
        raise WorkspaceError("approved full annotation package checksum mismatch")
    return read_raw_jsonl(package)


def _validate_checkpoint(
    rows: list[dict], source_rows: list[dict], *, batch_id: str,
    source_package: list[dict[str, Any]] | None = None,
    completed_gold: bool = False,
) -> None:
    expected_record_fields = set(schema.RECORD_FIELDS)
    expected_opinion_fields = set(schema.OPINION_FIELDS)
    for row in rows:
        row_fields = set(row)
        if not expected_record_fields.issubset(row_fields) or row_fields - expected_record_fields - {"source_record_id"}:
            raise WorkspaceError(f"annotation validation: record {row.get('record_id')} has missing or unapproved extra fields")
        if not isinstance(row.get("opinions"), list) or any(
            not isinstance(opinion, dict) or set(opinion) != expected_opinion_fields
            for opinion in row.get("opinions", [])
        ):
            raise WorkspaceError(f"annotation validation: record {row.get('record_id')} has non-canonical opinion fields")
    ids = [str(row.get("record_id", "")) for row in rows]
    source_ids = [str(row.get("record_id", "")) for row in source_rows]
    if len(ids) != len(source_ids) or len(set(ids)) != len(ids) or set(ids) != set(source_ids):
        raise WorkspaceError("checkpoint must contain every approved batch record exactly once")
    membership = {batch_id: set(source_ids)}
    report = validate_records(rows, source_package or source_rows, membership, completed_gold=False)
    if completed_gold:
        gold_report = validate_records(rows, source_rows, membership, completed_gold=True)
        if gold_report["result"] != "PASS":
            report = gold_report
    if report["result"] != "PASS":
        codes = ", ".join(sorted(report["errors_by_code"]))
        raise WorkspaceError(f"checkpoint failed annotation/provenance validation: {codes}")


def _changed_annotation_ids(current: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> set[str]:
    editable = ("primary_intent", "public_warning", "opinions", "annotation_notes", "annotation_status")
    by_id = {str(row.get("record_id")): row for row in current}
    return {
        str(row.get("record_id")) for row in candidate
        if any(row.get(field) != by_id.get(str(row.get("record_id")), {}).get(field) for field in editable)
    }


def _require_explicit_human_decisions(
    current: list[dict[str, Any]], candidate: list[dict[str, Any]], *,
    explicit_record_ids: list[str] | None,
    researcher_acknowledgements: dict[str, str] | None,
    decision_actors: dict[str, str] | None,
    actor: str,
) -> set[str]:
    changed = _changed_annotation_ids(current, candidate)
    explicit = set(explicit_record_ids or [])
    acknowledgements = researcher_acknowledgements or {}
    actors = decision_actors or {}
    if not changed or explicit != changed or set(acknowledgements) != changed or set(actors) != changed:
        raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: identify exactly the records with explicit human annotation decisions")
    rows_by_id = {str(row.get("record_id")): row for row in candidate}
    for record_id in sorted(changed):
        ack = acknowledgements.get(record_id)
        if ack != RESEARCHER_ACKNOWLEDGEMENT:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['acknowledgement']}: acknowledgement required for {record_id}")
        if actors.get(record_id) != actor:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['acknowledgement']}: explicit decision actor mismatch for {record_id}")
        row = rows_by_id[record_id]
        row_fields = set(row)
        if not set(schema.RECORD_FIELDS).issubset(row_fields) or row_fields - set(schema.RECORD_FIELDS) - {"source_record_id"}:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: record {record_id} contains missing/extra fields")
        if "primary_intent" not in row or row.get("primary_intent") is None:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['primary_intent']}: explicit intent required for {record_id}")
        if "public_warning" not in row or not isinstance(row.get("public_warning"), bool):
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['public_warning']}: explicit Boolean required for {record_id}")
        if "opinions" not in row or not isinstance(row.get("opinions"), list):
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['opinions']}: explicit opinion list required for {record_id}")
        for opinion_index, opinion in enumerate(row["opinions"]):
            if not isinstance(opinion, dict):
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['opinions']}: each opinion must be an explicit object")
            if set(opinion) != set(schema.OPINION_FIELDS):
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: opinion {opinion_index} on {record_id} contains missing/extra fields")
            if "target" not in opinion or "target_type" not in opinion:
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['target']}: target decision required for {record_id}")
            required = ("target", "target_type", "entity", "attribute", "category", "opinion_phrase", "sentiment", "annotation_notes")
            if any(name not in opinion for name in required):
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: opinion {opinion_index} on {record_id} lacks explicit required decisions")
            if opinion.get("sentiment") is None:
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['sentiment']}: explicit opinion sentiment required for {record_id}")
    return changed


def exact_text_offsets(record_text: str, researcher_selected_text: str) -> tuple[int, int]:
    """Resolve offsets only for an exact, researcher-supplied unique substring."""
    if not isinstance(record_text, str) or not isinstance(researcher_selected_text, str) or not researcher_selected_text:
        raise WorkspaceError("an exact non-empty researcher-selected substring is required")
    first = record_text.find(researcher_selected_text)
    if first < 0:
        raise WorkspaceError("researcher-selected text is not an exact substring of the source record")
    if record_text.find(researcher_selected_text, first + 1) >= 0:
        raise WorkspaceError("researcher-selected text occurs more than once; explicit human offsets are required")
    return first, first + len(researcher_selected_text)


def apply_human_decisions(
    source_rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    actor: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply only explicit record decisions; compute offsets from exact selections.

    This helper neither chooses labels nor guesses annotation completeness.
    ``mark_completed`` and researcher acknowledgement must be explicit per row.
    """
    if not actor.strip():
        raise WorkspaceError("an explicit annotation actor is required")
    by_id = {str(row.get("record_id")): dict(row) for row in source_rows}
    if len(by_id) != len(source_rows):
        raise WorkspaceError("approved source contains duplicate record IDs")
    updated = {rid: dict(row) for rid, row in by_id.items()}
    changed_ids: list[str] = []
    seen_decisions: set[str] = set()
    for decision in decisions:
        record_id = decision.get("record_id")
        if not isinstance(record_id, str) or record_id not in by_id:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: decision must name an approved record_id")
        if record_id in seen_decisions:
            raise WorkspaceError(f"duplicate human decision for record {record_id}")
        seen_decisions.add(record_id)
        if decision.get("actor") != actor:
            raise WorkspaceError("decision actor must match the workspace operator")
        if decision.get("researcher_acknowledgement") != RESEARCHER_ACKNOWLEDGEMENT:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['acknowledgement']}: exact researcher acknowledgement required")
        for name in ("primary_intent", "public_warning", "opinions", "mark_completed"):
            if name not in decision:
                code = {"primary_intent": HUMAN_DECISION_CODES["primary_intent"], "public_warning": HUMAN_DECISION_CODES["public_warning"], "opinions": HUMAN_DECISION_CODES["opinions"]}.get(name, HUMAN_DECISION_CODES["decision"])
                raise WorkspaceError(f"{code}: explicit {name} decision required for {record_id}")
        if not isinstance(decision["public_warning"], bool):
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['public_warning']}: explicit Boolean required for {record_id}")
        if not isinstance(decision["opinions"], list):
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['opinions']}: explicit list required for {record_id}")
        if not isinstance(decision["mark_completed"], bool):
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: explicit Boolean completion decision required for {record_id}")
        row = updated[record_id]
        if not isinstance(decision["mark_completed"], bool):
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: explicit Boolean completion decision required for {record_id}")
        if decision["primary_intent"] is None:
            raise WorkspaceError(f"{HUMAN_DECISION_CODES['primary_intent']}: non-null intent required for {record_id}")
        row["primary_intent"] = decision["primary_intent"]
        row["public_warning"] = decision["public_warning"]
        opinions: list[dict[str, Any]] = []
        for supplied in decision["opinions"]:
            if not isinstance(supplied, dict):
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['opinions']}: each opinion decision must be an object")
            if set(supplied) != set(schema.OPINION_FIELDS):
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['decision']}: opinion contains missing or extra fields")
            required = ("target", "target_type", "entity", "attribute", "category", "opinion_phrase", "sentiment", "annotation_notes")
            absent = [name for name in required if name not in supplied]
            if absent:
                code = HUMAN_DECISION_CODES["target"] if "target" in absent or "target_type" in absent else HUMAN_DECISION_CODES["sentiment"] if "sentiment" in absent else HUMAN_DECISION_CODES["decision"]
                raise WorkspaceError(f"{code}: explicit opinion fields missing for {record_id}")
            if supplied["sentiment"] is None:
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['sentiment']}: sentiment is required for {record_id}")
            opinion = dict(supplied)
            if opinion["target_type"] == "implicit":
                if opinion["target"] is not None:
                    raise WorkspaceError(f"{HUMAN_DECISION_CODES['target']}: implicit target must be explicitly null")
                opinion["target_start"] = None
                opinion["target_end"] = None
            elif opinion["target_type"] == "explicit":
                if not isinstance(opinion["target"], str):
                    raise WorkspaceError(f"{HUMAN_DECISION_CODES['target']}: explicit target text required")
                if "target_start" in opinion or "target_end" in opinion:
                    if not isinstance(opinion.get("target_start"), int) or not isinstance(opinion.get("target_end"), int) or row["text"][opinion["target_start"]:opinion["target_end"]] != opinion["target"]:
                        raise WorkspaceError(f"{HUMAN_DECISION_CODES['target']}: explicit human offsets must exactly match the selected target")
                else:
                    opinion["target_start"], opinion["target_end"] = exact_text_offsets(row["text"], opinion["target"])
            else:
                raise WorkspaceError(f"{HUMAN_DECISION_CODES['target']}: target_type must be explicit or implicit")
            phrase = opinion["opinion_phrase"]
            if phrase is None:
                opinion["opinion_start"] = None
                opinion["opinion_end"] = None
            elif isinstance(phrase, str):
                if "opinion_start" in opinion or "opinion_end" in opinion:
                    if not isinstance(opinion.get("opinion_start"), int) or not isinstance(opinion.get("opinion_end"), int) or row["text"][opinion["opinion_start"]:opinion["opinion_end"]] != phrase:
                        raise WorkspaceError("human opinion phrase offsets must exactly match the selected phrase")
                else:
                    opinion["opinion_start"], opinion["opinion_end"] = exact_text_offsets(row["text"], phrase)
            else:
                raise WorkspaceError("opinion_phrase must be an exact string selection or explicit null")
            opinions.append(opinion)
        row["opinions"] = opinions
        row["annotation_status"] = "completed" if decision["mark_completed"] else "in_progress"
        parsed = schema.record_from_dict(row)
        errors = [issue.rule_id for issue in schema.validate_record(parsed) if issue.severity == "error"]
        if errors:
            raise WorkspaceError(f"human decisions for {record_id} fail schema validation: {', '.join(errors)}")
        changed_ids.append(record_id)
    ordered = [updated[str(row["record_id"])] for row in source_rows]
    return ordered, changed_ids


def _registered_backups(root: Path, reference: dict[str, Any], progress: dict[str, Any], project_root: str | Path) -> dict[str, str]:
    backups: dict[str, str] = {}
    initial_path = reference.get("initial_backup_path") or reference.get("backup_path")
    initial_sha = reference.get("initial_backup_checksum") or reference.get("backup_sha256")
    if isinstance(initial_path, str) and isinstance(initial_sha, str):
        path = Path(initial_path)
        if not path.is_absolute():
            path = (root if reference.get("initial_backup_path") else Path(project_root)) / path
        backups[str(path.resolve())] = initial_sha
    for entry in progress.get("backup_registry", []):
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) and isinstance(entry.get("sha256"), str):
            path = Path(entry["path"])
            if not path.is_absolute():
                path = root / path
            backups[str(path.resolve())] = entry["sha256"]
    return backups


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError as exc:
        raise WorkspaceError("backup paths must remain inside the calibration workspace") from exc


def _event(progress: dict[str, Any], *, action: str, actor: str, reason: str, old_sha: str, new_sha: str, backup_path: str | None, backup_sha: str | None, completed: int, record_ids: list[str] | None = None) -> dict[str, Any]:
    previous = progress.get("audit_events", [])
    event = {
        "event": action,
        "actor": actor.strip(),
        "reason": reason.strip(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "previous_working_sha256": old_sha,
        "new_working_sha256": new_sha,
        "backup_path": backup_path,
        "backup_sha256": backup_sha,
        "completed_record_count": completed,
        "record_ids": sorted(record_ids or []),
    }
    prior_hash = None
    if previous:
        prior = previous[-1]
        prior_hash = prior.get("event_sha256")
        if not prior_hash:
            prior_hash = _sha256_bytes(json.dumps(prior, sort_keys=True, separators=(",", ":")).encode())
    event["previous_event_sha256"] = prior_hash
    event["event_sha256"] = _sha256_bytes(json.dumps(event, sort_keys=True, separators=(",", ":")).encode())
    return event


def _check_mutable_state(
    progress: dict[str, Any], reference: dict[str, Any], *,
    project_root: str | Path,
    expected_current_sha256: str, current_sha256: str, actor: str, reason: str,
    expected_workspace_version: int | None,
) -> dict[str, Any]:
    metadata = _workspace_metadata(Path(), progress, reference, project_root)
    if progress.get("batch_status") != "in_progress":
        raise WorkspaceError(f"only an in-progress {metadata['display_name']} can be changed")
    if not actor.strip() or not reason.strip():
        raise WorkspaceError("an explicit actor and reason are required for every mutation")
    if current_sha256 != expected_current_sha256:
        raise WorkspaceError("current working checksum changed; re-read it before retrying")
    current_version = progress.get("workspace_version", 1)
    if expected_workspace_version is None:
        raise WorkspaceError("expected workspace version is required for every mutation")
    if expected_workspace_version != current_version:
        raise WorkspaceError("workspace version changed; re-read status before retrying")
    if metadata["record_count"] != reference.get("record_count"):
        raise WorkspaceError("workspace and approved batch record counts differ")
    return metadata


def save_checkpoint(
    workspace: str | Path,
    candidate_path: str | Path,
    *,
    project_root: str | Path,
    expected_current_sha256: str,
    actor: str,
    reason: str,
    expected_workspace_version: int | None = None,
    expected_guide_version: str | None = None,
    explicit_record_ids: list[str] | None = None,
    researcher_acknowledgements: dict[str, str] | None = None,
    decision_actors: dict[str, str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Validate a human-edited candidate and atomically checkpoint it.

    Dry-run is the default. On apply, the current file is preserved in a unique
    backup before the validated candidate replaces the working copy.
    """
    root, working, progress_path, reference_path = _workspace_files(workspace)
    progress = _load_json(progress_path)
    reference = _load_json(reference_path)
    current_bytes = working.read_bytes()
    current_sha = _sha256_bytes(current_bytes)
    batch_metadata = _check_mutable_state(
        progress, reference, project_root=project_root, expected_current_sha256=expected_current_sha256,
        current_sha256=current_sha, actor=actor, reason=reason,
        expected_workspace_version=expected_workspace_version,
    )
    guide_version = progress.get("guide_version") or progress.get("annotation_guide_version")
    if expected_guide_version is not None and expected_guide_version != guide_version:
        raise WorkspaceError("guide version changed; re-read status before retrying")
    if not guide_version or expected_guide_version is None:
        raise WorkspaceError("expected current guide version is required for annotation writes")
    candidate = Path(candidate_path).resolve()
    if not candidate.is_file():
        raise WorkspaceError("candidate submission file does not exist")
    candidate_bytes = candidate.read_bytes()
    try:
        candidate_rows = read_raw_jsonl(candidate)
        current_rows = read_raw_jsonl(working)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("candidate or working file is not valid JSONL") from exc
    source_rows, _ = _load_approved_source(reference, project_root)
    source_package = _load_source_package(reference, project_root)
    _validate_checkpoint(
        candidate_rows, source_rows,
        batch_id=batch_metadata["technical_batch_id"],
        source_package=source_package or source_rows,
    )
    changed_ids = _require_explicit_human_decisions(
        current_rows, candidate_rows,
        explicit_record_ids=explicit_record_ids,
        researcher_acknowledgements=researcher_acknowledgements,
        decision_actors=decision_actors,
        actor=actor,
    )
    new_sha = _sha256_bytes(candidate_bytes)
    completed = sum(row.get("annotation_status") == "completed" for row in candidate_rows)
    if not apply:
        return {
            "result": "DRY_RUN_PASS", "action": "save_checkpoint", "writes": 0,
            "technical_batch_id": batch_metadata["technical_batch_id"],
            "display_name": batch_metadata["display_name"],
            "workspace_version": progress.get("workspace_version", 1),
            "guide_version": guide_version,
            "current_sha256": current_sha, "candidate_sha256": new_sha,
            "candidate_records": len(candidate_rows), "completed_records": completed,
            "explicit_record_ids": sorted(changed_ids),
            "backup_required": True,
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / "backups" / f"working_annotations_{timestamp}_{current_sha[:12]}.jsonl"
    if backup.exists():
        raise WorkspaceError("generated backup path already exists")
    _atomic_write(backup, current_bytes)
    backup_sha = _sha256_file(backup)
    if backup_sha != current_sha:
        raise WorkspaceError("backup verification failed; working copy was not replaced")
    _atomic_write(working, candidate_bytes)
    progress.setdefault("backup_registry", []).append({"path": _relative(backup, root), "sha256": backup_sha, "created_by": actor.strip(), "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    progress["completed_record_count"] = completed
    progress["completed_count"] = completed
    progress["validated_count"] = completed
    progress["remaining_record_count"] = len(candidate_rows) - completed
    progress["working_checksum"] = new_sha
    progress.update(batch_metadata)
    progress["current_status"] = progress["batch_status"]
    progress["last_updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    progress["last_updated_by"] = actor.strip()
    progress["workspace_version"] = progress.get("workspace_version", 1) + 1
    progress["completed_record_count"] = completed
    progress["last_updated_by"] = actor.strip()
    progress.setdefault("audit_events", []).append(_event(
        progress, action="annotation_checkpoint_saved", actor=actor, reason=reason,
        old_sha=current_sha, new_sha=new_sha, backup_path=_relative(backup, root),
        backup_sha=backup_sha, completed=completed, record_ids=sorted(changed_ids),
    ))
    _atomic_write(progress_path, _json_bytes(progress))
    return {
        "result": "CHECKPOINT_SAVED", "action": "save_checkpoint", "writes": 1,
        "workspace_version": progress["workspace_version"],
        "guide_version": guide_version,
        "current_sha256": new_sha, "backup_path": _relative(backup, root),
        "backup_sha256": backup_sha, "completed_records": completed,
        "remaining_records": len(candidate_rows) - completed,
    }


def restore_checkpoint(
    workspace: str | Path,
    backup_path: str | Path,
    *,
    project_root: str | Path,
    expected_current_sha256: str,
    actor: str,
    reason: str,
    expected_workspace_version: int | None = None,
    expected_guide_version: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Restore a previously registered, checksum-verified checkpoint backup."""
    root, working, progress_path, reference_path = _workspace_files(workspace)
    progress = _load_json(progress_path)
    reference = _load_json(reference_path)
    current_bytes = working.read_bytes()
    current_sha = _sha256_bytes(current_bytes)
    batch_metadata = _check_mutable_state(
        progress, reference, project_root=project_root, expected_current_sha256=expected_current_sha256,
        current_sha256=current_sha, actor=actor, reason=reason,
        expected_workspace_version=expected_workspace_version,
    )
    guide_version = progress.get("guide_version") or progress.get("annotation_guide_version")
    if expected_guide_version is not None and expected_guide_version != guide_version:
        raise WorkspaceError("guide version changed; re-read status before retrying")
    if not guide_version or expected_guide_version is None:
        raise WorkspaceError("expected current guide version is required for restore")
    source_rows, _ = _load_approved_source(reference, project_root)
    source_package = _load_source_package(reference, project_root)
    requested = Path(backup_path)
    if not requested.is_absolute():
        workspace_candidate = root / requested
        project_candidate = Path(project_root) / requested
        requested = workspace_candidate if workspace_candidate.is_file() else project_candidate
    requested = requested.resolve()
    registered = _registered_backups(root, reference, progress, project_root)
    expected_backup_sha = registered.get(str(requested))
    if expected_backup_sha is None:
        raise WorkspaceError("restore source is not a registered workspace backup")
    if not requested.is_file() or _sha256_file(requested) != expected_backup_sha:
        raise WorkspaceError("registered backup is missing or its checksum has changed")
    backup_bytes = requested.read_bytes()
    try:
        backup_rows = read_raw_jsonl(requested)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("registered backup is not valid JSONL") from exc
    _validate_checkpoint(
        backup_rows, source_rows,
        batch_id=batch_metadata["technical_batch_id"],
        source_package=source_package or source_rows,
    )
    restored_sha = _sha256_bytes(backup_bytes)
    completed = sum(row.get("annotation_status") == "completed" for row in backup_rows)
    if not apply:
        return {
            "result": "DRY_RUN_PASS", "action": "restore_checkpoint", "writes": 0,
            "technical_batch_id": batch_metadata["technical_batch_id"],
            "display_name": batch_metadata["display_name"],
            "workspace_version": progress.get("workspace_version", 1),
            "guide_version": guide_version,
            "current_sha256": current_sha, "restore_sha256": restored_sha,
            "restore_records": len(backup_rows), "completed_records": completed,
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safety_backup = root / "backups" / f"working_annotations_before_restore_{timestamp}_{current_sha[:12]}.jsonl"
    if safety_backup.exists():
        raise WorkspaceError("generated safety backup path already exists")
    _atomic_write(safety_backup, current_bytes)
    safety_sha = _sha256_file(safety_backup)
    if safety_sha != current_sha:
        raise WorkspaceError("pre-restore safety backup verification failed")
    _atomic_write(working, backup_bytes)
    progress.setdefault("backup_registry", []).append({"path": _relative(safety_backup, root), "sha256": safety_sha, "created_by": actor.strip(), "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    progress["completed_record_count"] = completed
    progress["completed_count"] = completed
    progress["validated_count"] = completed
    progress["remaining_record_count"] = len(backup_rows) - completed
    progress["working_checksum"] = restored_sha
    progress.update(batch_metadata)
    progress["current_status"] = progress["batch_status"]
    progress["last_updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    progress["last_updated_by"] = actor.strip()
    progress["workspace_version"] = progress.get("workspace_version", 1) + 1
    progress.setdefault("audit_events", []).append(_event(
        progress, action="annotation_checkpoint_restored", actor=actor, reason=reason,
        old_sha=current_sha, new_sha=restored_sha, backup_path=_relative(safety_backup, root),
        backup_sha=safety_sha, completed=completed,
    ))
    _atomic_write(progress_path, _json_bytes(progress))
    return {
        "result": "CHECKPOINT_RESTORED", "action": "restore_checkpoint", "writes": 1,
        "workspace_version": progress["workspace_version"],
        "guide_version": guide_version,
        "current_sha256": restored_sha, "safety_backup_path": _relative(safety_backup, root),
        "safety_backup_sha256": safety_sha, "completed_records": completed,
        "remaining_records": len(backup_rows) - completed,
    }


def verify_audit_chain(workspace: str | Path) -> dict[str, Any]:
    """Verify event hashes and predecessor links added by this utility."""
    root, _working, progress_path, _reference = _workspace_files(workspace)
    progress = _load_json(progress_path)
    events = progress.get("audit_events", [])
    previous_hash: str | None = None
    verified = 0
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise WorkspaceError(f"invalid audit event at index {index}")
        event_hash = event.get("event_sha256")
        if event_hash is None:
            # Existing activation events predate hash-chained operations.
            previous_hash = _sha256_bytes(json.dumps(event, sort_keys=True, separators=(",", ":")).encode())
            continue
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        expected_hash = _sha256_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
        if event_hash != expected_hash or event.get("previous_event_sha256") != previous_hash:
            raise WorkspaceError(f"audit event chain mismatch at index {index}")
        previous_hash = event_hash
        verified += 1
    return {"result": "PASS", "events": len(events), "hash_chained_events_verified": verified}


def workspace_status(workspace: str | Path, *, project_root: str | Path) -> dict[str, Any]:
    root, working, progress_path, reference_path = _workspace_files(workspace)
    progress = _load_json(progress_path)
    reference = _load_json(reference_path)
    batch_metadata = _workspace_metadata(root, progress, reference, project_root)
    rows = read_raw_jsonl(working)
    if len(rows) != reference.get("record_count"):
        raise WorkspaceError("working calibration record count does not match immutable reference")
    return {
        **batch_metadata,
        "current_status": progress.get("batch_status"),
        "workspace_version": progress.get("workspace_version", 1),
        "guide_version": progress.get("guide_version") or progress.get("annotation_guide_version"),
        "last_updated_at": progress.get("last_updated_at") or progress.get("opened_at"),
        "last_updated_by": progress.get("last_updated_by") or (progress.get("audit_events") or [{}])[-1].get("actor"),
        "record_count": len(rows),
        "completed_record_count": sum(row.get("annotation_status") == "completed" for row in rows),
        "completed_count": sum(row.get("annotation_status") == "completed" for row in rows),
        "validated_count": progress.get("validated_count", 0),
        "failed_validation_count": progress.get("failed_validation_count", 0),
        "remaining_count": len(rows) - sum(row.get("annotation_status") == "completed" for row in rows),
        "working_sha256": _sha256_file(working),
        "manifest_working_sha256_matches": _sha256_file(working) == progress.get("working_checksum"),
        "legacy_main_batches_unlocked_flag_ignored": progress.get("main_batches_unlocked"),
        "audit_events": len(progress.get("audit_events", [])),
        "registered_backups": len(_registered_backups(root, reference, progress, project_root)),
        "audit_chain": verify_audit_chain(root),
    }
