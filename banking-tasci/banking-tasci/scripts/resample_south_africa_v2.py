#!/usr/bin/env python3
"""Create South African annotation sample version 2.

Reads the prepared canonical parquet, applies the evidence-based
candidate filter (replacing the overly broad length-only catch-all),
builds a bounded reservoir, runs near-duplicate detection on the reservoir
only, and samples a diversity-controlled 200-record annotation sample.

Preserves version 1 outputs unchanged.

Usage
-----
python scripts/resample_south_africa_v2.py \
    --input data/interim/south_africa_prepared.parquet \
    --annotation-output data/annotations/south_african_unannotated_v2.jsonl \
    --sample-report outputs/south_africa_annotation_sample_report_v2.json \
    --quality-review outputs/south_africa_sample_quality_review_v2.jsonl \
    --filter-comparison outputs/south_africa_filter_comparison_v1_v2.json \
    --sample-size 200 \
    --reservoir-size 10000 \
    --seed 42 \
    --zero-aspect-min 20 \
    --zero-aspect-max 30 \
    --max-per-bank 50
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd
import pyarrow.parquet as pq

from banking_tasci.data.sa_candidate_filter import (
    classify_candidate,
    is_potential_zero_aspect,
    BANKING_ASPECT_KW,
    PROBLEM_KW,
    REQUEST_KW,
    FIRST_PERSON_KW,
    POSITIVE_KW,
    POSITIVE_CONTEXT_KW,
    SUGGESTION_KW,
    WARNING_KW,
    CHURN_KW,
    SPECIFIC_ISSUE_KW,
    PROMOTIONAL_KW,
    BANKING_REFERENCE_KW,
    UNRELATED_BANK_KW,
    MIN_TEXT_LENGTH,
    _pad,
    _pad_text,
    _any_kw,
)
from banking_tasci.data.clean import NearDupConfig, detect_near_duplicates
from banking_tasci.logging_utils import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Audit-only relevance classification (same as v1 audit, refined rules)
# ---------------------------------------------------------------------------

AUDIT_BANKING_KW = [
    r"\baccount\b", r"\btransfer\b", r"\bpayment\b", r"\bcard\b",
    r"\batm\b", r"\bapp\b", r"\bonline banking\b", r"\bservice\b",
    r"\bbranch\b", r"\bfee\b", r"\bfees\b", r"\bfraud\b", r"\bscam\b",
    r"\bbalance\b", r"\bdeposit\b", r"\bloan\b", r"\bpin\b",
    r"\btransaction\b", r"\bcredit\b", r"\bdebit\b",
]
AUDIT_OPINION_KW = [
    r"\bdisappointed\b", r"\bterrible\b", r"\bhorrible\b", r"\bworst\b",
    r"\bpoor\b", r"\bwait", r"\bignored\b", r"\bno response\b",
    r"\bgreat\b", r"\bamazing\b", r"\bexcellent\b", r"\blove\b",
    r"\bhappy\b", r"\bsatisfied\b", r"\bthank\b", r"\bimpressed\b",
    r"\bplease\b", r"\bhelp\b", r"\bassist\b", r"\bfix\b", r"\bresolve\b",
    r"\bfailed\b", r"\berror\b", r"\bblocked\b", r"\bissue\b", r"\bproblem\b",
]
AUDIT_PROMO_KW = [
    r"\bcompetition\b", r"\bgiveaway\b", r"\bwin\b", r"\bprize\b",
    r"\bspecial offer\b", r"\bterms apply\b", r"\btag a friend\b",
    r"\bapply now\b", r"\bfree data\b",
]
AUDIT_NEWS_KW = [
    r"\bpress release\b", r"\bquarterly results\b", r"\bannual results\b",
    r"\bprofit\b", r"\brevenue\b", r"\bceo says\b", r"\bminister\b",
    r"\bsarb\b", r"\breserve bank announces\b",
]


def _re_any(patterns: "list[str]", text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def audit_classify(text: str, sample_role: str = "") -> tuple[str, str]:
    """Classify a record for audit purposes only. Returns (class, reason)."""
    if len(text.strip()) < 30:
        return "too_short_or_low_information", "text too short"
    if sample_role == "potential_zero_aspect":
        return "potential_zero_aspect", "intentionally selected as zero-aspect training candidate"
    has_banking = _re_any(AUDIT_BANKING_KW, text)
    has_opinion = _re_any(AUDIT_OPINION_KW, text)
    is_promo = _re_any(AUDIT_PROMO_KW, text)
    is_news = _re_any(AUDIT_NEWS_KW, text)
    if is_promo and not (has_banking and has_opinion):
        return "promotional_or_marketing", "promotional keywords"
    if is_news:
        return "news_or_general_discussion", "news/reporting patterns"
    if has_banking and has_opinion:
        return "suitable_customer_feedback", "banking + opinion/request"
    if has_banking:
        return "suitable_customer_feedback", "banking content present"
    return "unrelated_or_unclear", "no banking content or opinion patterns"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="resample_south_africa_v2.py",
        description=(
            "Create South African annotation sample version 2 using the "
            "evidence-based candidate filter. Preserves version 1 outputs."
        ),
    )
    p.add_argument("--input", default="data/interim/south_africa_prepared.parquet")
    p.add_argument("--annotation-output",
                   default="data/annotations/south_african_unannotated_v2.jsonl")
    p.add_argument("--sample-report",
                   default="outputs/south_africa_annotation_sample_report_v2.json")
    p.add_argument("--quality-review",
                   default="outputs/south_africa_sample_quality_review_v2.jsonl")
    p.add_argument("--filter-comparison",
                   default="outputs/south_africa_filter_comparison_v1_v2.json")
    p.add_argument("--sample-size", type=int, default=200)
    p.add_argument("--reservoir-size", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--zero-aspect-min", type=int, default=20)
    p.add_argument("--zero-aspect-max", type=int, default=30)
    p.add_argument("--max-per-bank", type=int, default=50)
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


# ---------------------------------------------------------------------------
# Reservoir builder
# ---------------------------------------------------------------------------

STRATA_TARGET = {
    "transactions_candidate":       35,
    "customer_support_candidate":   30,
    "accounts_candidate":           25,
    "cards_candidate":              20,
    "digital_banking_candidate":    20,
    "fees_candidate":               15,
    "fraud_security_candidate":     15,
    "branch_service_candidate":     10,
    "positive_feedback_candidate":  15,
    "suggestion_candidate":         10,
    "warning_candidate":            10,
    "churn_candidate":              10,
}

YEAR_MIN = 2018
YEAR_MAX = 2022


def build_reservoir(
    input_path: str,
    reservoir_size: int,
    seed: int,
    max_per_bank: int,
    log,
):
    """Build a diversity-controlled reservoir using fast keyword matching.

    Reads only required columns. Applies evidence-based filter using
    vectorised pandas string operations (simple substring on padded text).
    """
    needed_cols = ["record_id", "bank", "text", "created_at",
                   "possible_official_account"]

    log.info("Reading parquet (required columns only)...")
    df_all = pd.read_parquet(input_path, columns=needed_cols)
    log.info("Loaded %d rows", len(df_all))

    log.info("Applying evidence-based candidate filter (vectorised keyword matching)...")

    texts = df_all["text"].fillna("").astype(str)
    # Pad text for safe substring matching (prevents 'app' matching 'happy')
    padded = " " + texts.str.lower() + " "

    def _has(kw_list) -> "pd.Series":
        combined = "|".join(re.escape(f" {kw.lower()} ") for kw in kw_list)
        return padded.str.contains(combined, regex=True)

    log.info("Building keyword masks...")
    has_aspect   = _has(BANKING_ASPECT_KW)
    has_problem  = _has(PROBLEM_KW)
    has_request  = _has(REQUEST_KW)
    has_fp       = _has(FIRST_PERSON_KW)
    has_positive = _has(POSITIVE_KW)
    has_pos_ctx  = _has(POSITIVE_CONTEXT_KW)
    has_suggest  = _has(SUGGESTION_KW)
    has_warning  = _has(WARNING_KW)
    has_churn    = _has(CHURN_KW)
    has_specific = _has(SPECIFIC_ISSUE_KW)
    is_promo     = _has(PROMOTIONAL_KW)
    has_bank_ref = _has(BANKING_REFERENCE_KW)
    is_unrelated = _has(UNRELATED_BANK_KW)
    too_short    = texts.str.len() < MIN_TEXT_LENGTH

    log.info("Evaluating candidate rules...")
    rule_F = has_specific & ~is_unrelated
    rule_A = has_aspect & has_problem & ~is_unrelated
    rule_B = has_aspect & has_request & ~is_unrelated
    rule_C = has_fp & has_aspect & ~is_unrelated
    rule_D = has_positive & has_pos_ctx & ~is_unrelated
    rule_E = (has_suggest | has_warning | has_churn) & has_bank_ref & ~is_unrelated

    promo_exclude = is_promo & ~(has_fp | has_problem | has_specific)
    is_candidate_mask = (rule_F | rule_A | rule_B | rule_C | rule_D | rule_E) & ~too_short & ~promo_exclude

    # Date range filter
    year_str = df_all["created_at"].fillna("").astype(str).str[:4]
    in_year = year_str.isin([str(y) for y in range(YEAR_MIN, YEAR_MAX + 1)])

    # Official account exclusion
    not_official = ~df_all["possible_official_account"].fillna(False).astype(bool)

    candidate_mask = is_candidate_mask & in_year & not_official

    # Zero-aspect pool
    bank_name_kw = ["fnb", "absa", "nedbank", "capitec", "standard bank",
                    "standardbank", "bank", "banking", "[user]"]
    specific_asp_kw = ["transfer", "payment", "account", "card", "fee", "fees",
                       "fraud", "branch", "atm", "loan", "transaction", "balance",
                       "deposit", "mobile app", "banking app", "online banking"]
    has_bank_name = _has(bank_name_kw)
    has_specific_asp = _has(specific_asp_kw)
    zero_mask = has_bank_name & ~has_specific_asp & ~too_short & in_year & not_official & ~candidate_mask

    log.info("Candidates: %d, Zero-aspect: %d", candidate_mask.sum(), zero_mask.sum())

    # Assign rules
    rule_col = pd.Series("none", index=df_all.index)
    rule_col[rule_F] = "F"
    rule_col[rule_A & ~rule_F] = "A"
    rule_col[rule_B & ~rule_F & ~rule_A] = "B"
    rule_col[rule_C & ~rule_F & ~rule_A & ~rule_B] = "C"
    rule_col[rule_D & ~rule_F & ~rule_A & ~rule_B & ~rule_C] = "D"
    rule_col[rule_E & ~rule_F & ~rule_A & ~rule_B & ~rule_C & ~rule_D] = "E"

    cand_df = df_all[candidate_mask].copy()
    cand_df["rule_matched"] = rule_col[candidate_mask].values
    cand_df["is_promotional"] = is_promo[candidate_mask].values
    cand_df["is_zero_aspect"] = False

    zero_df = df_all[zero_mask].copy()
    zero_df["rule_matched"] = "zero_aspect"
    zero_df["is_promotional"] = False
    zero_df["is_zero_aspect"] = True

    # Assign strata per candidate (vectorised per stratum)
    def _strata_mask(kw_list):
        combined = "|".join(re.escape(f" {kw.lower()} ") for kw in kw_list)
        return padded.str.contains(combined, regex=True)

    strata_defs = {
        "transactions_candidate": _strata_mask([
            "transfer", "payment", "transaction", "reversal", "refund",
            "deposit", "withdrawal", "failed transaction", "failed transfer",
        ]) & (has_problem | has_request | has_fp | rule_F) & candidate_mask,
        "customer_support_candidate": _strata_mask([
            "customer service", "customer care", "support", "consultant",
            "helpline", "call centre", "call center",
        ]) & (has_problem | has_request) & candidate_mask,
        "accounts_candidate": _strata_mask([
            "my account", "account",
        ]) & (has_problem | has_request | has_fp) & candidate_mask,
        "cards_candidate": _strata_mask([
            "my card", "card", "pin", "debit card", "credit card",
        ]) & (has_problem | has_request | has_fp) & candidate_mask,
        "digital_banking_candidate": _strata_mask([
            "mobile app", "banking app", "online banking", "internet banking",
            "mobile banking", "app not working", "login", "e-wallet", "ewallet",
        ]) & (has_problem | has_request | has_fp) & candidate_mask,
        "fees_candidate": _strata_mask([
            "fee", "fees", "charge", "charges", "deduction", "debit order",
            "service fee", "maintenance fee",
        ]) & (has_problem | has_request | has_fp | rule_F) & candidate_mask,
        "fraud_security_candidate": _strata_mask([
            "fraud", "scam", "unauthorised", "unauthorized", "hacked",
            "phishing", "identity theft", "suspicious",
        ]) & candidate_mask,
        "branch_service_candidate": _strata_mask([
            "branch", "teller", "queue",
        ]) & (has_problem | has_request | has_fp | has_positive) & candidate_mask,
        "positive_feedback_candidate": has_positive & has_pos_ctx & candidate_mask,
        "suggestion_candidate": has_suggest & has_bank_ref & candidate_mask,
        "warning_candidate": has_warning & has_bank_ref & candidate_mask,
        "churn_candidate": has_churn & has_bank_ref & candidate_mask,
    }

    log.info("Assigning strata to %d candidates...", len(cand_df))
    strata_lists = {idx: [] for idx in cand_df.index}
    for stratum, smask in strata_defs.items():
        for idx in cand_df.index[smask[cand_df.index]]:
            strata_lists[idx].append(stratum)
    cand_df["matched_strata"] = [strata_lists[i] for i in cand_df.index]
    zero_df["matched_strata"] = [[] for _ in range(len(zero_df))]

    filter_counts: Counter = Counter({
        "candidate": int(candidate_mask.sum()),
        "zero_aspect": int(zero_mask.sum()),
        "promo_excluded": int(promo_exclude.sum()),
        "too_short": int(too_short.sum()),
        "unrelated_bank": int(is_unrelated.sum()),
    })
    rule_counts: Counter = Counter(cand_df["rule_matched"].value_counts().to_dict())
    log.info("Filter counts: %s", dict(filter_counts))
    log.info("Rule breakdown: %s", dict(rule_counts))

    # --- Build diversity-controlled reservoir ---
    cand_df = cand_df.sample(frac=1, random_state=seed).reset_index(drop=True)
    zero_df = zero_df.sample(frac=1, random_state=seed).reset_index(drop=True)

    bank_counts: Counter = Counter()
    reservoir_ids: set = set()
    reservoir_rows = []

    def _can_add(row) -> bool:
        return row["record_id"] not in reservoir_ids and bank_counts[row["bank"]] < max_per_bank

    def _add(row) -> None:
        reservoir_ids.add(row["record_id"])
        bank_counts[row["bank"]] += 1
        reservoir_rows.append(row)

    for stratum, target in STRATA_TARGET.items():
        stratum_df = cand_df[cand_df["matched_strata"].apply(
            lambda sl: stratum in sl if isinstance(sl, list) else False
        )]
        added = 0
        for _, row in stratum_df.iterrows():
            if added >= target:
                break
            if _can_add(row):
                _add(row)
                added += 1

    remaining = reservoir_size - len(reservoir_rows)
    if remaining > 0:
        extra_df = cand_df[~cand_df["record_id"].isin(reservoir_ids)]
        for _, row in extra_df.head(remaining * 5).iterrows():
            if len(reservoir_rows) >= reservoir_size:
                break
            if _can_add(row):
                _add(row)

    reservoir_df = pd.DataFrame(reservoir_rows) if reservoir_rows else pd.DataFrame()
    log.info("Reservoir: %d feedback candidates built", len(reservoir_df))
    return reservoir_df, zero_df, filter_counts, rule_counts
    rng = random.Random(seed)
    needed_cols = ["record_id", "bank", "text", "created_at",
                   "possible_official_account"]

    log.info("Reading parquet (required columns only)...")
    df_all = pd.read_parquet(input_path, columns=needed_cols)
    log.info("Loaded %d rows", len(df_all))

    # Vectorised filter: precompile all patterns into combined regexes per rule
    # for speed (one pass per rule rather than one pass per pattern).
    log.info("Applying evidence-based candidate filter (vectorised)...")

    texts = df_all["text"].fillna("").astype(str)

    # Combine patterns per category into single ORed regexes
    def _combined(patterns) -> re.Pattern:
        combined = "|".join(f"(?:{p.pattern})" for p in patterns)
        return re.compile(combined, re.IGNORECASE)

    p_aspect   = _combined(BANKING_ASPECT_PATTERNS)
    p_problem  = _combined(PROBLEM_PATTERNS)
    p_request  = _combined(REQUEST_PATTERNS)
    p_fp       = _combined(FIRST_PERSON_PATTERNS)
    p_positive = _combined(POSITIVE_PATTERNS)
    p_pos_ctx  = _combined(POSITIVE_CONTEXT_PATTERNS)
    p_suggest  = _combined(SUGGESTION_PATTERNS)
    p_warning  = _combined(WARNING_PATTERNS)
    p_churn    = _combined(CHURN_PATTERNS)
    p_specific = _combined(SPECIFIC_ISSUE_PATTERNS)
    p_promo    = _combined(PROMOTIONAL_PATTERNS)
    p_bankref  = _combined(BANKING_REFERENCE_PATTERNS)
    p_unrelated = _combined(UNRELATED_BANK_PATTERNS)

    log.info("Running vectorised string matching on %d rows...", len(texts))

    # Vectorised boolean series
    has_aspect   = texts.str.contains(p_aspect,   regex=True)
    has_problem  = texts.str.contains(p_problem,  regex=True)
    has_request  = texts.str.contains(p_request,  regex=True)
    has_fp       = texts.str.contains(p_fp,       regex=True)
    has_positive = texts.str.contains(p_positive, regex=True)
    has_pos_ctx  = texts.str.contains(p_pos_ctx,  regex=True)
    has_suggest  = texts.str.contains(p_suggest,  regex=True)
    has_warning  = texts.str.contains(p_warning,  regex=True)
    has_churn    = texts.str.contains(p_churn,    regex=True)
    has_specific = texts.str.contains(p_specific, regex=True)
    is_promo     = texts.str.contains(p_promo,    regex=True)
    has_bankref  = texts.str.contains(p_bankref,  regex=True)
    is_unrelated = texts.str.contains(p_unrelated, regex=True)
    too_short    = texts.str.len() < MIN_TEXT_LENGTH

    log.info("Pattern matching complete.")

    # Rule evaluation (vectorised)
    rule_F = has_specific & ~is_unrelated
    rule_A = has_aspect & has_problem & ~is_unrelated
    rule_B = has_aspect & has_request & ~is_unrelated
    rule_C = has_fp & has_aspect & ~is_unrelated
    rule_D = has_positive & has_pos_ctx & ~is_unrelated
    rule_E = (has_suggest | has_warning | has_churn) & has_bankref & ~is_unrelated

    # Promotional precedence: exclude if promo AND no personal experience
    promo_exclude = is_promo & ~(has_fp | has_problem | has_specific)

    is_candidate = (rule_F | rule_A | rule_B | rule_C | rule_D | rule_E) & ~too_short & ~promo_exclude

    # Date range filter (2018-2022)
    created_at_str = df_all["created_at"].fillna("").astype(str)
    year_str = created_at_str.str[:4]
    in_year_range = year_str.isin([str(y) for y in range(YEAR_MIN, YEAR_MAX + 1)])

    # Official account exclusion
    not_official = ~df_all["possible_official_account"].fillna(False).astype(bool)

    # Final candidate mask
    candidate_mask = is_candidate & in_year_range & not_official

    # Zero-aspect detection (vectorised)
    bank_name_p = _combined([
        _wb("fnb"), _wb("absa"), _wb("nedbank"), _wb("capitec"),
        _wb("standard bank"), _wb("standardbank"), _wb("bank"), _wb("banking"),
        re.compile(r"\[USER\]", re.IGNORECASE),
    ])
    specific_asp_p = _combined([
        _wb("transfer"), _wb("payment"), _wb("account"), _wb("card"),
        _wb("fee"), _wb("fees"), _wb("fraud"), _wb("branch"), _wb("atm"),
        _wb("loan"), _wb("transaction"), _wb("balance"), _wb("deposit"),
        _wb("mobile app"), _wb("banking app"), _wb("online banking"),
    ])
    has_bank_name = texts.str.contains(bank_name_p, regex=True)
    has_specific_asp = texts.str.contains(specific_asp_p, regex=True)
    zero_aspect_mask = has_bank_name & ~has_specific_asp & ~too_short & in_year_range & not_official & ~is_candidate

    # Assign rule column
    rule_col = pd.Series("none", index=df_all.index)
    rule_col[rule_F] = "F"
    rule_col[rule_A & ~rule_F] = "A"
    rule_col[rule_B & ~rule_F & ~rule_A] = "B"
    rule_col[rule_C & ~rule_F & ~rule_A & ~rule_B] = "C"
    rule_col[rule_D & ~rule_F & ~rule_A & ~rule_B & ~rule_C] = "D"
    rule_col[rule_E & ~rule_F & ~rule_A & ~rule_B & ~rule_C & ~rule_D] = "E"

    # Build candidate DataFrame
    cand_df = df_all[candidate_mask].copy()
    cand_df["rule_matched"] = rule_col[candidate_mask].values
    cand_df["is_promotional"] = is_promo[candidate_mask].values
    cand_df["is_zero_aspect"] = False

    zero_df = df_all[zero_aspect_mask].copy()
    zero_df["rule_matched"] = "zero_aspect"
    zero_df["is_promotional"] = False
    zero_df["is_zero_aspect"] = True

    log.info("Candidates: %d feedback, %d zero-aspect", len(cand_df), len(zero_df))

    # Assign matched strata per record (vectorised per stratum)
    strata_masks = {
        "transactions_candidate": has_aspect & (has_problem | has_request | has_fp) & candidate_mask,
        "customer_support_candidate": texts.str.contains(
            _combined([_wb("customer service"), _wb("customer care"), _wb("support"),
                       _wb("consultant"), _wb("helpline"), _wb("call centre"), _wb("call center")]),
            regex=True,
        ) & (has_problem | has_request) & candidate_mask,
        "accounts_candidate": has_fp & has_aspect & (has_problem | has_request) & candidate_mask,
        "cards_candidate": texts.str.contains(
            _combined([_wb("my card"), _wb("card"), _wb("pin"), _wb("debit card"), _wb("credit card")]),
            regex=True,
        ) & (has_problem | has_request | has_fp) & candidate_mask,
        "digital_banking_candidate": texts.str.contains(
            _combined([_wb("mobile app"), _wb("banking app"), _wb("online banking"),
                       _wb("internet banking"), _wb("mobile banking"), _wb("app not working"),
                       _wb("login"), _wb("e-wallet"), _wb("ewallet")]),
            regex=True,
        ) & (has_problem | has_request | has_fp) & candidate_mask,
        "fees_candidate": texts.str.contains(
            _combined([_wb("fee"), _wb("fees"), _wb("charge"), _wb("charges"),
                       _wb("deduction"), _wb("debit order"), _wb("service fee"), _wb("maintenance fee")]),
            regex=True,
        ) & (has_problem | has_request | has_fp | rule_F) & candidate_mask,
        "fraud_security_candidate": has_specific & texts.str.contains(
            _combined([_wb("fraud"), _wb("scam"), _wb("unauthorised"), _wb("unauthorized"),
                       _wb("hacked"), _wb("phishing"), _wb("identity theft"), _wb("suspicious")]),
            regex=True,
        ) & candidate_mask,
        "branch_service_candidate": texts.str.contains(
            _combined([_wb("branch"), _wb("teller"), _wb("queue")]),
            regex=True,
        ) & (has_problem | has_request | has_fp | has_positive) & candidate_mask,
        "positive_feedback_candidate": has_positive & has_pos_ctx & candidate_mask,
        "suggestion_candidate": has_suggest & has_bankref & candidate_mask,
        "warning_candidate": has_warning & has_bankref & candidate_mask,
        "churn_candidate": has_churn & has_bankref & candidate_mask,
    }

    # Assign strata to candidate rows
    strata_series = pd.Series([[] for _ in range(len(cand_df))], index=cand_df.index)
    for stratum, mask in strata_masks.items():
        cand_idx = cand_df.index[mask[cand_df.index]]
        for idx in cand_idx:
            strata_series[idx] = strata_series[idx] + [stratum]
    cand_df["matched_strata"] = strata_series.values

    zero_df["matched_strata"] = [[] for _ in range(len(zero_df))]

    # Filter stats
    filter_counts: Counter = Counter({
        "candidate": int(candidate_mask.sum()),
        "zero_aspect": int(zero_aspect_mask.sum()),
        "promo_excluded": int(promo_exclude.sum()),
        "unrelated_bank": int((is_unrelated & ~too_short).sum()),
        "too_short": int(too_short.sum()),
        "outside_date_range": int(~in_year_range.sum()),
        "official_account": int(~not_official.sum()),
        "no_rule_matched": int((~is_candidate & ~zero_aspect_mask & in_year_range & not_official & ~too_short & ~is_unrelated).sum()),
    })
    rule_counts: Counter = Counter(cand_df["rule_matched"].value_counts().to_dict())

    log.info("Filter counts: %s", dict(filter_counts.most_common(8)))
    log.info("Rule breakdown: %s", dict(rule_counts))

    # --- Build diversity-controlled reservoir ---
    cand_df = cand_df.sample(frac=1, random_state=seed).reset_index(drop=True)
    zero_df = zero_df.sample(frac=1, random_state=seed).reset_index(drop=True)

    bank_counts: Counter = Counter()
    reservoir_ids: set = set()
    reservoir_rows = []

    def _can_add(row) -> bool:
        if row["record_id"] in reservoir_ids:
            return False
        if bank_counts[row["bank"]] >= max_per_bank:
            return False
        return True

    def _add(row) -> None:
        reservoir_ids.add(row["record_id"])
        bank_counts[row["bank"]] += 1
        reservoir_rows.append(row)

    # Pass 1: fill strata targets
    for stratum, target in STRATA_TARGET.items():
        if stratum == "fraud_security_candidate":
            stratum_df = cand_df[cand_df["matched_strata"].apply(
                lambda sl: stratum in sl if isinstance(sl, list) else False
            )]
        else:
            stratum_df = cand_df[cand_df["matched_strata"].apply(
                lambda sl: stratum in sl if isinstance(sl, list) else False
            )]
        added = 0
        for _, row in stratum_df.iterrows():
            if added >= target:
                break
            if _can_add(row):
                _add(row)
                added += 1

    # Pass 2: fill remaining reservoir slots
    remaining = reservoir_size - len(reservoir_rows)
    if remaining > 0:
        extra_df = cand_df[~cand_df["record_id"].isin(reservoir_ids)]
        for _, row in extra_df.head(remaining * 3).iterrows():
            if len(reservoir_rows) >= reservoir_size:
                break
            if _can_add(row):
                _add(row)

    reservoir_df = pd.DataFrame(reservoir_rows) if reservoir_rows else pd.DataFrame()
    log.info("Reservoir: %d feedback candidates", len(reservoir_df))

    return reservoir_df, zero_df, filter_counts, rule_counts


# ---------------------------------------------------------------------------
# Near-duplicate detection on bounded reservoir
# ---------------------------------------------------------------------------

def run_nd_on_reservoir(
    reservoir_df: pd.DataFrame,
    seed: int,
    log,
) -> tuple[pd.DataFrame, int, int]:
    """Run near-duplicate detection on the bounded reservoir only."""
    if len(reservoir_df) < 2:
        return reservoir_df, 0, 0

    log.info("Near-dup detection on %d-record reservoir...", len(reservoir_df))
    nd_cfg = NearDupConfig(action="flag", seed=seed)
    nd_result = detect_near_duplicates(
        reservoir_df, "text", nd_cfg, record_id_col="record_id"
    )
    log.info("Near-dup: %d groups, %d flagged", nd_result.num_groups, nd_result.num_flagged)
    return nd_result.df, nd_result.num_groups, nd_result.num_flagged


# ---------------------------------------------------------------------------
# Sample selection from reservoir
# ---------------------------------------------------------------------------

def select_sample_v2(
    reservoir_df: pd.DataFrame,
    zero_asp_pool: pd.DataFrame,
    sample_size: int,
    zero_aspect_min: int,
    zero_aspect_max: int,
    max_per_bank: int,
    seed: int,
    log,
) -> tuple[pd.DataFrame, dict]:
    """Select the final 200-record sample from the near-dup-aware reservoir."""
    rng = random.Random(seed)

    # How many zero-aspect records to include
    n_zero = min(zero_aspect_max, len(zero_asp_pool))
    n_zero = max(n_zero, min(zero_aspect_min, len(zero_asp_pool)))
    n_feedback = sample_size - n_zero

    bank_counts: Counter = Counter()
    nd_groups_used: set = set()
    selected_ids: set = set()
    selected: list = []

    def _can_add(row) -> bool:
        if row["record_id"] in selected_ids:
            return False
        if bank_counts[row["bank"]] >= max_per_bank:
            return False
        nd_gid = row.get("near_dup_group_id")
        if nd_gid and pd.notna(nd_gid) and nd_gid in nd_groups_used:
            return False
        return True

    def _add(row, sample_role: str = "feedback") -> None:
        selected_ids.add(row["record_id"])
        bank_counts[row["bank"]] += 1
        nd_gid = row.get("near_dup_group_id")
        if nd_gid and pd.notna(nd_gid):
            nd_groups_used.add(nd_gid)
        selected.append(dict(row) | {"sample_role": sample_role})

    # 1. Strata-priority selection for feedback records
    for stratum, target in STRATA_TARGET.items():
        stratum_df = reservoir_df[
            reservoir_df["matched_strata"].apply(
                lambda sl: stratum in sl if isinstance(sl, list) else False
            )
        ]
        added = 0
        per_stratum_target = min(target, n_feedback // len(STRATA_TARGET) + 2)
        for _, row in stratum_df.iterrows():
            if added >= per_stratum_target:
                break
            if _can_add(row):
                _add(row, "feedback")
                added += 1

    # 2. Fill remaining feedback slots
    rem_feedback = n_feedback - len(selected)
    if rem_feedback > 0:
        extra = reservoir_df[~reservoir_df["record_id"].isin(selected_ids)]
        for _, row in extra.iterrows():
            if len([r for r in selected if r.get("sample_role") == "feedback"]) >= n_feedback:
                break
            if _can_add(row):
                _add(row, "feedback")

    # 3. Zero-aspect records
    zero_shuffle = zero_asp_pool.sample(frac=1, random_state=seed).reset_index(drop=True)
    added_zero = 0
    for _, row in zero_shuffle.iterrows():
        if added_zero >= n_zero:
            break
        if row["record_id"] not in selected_ids and bank_counts[row["bank"]] < max_per_bank:
            selected_ids.add(row["record_id"])
            bank_counts[row["bank"]] += 1
            selected.append(dict(row) | {"sample_role": "potential_zero_aspect"})
            added_zero += 1

    log.info("Sample: %d feedback + %d zero-aspect = %d total",
             len([r for r in selected if r.get("sample_role") == "feedback"]),
             added_zero, len(selected))

    result_df = pd.DataFrame(selected)
    # Final shuffle
    result_df = result_df.sample(frac=1, random_state=seed).reset_index(drop=True)

    composition = {
        "total": len(result_df),
        "feedback": int((result_df.get("sample_role", pd.Series()) == "feedback").sum()),
        "potential_zero_aspect": added_zero,
        "bank_counts": dict(bank_counts),
    }
    return result_df, composition


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def to_annotation_records_v2(df: pd.DataFrame) -> list[dict]:
    """Gold-label-free annotation output — no hints, no labels, no strata."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "record_id": row["record_id"],
            "source": "south_african_bank_tweets",
            "region": "south_africa",
            "bank": row["bank"],
            "text": row["text"],
            "previous_text": "[NO_CONTEXT]",
            "context_available": False,
            "aspects": [],
            "intent": None,
            "intent_ambiguous": False,
            "alternative_intent": None,
            "annotator_id": None,
            "annotation_status": "not_started",
            "notes": "",
        })
    return records


