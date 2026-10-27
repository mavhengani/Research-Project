"""Candidate-2 evidence enrichment tests (NOT_RUN in implementation-only session)."""
from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from banking_tasci.data.candidate_package_diff import compare_candidate_packages  # noqa: E402
from banking_tasci.data.candidate_package_v2 import (  # noqa: E402
    CandidatePackageBuildError,
    build_candidate2_package,
    build_review_metadata_map,
    build_v2_rule_map,
)
from banking_tasci.data.gold_sample_plan import (  # noqa: E402
    INTERNATIONAL_REVIEW,
    INTERNATIONAL_TWEET,
    SOUTH_AFRICA_TWEET,
)
from banking_tasci.data.ingest import make_record_id  # noqa: E402
from banking_tasci.data.sa_candidates_v2 import SelectionResult  # noqa: E402
from scripts.build_candidate_package_v2 import (  # noqa: E402
    DEFAULT_CANDIDATE1,
    DEFAULT_CANDIDATE2,
    _install_transaction,
    _parser,
)
import scripts.build_candidate_package_v2 as staging_module  # noqa: E402


def _candidate_fixture():
    plan = []
    metadata = {}
    rules = {}
    rule_names = "ABCDEF"
    banks = ("fnb", "absa", "nedbank", "standard_bank", "capitec")
    for index in range(500):
        source_id = f"sa-{index:04d}"
        record_id = f"{SOUTH_AFRICA_TWEET}::{source_id}"
        text = f"SA feedback {index}"
        if index in {0, 1}:
            text = "verified duplicate text"
        plan.append({
            "record_id": record_id, "source_record_id": source_id,
            "source": SOUTH_AFRICA_TWEET, "region": "south_africa",
            "bank": banks[index % len(banks)], "text": text,
            "selection_reason": "bank=test; length_band=short; v2_rule=unavailable",
            "previous_text": None, "context_available": False,
        })
        metadata[source_id] = {
            "record_id": source_id, "text": text, "bank": banks[index % len(banks)],
            "near_dup_group_id": "near-verified-1" if index in {0, 1} else None,
            "thread_id": None, "source_checksum": "sa-checksum",
        }
        rules[source_id] = rule_names[index % len(rule_names)]

    for source, count, prefix in (
        (INTERNATIONAL_TWEET, 250, "it"),
        (INTERNATIONAL_REVIEW, 250, "ir"),
    ):
        for index in range(count):
            source_id = f"{prefix}-{index:04d}"
            plan.append({
                "record_id": f"{source}::{source_id}", "source_record_id": source_id,
                "source": source, "region": "international", "bank": None,
                "text": "verified duplicate text" if source == INTERNATIONAL_TWEET and index == 0 else f"{prefix} feedback {index}",
                "selection_reason": "length_band=medium", "previous_text": "fabricated old context",
                "context_available": True,
            })
    review_map = {
        f"ir-{index:04d}": {
            "bank": "HDFC Bank", "review_id": f"review::bank_reviews::ir-{index:04d}",
            "review_source_record_id": f"ir-{index:04d}",
            "review_identity_method": "review::bank_reviews::<make_record_id output>; make_record_id('bank_reviews', clean.normalise_text(full review)) computes sha256(f'{source}:{normalized_text}')[:16]; clean.normalise_text preserves case",
            "bank_correction_reason": None, "original_invalid_bank_values": [],
            "context_available": False, "previous_text": None, "source_checksum": "intl-checksum",
        }
        for index in range(250)
    }
    return plan, metadata, rules, review_map


def test_rule_join_uses_ids_after_parent_shuffle(monkeypatch):
    frame = pd.DataFrame({"record_id": ["id-a", "id-b"], "text": ["a", "b"]}).sample(frac=1, random_state=4)
    mask = pd.Series([True, True], index=frame.index)
    labels = pd.Series(["A", "F"], index=frame.index)
    from banking_tasci.data import sa_candidates_v2
    monkeypatch.setattr(sa_candidates_v2, "select_v2_candidates", lambda _: SelectionResult(mask=mask, rule_labels=labels))
    mapping = build_v2_rule_map(frame, ["id-a", "id-b"])
    expected_by_id = dict(zip(frame["record_id"], labels))
    assert mapping == expected_by_id


