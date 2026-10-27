"""Canonical data ingestion pipeline for the banking-tasci project.

Converts schema-validated `sampledbanktweet.csv` and `bank_reviews3.csv`
rows into a single canonical record schema (`CANONICAL_COLUMNS`) via a
fixed stage order: validate -> normalise -> drop empty -> drop exact
duplicate -> anonymise -> map to Canonical_Record fields.

Requirements:
- 7.1: produce a Canonical_Record populating every CANONICAL_COLUMNS field
  for each schema-validated tweet row.
- 7.2: map `review` -> `text` and `review_title_by_user` -> `title` for
  each schema-validated review row.
- 7.3: `record_id` is a deterministic hash of source + normalised text.
- 7.4: `context_available=False` and `previous_text="[NO_CONTEXT]"` for
  every Canonical_Record produced.
- 7.5: `rating` is carried as metadata only; it is never used to derive
  any other field.
- 7.8: always return a DataFrame with CANONICAL_COLUMNS, even when a
  source yields zero rows.
- 7.9: propagate SchemaValidationError unchanged to the caller; halt
  processing for that file.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from banking_tasci.data import clean
from banking_tasci.data.clean import NearDupConfig, detect_near_duplicates
from banking_tasci.data.anonymise import AnonymisationAudit, anonymise_batch
from banking_tasci.data.schema import validate_reviews_schema, validate_tweets_schema
from banking_tasci.logging_utils import get_logger

if TYPE_CHECKING:
    from banking_tasci.config import Config

CANONICAL_COLUMNS = [
    "record_id",
    "source",
    "region",
    "bank",
    "rating",
    "title",
    "text",
    "previous_text",
    "context_available",
    "thread_id",
    "created_at",
    "created_at_raw",
    "split",
]


@dataclass
class SourceStats:
    """Row-count bookkeeping for a single source's ingestion run."""

    source: str
    rows_before: int
    rows_after: int
    empty_removed: int
    exact_duplicate_removed: int
    near_dup_groups: int = 0
    near_dup_flagged: int = 0
    near_dup_removed: int = 0


@dataclass
class IngestionResult:
    """Combined output of `run_ingestion`."""

    records: pd.DataFrame  # CANONICAL_COLUMNS
    per_source_stats: list = field(default_factory=list)
    anonymisation_audit: AnonymisationAudit = field(default_factory=AnonymisationAudit)


def _empty_canonical_df() -> pd.DataFrame:
    """A zero-row DataFrame with exactly CANONICAL_COLUMNS (Req 7.8)."""
    return pd.DataFrame({col: pd.Series(dtype="object") for col in CANONICAL_COLUMNS})


def make_record_id(source: str, normalised_text: str) -> str:
    """Deterministic id: sha256(f"{source}:{normalised_text}")[:16] (Req 7.3)."""
    digest = hashlib.sha256(f"{source}:{normalised_text}".encode("utf-8")).hexdigest()
    return digest[:16]


