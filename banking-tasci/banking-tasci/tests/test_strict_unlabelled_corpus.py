"""Tests for the strict unlabelled-corpus builder.

The central invariant: **the strict 110,615-record corpus must not be claimed
or produced while the 1,000 gold identifiers do not exist.** Requirements
Migration Principle 6 forbids fabricating identifiers, and removing 1,000
arbitrary records to hit the target would be exactly that.

These tests therefore spend as much effort proving the builder *refuses* as
proving it works.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from banking_tasci.data.unlabelled_corpus import (  # noqa: E402
    APPROVED_TEXT_FIELDS,
    EXCLUDED_FIELDS,
    EXPECTED_COUNTS,
    MODE_FINAL,
    MODE_PREPARATION,
    READINESS_BLOCKED,
    READINESS_READY,
    GoldIdSet,
    all_excluded_fields,
    assess_readiness,
    build_strict_corpus,
    load_gold_ids,
)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "strict_corpus_cli",
        _PROJECT_ROOT / "scripts" / "build_strict_unlabelled_corpus.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = _load_cli()

VERIFIED = {"status": "VERIFIED", "row_count": 100_768, "sha256": "abc"}
VERIFIED_INTL = {"status": "VERIFIED", "row_count": 10_847, "sha256": "def"}
VERIFIED_COMBINED = {
    "status": "VERIFIED",
    "counts": {"combined_relevant": 111_615},
    "sha256": "ghi",
}


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


def test_expected_counts_match_requirements():
    c = EXPECTED_COUNTS
    assert c["south_africa_candidates"] == 100_768
    assert c["south_africa_gold"] == 500
    assert c["south_africa_unlabelled"] == 100_268
    assert c["international_prepared"] == 10_847
    assert c["international_gold"] == 500
    assert c["international_unlabelled"] == 10_347
    assert c["combined_relevant"] == 111_615
    assert c["gold_total"] == 1_000
    assert c["strict_unlabelled"] == 110_615


def test_arithmetic_is_internally_consistent():
    report = assess_readiness()
    checks = report.arithmetic_checks
    assert checks["south_africa"]["consistent"] is True
    assert checks["international"]["consistent"] is True
    assert checks["international_gold_split"]["consistent"] is True
    assert checks["combined"]["consistent"] is True
    assert checks["cross_check"]["consistent"] is True
    assert checks["all_consistent"] is True


def test_source_unlabelled_counts_sum_to_strict_total():
    c = EXPECTED_COUNTS
    assert c["south_africa_unlabelled"] + c["international_unlabelled"] == c[
        "strict_unlabelled"
    ]


# ---------------------------------------------------------------------------
# PREPARATION mode never claims a corpus
# ---------------------------------------------------------------------------


def test_preparation_never_reports_corpus_built():
    report = assess_readiness()
    assert report.mode == MODE_PREPARATION
    assert report.corpus_built is False


def test_preparation_is_blocked_without_gold_ids():
    report = assess_readiness(
        south_africa_manifest=VERIFIED,
        international_manifest=VERIFIED_INTL,
        combined_manifest=VERIFIED_COMBINED,
    )
    assert report.readiness == READINESS_BLOCKED
    assert any("gold" in b.lower() for b in report.blockers)


def test_preparation_blocked_when_manifest_missing():
    report = assess_readiness(south_africa_manifest=VERIFIED)
    assert report.readiness == READINESS_BLOCKED
    assert any("international" in b for b in report.blockers)


def test_preparation_blocked_when_manifest_not_verified():
    report = assess_readiness(
        south_africa_manifest={"status": "MISMATCH", "row_count": 1},
        international_manifest=VERIFIED_INTL,
        combined_manifest=VERIFIED_COMBINED,
    )
    assert report.readiness == READINESS_BLOCKED
    assert any("not VERIFIED" in b for b in report.blockers)


def test_preparation_reports_missing_gold_manifest_path(tmp_path):
    report = assess_readiness(
        south_africa_manifest=VERIFIED,
        international_manifest=VERIFIED_INTL,
        combined_manifest=VERIFIED_COMBINED,
        gold_id_manifest_paths={"combined_gold": tmp_path / "absent.json"},
    )
    assert report.gold_id_manifests["combined_gold"]["exists"] is False
    assert report.readiness == READINESS_BLOCKED


def test_preparation_lists_final_mode_requirements():
    report = assess_readiness()
    joined = " ".join(report.gold_exclusion_requirements).lower()
    assert "500" in joined
    assert "250" in joined
    assert "1,000" in joined or "1000" in joined
    assert "zero overlap" in joined
    assert "stable identifier" in joined


def test_preparation_notes_prohibit_arbitrary_removal():
    report = assess_readiness()
    joined = " ".join(report.notes).lower()
    assert "prohibited" in joined or "cannot be produced" in joined


def test_readiness_becomes_ready_with_valid_gold_manifest(tmp_path):
    gold = {
        "south_africa": [f"sa{i}" for i in range(500)],
        "international_tweets": [f"it{i}" for i in range(250)],
        "international_reviews": [f"ir{i}" for i in range(250)],
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(gold), encoding="utf-8")

    report = assess_readiness(
        south_africa_manifest=VERIFIED,
        international_manifest=VERIFIED_INTL,
        combined_manifest=VERIFIED_COMBINED,
        gold_id_manifest_paths={"combined_gold": path},
    )
    assert report.blockers == []
    assert report.readiness == READINESS_READY
    # Even when READY, PREPARATION still builds nothing.
    assert report.corpus_built is False


# ---------------------------------------------------------------------------
# Gold ID validation
# ---------------------------------------------------------------------------


def _valid_gold() -> GoldIdSet:
    return GoldIdSet(
        south_africa=tuple(f"sa{i}" for i in range(500)),
        international_tweets=tuple(f"it{i}" for i in range(250)),
        international_reviews=tuple(f"ir{i}" for i in range(250)),
    )


def test_valid_gold_set_passes():
    assert _valid_gold().validate() == []
    assert _valid_gold().total == 1_000


def test_wrong_south_africa_count_rejected():
    gold = GoldIdSet(
        south_africa=tuple(f"sa{i}" for i in range(499)),
        international_tweets=tuple(f"it{i}" for i in range(250)),
        international_reviews=tuple(f"ir{i}" for i in range(250)),
    )
    problems = gold.validate()
    assert any("500 South African" in p for p in problems)


def test_wrong_tweet_count_rejected():
    gold = GoldIdSet(
        south_africa=tuple(f"sa{i}" for i in range(500)),
        international_tweets=tuple(f"it{i}" for i in range(249)),
        international_reviews=tuple(f"ir{i}" for i in range(250)),
    )
    assert any("250 international tweet" in p for p in gold.validate())


def test_wrong_review_count_rejected():
    gold = GoldIdSet(
        south_africa=tuple(f"sa{i}" for i in range(500)),
        international_tweets=tuple(f"it{i}" for i in range(250)),
        international_reviews=tuple(f"ir{i}" for i in range(251)),
    )
    assert any("250 international review" in p for p in gold.validate())


def test_duplicate_gold_ids_rejected():
    gold = GoldIdSet(
        south_africa=tuple(["dup"] * 500),
        international_tweets=tuple(f"it{i}" for i in range(250)),
        international_reviews=tuple(f"ir{i}" for i in range(250)),
    )
    assert any("not unique" in p for p in gold.validate())


def test_cross_source_duplicate_ids_rejected():
    shared = "shared_id"
    gold = GoldIdSet(
        south_africa=tuple([shared] + [f"sa{i}" for i in range(499)]),
        international_tweets=tuple([shared] + [f"it{i}" for i in range(249)]),
        international_reviews=tuple(f"ir{i}" for i in range(250)),
    )
    assert any("not unique" in p for p in gold.validate())


def test_load_gold_ids_round_trip(tmp_path):
    payload = {
        "south_africa": ["a", "b"],
        "international_tweets": ["c"],
        "international_reviews": ["d"],
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    gold = load_gold_ids(path)
    assert gold.south_africa == ("a", "b")
    assert gold.total == 4
    assert gold.all_ids == {"a", "b", "c", "d"}


# ---------------------------------------------------------------------------
# FINAL mode refuses invalid input
# ---------------------------------------------------------------------------


def _combined_frame(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "record_id": [f"r{i}" for i in range(n)],
            "text": [f"banking feedback {i}" for i in range(n)],
        }
    )


def test_final_refuses_invalid_gold_set():
    frame = _combined_frame(10)
    bad = GoldIdSet(south_africa=("r0",))
    with pytest.raises(ValueError, match="invalid gold ID set"):
        build_strict_corpus(frame, bad)


def test_final_refuses_when_gold_ids_absent_from_corpus():
    """Gold IDs that are not present cannot be excluded, so the count is wrong."""
    frame = _combined_frame(2_000)  # no sa*/it*/ir* identifiers
    with pytest.raises(ValueError, match="some gold identifiers were absent"):
        build_strict_corpus(frame, _valid_gold(), expected_count=1_000)


def test_final_refuses_on_count_mismatch():
    gold = _valid_gold()
    rows = list(gold.all_ids) + [f"extra{i}" for i in range(5)]
    frame = pd.DataFrame({"record_id": rows, "text": ["x"] * len(rows)})
    # 1,005 - 1,000 = 5 remain, but claim to expect 110,615.
    with pytest.raises(ValueError, match="Refusing to trim or pad"):
        build_strict_corpus(frame, gold, expected_count=110_615)


def test_final_requires_record_id():
    gold = _valid_gold()
    frame = pd.DataFrame({"text": ["x"]})
    with pytest.raises(ValueError, match="record_id"):
        build_strict_corpus(frame, gold)


def test_final_requires_approved_text_field():
    gold = _valid_gold()
    frame = pd.DataFrame({"record_id": ["a"]})
    with pytest.raises(ValueError, match="approved text field"):
        build_strict_corpus(frame, gold)


# ---------------------------------------------------------------------------
# FINAL mode succeeds on a valid, complete input
# ---------------------------------------------------------------------------


def _frame_with_gold(extra: int) -> pd.DataFrame:
    gold = _valid_gold()
    ids = list(gold.all_ids) + [f"keep{i}" for i in range(extra)]
    return pd.DataFrame(
        {
            "record_id": ids,
            "text": [f"text {i}" for i in range(len(ids))],
            # Fields that MUST be excluded from the strict corpus.
            "sentiment": ["positive"] * len(ids),
            "intent": ["complaint"] * len(ids),
            "bank": ["fnb"] * len(ids),
            "region": ["south_africa"] * len(ids),
            "rating": [5.0] * len(ids),
            "split": ["train"] * len(ids),
            "candidate_strata": ["x"] * len(ids),
            "annotation_status": ["completed"] * len(ids),
        }
    )


def test_final_excludes_exactly_the_gold_records():
    frame = _frame_with_gold(extra=50)
    strict, report = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    assert len(strict) == 50
    assert report["gold_records_excluded"] == 1_000
    assert report["corpus_built"] is True


def test_final_leaves_zero_gold_overlap():
    frame = _frame_with_gold(extra=50)
    strict, report = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    assert set(strict["record_id"]) & _valid_gold().all_ids == set()
    assert report["gold_overlap_with_strict"] == 0


def test_final_strips_every_excluded_field():
    frame = _frame_with_gold(extra=50)
    strict, _ = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    for forbidden in all_excluded_fields():
        assert forbidden not in strict.columns


def test_final_retains_only_identifier_and_text_by_default():
    frame = _frame_with_gold(extra=50)
    strict, _ = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    assert set(strict.columns) == {"record_id", *APPROVED_TEXT_FIELDS}


def test_final_can_retain_context_when_approved():
    frame = _frame_with_gold(extra=50)
    frame["previous_text"] = "earlier sentence"
    frame["context_available"] = True
    strict, report = build_strict_corpus(
        frame, _valid_gold(), include_context=True, expected_count=50
    )
    assert "previous_text" in strict.columns
    assert report["include_context"] is True


def test_final_report_has_logical_checksum():
    frame = _frame_with_gold(extra=50)
    _, report = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    assert len(report["logical_checksum"]) == 64


def test_final_is_deterministic():
    frame = _frame_with_gold(extra=50)
    first, r1 = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    second, r2 = build_strict_corpus(frame, _valid_gold(), expected_count=50)
    assert r1["logical_checksum"] == r2["logical_checksum"]
    assert list(first["record_id"]) == list(second["record_id"])


# ---------------------------------------------------------------------------
# Field policy
# ---------------------------------------------------------------------------


def test_excluded_fields_cover_every_required_category():
    """Requirements Section 16's exclusion list."""
    assert "sentiment" in EXCLUDED_FIELDS["task_labels"]
    assert "intent" in EXCLUDED_FIELDS["task_labels"]
    assert "category" in EXCLUDED_FIELDS["task_labels"]
    assert "target" in EXCLUDED_FIELDS["task_labels"]
    assert "annotation_notes" in EXCLUDED_FIELDS["annotation_metadata"]
    assert "annotation_status" in EXCLUDED_FIELDS["annotation_metadata"]
    assert "split" in EXCLUDED_FIELDS["partition_labels"]
    assert "rating" in EXCLUDED_FIELDS["predictive_shortcuts"]
    assert "bank" in EXCLUDED_FIELDS["predictive_shortcuts"]
    assert "region" in EXCLUDED_FIELDS["predictive_shortcuts"]
    assert "source" in EXCLUDED_FIELDS["predictive_shortcuts"]
    assert "candidate_strata" in EXCLUDED_FIELDS["candidate_and_sampling_rules"]


