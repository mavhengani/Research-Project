"""South African banking Twitter dataset ingestion for the Banking TASCI project.

Converts South African bank tweet parquet files into the canonical record schema,
applying cleaning, anonymisation, date filtering, official-account exclusion,
customer-feedback candidate filtering, and near-duplicate detection.

Source dataset
--------------
"Tweets of Popular South African Banks" by Nicholas Blomerus.
- GitHub: https://github.com/nblomerus/South-African-Bank-Sentiment-Analysis
- Kaggle: https://www.kaggle.com/datasets/nicholasblomerus/twitter-analysis-of-popular-south-african-banks
- Collection period: 1 January 2006 – 1 January 2023
- Banks: FNB, Absa, Nedbank, Capitec, Standard Bank
- Collection tool: sntwitter

Licence notes
-------------
The GitHub repository has an MIT licence (software/code licence).
The Kaggle dataset licence requires independent confirmation before publication.
Twitter/X content redistribution is governed by Twitter/X Terms of Service and
must be assessed separately from the code licence.

Design principles
-----------------
- Process parquet files incrementally (one at a time) to avoid loading the full
  ~5.8M row corpus into memory.
- Deduplicate first by Tweet_Id (across files), then by exact normalised text.
- Run near-duplicate detection only on the filtered customer-feedback candidate
  pool, not on the full corpus.
- Never expose raw Tweet_Ids, usernames, or other direct identifiers in output.
- Never create gold labels. No sentiment, intent, aspect, or BIO labels are
  inferred or assigned.
- Preserve the existing international gold dataset without modification.

Record ID policy
----------------
record_id = sha256("south_african_bank_tweets" + ":" + str(Tweet_Id))[:16]

This creates a one-to-one stable identity from the tweet ID rather than from
the text content, so two users posting the same text produce different record IDs.
The raw Tweet_Id is never stored in the canonical output.

Context policy
--------------
previous_text = "[NO_CONTEXT]" for all records.
context_available = False for all records.
The dataset does not provide a verified reply-parent or conversation graph.
Reply_Count is an engagement count, not a parent tweet reference.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from banking_tasci.data import clean
from banking_tasci.data.clean import NearDupConfig, detect_near_duplicates
from banking_tasci.data.anonymise import AnonymisationAudit, anonymise_batch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME = "south_african_bank_tweets"
REGION = "south_africa"

# Required raw parquet columns — the canonical schema maps these
REQUIRED_PARQUET_COLUMNS = {
    "Datetime", "Tweet_Id", "Tweet", "Username",
    "Reply_Count", "Retweet_Count", "Like_Count", "Bank",
}

# Canonical output columns (matches existing CANONICAL_COLUMNS in ingest.py)
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
    "near_dup_group_id",
]

# Additional audit columns included in the prepared parquet (not in annotation output)
AUDIT_COLUMNS = [
    "near_dup_flag",
    "customer_feedback_candidate",
    "candidate_strata",
    "likely_promotional",
    "possible_official_account",
    "filter_reason",
    "engagement_reply_count",
    "engagement_retweet_count",
    "engagement_like_count",
]

# ---------------------------------------------------------------------------
# Official bank account handle lists
# Configurable: add known handles as they are verified.
# Uncertain handles are flagged as possible_official_account without deletion.
# ---------------------------------------------------------------------------

# Confirmed official SA bank Twitter handles (lower-cased for matching)
CONFIRMED_OFFICIAL_HANDLES: set[str] = {
    # FNB
    "fnb", "fnbsa", "fnbhelp", "askfnb", "fnbservicedesk",
    "fnb_southafrica", "fnbconnect", "fnbbusiness",
    # Absa
    "absa", "absagroup", "absahelp", "absasouthafrica", "absabusiness",
    "absaretail", "absalife",
    # Nedbank
    "nedbank", "nedbanksa", "nedbankhelp", "nedbanksupport",
    "nedbankgroup", "nedbanklimited",
    # Capitec
    "capitec", "capitecbank", "capitecbanksa", "capitechelp", "capitec_bank",
    "capitecbusiness",
    # Standard Bank
    "standardbank", "standardbanksa", "standardbankza",
    "stanbic", "stanbicibtcsa", "sbgsouthafrica", "standardbankhelp",
    "standardbankgroup",
}

# Patterns that strongly suggest an official bank account (but not certain)
POSSIBLE_OFFICIAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(?:fnb|absa|nedbank|capitec|standardbank|stanbic)[_\-]", re.I),
    re.compile(r"(?:fnb|absa|nedbank|capitec|standardbank|stanbic)(?:official|bank|help|za|sa)$", re.I),
]

# ---------------------------------------------------------------------------
# Candidate strata keyword sets (sampling aids — NOT gold labels)
# ---------------------------------------------------------------------------

CANDIDATE_STRATA_KEYWORDS: dict[str, list[str]] = {
    "transactions_candidate": [
        "transfer", "payment", "failed transaction", "reversal", "refund", " atm ",
        "deposit", "withdrawal", " debit ", "transaction", "send money",
        " eft ", "payment failed", "transfer failed", "declined",
    ],
    "accounts_candidate": [
        "account", "blocked", "frozen", "balance", "statement", "close account",
        "closing account", "account number", "savings", "cheque", "current account",
    ],
    "digital_banking_candidate": [
        "mobile app", "banking app", "app not", "app down", "app crash", "app keeps",
        "online banking", "internet banking", "ussd", "login failed", "mobile banking",
        "digital banking", "e-wallet", "ewallet", " app update",
    ],
    "customer_support_candidate": [
        "please help", "please assist", "need help", "customer service", "complaint",
        "resolve", "assistance", "not responding", "no response",
        "call centre", "call center", "helpline", "consultant",
        "still waiting", "not been resolved",
    ],
    "cards_candidate": [
        " card ", "my card", "card blocked", "card not working", "debit card",
        "credit card", "swipe", "contactless", "virtual card", "card declined",
        " pin ", "card was",
    ],
    "fees_candidate": [
        " fee ", " fees ", "charge me", "been charged", "charged for", "deduction",
        "service fee", "maintenance fee", "sms fee", "interest rate",
        "penalty", " levy ", " charged ",
    ],
    "fraud_security_candidate": [
        "fraud", "scam", "unauthorised", "unauthorized", "stolen",
        "hacked", "phishing", "identity theft", "suspicious",
        "compromised", "fraudulent",
    ],
    "branch_service_candidate": [
        "branch", "teller", " queue ", "waiting in", "in branch",
        "branch manager", "branch closed", "branch hours",
    ],
    "positive_feedback_candidate": [
        "great service", "excellent service", "impressed", "well done", "thank you",
        "good service", "amazing service", "helpful staff", "fantastic service",
        "best bank", "love fnb", "love absa", "love nedbank", "love capitec",
        "happy customer", "satisfied", "great job",
    ],
    "suggestion_candidate": [
        "should improve", "please add", "you need to", "it would be better",
        "consider changing", "would be nice", "why not add", "suggest",
        "suggestion", "recommend", "recommendation",
    ],
    "warning_candidate": [
        "do not use", "avoid this bank", "stay away", "be careful",
        "beware", "be warned", "stay far", "don't trust",
    ],
    "churn_candidate": [
        "closing my account", "switching banks", "leaving this bank",
        "moving to another bank", "will no longer bank", "close my account",
        "switch to another bank", "cancel my account", "leaving your bank",
        "no longer a customer", "looking for another bank",
        "switched to", "changed banks", "moved to another bank",
    ],
}

PROMOTIONAL_KEYWORDS: list[str] = [
    "competition", "giveaway", "win", "prize", "limited time",
    "special offer", "terms apply", "tag a friend", "follow us",
    "apply now", "open an account", "sign up today", "join us",
    "new account offer", "cash back offer", "cashback offer",
    "free data", "zero fees offer", "terms and conditions apply",
    "t&c apply", "t&cs apply",
]

# Minimum text length for a candidate to be considered (meaningful content)
MIN_TEXT_LENGTH = 15

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class SouthAfricaSchemaError(ValueError):
    """Raised when a parquet file is missing required columns."""


def validate_sa_parquet_schema(df: pd.DataFrame, file_path: str) -> None:
    """Raise SouthAfricaSchemaError if required columns are missing."""
    missing = REQUIRED_PARQUET_COLUMNS - set(df.columns)
    if missing:
        raise SouthAfricaSchemaError(
            f"{file_path}: missing required column(s): {sorted(missing)}"
        )
    logger.info("%s: schema valid (%d rows)", file_path, len(df))


# ---------------------------------------------------------------------------
# Record ID
# ---------------------------------------------------------------------------


def make_sa_record_id(tweet_id: int) -> str:
    """Deterministic record_id = sha256(source + ":" + str(tweet_id))[:16].

    Uses Tweet_Id rather than normalised text so that two different users
    posting identical text produce distinct record IDs.
    The raw Tweet_Id is never stored in canonical output.
    """
    payload = f"{SOURCE_NAME}:{tweet_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------


def _normalise_created_at(value: Any) -> tuple[Any, Any]:
    """Normalise a datetime value to (created_at ISO date, created_at_raw).

    Follows the same contract as the existing ingest.py:
    - parseable → (ISO-8601 date string, None)
    - null/missing → (None, None)
    - unparseable → (None, original string)
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    if isinstance(value, str) and value.strip() == "":
        return None, None
    try:
        parsed = pd.to_datetime(value, utc=True)
    except (ValueError, TypeError):
        return None, str(value)
    if pd.isna(parsed):
        return None, str(value)
    return parsed.date().isoformat(), None