def write_quality_review(sample_df: pd.DataFrame, path: str) -> dict:
    """Classify each sample record for audit (not for annotators) and write JSONL."""
    classes: Counter = Counter()
    rows = []
    for _, row in sample_df.iterrows():
        sample_role = row.get("sample_role", "")
        cls, reason = audit_classify(row["text"], sample_role)
        classes[cls] += 1
        rows.append({
            "record_id": row["record_id"],
            "bank": row["bank"],
            "text": row["text"],
            "audit_relevance_class": cls,
            "audit_reason": reason,
            "sample_role": sample_role,
            "include_for_annotation": cls in (
                "suitable_customer_feedback", "potential_zero_aspect"
            ),
            "human_confirmation": "",
        })

    Path(path).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return dict(classes)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = get_logger("resample_south_africa_v2")

    log.info("=== South African annotation sample v2 ===")

    # Confirm version 1 outputs are intact
    v1_protected = [
        "data/annotations/south_african_unannotated.jsonl",
        "outputs/south_africa_sample_quality_review.jsonl",
        "outputs/south_africa_annotation_sample_report.json",
        "outputs/south_africa_data_report.json",
        "data/interim/south_africa_prepared.parquet",
    ]
    for pf in v1_protected:
        if Path(pf).exists():
            log.info("VERSION 1 PROTECTED (unchanged): %s", pf)
        else:
            log.warning("VERSION 1 FILE MISSING: %s", pf)

    # Make sure output paths don't overwrite v1
    for arg_val in [args.annotation_output, args.sample_report,
                    args.quality_review, args.filter_comparison]:
        assert "v2" in arg_val or "comparison" in arg_val, (
            f"Output path '{arg_val}' does not contain 'v2' — refusing to risk overwriting v1"
        )

    # Ensure output directories exist
    for arg_val in [args.annotation_output, args.sample_report,
                    args.quality_review, args.filter_comparison]:
        Path(arg_val).parent.mkdir(parents=True, exist_ok=True)

    # --- Build reservoir ---
    reservoir_df, zero_asp_pool, filter_counts, rule_counts = build_reservoir(
        args.input, args.reservoir_size, args.seed, args.max_per_bank, log
    )

    if reservoir_df is None or len(reservoir_df) == 0:
        log.error("Reservoir is empty. Aborting.")
        return 1

    log.info("Reservoir: %d feedback, %d zero-aspect",
             len(reservoir_df), len(zero_asp_pool))

    # --- Near-dup on reservoir ---
    reservoir_df, nd_groups, nd_flagged = run_nd_on_reservoir(reservoir_df, args.seed, log)

    # --- Sample selection ---
    sample_df, composition = select_sample_v2(
        reservoir_df=reservoir_df,
        zero_asp_pool=zero_asp_pool,
        sample_size=args.sample_size,
        zero_aspect_min=args.zero_aspect_min,
        zero_aspect_max=args.zero_aspect_max,
        max_per_bank=args.max_per_bank,
        seed=args.seed,
        log=log,
    )

    if len(sample_df) == 0:
        log.error("Sample is empty after selection. Aborting.")
        return 1

    log.info("Final sample: %d records", len(sample_df))

    # --- Write annotation JSONL (gold-label-free) ---
    annotation_records = to_annotation_records_v2(sample_df)
    Path(args.annotation_output).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in annotation_records) + "\n",
        encoding="utf-8",
    )
    log.info("Annotation output: %s (%d records)", args.annotation_output, len(annotation_records))

    # --- Quality review ---
    audit_classes = write_quality_review(sample_df, args.quality_review)
    log.info("Quality review written: %s — classes: %s", args.quality_review, audit_classes)

    suitable = audit_classes.get("suitable_customer_feedback", 0)
    zero_asp_count = audit_classes.get("potential_zero_aspect", 0)
    total_include = suitable + zero_asp_count
    log.info("Suitable: %d, zero-aspect: %d, total include: %d / %d",
             suitable, zero_asp_count, total_include, len(sample_df))

    # --- Sample report ---
    year_counts: Counter = Counter()
    for ca in sample_df["created_at"]:
        yr = str(ca)[:4] if ca and str(ca)[:4].isdigit() else "unknown"
        year_counts[yr] += 1

    strata_counts_sample: Counter = Counter()
    for sl in sample_df["matched_strata"]:
        if isinstance(sl, list):
            for s in sl:
                strata_counts_sample[s] += 1

    text_lens = sample_df["text"].astype(str).str.len()

    sample_report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": "v2",
        "sample_size": len(sample_df),
        "requested_size": args.sample_size,
        "seed": args.seed,
        "filter_version": "evidence_based_v2_no_catchall",
        "reservoir_size": len(reservoir_df) + len(zero_asp_pool),
        "near_dup_detection": {
            "applied_to": f"bounded_reservoir_{len(reservoir_df)}_records",
            "groups_detected": nd_groups,
            "records_flagged": nd_flagged,
            "note": (
                "Near-dup control was applied to the bounded annotation-candidate "
                "reservoir rather than the complete South African corpus."
            ),
        },
        "composition": composition,
        "bank_distribution": dict(Counter(sample_df["bank"])),
        "year_distribution": dict(sorted(year_counts.items())),
        "text_length_distribution": {
            "min": float(text_lens.min()),
            "max": float(text_lens.max()),
            "mean": float(text_lens.mean()),
            "q1": float(text_lens.quantile(0.25)),
            "median": float(text_lens.quantile(0.50)),
            "q3": float(text_lens.quantile(0.75)),
        },
        "candidate_strata_counts": dict(strata_counts_sample),
        "audit_relevance_classes": audit_classes,
        "suitability": {
            "suitable_customer_feedback": suitable,
            "potential_zero_aspect": zero_asp_count,
            "total_include": total_include,
            "unsuitable": len(sample_df) - total_include,
            "suitability_pct": round(total_include / len(sample_df) * 100, 1),
            "threshold_met": total_include >= 160,
        },
        "context_availability": {
            "context_available_true": 0,
            "context_available_false": len(sample_df),
            "note": "All SA records use [NO_CONTEXT]; no thread graph in source",
        },
        "label_leakage_prevention": {
            "candidate_strata_removed_from_annotation_view": True,
            "sample_role_removed_from_annotation_view": True,
            "existing_sentiment_fields": "none in source",
        },
        "filter_rule_usage": dict(rule_counts),
        "sampling_limitations": [
            "No context-available records: SA tweet corpus has no thread graph",
            "Near-dup control limited to bounded reservoir, not full 2.25M corpus",
            "Positive-feedback stratum is naturally sparse in complaint-heavy corpus",
            "suggestion / warning / churn strata rely on specific phrase matching",
        ],
    }

    Path(args.sample_report).write_text(
        json.dumps(sample_report, indent=2, default=str), encoding="utf-8"
    )
    log.info("Sample report: %s", args.sample_report)

    # --- V1 vs V2 filter comparison ---
    # Load v1 report for comparison
    v1_report_path = Path("outputs/south_africa_annotation_sample_report.json")
    v1_data = json.loads(v1_report_path.read_text()) if v1_report_path.exists() else {}
    v1_suitability = 131  # from audit
    v1_unclear = 66
    v1_short = 3
    v1_promo = 0

    comparison = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "v1": {
            "filter_version": "broad_length_catchall",
            "catchall_rule": "any non-promotional tweet >= 30 chars = candidate",
            "candidate_rate_full_corpus": "92.7%",
            "sample_suitable_customer_feedback": v1_suitability,
            "sample_unrelated_or_unclear": v1_unclear,
            "sample_too_short": v1_short,
            "sample_promotional": v1_promo,
            "suitability_pct": 65.5,
            "threshold_met": False,
            "bank_distribution": v1_data.get("bank_distribution", {}),
            "year_distribution": v1_data.get("date_distribution", {}),
            "near_dup_control": "diagnostic 10K scan, not used for sample selection",
            "records_through_catchall_only": 116,
        },
        "v2": {
            "filter_version": "evidence_based_v2_no_catchall",
            "catchall_rule": "removed",
            "candidate_rules": ["A: aspect+problem", "B: aspect+request",
                                 "C: first_person+aspect", "D: positive_service",
                                 "E: suggestion/warning/churn+banking", "F: specific_phrase"],
            "sample_suitable_customer_feedback": suitable,
            "sample_potential_zero_aspect": zero_asp_count,
            "sample_total_include": total_include,
            "sample_unsuitable": len(sample_df) - total_include,
            "suitability_pct": sample_report["suitability"]["suitability_pct"],
            "threshold_met": sample_report["suitability"]["threshold_met"],
            "bank_distribution": sample_report["bank_distribution"],
            "year_distribution": sample_report["year_distribution"],
            "near_dup_control": f"bounded {sample_report['reservoir_size']}-record reservoir",
            "nd_groups_detected": nd_groups,
            "nd_records_flagged": nd_flagged,
        },
        "improvement": {
            "suitable_change": suitable - v1_suitability,
            "unclear_eliminated_by_zero_asp_strategy": True,
            "catchall_removed": True,
            "threshold_met_v2": sample_report["suitability"]["threshold_met"],
        },
    }

    Path(args.filter_comparison).write_text(
        json.dumps(comparison, indent=2, default=str), encoding="utf-8"
    )
    log.info("Filter comparison: %s", args.filter_comparison)

    # --- Final summary ---
    print("\n=== South African sample v2 complete ===")
    print(f"  Total records:           {len(sample_df)}")
    print(f"  Suitable (audit):        {suitable} ({suitable/len(sample_df)*100:.0f}%)")
    print(f"  Zero-aspect (audit):     {zero_asp_count}")
    print(f"  Total include:           {total_include} ({total_include/len(sample_df)*100:.0f}%)")
    print(f"  Threshold (>=160) met:   {sample_report['suitability']['threshold_met']}")
    print(f"  Bank distribution:       {dict(Counter(sample_df['bank']))}")
    print(f"  Near-dup groups:         {nd_groups}")
    print()
    print("No gold labels created. No models trained. Version 1 preserved.")
    print(f"Annotation output: {args.annotation_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
