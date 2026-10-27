"""Prepare_Data_CLI: command-line entry point for the Ingestion_Pipeline.

Usage:
    python scripts/prepare_data.py \\
        --tweets data/raw/sampledbanktweet.csv \\
        --reviews data/raw/bank_reviews3.csv \\
        --output data/interim/prepared.csv \\
        --report outputs/data_report.json

Wires Config_Loader -> Seed_Utility -> CSV read -> Schema_Validator ->
Ingestion_Pipeline -> canonical output write -> best-effort
Data_Quality_Reporter write, using Logging_Utility for all status output
(Req 9.1-9.5).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running this script directly without installing the package.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd  # noqa: E402

from banking_tasci.config import load_config  # noqa: E402
from banking_tasci.data.ingest import run_ingestion, write_data_quality_report  # noqa: E402
from banking_tasci.data.schema import (  # noqa: E402
    SchemaValidationError,
    validate_reviews_schema,
    validate_tweets_schema,
)
from banking_tasci.logging_utils import get_logger  # noqa: E402
from banking_tasci.seed import set_seed_from_config  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "base.yaml"


def build_arg_parser() -> argparse.ArgumentParser:
    """Defines --tweets, --reviews, --output, --report, --config
    (all with --help text); required unless supplied via --config."""
    parser = argparse.ArgumentParser(
        prog="prepare_data.py",
        description=(
            "Validate, clean, anonymise, and convert the raw tweets and "
            "reviews CSVs into a canonical Ingestion_Pipeline output, plus "
            "a JSON data-quality report."
        ),
    )
    parser.add_argument(
        "--tweets",
        required=True,
        help="Path to the raw tweets CSV (e.g. data/raw/sampledbanktweet.csv).",
    )
    parser.add_argument(
        "--reviews",
        required=True,
        help="Path to the raw reviews CSV (e.g. data/raw/bank_reviews3.csv).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the canonical ingestion output CSV (e.g. data/interim/prepared.csv).",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Path to write the JSON data-quality report (e.g. outputs/data_report.json).",
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="Path to the YAML configuration file (default: configs/base.yaml).",
    )
    return parser


def _check_readable_input(path_str: str, label: str) -> str | None:
    """Return a descriptive error message if `path_str` is missing or
    unreadable, else None (Req 9.3)."""
    path = Path(path_str)
    if not path.exists():
        return f"error: --{label} path does not exist: {path_str}"
    if not path.is_file():
        return f"error: --{label} path is not a file: {path_str}"
    if not os.access(path, os.R_OK):
        return f"error: --{label} path is not readable: {path_str}"
    return None


def main(argv: list[str] | None = None) -> int:
    """Parse args -> validate paths exist/readable (else print error, return
    non-zero) -> load_config -> set_seed_from_config -> read CSVs ->
    schema-validate -> run_ingestion -> write canonical output to --output
    (always attempted) -> try to write_data_quality_report to --report,
    catching and logging any failure without affecting the process's exit
    code -> return 0 on success."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Validate input paths exist/readable BEFORE any config loading or
    # ingestion runs (Req 9.3).
    for path_str, label in ((args.tweets, "tweets"), (args.reviews, "reviews")):
        error = _check_readable_input(path_str, label)
        if error is not None:
            print(error, file=sys.stderr)
            return 1

    cfg = load_config(args.config)
    set_seed_from_config(cfg)

    logger = get_logger(__name__, cfg)

    logger.info("Reading tweets from %s", args.tweets)
    tweets_df = pd.read_csv(args.tweets)
    logger.info("Reading reviews from %s", args.reviews)
    reviews_df = pd.read_csv(args.reviews)

    try:
        validate_tweets_schema(tweets_df, args.tweets)
        validate_reviews_schema(reviews_df, args.reviews)
    except SchemaValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    logger.info("Running ingestion pipeline")
    result = run_ingestion(tweets_df, reviews_df, cfg)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.records.to_csv(output_path, index=False)
    logger.info("Wrote canonical output to %s (%d rows)", output_path, len(result.records))

    try:
        write_data_quality_report(result, args.report)
        logger.info("Wrote data quality report to %s", args.report)
    except Exception as exc:  # noqa: BLE001 - report-write failure must not affect exit code (Req 9.4)
        logger.error("Failed to write data quality report to %s: %s", args.report, exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
