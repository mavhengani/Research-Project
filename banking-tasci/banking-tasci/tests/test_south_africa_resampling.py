"""Focused tests for the South African v2 candidate filter and resampling.

Tests only the filter logic and sampling mechanics using in-memory fixtures.
Does not read any raw parquet, does not modify gold files, does not train models.

Run with (after approval):
    PYTHONPATH=src python3 -m pytest tests/test_ingest_south_africa.py \
        tests/test_south_africa_resampling.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Nine tests in this module import `scripts.resample_south_africa_v2`. There is
# no `scripts/__init__.py`, so `scripts` is only importable while the PROJECT
# ROOT (not just `src/`) is on sys.path. Relying on pytest's implicit rootdir
# insertion made those nine tests order-dependent: this module passed 54/54 in
# isolation but its nine `from scripts...` tests failed when run after modules
# whose own sys.path manipulation changed resolution order, producing
# "ModuleNotFoundError: No module named 'scripts'".
#
# Inserting the project root explicitly - exactly as this module already does
# for `src/` - makes the import self-sufficient and order-independent. The
# resampling implementation itself was not changed; the fragility was in how
# the test module resolved its own imports.
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from banking_tasci.data.sa_candidate_filter import (
    classify_candidate,
    is_potential_zero_aspect,
    BANKING_ASPECT_PATTERNS,
    PROBLEM_PATTERNS,
    REQUEST_PATTERNS,
    FIRST_PERSON_PATTERNS,
    POSITIVE_PATTERNS,
    CHURN_PATTERNS,
    WARNING_PATTERNS,
    SUGGESTION_PATTERNS,
    SPECIFIC_ISSUE_PATTERNS,
)


# ---------------------------------------------------------------------------
# Catch-all removal
# ---------------------------------------------------------------------------

class TestNoCatchAll:
    def test_long_unrelated_text_not_candidate(self):
        """A long text with no banking keywords must not be a candidate."""
        text = ("I had a wonderful birthday party last night with all my friends "
                "and family. The food was amazing and the music was great. "
                "I will never forget this special day.")
        result = classify_candidate(text)
        assert not result.is_candidate, f"Expected not candidate, got rule={result.rule_matched}"

    def test_length_alone_not_sufficient(self):
        """Text length >= 30 alone must not qualify a record."""
        text = "Today was a really great day for sport and politics in South Africa."
        result = classify_candidate(text)
        assert not result.is_candidate

    def test_bank_name_alone_not_sufficient(self):
        """Mentioning FNB without a banking experience does not qualify."""
        text = "I saw an FNB advertisement on television this morning."
        result = classify_candidate(text)
        assert not result.is_candidate

    def test_user_token_alone_not_sufficient(self):
        """[USER] token (anonymised @mention) alone does not qualify."""
        text = "[USER] I really agree with what you said about the weather."
        result = classify_candidate(text)
        assert not result.is_candidate


# ---------------------------------------------------------------------------
# Rule A: aspect + problem
# ---------------------------------------------------------------------------

class TestRuleA:
    def test_transfer_failed(self):
        result = classify_candidate("My transfer failed and the money has not been reversed.")
        assert result.is_candidate
        assert result.rule_matched == "A"

    def test_card_declined(self):
        result = classify_candidate("My card was declined at the till today.")
        assert result.is_candidate
        assert result.rule_matched in ("A", "C", "F")

    def test_account_blocked(self):
        result = classify_candidate("My account has been blocked for no reason.")
        assert result.is_candidate

    def test_online_banking_error(self):
        result = classify_candidate("I keep getting an error when I use online banking.")
        assert result.is_candidate

    def test_poor_customer_service(self):
        result = classify_candidate("The customer service at this branch is terrible.")
        assert result.is_candidate


# ---------------------------------------------------------------------------
# Rule B: aspect + request
# ---------------------------------------------------------------------------

class TestRuleB:
    def test_please_help_transfer(self):
        result = classify_candidate("Please help me with my transfer that has not gone through.")
        assert result.is_candidate
        assert result.rule_matched in ("A", "B", "C")

    def test_kindly_reverse(self):
        result = classify_candidate(
            "Kindly reverse the transaction that was debited from my account."
        )
        assert result.is_candidate

    def test_need_help_with_card(self):
        result = classify_candidate("I need help with my card that is not working.")
        assert result.is_candidate

    def test_investigate_deduction(self):
        result = classify_candidate(
            "Please investigate the deduction that appeared on my account today."
        )
        assert result.is_candidate


# ---------------------------------------------------------------------------
# Rule C: first-person + aspect
# ---------------------------------------------------------------------------

class TestRuleC:
    def test_my_account_issue(self):
        result = classify_candidate("My account has been frozen since yesterday.")
        assert result.is_candidate
        assert result.rule_matched in ("A", "C", "F")

    def test_i_was_charged(self):
        result = classify_candidate("I was charged a fee I did not expect.")
        assert result.is_candidate

    def test_my_card_problem(self):
        result = classify_candidate("My card keeps getting declined at the ATM.")
        assert result.is_candidate

    def test_they_debited_me(self):
        result = classify_candidate("They debited me twice for the same transaction.")
        assert result.is_candidate


# ---------------------------------------------------------------------------
# Rule D: positive service + bank reference
# ---------------------------------------------------------------------------

class TestRuleD:
    def test_great_service(self):
        result = classify_candidate(
            "Excellent service at my bank today — the consultant was very helpful."
        )
        assert result.is_candidate
        assert result.rule_matched in ("A", "B", "C", "D")

    def test_thank_you_for_resolving(self):
        result = classify_candidate(
            "Thank you for resolving my query so quickly. Great support!"
        )
        assert result.is_candidate

    def test_positive_no_bank_context_not_rule_D(self):
        # No banking keyword: should not be a candidate
        result = classify_candidate("Amazing food and wonderful atmosphere at the restaurant.")
        assert not result.is_candidate


# ---------------------------------------------------------------------------
# Rule E: suggestion / warning / churn + banking reference
# ---------------------------------------------------------------------------

class TestRuleE:
    def test_suggestion_banking(self):
        result = classify_candidate(
            "Please add an option to schedule payments in advance on the banking app."
        )
        assert result.is_candidate
        assert result.rule_matched in ("B", "E")

    def test_warning_banking(self):
        result = classify_candidate(
            "Beware of this bank — they charge hidden fees and never respond."
        )
        assert result.is_candidate

    def test_churn_banking(self):
        result = classify_candidate(
            "I am closing my account and switching banks after this experience."
        )
        assert result.is_candidate

    def test_churn_without_banking_reference_not_E(self):
        # "switching banks" itself contains "bank" so this should still match
        result = classify_candidate("Switching banks is the only option left for me.")
        assert result.is_candidate  # "banks" matches banking reference


# ---------------------------------------------------------------------------
# Rule F: strongly specific phrases
# ---------------------------------------------------------------------------

class TestRuleF:
    def test_failed_transaction(self):
        result = classify_candidate("A failed transaction occurred on my account.")
        assert result.is_candidate
        # Rule F fires for specific phrases; A may also match via aspect+problem
        assert result.rule_matched in ("A", "C", "F")

    def test_unauthorised_transaction(self):
        result = classify_candidate(
            "There was an unauthorised transaction on my account last night."
        )
        assert result.is_candidate
        assert result.rule_matched == "F"

    def test_blocked_account(self):
        result = classify_candidate("My blocked account has not been restored in five days.")
        assert result.is_candidate

    def test_card_not_working(self):
        result = classify_candidate("Card not working at the ATM — please fix this.")
        assert result.is_candidate


# ---------------------------------------------------------------------------
# Word-boundary handling
# ---------------------------------------------------------------------------

class TestWordBoundaries:
    def test_app_does_not_match_happy(self):
        """'app' must not fire inside 'happy'."""
        # "happy" has no banking aspect or problem expression
        # so even if 'app' were to match, it would not make a candidate
        # without another signal. Test directly:
        text = "I am so happy about my birthday party today."
        result = classify_candidate(text)
        assert not result.is_candidate

    def test_app_does_not_match_nappy(self):
        text = "Buying nappies is getting expensive these days."
        result = classify_candidate(text)
        assert not result.is_candidate

    def test_bank_in_river_context_excluded(self):
        result = classify_candidate(
            "We went fishing on the river bank last Sunday."
        )
        assert not result.is_candidate

    def test_bank_in_blood_bank_excluded(self):
        result = classify_candidate(
            "Please donate blood at the blood bank this weekend."
        )
        assert not result.is_candidate

    def test_pin_not_matching_inside_opinion(self):
        """'pin' should not fire in 'pinpoint' or random contexts."""
        text = "The artist used a pin to attach the poster."
        result = classify_candidate(text)
        assert not result.is_candidate

    def test_card_not_matching_cardboard(self):
        """'card' as word boundary should not match 'cardboard'."""
        text = "I used cardboard to make a birthday decoration."
        result = classify_candidate(text)
        assert not result.is_candidate

    def test_fee_not_matching_feel(self):
        """'fee' should not match inside 'feel'."""
        text = "I feel happy today about my new job."
        result = classify_candidate(text)
        assert not result.is_candidate


# ---------------------------------------------------------------------------
# Promotional precedence
# ---------------------------------------------------------------------------

class TestPromotionalPrecedence:
    def test_giveaway_only_excluded(self):
        result = classify_candidate(
            "Win R500 in our amazing giveaway competition this weekend."
        )
        assert not result.is_candidate or result.is_promotional

    def test_promo_with_personal_experience_may_qualify(self):
        # If promo + genuine first-person banking issue, should be retained
        result = classify_candidate(
            "I entered the competition but my account was debited incorrectly."
        )
        # Has "my account" + "debited" (aspect+problem) — should qualify
        assert result.is_candidate

    def test_recruitment_not_candidate(self):
        result = classify_candidate(
            "We are hiring customer service consultants. Apply now for banking career."
        )
        # Promotional/recruitment — should not be candidate
        # May match some rules but promotional should precede
        # The filter applies promotional precedence when no personal experience
        assert not result.is_candidate or result.is_promotional


# ---------------------------------------------------------------------------
# Unrelated bank meanings
# ---------------------------------------------------------------------------

class TestUnrelatedBankMeanings:
    def test_food_bank_excluded(self):
        result = classify_candidate(
            "Please donate food to the local food bank in your area."
        )
        assert not result.is_candidate

    def test_bank_of_england_excluded(self):
        result = classify_candidate(
            "The Bank of England raised interest rates today."
        )
        assert not result.is_candidate

    def test_sa_bank_name_in_genuine_complaint_included(self):
        result = classify_candidate(
            "FNB has debited my account twice this month without explanation."
        )
        assert result.is_candidate


# ---------------------------------------------------------------------------
# Zero-aspect identification
# ---------------------------------------------------------------------------

class TestZeroAspect:
    def test_bank_mention_no_aspect_is_zero_aspect(self):
        text = "I really like the way FNB has been handling things lately."
        assert is_potential_zero_aspect(text) is True

    def test_generic_comment_with_bank_name(self):
        text = "ABSA is a well-known South African bank."
        assert is_potential_zero_aspect(text) is True

    def test_clear_transaction_complaint_not_zero_aspect(self):
        text = "My transfer failed and the money is missing from my account."
        assert is_potential_zero_aspect(text) is False  # has specific aspect

    def test_short_text_not_zero_aspect(self):
        text = "FNB"
        assert is_potential_zero_aspect(text) is False


# ---------------------------------------------------------------------------
# Annotation output has no hints or labels
# ---------------------------------------------------------------------------

class TestAnnotationOutputV2:
    def _make_sample_row(self):
        return {
            "record_id": "abc123",
            "bank": "fnb",
            "text": "My transfer failed please help me resolve this.",
            "created_at": "2021-05-10",
            "rule_matched": "A",
            "matched_strata": ["transactions_candidate"],
            "is_promotional": False,
            "is_zero_aspect": False,
            "sample_role": "feedback",
        }

    def test_annotation_record_has_no_labels(self):
        import pandas as pd
        from scripts.resample_south_africa_v2 import to_annotation_records_v2
        df = pd.DataFrame([self._make_sample_row()])
        records = to_annotation_records_v2(df)
        r = records[0]
        assert r["aspects"] == []
        assert r["intent"] is None
        assert r["annotation_status"] == "not_started"

    def test_annotation_record_no_strata_hints(self):
        import pandas as pd
        from scripts.resample_south_africa_v2 import to_annotation_records_v2
        df = pd.DataFrame([self._make_sample_row()])
        records = to_annotation_records_v2(df)
        r = records[0]
        assert "matched_strata" not in r
        assert "rule_matched" not in r
        assert "sample_role" not in r
        assert "candidate_strata" not in r

    def test_annotation_record_no_raw_ids(self):
        import pandas as pd
        from scripts.resample_south_africa_v2 import to_annotation_records_v2
        df = pd.DataFrame([self._make_sample_row()])
        records = to_annotation_records_v2(df)
        r = records[0]
        assert "Username" not in r
        assert "Tweet_Id" not in r
        assert "tweet_id" not in r

    def test_annotation_record_context_always_no_context(self):
        import pandas as pd
        from scripts.resample_south_africa_v2 import to_annotation_records_v2
        df = pd.DataFrame([self._make_sample_row()])
        records = to_annotation_records_v2(df)
        r = records[0]
        assert r["previous_text"] == "[NO_CONTEXT]"
        assert r["context_available"] is False

    def test_annotation_record_region_south_africa(self):
        import pandas as pd
        from scripts.resample_south_africa_v2 import to_annotation_records_v2
        df = pd.DataFrame([self._make_sample_row()])
        records = to_annotation_records_v2(df)
        r = records[0]
        assert r["region"] == "south_africa"


# ---------------------------------------------------------------------------
# Deterministic sampling
# ---------------------------------------------------------------------------

class TestDeterministicSampling:
    def _make_pool(self, n=50):
        import pandas as pd
        banks = ["fnb", "absa", "nedbank", "capitec", "standard_bank"]
        rows = []
        for i in range(n):
            bank = banks[i % 5]
            rows.append({
                "record_id": f"r{i:04d}",
                "bank": bank,
                "text": f"My {bank} transfer failed and I need help with my account {i}",
                "created_at": f"2020-0{(i % 9) + 1}-15",
                "rule_matched": "A",
                "matched_strata": ["transactions_candidate", "accounts_candidate"],
                "is_promotional": False,
                "is_zero_aspect": False,
                "near_dup_group_id": None,
                "near_dup_flag": False,
            })
        return pd.DataFrame(rows)

    def _make_zero_pool(self, n=10):
        import pandas as pd
        banks = ["fnb", "absa", "nedbank"]
        rows = []
        for i in range(n):
            bank = banks[i % 3]
            rows.append({
                "record_id": f"z{i:04d}",
                "bank": bank,
                "text": f"This {bank} bank is well known in South Africa {i}",
                "created_at": "2021-06-15",
                "rule_matched": "zero_aspect",
                "matched_strata": [],
                "is_promotional": False,
                "is_zero_aspect": True,
            })
        return pd.DataFrame(rows)

    def test_deterministic_same_seed(self):
        from scripts.resample_south_africa_v2 import select_sample_v2
        import logging
        log = logging.getLogger("test")
        pool = self._make_pool(50)
        zero = self._make_zero_pool(10)
        s1, _ = select_sample_v2(pool, zero, 30, 5, 10, 20, 42, log)
        s2, _ = select_sample_v2(pool, zero, 30, 5, 10, 20, 42, log)
        assert list(s1["record_id"]) == list(s2["record_id"])

    def test_no_duplicate_ids_in_sample(self):
        from scripts.resample_south_africa_v2 import select_sample_v2
        import logging
        log = logging.getLogger("test")
        pool = self._make_pool(50)
        zero = self._make_zero_pool(10)
        sample, _ = select_sample_v2(pool, zero, 30, 5, 10, 20, 42, log)
        assert sample["record_id"].nunique() == len(sample)


# ---------------------------------------------------------------------------
# Bank diversity
# ---------------------------------------------------------------------------

class TestBankDiversity:
    def test_max_per_bank_respected(self):
        """Sample must not exceed max_per_bank for any single bank."""
        import pandas as pd
        from scripts.resample_south_africa_v2 import select_sample_v2
        import logging
        log = logging.getLogger("test")

        # 50 records, all from FNB
        rows = [{"record_id": f"r{i}", "bank": "fnb",
                 "text": f"My fnb account has a problem today {i}",
                 "created_at": "2021-01-01",
                 "rule_matched": "A",
                 "matched_strata": ["accounts_candidate"],
                 "is_promotional": False, "is_zero_aspect": False,
                 "near_dup_group_id": None, "near_dup_flag": False}
                for i in range(50)]
        pool = pd.DataFrame(rows)
        zero = pd.DataFrame()
        sample, _ = select_sample_v2(pool, zero, 30, 0, 0, 15, 42, log)
        bank_counts = sample["bank"].value_counts()
        assert bank_counts.get("fnb", 0) <= 15


# ---------------------------------------------------------------------------
# Near-dup reservoir handling
# ---------------------------------------------------------------------------

class TestNearDupReservoir:
    def test_near_dup_detection_does_not_crash_on_small_reservoir(self):
        """Near-dup detection on a small DataFrame must complete without error."""
        import pandas as pd
        from scripts.resample_south_africa_v2 import run_nd_on_reservoir
        import logging
        log = logging.getLogger("test")

        rows = [{"record_id": f"r{i}", "bank": "absa",
                 "text": f"My absa account was debited incorrectly this morning {i}",
                 "rule_matched": "A", "matched_strata": ["accounts_candidate"],
                 "near_dup_group_id": None, "near_dup_flag": False}
                for i in range(5)]
        df = pd.DataFrame(rows)
        result_df, groups, flagged = run_nd_on_reservoir(df, 42, log)
        assert len(result_df) == 5  # all records retained (action=flag)
        assert groups >= 0
