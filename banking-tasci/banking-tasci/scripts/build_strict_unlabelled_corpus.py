#!/usr/bin/env python3
"""Build (or assess readiness for) the strict unlabelled corpus.

Requirements Section 16: the 110,615-record strict unlabelled corpus for domain
adaptation = 111,615 combined relevant - 1,000 gold.

**Defaults to PREPARATION mode**, which validates manifests and arithmetic,
inspects whether gold-ID manifests exist, and emits a readiness report. It never
builds a corpus and never claims one exists.

``FINAL`` mode requires frozen gold identifiers (exactly 1,000: 500 South
African, 250 international tweets, 250 international reviews). Those do not
exist yet, so FINAL will refuse to run. Removing 1,000 arbitrary records to
reach 110,615 is prohibited (Requirements Migration Principle 6).

Usage::

    python scripts/build_strict_unlabelled_corpus.py
    python scripts/build_strict_unlabelled_corpus.py --mode FINAL \\
        --gold-ids artifacts/manifests/new_pipeline_v1/gold_ids.json

Exit codes: ``0`` ready / report written, ``1`` IO error, ``3`` blocked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.manifest import git_commit  # noqa: E402
from banking_tasci.data.unlabelled_corpus import (  # noqa: E402
    EXPECTED_COUNTS,
    MODE_FINAL,
    MODE_PREPARATION,
    READINESS_READY,
    assess_readiness,
    load_gold_ids,
    build_strict_corpus,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1"

SA_MANIFEST = MANIFEST_DIR / "south_africa_candidates_v2_source_manifest.json"
INTL_MANIFEST = MANIFEST_DIR / "international_source_manifest.json"
COMBINED_MANIFEST = MANIFEST_DIR / "combined_relevant_manifest.json"
DEFAULT_GOLD_IDS = MANIFEST_DIR / "gold_ids.json"
DEFAULT_FROZEN_GOLD_MANIFEST = (
    PROJECT_ROOT / "artifacts" / "frozen" / "new_pipeline_v1" / "gold_sample_manifest.json"
)
DEFAULT_REPORT = MANIFEST_DIR / "strict_unlabelled_readiness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/processed/new_pipeline_v1/strict_unlabelled.jsonl"
DEFAULT_EVIDENCE_DIR = MANIFEST_DIR / "strict_unlabelled"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_strict_unlabelled_corpus.py",
        description=(
            "Assess readiness for (PREPARATION) or build (FINAL) the strict "
            "110,615-record unlabelled corpus. PREPARATION is the default and "
            "builds nothing."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_PREPARATION, MODE_FINAL],
        default=MODE_PREPARATION,
    )
    parser.add_argument("--south-africa-manifest", default=str(SA_MANIFEST))
    parser.add_argument("--international-manifest", default=str(INTL_MANIFEST))
    parser.add_argument("--combined-manifest", default=str(COMBINED_MANIFEST))
    parser.add_argument("--gold-ids", default=str(DEFAULT_GOLD_IDS))
    parser.add_argument(
        "--frozen-gold-manifest",
        default=None,
        help=(
            "Use a checksum-verified immutable_status=FROZEN manifest and its "
            "gold_record_ids.jsonl instead of the legacy grouped JSON ID file."
        ),
    )
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="FINAL-mode corpus output path.")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--south-africa-source", default=str(PROJECT_ROOT / "data/processed/new_pipeline_v1/south_africa_candidates_v2.parquet"))
    parser.add_argument("--international-source", default=str(PROJECT_ROOT / "data/interim/prepared.csv"))
    parser.add_argument("--dry-run", action="store_true", help="Validate FINAL inputs and exclusions without writing outputs.")
    parser.add_argument(
        "--include-context",
        action="store_true",
        help="Retain genuine previous context (only when the experiment approves it).",
    )
    return parser


def _maybe_load(path: Path) -> "dict | None":
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)

    sa = _maybe_load(Path(args.south_africa_manifest))
    intl = _maybe_load(Path(args.international_manifest))
    combined = _maybe_load(Path(args.combined_manifest))

    gold_ids_path = Path(args.frozen_gold_manifest) if args.frozen_gold_manifest else Path(args.gold_ids)
    report = assess_readiness(
        south_africa_manifest=sa,
        international_manifest=intl,
        combined_manifest=combined,
        gold_id_manifest_paths={"combined_gold": gold_ids_path},
        git_commit_value=git_commit(),
    )

    print("=== strict unlabelled corpus ===")
    print(f"  mode:               {args.mode}")
    print(f"  target records:     {EXPECTED_COUNTS['strict_unlabelled']:,}")
    print(f"  readiness:          {report.readiness}")
    print(f"  corpus built:       {report.corpus_built}")

    print("\n  arithmetic:")
    for name, check in report.arithmetic_checks.items():
        if isinstance(check, dict):
            print(f"    {name}: consistent={check['consistent']}")
    print(f"    all_consistent: {report.arithmetic_checks['all_consistent']}")

    print("\n  source manifests:")
    for name, check in report.source_manifest_checks.items():
        print(
            f"    {name}: present={check['present']} status={check.get('status')} "
            f"rows={check.get('row_count')}"
        )

    print("\n  gold-ID manifests:")
    for name, check in report.gold_id_manifests.items():
        if name == "supplied":
            continue
        if isinstance(check, dict):
            print(f"    {name}: exists={check.get('exists')} path={check.get('path')}")

    if report.blockers:
        print("\n  BLOCKERS:")
        for blocker in report.blockers:
            print(f"    - {blocker}")

    print("\n  FINAL mode will require:")
    for requirement in report.gold_exclusion_requirements:
        print(f"    - {requirement}")

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"\n  readiness report: {report_path}")

    if args.mode == MODE_PREPARATION:
        print(
            "\nPREPARATION mode: no corpus was built and none is claimed to exist."
        )
        return 0 if report.readiness == READINESS_READY else 3

    # --- FINAL mode ---------------------------------------------------------
    gold_path = gold_ids_path
    if not gold_path.is_file():
        print(
            f"\nFINAL mode refused: gold-identifier manifest not found at "
            f"{gold_path}.\nThe 1,000 gold identifiers do not exist yet. Removing "
            f"1,000 arbitrary records to reach "
            f"{EXPECTED_COUNTS['strict_unlabelled']:,} is prohibited.",
            file=sys.stderr,
        )
        return 3

    gold = load_gold_ids(gold_path)
    problems = gold.validate()
    if problems:
        print("\nFINAL mode refused: gold-ID set is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 3

    import pandas as pd

    sa_source = Path(args.south_africa_source)
    intl_source = Path(args.international_source)
    if not sa_source.is_file() or not intl_source.is_file():
        print("FINAL mode refused: a verified source data file is missing.", file=sys.stderr)
        return 3
    south_africa = pd.read_parquet(sa_source)
    international = pd.read_csv(intl_source)
    combined_frame = pd.concat([south_africa, international], ignore_index=True, sort=False)
    strict, final_report = build_strict_corpus(combined_frame, gold, include_context=args.include_context)
    if args.dry_run:
        print(json.dumps(final_report, indent=2, sort_keys=True))
        print("FINAL dry-run: no corpus or evidence files written.")
        return 0
    output = Path(args.output)
    evidence_dir = Path(args.evidence_dir)
    if output.exists() or evidence_dir.exists():
        print("FINAL mode refused: strict corpus output or evidence directory already exists.", file=sys.stderr)
        return 3
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".strict_unlabelled.", dir=output.parent))
    try:
        staged_output = staging / output.name
        strict.to_json(staged_output, orient="records", lines=True, force_ascii=False)
        corpus_checksum = hashlib.sha256(staged_output.read_bytes()).hexdigest()
        evidence_dir.mkdir(parents=True, exist_ok=False)
        source_refs = {
            "south_africa": {"data_path": str(sa_source), "manifest_path": str(args.south_africa_manifest), "record_count": len(south_africa)},
            "international": {"data_path": str(intl_source), "manifest_path": str(args.international_manifest), "record_count": len(international)},
            "combined": {"manifest_path": str(args.combined_manifest), "record_count": len(combined_frame)},
        }
        manifest = {**final_report, "pipeline_version": "new_pipeline_v1", "corpus_path": str(output), "corpus_checksum": corpus_checksum, "frozen_gold_manifest": str(gold_path), "frozen_gold_checksum": hashlib.sha256(gold_path.read_bytes()).hexdigest(), "source_references": source_refs, "git_commit": git_commit()}
        privacy = {"pipeline_version": "new_pipeline_v1", "record_count": len(strict), "retained_columns": list(strict.columns), "excluded_columns_absent": [field for field in __import__('banking_tasci.data.unlabelled_corpus', fromlist=['all_excluded_fields']).all_excluded_fields() if field not in strict.columns], "privacy_status": "PASS"}
        exclusion = {"pipeline_version": "new_pipeline_v1", "gold_manifest": str(gold_path), "gold_id_checksum": hashlib.sha256((gold_path.parent / json.loads(gold_path.read_text())["gold_id_file"]).read_bytes()).hexdigest(), "gold_records_excluded": final_report["gold_records_excluded"], "gold_overlap_with_strict": 0, "strict_record_count": len(strict)}
        (evidence_dir / "strict_unlabelled_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (evidence_dir / "gold_exclusion_report.json").write_text(json.dumps(exclusion, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (evidence_dir / "privacy_report.json").write_text(json.dumps(privacy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (evidence_dir / "strict_unlabelled.sha256").write_text(corpus_checksum + "  " + output.name + "\n", encoding="utf-8")
        os.replace(staged_output, output)
    except Exception:
        if evidence_dir.exists():
            import shutil
            shutil.rmtree(evidence_dir)
        raise
    finally:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
    print(f"strict unlabelled corpus written: {output}")
    print(f"strict corpus evidence written: {evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