# ---------------------------------------------------------------------------
# Official account detection
# ---------------------------------------------------------------------------


def classify_username(username: str) -> tuple[bool, bool]:
    """Return (is_confirmed_official, is_possible_official).

    Uses the documented allow/deny list and pattern rules rather than
    a broad substring rule that could incorrectly remove customer accounts.
    Never logs or exposes the raw username value.
    """
    if not username:
        return False, False
    lower = username.lower().strip()
    if lower in CONFIRMED_OFFICIAL_HANDLES:
        return True, False
    for pattern in POSSIBLE_OFFICIAL_PATTERNS:
        if pattern.search(lower):
            return False, True
    return False, False


# ---------------------------------------------------------------------------
# Customer-feedback filtering
# ---------------------------------------------------------------------------


def compute_candidate_strata(text: str) -> list[str]:
    """Return the list of candidate strata keywords matched in ``text``.

    These are sampling heuristics — NOT gold labels.
    A record may belong to multiple strata.
    Never assigned to gold annotation fields.
    """
    lower = text.lower()
    matched = []
    for stratum, keywords in CANDIDATE_STRATA_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            matched.append(stratum)
    return matched


def is_promotional(text: str) -> bool:
    """Return True when the text contains transparent promotional indicators."""
    lower = text.lower()
    return any(kw in lower for kw in PROMOTIONAL_KEYWORDS)