def test_rule_join_fails_on_missing_selected_rule(monkeypatch):
    frame = pd.DataFrame({"record_id": ["id-a"], "text": ["a"]})
    mask = pd.Series([False], index=frame.index)
    labels = pd.Series(["A"], index=frame.index)
    from banking_tasci.data import sa_candidates_v2
    monkeypatch.setattr(sa_candidates_v2, "select_v2_candidates", lambda _: SelectionResult(mask=mask, rule_labels=labels))
    with pytest.raises(CandidatePackageBuildError, match="no v2 rule"):
        build_v2_rule_map(frame, ["id-a"])


def test_rule_join_fails_on_duplicate_parent_ids():
    frame = pd.DataFrame({"record_id": ["same", "same"], "text": ["a", "b"]})
    with pytest.raises(CandidatePackageBuildError, match="duplicate"):
        build_v2_rule_map(frame, ["same"])


def test_review_id_matches_ingestion_identity_and_preserves_case():
    text = "Case Sensitive Review"
    source_id = make_record_id("bank_reviews", text)
    raw = pd.DataFrame([{"review": text, "bank": "HDFC Bank", "bank_image": "hdfc.png"}])
    prepared = pd.DataFrame([{"record_id": source_id, "source": "bank_reviews", "bank": "review"}])
    mapped, report = build_review_metadata_map(raw, prepared, source_checksum="manifest-sha")
    assert mapped[source_id]["review_id"] == f"review::bank_reviews::{source_id}"
    assert mapped[source_id]["bank"] == "HDFC Bank"
    assert report["source_id_algorithm"] == "make_record_id('bank_reviews', clean.normalise_text(review))"


def test_invalid_review_bank_is_null_not_inferred_from_image():
    text = "review text"
    source_id = make_record_id("bank_reviews", text)
    raw = pd.DataFrame([{"review": text, "bank": "review", "bank_image": "ALL_BANKS.png"}])
    prepared = pd.DataFrame([{"record_id": source_id, "source": "bank_reviews", "bank": "review"}])
    mapped, report = build_review_metadata_map(raw, prepared)
    assert mapped[source_id]["bank"] is None
    assert report["set_null_because_bank_unavailable_or_invalid"] == 1


def test_candidate2_enrichment_is_label_hidden_and_groups_all_duplicate_members():
    plan, metadata, rules, review_map = _candidate_fixture()
    updated_plan, annotation, report = build_candidate2_package(
        plan, sa_source_metadata=metadata, v2_rule_map=rules,
        review_metadata=review_map,
        review_metadata_report={"corrected_using_verified_source_evidence": 0},
    )
    assert len(updated_plan) == len(annotation) == 1000
    assert len({record["record_id"] for record in annotation}) == 1000
    assert report["source_distribution"] == {
        SOUTH_AFRICA_TWEET: 500, INTERNATIONAL_TWEET: 250, INTERNATIONAL_REVIEW: 250,
    }
    assert report["region_distribution"] == {"international": 500, "south_africa": 500}
    assert set(report["rule_distribution"]) == set("ABCDEF")
    assert all(record["annotation_status"] == "not_started" for record in annotation)
    assert all(record["opinions"] == [] and record["primary_intent"] is None for record in annotation)
    assert all(record["previous_text"] is None and record["context_available"] is False
               for record in annotation if record["source"] == INTERNATIONAL_REVIEW)
    duplicate_members = [record for record in updated_plan if record["source_record_id"] in {"sa-0000", "sa-0001", "it-0000"}]
    assert len({record["duplicate_group"] for record in duplicate_members}) == 1
    assert len({record["leakage_group"] for record in duplicate_members}) == 1
    review_plan_records = [record for record in updated_plan if record["source"] == INTERNATIONAL_REVIEW]
    assert all(record["duplicate_group"] is None for record in review_plan_records)
    assert len({record["leakage_group"] for record in review_plan_records}) == len(review_plan_records)
    assert updated_plan[0]["verified_near_dup_group_id"] == "near-verified-1"


