#!/usr/bin/env python3
"""Prepare the South African banking Twitter dataset for the TASCI project.

Processes all parquet files in the archive incrementally (one file at a time),
applies cleaning and anonymisation, maps to the canonical schema, filters for
customer-feedback candidates, and creates a 200-record unannotated annotation
sample.

No gold labels are created.
No sentiment, intent, aspect category, or BIO labels are inferred.
The international gold dataset is not modified.
The South African prepared data is kept separate until human annotation
and adjudication are complete.

Dataset provenance
------------------
"Tweets of Popular South African Banks" by Nicholas Blomerus.
GitHub: https://github.com/nblomerus/South-African-Bank-Sentiment-Analysis
Kaggle: https://www.kaggle.com/datasets/nicholasblomerus/twitter-analysis-of-popular-south-african-banks
Banks: FNB, Absa, Nedbank, Capitec, Standard Bank
Collection period: 2006-01-01 to 2023-01-01

Usage
-----
python scripts/prepare_south_africa_data.py \\
    --input-dir data/raw/archive \\
    --output data/interim/south_africa_prepared.parquet \\
    --report outputs/south_africa_data_report.json \\
    --annotation-output data/annotations/south_african_unannotated.jsonl \\
    --sample-report outputs/south_africa_annotation_sample_report.json \\
    --sample-size 200 \\
    --start-date 2018-01-01 \\
    --end-date 2022-12-31 \\
    --seed 42
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ is on the path when run directly
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd

from banking_tasci.config import load_config
from banking_tasci.logging_utils import get_logger
from banking_tasci.data.ingest_south_africa import (
    CANONICAL_COLUMNS,
    AUDIT_COLUMNS,
    SOURCE_NAME,
    REGION,
    ProcessingStats,
    _process_single_file,
    run_near_dup_on_candidates,
    select_annotation_sample,
    to_annotation_records,
)
from banking_tasci.data.clean import NearDupConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "base.yaml"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepare_south_africa_data.py",
        description=(
            "Prepare South African banking Twitter dataset for TASCI annotation. "
            "Processes parquet files incrementally, applies cleaning and anonymisation, "
            "and creates an unannotated 200-record annotation sample. "
            "Does not create gold labels or modify the international gold dataset."
        ),
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing the raw parquet archive (tweets/ subdirectory).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the prepared canonical dataset (parquet preferred).",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Output path for the data quality report (JSON).",
    )
    parser.add_argument(
        "--annotation-output",
        required=True,
        help="Output path for the unannotated annotation sample (JSONL).",
    )
    parser.add_argument(
        "--sample-report",
        required=True,
        help="Output path for the annotation sample composition report (JSON).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=200,
        help="Number of records to include in the annotation sample (default: 200).",
    )
    parser.add_argument(
        "--start-date",
        default="2018-01-01",
        help="Start date for data inclusion (ISO format, inclusive, default: 2018-01-01).",
    )
    parser.add_argument(
        "--end-date",
        default="2022-12-31",
        help="End date for data inclusion (ISO format, inclusive, default: 2022-12-31).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic near-dup and sampling (default: 42).",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to project base.yaml config (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--max-per-bank",
        type=int,
        default=60,
        help="Maximum annotation sample records from any single bank (default: 60).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser


# ---------------------------------------------------------------------------
# Path and schema validation helpers
# ---------------------------------------------------------------------------


def _validate_paths(args: argparse.Namespace) -> None:
    """Raise SystemExit with a helpful message if required paths are invalid."""
    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(
            f"error: --input-dir '{args.input_dir}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    tweets_dir = input_dir / "tweets"
    if not tweets_dir.is_dir():
        print(
            f"error: Expected 'tweets/' subdirectory not found under '{args.input_dir}'.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    parquet_files = list(tweets_dir.glob("*.parquet"))
    if not parquet_files:
        print(
            f"error: No parquet files found under '{tweets_dir}'.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Validate output paths are writable
    for path_str in [args.output, args.report, args.annotation_output, args.sample_report]:
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)

    # Validate config exists
    if not Path(args.config).is_file():
        print(
            f"error: Config file '{args.config}' not found.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _select_parquet_files(input_dir: Path, start_date: pd.Timestamp, end_date: pd.Timestamp) -> list[Path]:
    """Return parquet files from both collections, ordered by file name.

    Files are included even if their name-implied date range partially overlaps
    the target window — date filtering is applied per-row during loading.
    Files whose entire name-implied range is clearly before start_date or after
    end_date are skipped to save loading time.
    """
    tweets_dir = input_dir / "tweets"
    all_files = sorted(tweets_dir.glob("*.parquet"))

    selected = []
    for f in all_files:
        name = f.stem
        # Extract the start and end year from the filename
        # Pattern: ..._from_YYYY-MM-DD_to_YYYY-MM-DD
        import re
        m = re.search(r"from_(\d{4})-\d{2}-\d{2}_to_(\d{4})-\d{2}-\d{2}", name)
        if m:
            file_start_year = int(m.group(1))
            file_end_year = int(m.group(2))
            # Skip if file entirely precedes start_date or entirely follows end_date
            if file_end_year < start_date.year:
                continue
            if file_start_year > end_date.year:
                continue
        selected.append(f)

    return selected


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------


def _build_data_report(
    stats: ProcessingStats,
    args: argparse.Namespace,
    files_considered: list[str],
    files_included: list[str],
    files_skipped: list[str],
    nd_groups: int,
    nd_flagged: int,
    total_rows_final: int,
) -> dict:
    """Build the data quality report dict. No personal identifiers included."""
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE_NAME,
        "region": REGION,
        "selected_date_range": {
            "start": args.start_date,
            "end": args.end_date,
        },
        "files_summary": {
            "total_considered": len(files_considered),
            "included": len(files_included),
            "skipped_outside_date_range_or_empty": len(files_skipped),
            "included_files": [Path(f).name for f in files_included],
            "skipped_files": [Path(f).name for f in files_skipped],
        },
        "row_counts": {
            "total_read": stats.rows_read,
            "outside_date_range": stats.rows_outside_date_range,
            "empty_or_short_excluded": stats.rows_empty_or_short,
            "pure_retweets_excluded": stats.pure_retweets_excluded,
            "tweet_id_duplicates_removed": stats.tweet_id_duplicates_removed,
            "exact_text_duplicates_removed": stats.exact_text_duplicates_removed,
            "confirmed_official_accounts_excluded": stats.confirmed_official_excluded,
            "possible_official_accounts_flagged": stats.possible_official_flagged,
            "rows_after_all_filters": total_rows_final,
            "customer_feedback_candidates": stats.customer_feedback_candidates,
            "likely_promotional_records": stats.promotional_records,
        },
        "near_duplicate_detection": {
            "applied_to": "customer_feedback_candidates_only",
            "action": "flag",
            "groups_detected": nd_groups,
            "records_flagged": nd_flagged,
        },
        "by_bank": dict(stats.bank_counts),
        "by_year": dict(sorted(stats.year_counts.items())),
        "date_parsing": {
            "success": stats.date_parse_success,
            "failed": stats.date_parse_failed,
        },
        "anonymisation_counts": stats.anonymisation_audit.to_dict(),
        "context_coverage": {
            "context_available_true": 0,
            "context_available_false": total_rows_final,
            "note": "All records use [NO_CONTEXT]; no thread graph available",
        },
        "sentiment_fields": {
            "note": "No sentiment, polarity, or label fields exist in source parquet files.",
            "weak_label_fields_found": [],
        },
        "privacy_and_licence": {
            "username_column_dropped": True,
            "tweet_id_not_stored": True,
            "amounts_preserved": True,
            "replace_amounts_config": False,
            "licence_status": "Kaggle dataset licence requires independent confirmation before publication",
            "github_repo_licence": "MIT (software/code only — does not cover tweet content redistribution)",
            "twitter_content_note": "Twitter/X content redistribution governed by Twitter/X Terms of Service — assess separately",
        },
        "study_scope_note": (
            "Date range 2018-2022 selected for relevance to contemporary digital banking. "
            "Records outside this range are excluded from the annotation sample but remain "
            "in the raw archive. This is a study-scope decision, not a cleaning error."
        ),
    }


def _build_sample_report(
    sample_df: pd.DataFrame,
    args: argparse.Namespace,
    nd_groups_in_sample: int,
) -> dict:
    """Build the annotation sample composition report. No personal identifiers."""
    bank_dist = dict(Counter(sample_df["bank"].tolist()))
    year_dist: Counter = Counter()
    for dt in sample_df["created_at"]:
        if dt and str(dt) != "None":
            year_dist[str(dt)[:4]] += 1

    strata_counts: Counter = Counter()
    for strata_str in sample_df.get("candidate_strata", pd.Series(dtype=str)):
        if strata_str:
            for s in strata_str.split(";"):
                if s:
                    strata_counts[s] += 1

    text_lengths = sample_df["text"].astype(str).str.len()

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample_size": len(sample_df),
        "requested_size": args.sample_size,
        "seed": args.seed,
        "source_distribution": {"south_african_bank_tweets": len(sample_df)},
        "bank_distribution": bank_dist,
        "date_distribution": dict(sorted(year_dist.items())),
        "text_length_distribution": {
            "min": float(text_lengths.min()),
            "max": float(text_lengths.max()),
            "mean": float(text_lengths.mean()),
            "q1": float(text_lengths.quantile(0.25)),
            "median": float(text_lengths.quantile(0.50)),
            "q3": float(text_lengths.quantile(0.75)),
        },
        "candidate_strata_counts": dict(strata_counts),
        "context_availability": {
            "context_available_true": 0,
            "context_available_false": len(sample_df),
            "note": "All SA records are context-unavailable; no thread graph in source",
        },
        "near_duplicate_coverage": {
            "records_with_near_dup_flag": int(sample_df.get("near_dup_flag", pd.Series(False)).sum()),
            "unique_near_dup_groups_in_sample": nd_groups_in_sample,
            "note": "Near-dup flagged records are included for annotation diversity; annotators see no flag",
        },
        "sampling_limitations": [
            "No context-available records: SA tweet corpus has no thread graph",
            "No South African records previously in pilot — this is the first SA annotation batch",
            "Candidate strata are keyword heuristics only — not gold labels",
            "suggestion, warning, churn_signal strata rely on keyword matching which may miss indirect signals",
            f"Bank cap of {args.max_per_bank} per bank applied to prevent single-bank dominance",
            "Records from possible_official_account=True are excluded from sample",
        ],
        "label_leakage_prevention": {
            "candidate_strata_removed_from_annotation_view": True,
            "filter_reason_removed_from_annotation_view": True,
            "engagement_removed_from_annotation_view": True,
            "existing_sentiment_fields": "none — no sentiment columns in source parquet files",
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = get_logger("prepare_south_africa_data")

    log.info("=== South African data preparation starting ===")
    log.info("Input dir: %s", args.input_dir)
    log.info("Output: %s", args.output)
    log.info("Date range: %s to %s", args.start_date, args.end_date)
    log.info("Sample size: %d, seed: %d", args.sample_size, args.seed)

    # --- Validate paths ---
    _validate_paths(args)

    # --- Load config (for anonymisation settings) ---
    cfg = load_config(args.config)
    log.info("Config loaded from %s", args.config)
    log.info("replace_amounts: %s", getattr(getattr(cfg, "anonymise", None), "replace_amounts", False))

    # --- Parse dates ---
    start_date = pd.Timestamp(args.start_date, tz="UTC")
    end_date = pd.Timestamp(args.end_date + " 23:59:59", tz="UTC")

    # --- Select parquet files ---
    input_dir = Path(args.input_dir)
    all_files = _select_parquet_files(input_dir, start_date, end_date)
    log.info("Parquet files selected for date range: %d", len(all_files))

    # --- Resource pre-check ---
    total_size_mb = sum(f.stat().st_size for f in all_files) / 1024 / 1024
    log.info("Total selected parquet size: %.0f MB", total_size_mb)
    log.info("Processing incrementally (one file at a time) — peak memory ~%.1f GB",
             total_size_mb * 3 / 1024)

    # --- Confirm protected files will not be modified ---
    protected_files = [
        "data/annotations/pilot_adjudicated.jsonl",
        "data/annotations/pilot_annotator_a.jsonl",
        "data/annotations/pilot_annotator_b.jsonl",
        "data/processed/train_manifest.csv",
        "data/processed/validation_manifest.csv",
        "data/processed/test_manifest.csv",
        "data/interim/prepared.csv",
    ]
    for pf in protected_files:
        full_pf = Path(args.input_dir).parent.parent / pf
        if full_pf.exists():
            log.info("PROTECTED (not modified): %s", pf)

    # --- Incremental processing ---
    stats = ProcessingStats()
    seen_tweet_ids: set = set()
    all_canonical_chunks: list[pd.DataFrame] = []
    files_included = []
    files_skipped = []

    for parquet_path in all_files:
        log.info("Processing: %s", parquet_path.name)
        result_df = _process_single_file(
            parquet_path=parquet_path,
            start_date=start_date,
            end_date=end_date,
            seen_tweet_ids=seen_tweet_ids,
            cfg_anonymise=cfg,
            stats=stats,
        )
        if result_df is not None and len(result_df) > 0:
            all_canonical_chunks.append(result_df)
            files_included.append(str(parquet_path))
        else:
            files_skipped.append(str(parquet_path))

    if not all_canonical_chunks:
        log.error("No data produced after processing all files. Check date range and input.")
        return 1

    # --- Concatenate all chunks ---
    log.info("Concatenating %d file chunks...", len(all_canonical_chunks))
    full_df = pd.concat(all_canonical_chunks, ignore_index=True)
    log.info("Combined dataset: %d rows", len(full_df))

    # --- Cross-file exact text deduplication ---
    before_cross_dedup = len(full_df)
    full_df = full_df.drop_duplicates(subset=["text"], keep="first").reset_index(drop=True)
    cross_dedup_removed = before_cross_dedup - len(full_df)
    stats.exact_text_duplicates_removed += cross_dedup_removed
    log.info("Cross-file exact text deduplication removed %d rows; %d remaining",
             cross_dedup_removed, len(full_df))

    # --- Near-duplicate detection on candidate pool ---
    # IMPORTANT: Run near-dup only on the 200-record annotation sample pool
    # (candidates with sufficient keyword strata), NOT on all 2M+ records.
    # Running on all candidates would require ~8 GB RAM and is not feasible here.
    # Near-dup is used for sample diversity, not corpus-wide deduplication.
    nd_cfg = NearDupConfig(action="flag", seed=args.seed)
    log.info("Running near-duplicate detection on customer-feedback candidates...")
    full_df, nd_groups, nd_flagged = run_near_dup_on_candidates(full_df, nd_cfg)
    stats.near_dup_groups = nd_groups
    stats.near_dup_flagged = nd_flagged
    log.info("Near-dup: %d groups, %d flagged", nd_groups, nd_flagged)

    # --- Write canonical parquet output ---
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_columns = [c for c in CANONICAL_COLUMNS + AUDIT_COLUMNS if c in full_df.columns]
    full_df[output_columns].to_parquet(output_path, index=False)
    log.info("Canonical output written: %s (%d rows)", output_path, len(full_df))

    # Also write CSV if extension is .csv or if CSV sibling is requested
    csv_path = output_path.with_suffix(".csv")
    if args.output.endswith(".csv"):
        # User requested CSV directly
        csv_path = output_path
        full_df[output_columns].to_csv(csv_path, index=False)
        log.info("CSV output written: %s", csv_path)
    else:
        # Write a CSV copy too for tooling compatibility
        full_df[output_columns].to_csv(csv_path, index=False)
        log.info("CSV copy written: %s (%.0f MB)", csv_path, csv_path.stat().st_size / 1024 / 1024)

    # --- Data quality report ---
    report = _build_data_report(
        stats=stats,
        args=args,
        files_considered=[str(f) for f in all_files],
        files_included=files_included,
        files_skipped=files_skipped,
        nd_groups=nd_groups,
        nd_flagged=nd_flagged,
        total_rows_final=len(full_df),
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("Data quality report written: %s", report_path)

    # --- Annotation sample selection ---
    log.info("Selecting annotation sample (n=%d, seed=%d)...", args.sample_size, args.seed)
    sample_df = select_annotation_sample(
        full_df,
        sample_size=args.sample_size,
        seed=args.seed,
        max_per_bank=args.max_per_bank,
    )
    log.info("Annotation sample: %d records selected", len(sample_df))

    # --- Write unannotated annotation JSONL (gold-label-free) ---
    annotation_path = Path(args.annotation_output)
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_records = to_annotation_records(sample_df)
    with open(annotation_path, "w", encoding="utf-8") as fh:
        for rec in annotation_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log.info("Unannotated annotation sample written: %s (%d records)", annotation_path, len(annotation_records))

    # --- Sample composition report ---
    nd_groups_in_sample = len(
        {row["near_dup_group_id"] for _, row in sample_df.iterrows()
         if row.get("near_dup_group_id") and pd.notna(row.get("near_dup_group_id"))}
    )
    sample_report = _build_sample_report(sample_df, args, nd_groups_in_sample)
    sample_report_path = Path(args.sample_report)
    sample_report_path.parent.mkdir(parents=True, exist_ok=True)
    sample_report_path.write_text(json.dumps(sample_report, indent=2, default=str), encoding="utf-8")
    log.info("Sample report written: %s", sample_report_path)

    # --- Update source provenance JSON ---
    provenance_path = Path(args.report).parent / "south_africa_source_provenance.json"
    provenance = {
        "dataset_name": "Tweets of Popular South African Banks",
        "project_author": "Nicholas Blomerus",
        "github_repository": "https://github.com/nblomerus/South-African-Bank-Sentiment-Analysis",
        "kaggle_dataset": "https://www.kaggle.com/datasets/nicholasblomerus/twitter-analysis-of-popular-south-african-banks",
        "collection_period": "2006-01-01 to 2023-01-01",
        "collection_mechanism": "sntwitter (snscrape)",
        "banks": ["FNB", "Absa", "Nedbank", "Capitec", "Standard Bank"],
        "github_repo_licence": "MIT (applies to software/code in the repository)",
        "kaggle_dataset_licence": "Kaggle dataset licence requires independent confirmation before publication",
        "twitter_content_note": (
            "Twitter/X content redistribution is governed by the Twitter/X Terms of Service "
            "and Developer Agreement. The MIT licence on the collection code does not resolve "
            "tweet-content reuse obligations. This must be assessed independently before publication."
        ),
        "study_date_range_used": {
            "start": args.start_date,
            "end": args.end_date,
            "rationale": (
                "2018–2022 selected for contemporary digital banking relevance, "
                "stronger coverage of mobile/online banking, and manageable scope. "
                "This is a study-scope decision, not a data-quality filtering decision."
            ),
        },
        "source_identifier_in_canonical": SOURCE_NAME,
        "region_in_canonical": REGION,
        "region_provenance_basis": (
            "All five tracked institutions (FNB, Absa, Nedbank, Capitec, Standard Bank) "
            "are South African retail banks. The dataset was constructed to collect SA banking "
            "Twitter content. Bank column contains only SA bank identifiers. "
            "Region is not inferred from bank names alone — it is confirmed by the dataset's scope."
        ),
        "raw_text_column": "Tweet",
        "raw_text_rationale": (
            "The Tweet column contains raw collected tweet text as returned by the Twitter API. "
            "No pre-cleaned text column exists. The Tweet field is the authoritative source text."
        ),
        "columns_dropped": ["Username (author handle — personal identifier)", "__index_level_0__ (pandas artifact)"],
        "tweet_id_handling": "Hashed into record_id (sha256); raw Tweet_Id not stored in canonical output",
        "preparation_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    log.info("Source provenance updated: %s", provenance_path)

    # --- Final summary ---
    log.info("=== Preparation complete ===")
    log.info("Total rows produced: %d", len(full_df))
    log.info("Customer-feedback candidates: %d", stats.customer_feedback_candidates)
    log.info("Annotation sample: %d records", len(annotation_records))
    log.info("Near-dup groups in full dataset: %d", nd_groups)
    log.info("Output: %s", output_path)
    log.info("Annotation: %s", annotation_path)

    print("\nSouth African data preparation complete.")
    print(f"  Rows produced:            {len(full_df):,}")
    print(f"  Customer-feedback cands:  {stats.customer_feedback_candidates:,}")
    print(f"  Near-dup groups (cands):  {nd_groups:,}")
    print(f"  Annotation sample:        {len(annotation_records)}")
    print(f"  Output parquet:           {output_path}")
    print(f"  Data report:              {report_path}")
    print(f"  Annotation sample:        {annotation_path}")
    print(f"  Sample report:            {sample_report_path}")
    print()
    print("No gold labels were created. No models were trained.")
    print("The international gold dataset was not modified.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