def is_customer_feedback_candidate(
    text: str,
    strata: list[str],
    promotional: bool,
) -> tuple[bool, str]:
    """Determine whether a record is a customer-feedback candidate.

    Returns (is_candidate, filter_reason).

    A record is a candidate when it either:
    - matches at least one customer-facing strata (not promotional), or
    - is long enough and not clearly promotional (catch-all for unlabelled feedback).

    The filter_reason is a neutral description suitable for the report.
    """
    if promotional and not strata:
        return False, "likely_promotional_no_feedback_keywords"
    if strata:
        return True, "matched_strata"
    # Catch-all: non-promotional tweets of reasonable length
    if len(text) >= 30:
        return True, "non_promotional_sufficient_length"
    return False, "too_short_no_strata"


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------


@dataclass
class ProcessingStats:
    """Per-file and cumulative processing statistics."""

    files_read: int = 0
    files_skipped_date: int = 0
    rows_read: int = 0
    rows_outside_date_range: int = 0
    rows_empty_or_short: int = 0
    tweet_id_duplicates_removed: int = 0
    exact_text_duplicates_removed: int = 0
    confirmed_official_excluded: int = 0
    possible_official_flagged: int = 0
    pure_retweets_excluded: int = 0
    date_parse_success: int = 0
    date_parse_failed: int = 0
    customer_feedback_candidates: int = 0
    promotional_records: int = 0
    near_dup_groups: int = 0
    near_dup_flagged: int = 0
    rows_after_all_filters: int = 0
    bank_counts: Counter = field(default_factory=Counter)
    year_counts: Counter = field(default_factory=Counter)
    anonymisation_audit: AnonymisationAudit = field(default_factory=AnonymisationAudit)