def test_candidate2_rejects_review_id_not_derived_from_source_record_id():
    plan, metadata, rules, review_map = _candidate_fixture()
    review_map["ir-0000"]["review_id"] = "review::invented"
    with pytest.raises(CandidatePackageBuildError, match="immutable source record ID"):
        build_candidate2_package(
            plan, sa_source_metadata=metadata, v2_rule_map=rules,
            review_metadata=review_map,
        )


def test_candidate_diff_joins_by_canonical_id_not_row_position():
    first = [
        {"record_id": "source::a", "source": "s", "region": "r", "bank": "review"},
        {"record_id": "source::b", "source": "s", "region": "r", "bank": None},
    ]
    second = [dict(first[1]), dict(first[0], bank=None, review_id="review::stable")]
    diff = compare_candidate_packages(
        first, second, candidate1_checksum="one", candidate2_checksum="two",
    )
    assert diff["changed_canonical_ids"] == ["source::a"]
    assert diff["bank_corrections"]["source::a"] == {"candidate_1": "review", "candidate_2": None}
    assert diff["records_added"] == diff["records_removed"] == 0
    assert diff["review_id_changes"]["source::a"]["candidate_2"] == "review::stable"


def test_annotation_batches_has_single_public_function_definitions():
    path = SRC / "banking_tasci/data/annotation_batches.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    definitions = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert len(definitions) == len(set(definitions))


def test_candidate2_staging_is_dry_run_by_default_and_has_separate_root():
    args = _parser().parse_args([])
    assert args.write is False
    assert args.candidate1_root == DEFAULT_CANDIDATE1
    assert args.candidate2_root == DEFAULT_CANDIDATE2
    assert DEFAULT_CANDIDATE1 != DEFAULT_CANDIDATE2


def test_staging_cli_dry_run_does_not_write(monkeypatch, tmp_path):
    target = tmp_path / "candidate2"
    monkeypatch.setattr(
        staging_module, "_prepare",
        lambda _args: ({target: {"record.jsonl": b"candidate-2\n"}}, {"dry_run": True}),
    )
    assert staging_module.main([]) == 0
    assert not target.exists()


def test_staging_transaction_refuses_overwrite_and_preserves_candidate1(tmp_path):
    protected_candidate1 = tmp_path / "data/annotations/new_pipeline_v1"
    protected_candidate1.mkdir(parents=True)
    protected_file = protected_candidate1 / "annotation_records.jsonl"
    protected_file.write_text("candidate-1\n", encoding="utf-8")
    before = hashlib.sha256(protected_file.read_bytes()).hexdigest()

    candidate2 = tmp_path / "data/annotations/new_pipeline_v1_candidate_2"
    candidate2.mkdir(parents=True)
    (candidate2 / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    staging = tmp_path / ".candidate2.staging"
    staging.mkdir()
    (staging / "new.txt").write_text("candidate-2", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _install_transaction({candidate2: staging}, overwrite=False)
    assert hashlib.sha256(protected_file.read_bytes()).hexdigest() == before
    assert (candidate2 / "existing.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_explicit_staging_overwrite_only_replaces_candidate2(tmp_path):
    candidate1 = tmp_path / "data/annotations/new_pipeline_v1"
    candidate1.mkdir(parents=True)
    protected = candidate1 / "gold_sample_plan.jsonl"
    protected.write_text("immutable", encoding="utf-8")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    candidate2 = tmp_path / "data/annotations/new_pipeline_v1_candidate_2"
    candidate2.mkdir(parents=True)
    (candidate2 / "old.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / ".candidate2.replacement"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")
    _install_transaction({candidate2: staging}, overwrite=True)
    assert (candidate2 / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (candidate2 / "old.txt").exists()
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before
