#!/usr/bin/env python3
"""Prepare a corrected candidate-2 package; dry-run by default.

This command reuses candidate 1's selected canonical IDs. It never resamples,
approves, freezes, annotates, or changes candidate 1. Candidate 2 is written
only when ``--write`` is explicit, and only beneath its dedicated data,
manifest, and report roots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from banking_tasci.data.annotation_batches import (  # noqa: E402
    BATCH_SPECS,
    DEFAULT_SEED,
    assign_batches,
    build_batch_metadata,
    build_combined_batch_manifest,
)
from banking_tasci.data.annotation_package_review import load_jsonl_dicts  # noqa: E402
from banking_tasci.data.candidate_package_diff import compare_candidate_packages  # noqa: E402
from banking_tasci.data.candidate_package_v2 import (  # noqa: E402
    build_candidate2_package,
    build_review_metadata_map,
    build_v2_rule_map,
)
from banking_tasci.data.manifest import NO_COMMIT_MARKER, git_commit, sha256_file  # noqa: E402

DEFAULT_CANDIDATE1 = ROOT / "data/annotations/new_pipeline_v1"
DEFAULT_CANDIDATE2 = ROOT / "data/annotations/new_pipeline_v1_candidate_2"
DEFAULT_MANIFEST1 = ROOT / "artifacts/manifests/new_pipeline_v1"
DEFAULT_MANIFEST2 = ROOT / "artifacts/manifests/new_pipeline_v1/candidate_2"
DEFAULT_REPORT2 = ROOT / "artifacts/reports/new_pipeline_v1/candidate_2"
DEFAULT_SA_DATA = ROOT / "data/processed/new_pipeline_v1/south_africa_candidates_v2.parquet"
DEFAULT_SA_PARENT = ROOT / "data/interim/south_africa_prepared.parquet"
DEFAULT_INTL_DATA = ROOT / "data/interim/prepared.csv"
DEFAULT_RAW_REVIEWS = ROOT / "bank_reviews3.csv"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate1-root", type=Path, default=DEFAULT_CANDIDATE1)
    parser.add_argument("--candidate2-root", type=Path, default=DEFAULT_CANDIDATE2)
    parser.add_argument("--candidate1-manifests", type=Path, default=DEFAULT_MANIFEST1)
    parser.add_argument("--candidate2-manifests", type=Path, default=DEFAULT_MANIFEST2)
    parser.add_argument("--candidate2-reports", type=Path, default=DEFAULT_REPORT2)
    parser.add_argument("--sa-source", type=Path, default=DEFAULT_SA_DATA)
    parser.add_argument("--sa-parent-source", type=Path, default=DEFAULT_SA_PARENT)
    parser.add_argument("--international-source", type=Path, default=DEFAULT_INTL_DATA)
    parser.add_argument("--raw-reviews", type=Path, default=DEFAULT_RAW_REVIEWS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--write", action="store_true", help="write candidate-2 outputs (default is dry-run)")
    parser.add_argument("--overwrite", action="store_true", help="replace only existing candidate-2 outputs")
    return parser


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _read_verified_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "VERIFIED":
        raise ValueError(f"source manifest is not VERIFIED: {path}")
    return data


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def _stage_directory(target: Path, files: dict[str, bytes]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging.", dir=target.parent))
    for relative, payload in files.items():
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return staging


def _install_transaction(staged: dict[Path, Path], *, overwrite: bool) -> None:
    existing = [target for target in staged if target.exists()]
    if existing and not overwrite:
        raise FileExistsError("candidate-2 output exists; pass --overwrite to replace these candidate-2 paths: " + ", ".join(map(str, existing)))
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for target in existing:
            backup = target.with_name(f".{target.name}.backup.{os.getpid()}")
            if backup.exists():
                raise FileExistsError(f"candidate-2 backup path already exists: {backup}")
            os.replace(target, backup)
            backups[target] = backup
        for target, staging in staged.items():
            os.replace(staging, target)
            installed.append(target)
    except Exception:
        for target in reversed(installed):
            shutil.rmtree(target, ignore_errors=True)
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise
    else:
        for backup in backups.values():
            shutil.rmtree(backup, ignore_errors=True)


def _prepare(args: argparse.Namespace) -> tuple[dict[Path, dict[str, bytes]], dict[str, Any]]:
    import pandas as pd

    candidate1_root = _resolve(args.candidate1_root)
    candidate2_root = _resolve(args.candidate2_root)
    manifest1_root = _resolve(args.candidate1_manifests)
    manifest2_root = _resolve(args.candidate2_manifests)
    report2_root = _resolve(args.candidate2_reports)
    protected_candidate1 = DEFAULT_CANDIDATE1.resolve()
    if candidate2_root.resolve() == protected_candidate1 or protected_candidate1 in candidate2_root.resolve().parents:
        raise ValueError("candidate-2 output must not be inside or equal to candidate-1 data paths")
    if candidate2_root.resolve() != DEFAULT_CANDIDATE2.resolve():
        raise ValueError(f"candidate-2 data output is fixed to {DEFAULT_CANDIDATE2}")
    if manifest2_root.resolve() != DEFAULT_MANIFEST2.resolve():
        raise ValueError(f"candidate-2 manifest output is fixed to {DEFAULT_MANIFEST2}")
    if report2_root.resolve() != DEFAULT_REPORT2.resolve():
        raise ValueError(f"candidate-2 report output is fixed to {DEFAULT_REPORT2}")

    plan_path = candidate1_root / "gold_sample_plan.jsonl"
    annotation_path = candidate1_root / "annotation_records.jsonl"
    candidate1_batch_dir = candidate1_root / "batches"
    candidate1_plan_manifest = manifest1_root / "gold_sample_plan_manifest.json"
    candidate1_annotation_manifest = manifest1_root / "annotation_package_manifest.json"
    candidate1_batch_manifest_path = manifest1_root / "annotation_batch_manifest.json"
    candidate1_review_markdown = ROOT / "artifacts/reports/new_pipeline_v1/annotation_package_review.md"
    candidate1_review_json = ROOT / "artifacts/reports/new_pipeline_v1/annotation_package_review.json"
    sa_manifest_path = manifest1_root / "south_africa_candidates_v2_source_manifest.json"
    sa_parent_manifest_path = manifest1_root / "south_africa_source_manifest.json"
    intl_manifest_path = manifest1_root / "international_source_manifest.json"
    required = [plan_path, annotation_path, candidate1_plan_manifest, candidate1_annotation_manifest,
                candidate1_batch_manifest_path, sa_manifest_path, intl_manifest_path,
                candidate1_review_markdown, _resolve(args.sa_source), _resolve(args.sa_parent_source),
                _resolve(args.international_source),
                _resolve(args.raw_reviews)]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("required candidate/source input(s) missing: " + ", ".join(missing))

    candidate1_plan_checksum = sha256_file(plan_path)
    candidate1_annotation_checksum = sha256_file(annotation_path)
    candidate1_plan = load_jsonl_dicts(plan_path)
    candidate1_annotation = load_jsonl_dicts(annotation_path)
    plan_manifest_data = json.loads(candidate1_plan_manifest.read_text(encoding="utf-8"))
    annotation_manifest_data = json.loads(candidate1_annotation_manifest.read_text(encoding="utf-8"))
    batch_manifest_data = json.loads(candidate1_batch_manifest_path.read_text(encoding="utf-8"))
    if plan_manifest_data.get("plan_output_sha256") != candidate1_plan_checksum:
        raise ValueError("candidate-1 plan checksum does not match its manifest")
    if annotation_manifest_data.get("output_checksum") != candidate1_annotation_checksum:
        raise ValueError("candidate-1 annotation checksum does not match its manifest")
    if annotation_manifest_data.get("input_sample_plan_checksum") != candidate1_plan_checksum:
        raise ValueError("candidate-1 annotation manifest references a different plan")
    candidate1_artifact_checksums = {
        str(path): sha256_file(path)
        for path in (
            plan_path, annotation_path, candidate1_plan_manifest,
            candidate1_annotation_manifest, candidate1_batch_manifest_path, candidate1_review_markdown,
        )
    }
    if candidate1_review_json.is_file():
        candidate1_artifact_checksums[str(candidate1_review_json)] = sha256_file(candidate1_review_json)
    candidate1_batch_dir = candidate1_root / "batches"
    candidate1_batches: dict[str, list[dict]] = {}
    for batch_id, _, expected_size in BATCH_SPECS:
        batch_path = candidate1_batch_dir / f"{batch_id}.jsonl"
        if not batch_path.is_file():
            raise FileNotFoundError(f"protected candidate-1 batch is missing: {batch_path}")
        if sha256_file(batch_path) != batch_manifest_data.get("checksums", {}).get(batch_id):
            raise ValueError(f"protected candidate-1 batch checksum mismatch: {batch_id}")
        records_in_batch = load_jsonl_dicts(batch_path)
        if len(records_in_batch) != expected_size:
            raise ValueError(f"protected candidate-1 batch has wrong size: {batch_id}")
        candidate1_batches[batch_id] = records_in_batch
        candidate1_artifact_checksums[str(batch_path)] = sha256_file(batch_path)
    candidate1_batch_ids = [str(record.get("record_id")) for batch in candidate1_batches.values() for record in batch]
    candidate1_plan_ids = [str(record.get("record_id")) for record in candidate1_plan]
    if len(candidate1_batch_ids) != 1000 or len(set(candidate1_batch_ids)) != 1000 or set(candidate1_batch_ids) != set(candidate1_plan_ids):
        raise ValueError("candidate-1 batch files do not contain the protected sample IDs exactly once")
    sa_manifest = _read_verified_manifest(sa_manifest_path)
    intl_manifest = _read_verified_manifest(intl_manifest_path)
    sa_source_path = _resolve(args.sa_source)
    sa_parent_path = _resolve(args.sa_parent_source)
    intl_source_path = _resolve(args.international_source)
    if sha256_file(sa_source_path) != sa_manifest.get("sha256"):
        raise ValueError("South African source checksum does not match VERIFIED manifest")
    if sha256_file(intl_source_path) != intl_manifest.get("sha256"):
        raise ValueError("international source checksum does not match VERIFIED manifest")
    if not sa_parent_manifest_path.is_file():
        raise FileNotFoundError(f"South African parent checksum manifest is missing: {sa_parent_manifest_path}")
    sa_parent_manifest = json.loads(sa_parent_manifest_path.read_text(encoding="utf-8"))
    if sha256_file(sa_parent_path) != sa_parent_manifest.get("sha256"):
        raise ValueError("South African parent checksum does not match recorded source manifest")

    sa_frame = pd.read_parquet(sa_source_path)
    parent_columns = ["record_id", "text", "created_at", "possible_official_account"]
    sa_parent = pd.read_parquet(sa_parent_path, columns=parent_columns)
    selected_sa_ids = [str(row["source_record_id"]) for row in candidate1_plan if row.get("source") == "south_africa_tweet"]
    rule_map = build_v2_rule_map(sa_parent, selected_sa_ids)
    selected_ids = set(selected_sa_ids)
    sa_metadata: dict[str, dict[str, Any]] = {}
    for row in sa_frame[sa_frame["record_id"].astype(str).isin(selected_ids)].to_dict(orient="records"):
        record_id = str(row["record_id"])
        row["source_checksum"] = str(sa_manifest["sha256"])
        sa_metadata[record_id] = row

    prepared = pd.read_csv(intl_source_path)
    selected_tweet_ids = {
        str(row["source_record_id"])
        for row in candidate1_plan
        if row.get("source") == "international_tweet"
    }
    tweet_source_rows = prepared[
        (prepared["source"] == "international_bank_tweets")
        & prepared["record_id"].astype(str).isin(selected_tweet_ids)
    ].to_dict(orient="records")
    tweet_metadata = {}
    for row in tweet_source_rows:
        source_id = str(row["record_id"])
        if source_id in tweet_metadata:
            raise ValueError(f"duplicate international tweet source ID: {source_id}")
        row["source_checksum"] = str(intl_manifest["sha256"])
        tweet_metadata[source_id] = row
    raw_reviews = pd.read_csv(_resolve(args.raw_reviews))
    review_map, review_report = build_review_metadata_map(
        raw_reviews,
        prepared,
        source_checksum=str(intl_manifest["sha256"]),
        raw_source_checksum=sha256_file(_resolve(args.raw_reviews)),
    )
    candidate2_plan, annotation_records, enrichment_report = build_candidate2_package(
        candidate1_plan,
        sa_source_metadata=sa_metadata,
        v2_rule_map=rule_map,
        review_metadata=review_map,
        international_tweet_metadata=tweet_metadata,
        review_metadata_report=review_report,
    )
    assignment = assign_batches(annotation_records, seed=args.seed)
    candidate2_batches = {
        name: [annotation_records[index] for index in assignment.batches[name]]
        for name, _, _ in BATCH_SPECS
    }
    batch_metadata = [
        build_batch_metadata(
            name, batch_type, candidate2_batches[name],
            source_sample_manifest_checksum=candidate1_plan_checksum,
            group_count=assignment.group_counts.get(name, 0),
            source_target_distribution=assignment.source_targets.get(name, {}),
            source_deviation=assignment.source_deviations.get(name, {}),
            region_target_distribution=assignment.region_targets.get(name, {}),
            region_deviation=assignment.region_deviations.get(name, {}),
            constraint_warnings=[warning for warning in assignment.unresolved_balancing_warnings if name in warning],
            balancing_explanation=assignment.grouping_balance_explanations.get(name),
        )
        for name, batch_type, _ in BATCH_SPECS
    ]
    for metadata in batch_metadata:
        metadata.output_path = str(candidate2_root / "batches" / f"{metadata.batch_id}.jsonl")
        metadata.checksum = hashlib.sha256(_jsonl_bytes(candidate2_batches[metadata.batch_id])).hexdigest()
        metadata.checksum_algorithm = "jsonl_sha256"
    batch_manifest = build_combined_batch_manifest(
        batch_metadata, assignment,
        creation_command="python scripts/build_candidate_package_v2.py --write",
        seed=args.seed,
    )
    batch_manifest["seed"] = args.seed
    batch_manifest["candidate_number"] = 2
    batch_manifest["git_commit"] = git_commit() or NO_COMMIT_MARKER

    candidate2_plan_bytes = _jsonl_bytes(candidate2_plan)
    annotation_bytes = _jsonl_bytes(annotation_records)
    candidate2_checksum = hashlib.sha256(candidate2_plan_bytes).hexdigest()
    annotation_checksum = hashlib.sha256(annotation_bytes).hexdigest()
    plan_manifest = {
        "pipeline_version": "new_pipeline_v1",
        "candidate_number": 2,
        "candidate2_generated": bool(args.write),
        "git_commit": git_commit() or NO_COMMIT_MARKER,
        "record_count": len(candidate2_plan),
        "unique_record_count": len({r["record_id"] for r in candidate2_plan}),
        "source_distribution": enrichment_report["source_distribution"],
        "region_distribution": enrichment_report["region_distribution"],
        "source_checksums": enrichment_report["source_manifest_checksums"],
        "raw_source_checksums": enrichment_report.get("raw_source_checksums", {}),
        "south_africa_rule_parent_checksum": sa_parent_manifest.get("sha256"),
        "input_candidate1_plan_checksum": candidate1_plan_checksum,
        "candidate1_artifact_checksums": candidate1_artifact_checksums,
        "plan_output_sha256": candidate2_checksum,
        "annotation_output_sha256": annotation_checksum,
        "rule_distribution": enrichment_report["rule_distribution"],
        "duplicate_group_summary": enrichment_report["duplicate_group_summary"],
        "leakage_group_summary": enrichment_report["leakage_group_summary"],
        "bank_metadata": enrichment_report["bank_metadata"],
        "context_policy": enrichment_report["context_policy"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    annotation_manifest = {
        "pipeline_version": "new_pipeline_v1",
        "candidate_number": 2,
        "git_commit": git_commit() or NO_COMMIT_MARKER,
        "input_sample_plan_checksum": candidate2_checksum,
        "output_record_count": len(annotation_records),
        "output_checksum": annotation_checksum,
        "schema_version": "new_pipeline_schema_v1",
        "label_hidden": True,
        "candidate1_annotation_checksum": candidate1_annotation_checksum,
        "approval_status": "NOT_APPROVED",
        "freeze_status": "NOT_FROZEN",
    }
    diff = compare_candidate_packages(
        candidate1_plan,
        candidate2_plan,
        candidate1_checksum=candidate1_plan_checksum,
        candidate2_checksum=candidate2_checksum,
        candidate1_batches=candidate1_batches,
        candidate2_batches=candidate2_batches,
    )
    diff["candidate1_annotation_checksum"] = candidate1_annotation_checksum
    diff["candidate1_artifact_checksums"] = candidate1_artifact_checksums
    diff["candidate1_remains_unchanged"] = all(sha256_file(path) == checksum for path, checksum in candidate1_artifact_checksums.items())
    enrichment_report["candidate1_checksum"] = candidate1_plan_checksum
    enrichment_report["candidate1_annotation_checksum"] = candidate1_annotation_checksum
    enrichment_report["git_commit"] = git_commit() or NO_COMMIT_MARKER
    enrichment_report["candidate2_generated"] = bool(args.write)
    lineage_manifest = {
        "pipeline_version": "new_pipeline_v1",
        "candidate_number": 2,
        "parent_candidate": 1,
        "parent_plan_path": str(plan_path),
        "parent_plan_checksum": candidate1_plan_checksum,
        "parent_annotation_checksum": candidate1_annotation_checksum,
        "child_plan_checksum": candidate2_checksum,
        "child_annotation_checksum": annotation_checksum,
        "record_identity_rule": "canonical record_id comparison; no resampling and no positional comparison",
        "records_retained": diff["records_retained"],
        "records_added": diff["records_added"],
        "records_removed": diff["records_removed"],
        "changed_canonical_ids": diff["changed_canonical_ids"],
        "git_commit": git_commit() or NO_COMMIT_MARKER,
        "approval_status": "NOT_APPROVED",
        "freeze_status": "NOT_FROZEN",
    }
    enrichment_md = "\n".join([
        "# Candidate 2 enrichment report",
        "",
        "Implementation staging summary; this report is generated only by a later explicit --write.",
        f"- Candidate 1 plan checksum: `{candidate1_plan_checksum}`",
        f"- Candidate 2 plan checksum: `{candidate2_checksum}`",
        f"- Records: {len(candidate2_plan)}; source distribution: `{enrichment_report['source_distribution']}`",
        f"- Region distribution: `{enrichment_report['region_distribution']}`",
        f"- V2 rule distribution (sampling provenance only): `{enrichment_report['rule_distribution']}`",
        f"- Review bank corrections/nulling: `{enrichment_report['bank_metadata']}`",
        f"- Context policy: {enrichment_report['context_policy']}",
        "- Approval: NOT_APPROVED; freeze: NOT_FROZEN",
        "",
    ]).encode("utf-8")

    manifest_files: dict[str, bytes] = {
        "candidate_2_manifest.json": _json_bytes(plan_manifest),
        "annotation_package_manifest.json": _json_bytes(annotation_manifest),
        "annotation_batch_manifest.json": _json_bytes(batch_manifest),
        "candidate_lineage_diff.json": _json_bytes(diff),
        "candidate_lineage_manifest.json": _json_bytes(lineage_manifest),
    }
    for name, _, _ in BATCH_SPECS:
        manifest_files[f"batches/{name}.jsonl"] = _jsonl_bytes(candidate2_batches[name])
    data_files = {
        "gold_sample_plan.jsonl": candidate2_plan_bytes,
        "annotation_records.jsonl": annotation_bytes,
        **{f"batches/{name}.jsonl": _jsonl_bytes(candidate2_batches[name]) for name, _, _ in BATCH_SPECS},
    }
    report_files = {
        "candidate_2_enrichment_report.json": _json_bytes(enrichment_report),
        "candidate_2_enrichment_report.md": enrichment_md,
        "candidate_lineage_diff.json": _json_bytes(diff),
    }
    payloads = {candidate2_root: data_files, manifest2_root: manifest_files, report2_root: report_files}
    summary = {
        "candidate1_plan": str(plan_path),
        "candidate1_checksum": candidate1_plan_checksum,
        "candidate1_annotation_checksum": candidate1_annotation_checksum,
        "candidate1_artifact_checksums": candidate1_artifact_checksums,
        "candidate1_remains_unchanged": diff["candidate1_remains_unchanged"],
        "candidate2_data_output": str(candidate2_root),
        "candidate2_manifest_output": str(manifest2_root),
        "candidate2_report_output": str(report2_root),
        "proposed_manifest_paths": {
            "candidate": str(manifest2_root / "candidate_2_manifest.json"),
            "annotation_package": str(manifest2_root / "annotation_package_manifest.json"),
            "batches": str(manifest2_root / "annotation_batch_manifest.json"),
            "lineage": str(manifest2_root / "candidate_lineage_manifest.json"),
            "diff": str(manifest2_root / "candidate_lineage_diff.json"),
        },
        "candidate2_plan_checksum": candidate2_checksum,
        "record_count": len(candidate2_plan),
        "unique_canonical_ids": len({record["record_id"] for record in candidate2_plan}),
        "source_distribution": enrichment_report["source_distribution"],
        "region_distribution": enrichment_report["region_distribution"],
        "rule_distribution": enrichment_report["rule_distribution"],
        "bank_corrections": {
            key: value
            for key, value in enrichment_report["bank_metadata"].items()
            if key in {
                "corrected_using_verified_evidence", "corrected_source_record_ids",
                "review_records_set_null", "review_record_ids_set_null",
                "affected_record_ids", "original_invalid_values_by_source_record_id",
                "distribution_by_source",
            }
        },
        "review_id_coverage": {
            "selected_review_records": sum(record.get("source") == "international_review" for record in annotation_records),
            "selected_review_records_with_id": sum(
                record.get("source") == "international_review" and bool(record.get("review_id"))
                for record in annotation_records
            ),
            "algorithm": enrichment_report["review_identity"]["algorithm"],
        },
        "duplicate_group_coverage": enrichment_report["duplicate_group_summary"],
        "leakage_group_coverage": enrichment_report["leakage_group_summary"],
        "context_availability": enrichment_report["sampling_diversity"]["context_availability"],
        "source_checksums": enrichment_report["source_manifest_checksums"],
        "raw_source_checksums": enrichment_report.get("raw_source_checksums", {}),
        "south_africa_rule_parent_checksum": sa_parent_manifest.get("sha256"),
        "batch_warnings": assignment.unresolved_balancing_warnings,
        "batch_distributions": {
            metadata.batch_id: {
                "source_target": metadata.source_target_distribution,
                "source_observed": metadata.source_distribution,
                "source_deviation": metadata.source_deviation,
                "region_target": metadata.region_target_distribution,
                "region_observed": metadata.region_distribution,
                "region_deviation": metadata.region_deviation,
                "group_count": metadata.group_count,
                "warnings": metadata.constraint_warnings,
                "explanation": metadata.balancing_explanation,
            }
            for metadata in batch_metadata
        },
        "dry_run": not args.write,
    }
    return payloads, summary


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payloads, summary = _prepare(args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        if not args.write:
            print("dry-run: no files written; pass --write to stage candidate 2")
            return 0
        if not args.overwrite:
            existing = [str(path) for path in payloads if path.exists()]
            if existing:
                raise FileExistsError("refusing to overwrite: " + ", ".join(existing))
        staged: dict[Path, Path] = {}
        try:
            for target, files in payloads.items():
                staged[target] = _stage_directory(target, files)
            _install_transaction(staged, overwrite=args.overwrite)
            changed_candidate1 = [
                path for path, checksum in summary["candidate1_artifact_checksums"].items()
                if sha256_file(path) != checksum
            ]
            if changed_candidate1:
                raise RuntimeError("protected candidate-1 artifact checksum changed: " + ", ".join(changed_candidate1))
        except Exception:
            for staging in staged.values():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        print("candidate-2 staging outputs written; package remains unapproved and unfrozen")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"candidate-2 staging refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())