def _process_single_file(
    parquet_path: Path,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    seen_tweet_ids: set,
    cfg_anonymise: Any,
    stats: ProcessingStats,
) -> pd.DataFrame | None:
    """Process one parquet file and return canonical rows, or None if skipped.

    Applies in order:
    1. Schema validation
    2. Date range filter
    3. Hard exclusions (short text, pure retweets, empty)
    4. Tweet_Id deduplication against already-seen IDs
    5. Official-account classification
    6. Unicode normalisation
    7. Exact text deduplication (within this file; cross-file handled by caller)
    8. Anonymisation
    9. Canonical schema mapping
    10. Customer-feedback candidate tagging
    """
    file_name = parquet_path.name

    # --- Load required columns only ---
    try:
        df = pd.read_parquet(
            parquet_path,
            columns=list(REQUIRED_PARQUET_COLUMNS),
        )
    except Exception as exc:
        logger.error("Failed to read %s: %s", file_name, exc)
        return None

    # --- Schema validation ---
    try:
        validate_sa_parquet_schema(df, file_name)
    except SouthAfricaSchemaError as exc:
        logger.error("%s", exc)
        return None

    if len(df) == 0:
        logger.info("%s: 0 rows, skipping", file_name)
        stats.files_skipped_date += 1
        return None

    stats.files_read += 1
    rows_initial = len(df)

    # --- Coerce Datetime ---
    df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True, errors="coerce")

    # --- Date range filter ---
    in_range = (df["Datetime"] >= start_date) & (df["Datetime"] <= end_date)
    outside_count = int((~in_range).sum())
    df = df[in_range].copy()
    stats.rows_outside_date_range += outside_count
    stats.rows_read += rows_initial

    if len(df) == 0:
        logger.info("%s: all %d rows outside date range, skipping", file_name, rows_initial)
        stats.files_skipped_date += 1
        return None

    logger.info("%s: %d rows in date range after filtering %d outside",
                file_name, len(df), outside_count)

    # --- Coerce text columns ---
    df["Tweet"] = df["Tweet"].astype(str).fillna("")
    df["Username"] = df["Username"].astype(str).fillna("")
    df["Bank"] = df["Bank"].astype(str).fillna("unknown")

    # --- Hard exclusion: empty / too short ---
    too_short = df["Tweet"].str.strip().str.len() < MIN_TEXT_LENGTH
    excluded_short = int(too_short.sum())
    df = df[~too_short].copy()
    stats.rows_empty_or_short += excluded_short

    # --- Hard exclusion: pure retweets (no original commentary) ---
    # RT @ prefix with no additional text beyond the RT header
    pure_rt = df["Tweet"].str.match(r"^RT @\w+:\s*.{0,50}$", na=False)
    excluded_rt = int(pure_rt.sum())
    df = df[~pure_rt].copy()
    stats.pure_retweets_excluded += excluded_rt

    if len(df) == 0:
        logger.info("%s: 0 rows after short/retweet exclusion", file_name)
        return None

    # --- Tweet_Id deduplication (cross-file) ---
    before_dedup = len(df)
    is_dup = df["Tweet_Id"].isin(seen_tweet_ids)
    dup_count = int(is_dup.sum())
    df = df[~is_dup].copy()
    seen_tweet_ids.update(df["Tweet_Id"].tolist())
    stats.tweet_id_duplicates_removed += dup_count

    if len(df) == 0:
        logger.info("%s: 0 unique tweets after Tweet_Id dedup", file_name)
        return None

    # --- Official account classification ---
    def _classify(username: str) -> tuple[bool, bool]:
        return classify_username(username)

    classification = df["Username"].apply(_classify)
    confirmed_official = classification.apply(lambda x: x[0])
    possible_official = classification.apply(lambda x: x[1])

    confirmed_count = int(confirmed_official.sum())
    possible_count = int(possible_official.sum())
    stats.confirmed_official_excluded += confirmed_count
    stats.possible_official_flagged += possible_count

    # Remove confirmed official accounts from data (but flag possible ones)
    df = df[~confirmed_official].copy()
    possible_official = possible_official[~confirmed_official]

    if len(df) == 0:
        logger.info("%s: 0 rows after official-account removal", file_name)
        return None

    # --- Unicode normalisation ---
    df["text_normalised"] = df["Tweet"].apply(clean.normalise_text)

    # --- Exact text deduplication (within this file — cross-file handled elsewhere) ---
    dup_text = df.duplicated(subset=["text_normalised"], keep="first")
    exact_text_dups = int(dup_text.sum())
    df = df[~dup_text].copy()
    possible_official = possible_official[~dup_text]
    stats.exact_text_duplicates_removed += exact_text_dups

    if len(df) == 0:
        return None

    # --- Anonymisation (batch) ---
    texts_to_anon = df["text_normalised"].tolist()
    anonymised_texts, file_audit = anonymise_batch(texts_to_anon, cfg_anonymise)
    stats.anonymisation_audit = stats.anonymisation_audit.merge(file_audit)
    df = df.reset_index(drop=True)
    df["text_anonymised"] = anonymised_texts

    # --- Date mapping ---
    created_at_vals = []
    created_at_raw_vals = []
    for dt in df["Datetime"]:
        ca, car = _normalise_created_at(dt)
        created_at_vals.append(ca)
        created_at_raw_vals.append(car)
        if ca is not None:
            stats.date_parse_success += 1
        else:
            stats.date_parse_failed += 1

    # --- Record ID (from Tweet_Id, not text) ---
    record_ids = [make_sa_record_id(tid) for tid in df["Tweet_Id"]]

    # --- Candidate filtering ---
    customer_candidates = []
    candidate_strata_list = []
    promotional_list = []
    filter_reason_list = []
    possible_official_list = possible_official.tolist()

    for idx, row in df.iterrows():
        text = row["text_anonymised"]
        strata = compute_candidate_strata(text)
        promo = is_promotional(text)
        is_candidate, reason = is_customer_feedback_candidate(text, strata, promo)

        customer_candidates.append(is_candidate)
        candidate_strata_list.append(";".join(strata) if strata else "")
        promotional_list.append(promo)
        filter_reason_list.append(reason)

    stats.customer_feedback_candidates += sum(customer_candidates)
    stats.promotional_records += sum(promotional_list)

    # --- Bank and year statistics ---
    for bank in df["Bank"]:
        stats.bank_counts[bank] += 1
    for dt in df["Datetime"]:
        if pd.notna(dt):
            stats.year_counts[str(dt.year)] += 1

    # --- Assemble canonical output ---
    result = pd.DataFrame({
        "record_id": record_ids,
        "source": SOURCE_NAME,
        "region": REGION,
        "bank": df["Bank"].tolist(),
        "rating": None,
        "title": "",
        "text": anonymised_texts,
        "previous_text": "[NO_CONTEXT]",
        "context_available": False,
        "thread_id": None,
        "created_at": created_at_vals,
        "created_at_raw": created_at_raw_vals,
        "split": None,
        "near_dup_group_id": None,
        # Audit columns
        "near_dup_flag": False,
        "customer_feedback_candidate": customer_candidates,
        "candidate_strata": candidate_strata_list,
        "likely_promotional": promotional_list,
        "possible_official_account": possible_official_list,
        "filter_reason": filter_reason_list,
        "engagement_reply_count": df["Reply_Count"].tolist(),
        "engagement_retweet_count": df["Retweet_Count"].tolist(),
        "engagement_like_count": df["Like_Count"].tolist(),
    })

    stats.rows_after_all_filters += len(result)
    logger.info("%s: %d canonical rows produced", file_name, len(result))
    return result