def _normalise_created_at(value) -> "tuple[object, object]":
    """Normalise a raw date value into ``(created_at, created_at_raw)`` under a
    single, well-defined contract (Phase 3A Part 5):

    - a valid, parseable date becomes an ISO 8601 (date-level) string in
      ``created_at``, with ``created_at_raw = None`` (nothing to preserve);
    - a missing/empty value becomes ``(None, None)``;
    - a present-but-unparseable value becomes ``(None, <original string>)`` so
      the raw provenance is retained in ``created_at_raw`` while ``created_at``
      stays strictly ISO-or-null.

    ``created_at`` is therefore NEVER an arbitrary raw string — it is always
    either a valid ISO 8601 date string or ``None``.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    # Treat empty/whitespace-only strings as missing.
    if isinstance(value, str) and value.strip() == "":
        return None, None
    try:
        parsed = pd.to_datetime(value)
    except (ValueError, TypeError):
        return None, str(value)
    if pd.isna(parsed):
        return None, str(value)
    return parsed.date().isoformat(), None


def _near_dup_config_from_cfg(cfg: "Config") -> "NearDupConfig":
    """Build a NearDupConfig from the ``near_dup`` sub-section of ``cfg``.

    All fields fall back to NearDupConfig defaults when absent, so the
    pipeline remains backward-compatible with configs that have no
    ``near_dup`` section.
    """
    try:
        nd = cfg.near_dup  # type: ignore[attr-defined]
    except AttributeError:
        return NearDupConfig()

    def _g(key: str, default):
        try:
            v = getattr(nd, key, None)
            return v if v is not None else default
        except Exception:
            return default

    return NearDupConfig(
        threshold=float(_g("threshold", 0.7)),
        shingle_size=int(_g("shingle_size", 4)),
        num_perm=int(_g("num_perm", 128)),
        num_bands=int(_g("num_bands", 16)),
        action=str(_g("action", "flag")),
        min_group_size=int(_g("min_group_size", 2)),
        seed=int(_g("seed", 42)),
    )


def ingest_tweets(df: pd.DataFrame, cfg: "Config") -> tuple[pd.DataFrame, SourceStats, AnonymisationAudit]:
    """Convert a schema-validated tweets dataframe into Canonical_Records.

    Stage order: validate -> normalise -> drop empty -> drop exact
    duplicate -> anonymise -> map to Canonical_Record fields (Req 7.1).
    """
    logger = get_logger(__name__)
    source = cfg.data.tweets_source_name
    region = cfg.data.default_region

    validate_tweets_schema(df, source)

    rows_before = len(df)

    working = df.copy()
    working["text"] = working["text"].apply(
        lambda v: clean.normalise_text(v) if not pd.isna(v) else v
    )

    working, empty_removed = clean.drop_empty_rows(working, "text")
    working, exact_duplicate_removed = clean.drop_exact_duplicates(working, ["text"])

    # Near-duplicate detection (Req 7.7).  Reads cfg.near_dup sub-section
    # when present; uses safe defaults when absent.
    near_dup_cfg = _near_dup_config_from_cfg(cfg)
    rows_before_nd = len(working)
    nd_result = detect_near_duplicates(working, "text", near_dup_cfg, record_id_col=None)
    working = nd_result.df  # may have rows dropped depending on action

    rows_after = len(working)
    stats = SourceStats(
        source=source,
        rows_before=rows_before,
        rows_after=rows_after,
        empty_removed=empty_removed,
        exact_duplicate_removed=exact_duplicate_removed,
        near_dup_groups=nd_result.num_groups,
        near_dup_flagged=nd_result.num_flagged,
        near_dup_removed=rows_before_nd - rows_after,
    )
    logger.info(
        "%s: empty_removed=%d exact_duplicate_removed=%d "
        "near_dup_groups=%d near_dup_flagged=%d",
        source,
        empty_removed,
        exact_duplicate_removed,
        nd_result.num_groups,
        nd_result.num_flagged,
    )

    if rows_after == 0:
        return _empty_canonical_df(), stats, AnonymisationAudit()

    normalised_texts = working["text"].tolist()
    anonymised_texts, audit = anonymise_batch(normalised_texts, cfg)

    records = pd.DataFrame(
        {
            "record_id": [make_record_id(source, t) for t in normalised_texts],
            "source": source,
            "region": region,
            "bank": None,
            "rating": None,
            "title": "",
            "text": anonymised_texts,
            "previous_text": "[NO_CONTEXT]",
            "context_available": False,
            "thread_id": None,
            "created_at": None,
            "created_at_raw": None,
            "split": None,
        }
    )
    records = records[CANONICAL_COLUMNS]
    return records, stats, audit


def ingest_reviews(df: pd.DataFrame, cfg: "Config") -> tuple[pd.DataFrame, SourceStats, AnonymisationAudit]:
    """Convert a schema-validated reviews dataframe into Canonical_Records.

    Stage order: validate -> normalise -> drop empty -> drop exact
    duplicate -> anonymise -> map to Canonical_Record fields (Req 7.2).
    `rating` is carried through as metadata only; it is never read to
    derive any other field (Req 7.5).
    """
    logger = get_logger(__name__)
    source = cfg.data.reviews_source_name
    region = cfg.data.default_region

    validate_reviews_schema(df, source)

    rows_before = len(df)

    working = df.copy()
    working["review"] = working["review"].apply(
        lambda v: clean.normalise_text(v) if not pd.isna(v) else v
    )

    working, empty_removed = clean.drop_empty_rows(working, "review")
    working, exact_duplicate_removed = clean.drop_exact_duplicates(working, ["review"])

    # Near-duplicate detection (Req 7.7).
    near_dup_cfg = _near_dup_config_from_cfg(cfg)
    rows_before_nd = len(working)
    nd_result = detect_near_duplicates(working, "review", near_dup_cfg, record_id_col=None)
    working = nd_result.df

    rows_after = len(working)
    stats = SourceStats(
        source=source,
        rows_before=rows_before,
        rows_after=rows_after,
        empty_removed=empty_removed,
        exact_duplicate_removed=exact_duplicate_removed,
        near_dup_groups=nd_result.num_groups,
        near_dup_flagged=nd_result.num_flagged,
        near_dup_removed=rows_before_nd - rows_after,
    )
    logger.info(
        "%s: empty_removed=%d exact_duplicate_removed=%d "
        "near_dup_groups=%d near_dup_flagged=%d",
        source,
        empty_removed,
        exact_duplicate_removed,
        nd_result.num_groups,
        nd_result.num_flagged,
    )

    if rows_after == 0:
        return _empty_canonical_df(), stats, AnonymisationAudit()

    normalised_reviews = working["review"].tolist()
    titles = [
        clean.normalise_text(v) if not pd.isna(v) else ""
        for v in working["review_title_by_user"].tolist()
    ]

    anonymised_reviews, review_audit = anonymise_batch(normalised_reviews, cfg)
    anonymised_titles, title_audit = anonymise_batch(titles, cfg)
    audit = review_audit.merge(title_audit)

    banks = working["bank"].where(~working["bank"].isna(), None).tolist()
    ratings = working["rating"].tolist()
    created_at_pairs = [_normalise_created_at(v) for v in working["date"].tolist()]
    created_ats = [pair[0] for pair in created_at_pairs]
    created_at_raws = [pair[1] for pair in created_at_pairs]

    records = pd.DataFrame(
        {
            "record_id": [make_record_id(source, t) for t in normalised_reviews],
            "source": source,
            "region": region,
            "bank": banks,
            "rating": ratings,
            "title": anonymised_titles,
            "text": anonymised_reviews,
            "previous_text": "[NO_CONTEXT]",
            "context_available": False,
            "thread_id": None,
            "created_at": created_ats,
            "created_at_raw": created_at_raws,
            "split": None,
        }
    )
    records = records[CANONICAL_COLUMNS]
    return records, stats, audit


def run_ingestion(tweets_df: pd.DataFrame, reviews_df: pd.DataFrame, cfg: "Config") -> IngestionResult:
    """Run both sub-pipelines and return a combined IngestionResult.

    Always returns a DataFrame with CANONICAL_COLUMNS even if a source
    yields zero rows (Req 7.8). Propagates SchemaValidationError from
    either sub-pipeline unchanged, halting processing (Req 7.9).
    """
    tweet_records, tweet_stats, tweet_audit = ingest_tweets(tweets_df, cfg)
    review_records, review_stats, review_audit = ingest_reviews(reviews_df, cfg)

    # Exclude empty frames and cast the remainder to ``object`` before
    # concatenation so pandas does not emit the FutureWarning about
    # concatenating empty or all-NA columns (Req 31.1). Casting to
    # ``object`` matches the canonical schema (see ``_empty_canonical_df``)
    # and leaves record_id, row filtering, and row counts untouched
    # (Req 31.3).
    frames = [f.astype(object) for f in (tweet_records, review_records) if not f.empty]
    if frames:
        combined_records = pd.concat(frames, ignore_index=True)
    else:
        combined_records = pd.DataFrame(columns=CANONICAL_COLUMNS)
    combined_records = combined_records.reindex(columns=CANONICAL_COLUMNS)

    combined_audit = tweet_audit.merge(review_audit)

    return IngestionResult(
        records=combined_records,
        per_source_stats=[tweet_stats, review_stats],
        anonymisation_audit=combined_audit,
    )


def write_data_quality_report(result: IngestionResult, report_path: "str | Path") -> None:
    """Serialise input/output/removed counts (overall + per-source) and
    `anonymisation_audit.to_dict()` to JSON at `report_path`.

    `overall` is the sum of `result.per_source_stats`; `per_source` keys
    are each `SourceStats.source` name (Req 8.3). Parent directories of
    `report_path` are created if they do not already exist (Req 8.2).

    Near-duplicate statistics are included under `near_duplicates` in both
    the `overall` and each `per_source` entry (Req 7.7).
    """
    overall = {
        "rows_before": 0,
        "rows_after": 0,
        "empty_removed": 0,
        "exact_duplicate_removed": 0,
        "near_dup_groups": 0,
        "near_dup_flagged": 0,
        "near_dup_removed": 0,
    }
    per_source: dict[str, dict[str, int]] = {}

    for stats in result.per_source_stats:
        overall["rows_before"] += stats.rows_before
        overall["rows_after"] += stats.rows_after
        overall["empty_removed"] += stats.empty_removed
        overall["exact_duplicate_removed"] += stats.exact_duplicate_removed
        overall["near_dup_groups"] += stats.near_dup_groups
        overall["near_dup_flagged"] += stats.near_dup_flagged
        overall["near_dup_removed"] += stats.near_dup_removed

        per_source[stats.source] = {
            "rows_before": stats.rows_before,
            "rows_after": stats.rows_after,
            "empty_removed": stats.empty_removed,
            "exact_duplicate_removed": stats.exact_duplicate_removed,
            "near_dup_groups": stats.near_dup_groups,
            "near_dup_flagged": stats.near_dup_flagged,
            "near_dup_removed": stats.near_dup_removed,
        }

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall": overall,
        "per_source": per_source,
        "anonymisation_audit": result.anonymisation_audit.to_dict(),
    }

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
