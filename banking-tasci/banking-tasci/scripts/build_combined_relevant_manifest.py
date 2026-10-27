#!/usr/bin/env python3
"""Build the combined relevant-corpus manifest (Requirements Section 4.3).

Describes the 111,615-record combined relevant corpus by **referencing** the
two immutable source manifests rather than concatenating their data:

    South African candidates   100,768
    International prepared      10,847
                               -------
    Combined relevant          111,615

Concatenating would duplicate ~12 MB + ~3 MB of source data for no benefit and
create a second artifact to keep in sync. Referencing keeps a single source of
truth per corpus and makes the relationship traceable.

**Identifier namespacing.** Requirements Section 8.1 requires stable, unique
identifiers. The two corpora use independent identifier namespaces, so a
collision would be silent and damaging. This script therefore:

- checks for actual overlap between the two identifier sets;
- defines deterministic namespaced identifiers
  (``south_africa::<id>``, ``international_tweet::<id>``,
  ``international_review::<id>``);
- preserves the original identifier as ``source_record_id`` - the original is
  never overwritten.

**Preconditions.** Both source manifests must already report ``VERIFIED``. The
script refuses to emit a combined manifest otherwise, so a combined corpus can
never claim more confidence than its weakest input.

Usage::

    python scripts/build_combined_relevant_manifest.py
    python scripts/build_combined_relevant_manifest.py --check-id-collisions

Exit codes: ``0`` success, ``1`` IO/usage error, ``2`` precondition failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.manifest import (  # noqa: E402
    NO_COMMIT_MARKER,
    STATUS_VERIFIED,
    git_commit,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "new_pipeline_v1.yaml"
MANIFEST_DIR = PROJECT_ROOT / "artifacts" / "manifests" / "new_pipeline_v1"

SA_MANIFEST = MANIFEST_DIR / "south_africa_candidates_v2_source_manifest.json"
INTL_MANIFEST = MANIFEST_DIR / "international_source_manifest.json"
DEFAULT_OUTPUT = MANIFEST_DIR / "combined_relevant_manifest.json"

PIPELINE_VERSION = "new_pipeline_v1"

# Deterministic identifier namespaces (Requirements 8.1 stable identifiers).
NAMESPACE_SOUTH_AFRICA = "south_africa"
NAMESPACE_INTL_TWEET = "international_tweet"
NAMESPACE_INTL_REVIEW = "international_review"
NAMESPACE_SEPARATOR = "::"

VALID_REGIONS = {"south_africa", "international"}


def namespaced_id(namespace: str, source_record_id: str) -> str:
    """Build a deterministic namespaced identifier.

    The original identifier is preserved verbatim after the separator and must
    also be retained separately as ``source_record_id``.
    """
    return f"{namespace}{NAMESPACE_SEPARATOR}{source_record_id}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_combined_relevant_manifest.py",
        description=(
            "Build the combined relevant-corpus manifest by reference. Requires "
            "both source manifests to be VERIFIED."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--south-africa-manifest", default=str(SA_MANIFEST))
    parser.add_argument("--international-manifest", default=str(INTL_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--check-id-collisions",
        action="store_true",
        help=(
            "Load both identifier sets and verify they do not overlap. Slower "
            "(reads both corpora) but gives direct evidence rather than an "
            "assumption."
        ),
    )
    return parser


def _load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"source manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_id_collisions(sa_path: Path, intl_path: Path) -> dict:
    """Directly verify the two identifier namespaces do not collide."""
    import pandas as pd

    sa_ids = set(
        pd.read_parquet(sa_path, columns=["record_id"])["record_id"].astype(str)
    )
    intl = pd.read_csv(intl_path, usecols=["record_id", "source"])
    intl_ids = set(intl["record_id"].astype(str))

    overlap = sa_ids & intl_ids
    return {
        "checked": True,
        "south_africa_unique_ids": len(sa_ids),
        "international_unique_ids": len(intl_ids),
        "raw_overlap_count": len(overlap),
        "raw_overlap_sample": sorted(overlap)[:5],
        "collision_free_after_namespacing": True,
        "note": (
            "Namespacing makes collisions structurally impossible regardless of "
            "raw overlap, because each identifier is prefixed with its source "
            "namespace. The raw overlap count is reported so the risk is "
            "measured rather than assumed."
        ),
    }


def main(argv: "list[str] | None" = None) -> int:
    args = build_arg_parser().parse_args(argv)

    cfg = load_config(args.config)
    counts = cfg.counts

    try:
        sa = _load_manifest(Path(args.south_africa_manifest))
        intl = _load_manifest(Path(args.international_manifest))
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("=== combined relevant-corpus manifest ===")

    failures: list[str] = []

    # --- precondition: both sources VERIFIED --------------------------------
    for name, manifest in (("south_africa", sa), ("international", intl)):
        status = manifest.get("status")
        print(f"  {name} manifest status: {status}")
        if status != STATUS_VERIFIED:
            failures.append(
                f"{name} source manifest is '{status}', not {STATUS_VERIFIED}"
            )

    # --- precondition: counts sum correctly ---------------------------------
    sa_count = sa.get("row_count")
    intl_count = intl.get("row_count")
    combined_observed = (sa_count or 0) + (intl_count or 0)
    expected_combined = counts.combined_relevant

    print(f"  south africa rows:     {sa_count:,}" if sa_count else "  south africa rows: ?")
    print(f"  international rows:    {intl_count:,}" if intl_count else "  international rows: ?")
    print(f"  combined observed:     {combined_observed:,}")
    print(f"  combined expected:     {expected_combined:,}")

    if sa_count != counts.south_africa_candidates:
        failures.append(
            f"south african count {sa_count} != configured "
            f"{counts.south_africa_candidates}"
        )
    if intl_count != counts.international_prepared:
        failures.append(
            f"international count {intl_count} != configured "
            f"{counts.international_prepared}"
        )
    if combined_observed != expected_combined:
        failures.append(
            f"combined {combined_observed} != expected {expected_combined}"
        )

    # --- precondition: pipeline versions match ------------------------------
    versions = {sa.get("pipeline_version"), intl.get("pipeline_version")}
    if versions != {PIPELINE_VERSION}:
        failures.append(f"pipeline_version mismatch across manifests: {versions}")

    # --- precondition: regions valid ----------------------------------------
    for name, manifest in (("south_africa", sa), ("international", intl)):
        region = manifest.get("region")
        if region not in VALID_REGIONS:
            failures.append(f"{name} region '{region}' is not a recognised value")

    # --- precondition: privacy acceptable -----------------------------------
    for name, manifest in (("south_africa", sa), ("international", intl)):
        privacy = manifest.get("privacy_status") or {}
        if privacy.get("username_column_present"):
            failures.append(f"{name} source exposes a raw username/handle column")

    # --- optional direct collision evidence ---------------------------------
    collision = {
        "checked": False,
        "note": (
            "Not verified directly this run. Namespacing makes collisions "
            "structurally impossible; re-run with --check-id-collisions for "
            "measured evidence."
        ),
        "collision_free_after_namespacing": True,
    }
    if args.check_id_collisions:
        print("  checking identifier collisions (reads both corpora)...")
        collision = _check_id_collisions(
            Path(sa["source_file"]), Path(intl["source_file"])
        )
        print(f"    raw overlap: {collision['raw_overlap_count']}")

    if failures:
        print("\nPRECONDITION FAILURES:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nRefusing to write a combined manifest. A combined corpus must not "
            "claim more confidence than its weakest input.",
            file=sys.stderr,
        )
        return 2

    commit = git_commit()

    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "manifest_type": "combined_relevant_corpus",
        "status": STATUS_VERIFIED,
        "construction": "by_reference",
        "construction_note": (
            "This manifest references the two immutable source manifests rather "
            "than concatenating their data. Concatenation would duplicate the "
            "underlying corpora and create a second artifact to keep in sync."
        ),
        "counts": {
            "south_africa_candidates": sa_count,
            "international_prepared": intl_count,
            "combined_relevant": combined_observed,
            "expected_combined_relevant": expected_combined,
            "counts_reconcile": combined_observed == expected_combined,
        },
        "sources": {
            "south_africa": {
                "manifest_path": str(Path(args.south_africa_manifest)),
                "source_file": sa.get("source_file"),
                "source_sha256": sa.get("sha256"),
                "row_count": sa_count,
                "unique_record_count": sa.get("unique_record_count"),
                "duplicate_record_count": sa.get("duplicate_record_count"),
                "status": sa.get("status"),
                "region": sa.get("region"),
                "source": sa.get("source"),
                "identifier_namespace": NAMESPACE_SOUTH_AFRICA,
            },
            "international": {
                "manifest_path": str(Path(args.international_manifest)),
                "source_file": intl.get("source_file"),
                "source_sha256": intl.get("sha256"),
                "row_count": intl_count,
                "unique_record_count": intl.get("unique_record_count"),
                "duplicate_record_count": intl.get("duplicate_record_count"),
                "status": intl.get("status"),
                "region": intl.get("region"),
                "source": intl.get("source"),
                "identifier_namespaces": [
                    NAMESPACE_INTL_TWEET,
                    NAMESPACE_INTL_REVIEW,
                ],
                "source_distribution": intl.get("source_distribution"),
            },
        },
        "identifier_policy": {
            "separator": NAMESPACE_SEPARATOR,
            "namespaces": [
                NAMESPACE_SOUTH_AFRICA,
                NAMESPACE_INTL_TWEET,
                NAMESPACE_INTL_REVIEW,
            ],
            "examples": [
                f"{NAMESPACE_SOUTH_AFRICA}{NAMESPACE_SEPARATOR}<record_id>",
                f"{NAMESPACE_INTL_TWEET}{NAMESPACE_SEPARATOR}<record_id>",
                f"{NAMESPACE_INTL_REVIEW}{NAMESPACE_SEPARATOR}<record_id>",
            ],
            "original_identifier_field": "source_record_id",
            "original_identifier_preserved": True,
            "note": (
                "Original identifiers are never overwritten. The namespaced form "
                "is additive and deterministic, so the same record always yields "
                "the same combined identifier."
            ),
        },
        "identifier_collision_check": collision,
        "validation": {
            "both_sources_verified": True,
            "counts_sum_correct": True,
            "pipeline_versions_match": True,
            "regions_valid": True,
            "privacy_acceptable": True,
        },
        "downstream_note": (
            "The strict unlabelled corpus (110,615) is derived from this combined "
            "corpus minus the 1,000 gold records. Those gold identifiers do not "
            "exist yet, so the strict corpus cannot be built - see "
            "scripts/build_strict_unlabelled_corpus.py PREPARATION mode."
        ),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generation_command": "python scripts/build_combined_relevant_manifest.py "
        + " ".join(argv if argv is not None else sys.argv[1:]),
        "git_commit": commit,
    }
    if commit == NO_COMMIT_MARKER:
        manifest["provenance_warning"] = (
            "The repository has no Git commit, so this manifest cannot be tied to "
            "a source revision (Requirements Section 25)."
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(f"\n  status:   {STATUS_VERIFIED}")
    print(f"  combined: {combined_observed:,}")
    print(f"  manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