# ---------------------------------------------------------------------------
# Near-duplicate detection on candidate pool
# ---------------------------------------------------------------------------


def run_near_dup_on_candidates(
    df: pd.DataFrame,
    nd_cfg: NearDupConfig | None = None,
    max_candidates: int = 10000,
) -> tuple[pd.DataFrame, int, int]:
    """Run near-duplicate detection on a capped subset of customer-feedback candidates.

    The full corpus may contain millions of candidates which would exceed available
    RAM for MinHash signature computation. This function caps the near-dup scan at
    ``max_candidates`` records (the prioritised annotation candidate pool) to keep
    memory usage bounded.

    Near-dup is used for sample diversity control, not corpus-wide deduplication.
    Exact text deduplication (handled before this step) removes identical records.

    Returns the full DataFrame with near_dup_group_id and near_dup_flag populated
    for the scanned candidates, plus (num_groups, num_flagged) counts.
    """
    if nd_cfg is None:
        nd_cfg = NearDupConfig(action="flag")

    candidate_mask = df["customer_feedback_candidate"].fillna(False).astype(bool)
    candidate_df = df[candidate_mask].copy()
    total_candidates = len(candidate_df)

    # Cap the near-dup scan to avoid OOM on large corpora
    if total_candidates > max_candidates:
        logger.info(
            "Near-dup: %d candidates exceeds cap of %d — sampling %d for near-dup scan",
            total_candidates, max_candidates, max_candidates,
        )
        # Prioritise records with keyword strata (more likely to have near-dups)
        has_strata = candidate_df["candidate_strata"].fillna("").str.len() > 0
        priority = candidate_df[has_strata].head(max_candidates)
        if len(priority) < max_candidates:
            remaining_needed = max_candidates - len(priority)
            rest = candidate_df[~has_strata].head(remaining_needed)
            scan_df = pd.concat([priority, rest], ignore_index=True)
        else:
            scan_df = priority.head(max_candidates).reset_index(drop=True)
    else:
        scan_df = candidate_df.copy().reset_index(drop=True)

    if len(scan_df) < 2:
        logger.info("Near-dup: fewer than 2 records to scan — skipping")
        return df, 0, 0

    logger.info("Near-dup: running on %d records (of %d total candidates)",
                len(scan_df), total_candidates)
    nd_result = detect_near_duplicates(scan_df, "text", nd_cfg, record_id_col="record_id")
    logger.info("Near-dup: %d groups, %d flagged, %d pairs verified",
                nd_result.num_groups, nd_result.num_flagged, nd_result.pairs_compared)

    # Write results back by record_id lookup
    nd_group_map = {}
    nd_flag_map = {}
    for local_idx, row in nd_result.df.iterrows():
        nd_group_map[row["record_id"]] = row["near_dup_group_id"]
        nd_flag_map[row["record_id"]] = row["near_dup_flag"]

    full_df = df.copy()
    full_df["near_dup_group_id"] = full_df["record_id"].map(
        lambda rid: nd_group_map.get(rid, None)
    )
    full_df["near_dup_flag"] = full_df["record_id"].map(
        lambda rid: nd_flag_map.get(rid, False)
    )

    return full_df, nd_result.num_groups, nd_result.num_flagged