def test_approved_text_fields_are_minimal():
    """Only text may be model-visible; provenance lives in the manifest."""
    assert APPROVED_TEXT_FIELDS == ("text",)


def test_field_policy_is_reported():
    report = assess_readiness()
    policy = report.field_policy
    assert policy["approved_text_fields"] == ["text"]
    assert "predictive_shortcuts" in policy["excluded_fields_by_reason"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_preparation_is_blocked_and_writes_report(tmp_path):
    report_path = tmp_path / "readiness.json"
    rc = CLI.main([
        "--mode", MODE_PREPARATION,
        "--gold-ids", str(tmp_path / "absent.json"),
        "--report", str(report_path),
    ])
    assert rc == 3  # blocked
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["corpus_built"] is False
    assert payload["readiness"] == READINESS_BLOCKED


def test_cli_final_refuses_without_gold_manifest(tmp_path):
    rc = CLI.main([
        "--mode", MODE_FINAL,
        "--gold-ids", str(tmp_path / "absent.json"),
        "--report", str(tmp_path / "r.json"),
    ])
    assert rc == 3


def test_cli_final_refuses_invalid_gold_manifest(tmp_path):
    path = tmp_path / "bad_gold.json"
    path.write_text(json.dumps({"south_africa": ["only_one"]}), encoding="utf-8")
    rc = CLI.main([
        "--mode", MODE_FINAL,
        "--gold-ids", str(path),
        "--report", str(tmp_path / "r.json"),
    ])
    assert rc == 3


def test_cli_preparation_never_writes_a_corpus(tmp_path):
    corpus_path = tmp_path / "strict.parquet"
    CLI.main([
        "--mode", MODE_PREPARATION,
        "--gold-ids", str(tmp_path / "absent.json"),
        "--report", str(tmp_path / "r.json"),
        "--output", str(corpus_path),
    ])
    assert not corpus_path.exists()