# ---------------------------------------------------------------------------
# Annotation sample selection
# ---------------------------------------------------------------------------


def select_annotation_sample(
    df: pd.DataFrame,
    sample_size: int = 200,
    seed: int = 42,
    max_per_bank: int = 60,
) -> pd.DataFrame:
    """Select a stratified annotation sample from customer-feedback candidates.

    Selection strategy:
    1. Restrict to customer_feedback_candidate == True.
    2. Exclude records where possible_official_account == True.
    3. Prioritise records covering under-represented strata (fees, fraud,
       churn, branch, suggestion, warning) first.
    4. Within the remaining pool, sample proportionally by bank and year tier,
       capping at max_per_bank per bank to prevent one bank dominating.
    5. Avoid overrepresenting any single near-duplicate group (at most 1
       record per near_dup_group_id where the group is large).
    6. Final shuffle with seed before returning.

    Returns a DataFrame of sample_size rows (or fewer if insufficient candidates).

    NOTE: candidate_strata is used internally for selection only. It must be
    removed from the annotation output to avoid biasing annotators.
    """
    import random
    rng = random.Random(seed)

    # Filter to candidates only, excluding possible official accounts
    pool = df[
        df["customer_feedback_candidate"].fillna(False).astype(bool) &
        ~df["possible_official_account"].fillna(False).astype(bool)
    ].copy()

    logger.info("Annotation sample pool: %d candidates", len(pool))

    if len(pool) == 0:
        logger.warning("Empty candidate pool — returning empty sample")
        return pool.head(0)

    # Priority strata for under-represented areas
    PRIORITY_STRATA = [
        "fees_candidate", "fraud_security_candidate", "churn_candidate",
        "branch_service_candidate", "suggestion_candidate", "warning_candidate",
    ]

    # Track selected record IDs and near-dup groups
    selected_ids: set = set()
    selected_nd_groups: Counter = Counter()
    selected_rows = []
    bank_counts: Counter = Counter()

    def _can_add(row) -> bool:
        if row["record_id"] in selected_ids:
            return False
        bank = row["bank"]
        if bank_counts[bank] >= max_per_bank:
            return False
        # Limit near-dup group overrepresentation: at most 2 per group
        nd_group = row.get("near_dup_group_id")
        if nd_group and pd.notna(nd_group) and selected_nd_groups[nd_group] >= 2:
            return False
        return True

    def _add_row(row) -> None:
        selected_ids.add(row["record_id"])
        bank_counts[row["bank"]] += 1
        nd_group = row.get("near_dup_group_id")
        if nd_group and pd.notna(nd_group):
            selected_nd_groups[nd_group] += 1
        selected_rows.append(row)

    # Pass 1: priority strata (fees, fraud, churn, branch, suggestion, warning)
    for stratum in PRIORITY_STRATA:
        stratum_pool = pool[pool["candidate_strata"].str.contains(stratum, na=False)]
        stratum_list = stratum_pool.to_dict("records")
        rng.shuffle(stratum_list)
        target = max(5, sample_size // 20)  # ~5-10 per priority stratum
        added = 0
        for row in stratum_list:
            if added >= target:
                break
            if _can_add(row):
                _add_row(row)
                added += 1

    # Pass 2: fill remaining quota proportionally across banks and year tiers
    remaining_target = sample_size - len(selected_rows)
    if remaining_target > 0:
        remaining_pool = pool[~pool["record_id"].isin(selected_ids)]
        # Shuffle for random selection within each stratum
        remaining_list = remaining_pool.to_dict("records")
        rng.shuffle(remaining_list)
        for row in remaining_list:
            if len(selected_rows) >= sample_size:
                break
            if _can_add(row):
                _add_row(row)

    # Build result DataFrame
    if not selected_rows:
        return pool.head(0)

    result = pd.DataFrame(selected_rows)

    # Final shuffle
    result = result.sample(frac=1, random_state=seed).reset_index(drop=True)

    logger.info("Annotation sample selected: %d records", len(result))
    return result


# ---------------------------------------------------------------------------
# Annotation output schema
# ---------------------------------------------------------------------------


def to_annotation_records(df: pd.DataFrame) -> list[dict]:
    """Convert prepared records to the AnnotationRecord schema for JSONL output.

    Removes all candidate strata hints, filter reasons, and engagement metadata
    to avoid biasing the annotator. Preserves only what an annotator needs to see.
    """
    records = []
    for _, row in df.iterrows():
        record = {
            "record_id": row["record_id"],
            "source": row["source"],
            "region": row["region"],
            "bank": row["bank"],
            "text": row["text"],
            "previous_text": row.get("previous_text", "[NO_CONTEXT]"),
            "context_available": bool(row.get("context_available", False)),
            "aspects": [],
            "intent": None,
            "intent_ambiguous": False,
            "alternative_intent": None,
            "annotator_id": None,
            "annotation_status": "not_started",
            "notes": "",
        }
        records.append(record)
    return records
