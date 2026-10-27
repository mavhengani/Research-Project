"""Tests for near-duplicate detection in banking_tasci.data.clean.

These tests use small in-memory examples only.  They do not read any file
from disk (no prepared.csv, no raw CSVs) and do not import or use any
neural model.

Run with:
    pytest tests/test_near_duplicates.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from banking_tasci.data.clean import (
    NearDupConfig,
    NearDupResult,
    _jaccard,
    _lsh_candidate_pairs,
    _minhash_signature,
    _shingle,
    _UnionFind,
    _build_hash_params,
    detect_near_duplicates,
)


# ---------------------------------------------------------------------------
# Unit tests: shingle
# ---------------------------------------------------------------------------


def test_shingle_basic():
    s = _shingle("hello", 3)
    assert isinstance(s, frozenset)
    # "hel", "ell", "llo"
    assert len(s) == 3


def test_shingle_text_shorter_than_k():
    assert _shingle("hi", 4) == frozenset()


def test_shingle_empty():
    assert _shingle("", 3) == frozenset()


def test_shingle_exact_k():
    # Text length == k → exactly one shingle
    assert len(_shingle("abc", 3)) == 1


def test_shingle_identical_texts_same_set():
    assert _shingle("hello world", 4) == _shingle("hello world", 4)


def test_shingle_different_texts_different_set():
    assert _shingle("hello world", 4) != _shingle("goodbye world", 4)


# ---------------------------------------------------------------------------
# Unit tests: Jaccard
# ---------------------------------------------------------------------------


def test_jaccard_identical():
    a = frozenset([1, 2, 3])
    assert _jaccard(a, a) == 1.0


def test_jaccard_disjoint():
    a = frozenset([1, 2])
    b = frozenset([3, 4])
    assert _jaccard(a, b) == 0.0


def test_jaccard_partial():
    a = frozenset([1, 2, 3])
    b = frozenset([2, 3, 4])
    j = _jaccard(a, b)
    assert abs(j - 2 / 4) < 1e-9


def test_jaccard_both_empty():
    assert _jaccard(frozenset(), frozenset()) == 1.0


def test_jaccard_one_empty():
    assert _jaccard(frozenset([1]), frozenset()) == 0.0


# ---------------------------------------------------------------------------
# Unit tests: UnionFind
# ---------------------------------------------------------------------------


def test_union_find_no_unions():
    uf = _UnionFind(4)
    for i in range(4):
        assert uf.find(i) == i


def test_union_find_basic_union():
    uf = _UnionFind(4)
    uf.union(0, 1)
    assert uf.find(0) == uf.find(1)
    assert uf.find(2) != uf.find(0)


def test_union_find_transitive():
    uf = _UnionFind(5)
    uf.union(0, 1)
    uf.union(1, 2)
    assert uf.find(0) == uf.find(2)


# ---------------------------------------------------------------------------
# Unit tests: MinHash signature
# ---------------------------------------------------------------------------


def test_minhash_signature_length():
    a_list, b_list = _build_hash_params(8, 42)
    shingles = _shingle("hello world test", 3)
    sig = _minhash_signature(shingles, a_list, b_list)
    assert len(sig) == 8


def test_minhash_signature_empty_shingles():
    a_list, b_list = _build_hash_params(4, 42)
    sig = _minhash_signature(frozenset(), a_list, b_list)
    # All positions should be at max value (never matches anything).
    assert all(v == (1 << 32) - 1 for v in sig)


def test_minhash_signature_identical_texts():
    a_list, b_list = _build_hash_params(16, 42)
    s1 = _shingle("the quick brown fox", 4)
    s2 = _shingle("the quick brown fox", 4)
    sig1 = _minhash_signature(s1, a_list, b_list)
    sig2 = _minhash_signature(s2, a_list, b_list)
    assert sig1 == sig2


def test_minhash_signature_different_texts_differ():
    a_list, b_list = _build_hash_params(16, 42)
    s1 = _shingle("the quick brown fox", 4)
    s2 = _shingle("pack my box with five", 4)
    sig1 = _minhash_signature(s1, a_list, b_list)
    sig2 = _minhash_signature(s2, a_list, b_list)
    assert sig1 != sig2


# ---------------------------------------------------------------------------
# Unit tests: NearDupConfig validation
# ---------------------------------------------------------------------------


def test_near_dup_config_defaults():
    cfg = NearDupConfig()
    assert cfg.threshold == 0.7
    assert cfg.action == "flag"
    assert cfg.num_perm % cfg.num_bands == 0


def test_near_dup_config_invalid_threshold():
    with pytest.raises(ValueError, match="threshold"):
        NearDupConfig(threshold=0.0)


def test_near_dup_config_invalid_threshold_above_one():
    with pytest.raises(ValueError, match="threshold"):
        NearDupConfig(threshold=1.1)


def test_near_dup_config_invalid_action():
    with pytest.raises(ValueError, match="action"):
        NearDupConfig(action="delete")


def test_near_dup_config_num_perm_not_divisible():
    with pytest.raises(ValueError, match="divisible"):
        NearDupConfig(num_perm=10, num_bands=3)


def test_near_dup_config_min_group_size_below_two():
    with pytest.raises(ValueError, match="min_group_size"):
        NearDupConfig(min_group_size=1)


# ---------------------------------------------------------------------------
# Integration tests: detect_near_duplicates
# ---------------------------------------------------------------------------


def _make_df(texts: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"text": texts})


def test_detect_no_near_dups_flag():
    """Completely distinct texts produce no groups."""
    df = _make_df(["hello world", "pack my box", "the quick fox"])
    cfg = NearDupConfig(threshold=0.8, action="flag")
    result = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    assert result.num_groups == 0
    assert result.num_flagged == 0
    assert not result.df["near_dup_flag"].any()
    assert len(result.df) == 3


def test_detect_identical_texts_flagged():
    """Two identical texts should be in the same group."""
    text = "the customer service at this bank is excellent and helpful"
    df = _make_df([text, text, "completely different text here"])
    cfg = NearDupConfig(threshold=0.9, action="flag")
    result = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    assert result.num_groups >= 1
    assert result.num_flagged >= 2
    # All rows retained with action=flag
    assert len(result.df) == 3


def test_detect_near_identical_texts_flagged():
    """Texts differing by one word should be detected at threshold=0.6."""
    base = "the mobile app crashed when I tried to transfer money yesterday"
    near = "the mobile app crashed when I tried to transfer funds yesterday"
    unrelated = "pizza delivery was late and cold"
    df = _make_df([base, near, unrelated])
    cfg = NearDupConfig(threshold=0.5, action="flag")
    result = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    assert result.num_groups >= 1
    # The two similar texts should be in the same group
    group_ids = result.df["near_dup_group_id"].tolist()
    assert group_ids[0] is not None
    assert group_ids[1] is not None
    assert group_ids[0] == group_ids[1]
    assert group_ids[2] is None


def test_detect_action_keep_first():
    """keep_first: second copy of near-duplicate is dropped."""
    text = "the internet banking portal keeps timing out every single time"
    df = _make_df([text, text])
    cfg = NearDupConfig(threshold=0.9, action="keep_first")
    result = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    # Should retain only 1 of the 2 identical rows
    assert len(result.df) == 1


def test_detect_action_remove_all():
    """remove_all: both copies of a near-duplicate group are dropped."""
    text = "charges for international transfers are unreasonably high"
    df = _make_df([text, text, "unrelated text about something else entirely"])
    cfg = NearDupConfig(threshold=0.9, action="remove_all")
    result = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    # The two identical rows are removed; the unrelated one stays
    assert len(result.df) == 1
    assert result.df.iloc[0]["text"] == "unrelated text about something else entirely"


def test_detect_single_row_returns_unchanged():
    df = _make_df(["only one record here"])
    result = detect_near_duplicates(df, "text", NearDupConfig(), record_id_col=None)
    assert len(result.df) == 1
    assert result.num_groups == 0


def test_detect_empty_dataframe():
    df = _make_df([])
    result = detect_near_duplicates(df, "text", NearDupConfig(), record_id_col=None)
    assert len(result.df) == 0
    assert result.num_groups == 0


def test_detect_group_id_stable_with_record_id_col():
    """When record_id_col is present, group_id equals the lex-minimum record_id."""
    text = "failed atm transaction not reversed after three business days"
    df = pd.DataFrame({"text": [text, text], "record_id": ["zzz_id", "aaa_id"]})
    cfg = NearDupConfig(threshold=0.9, action="flag")
    result = detect_near_duplicates(df, "text", cfg, record_id_col="record_id")
    assert result.num_groups == 1
    group_ids = result.df["near_dup_group_id"].tolist()
    # Group id must be the lex-minimum: "aaa_id"
    assert group_ids[0] == "aaa_id"
    assert group_ids[1] == "aaa_id"


def test_detect_result_has_required_columns():
    df = _make_df(["text one", "text two"])
    result = detect_near_duplicates(df, "text", NearDupConfig(), record_id_col=None)
    assert "near_dup_flag" in result.df.columns
    assert "near_dup_group_id" in result.df.columns


def test_detect_deterministic_same_seed():
    """Two calls with the same seed produce identical results."""
    texts = [
        "poor customer service response times consistently",
        "poor customer service response time consistently",
        "excellent branch staff helpful and professional",
    ]
    df = _make_df(texts)
    cfg = NearDupConfig(threshold=0.7, seed=99)
    r1 = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    r2 = detect_near_duplicates(df, "text", cfg, record_id_col=None)
    assert r1.num_groups == r2.num_groups
    assert r1.num_flagged == r2.num_flagged


def test_detect_does_not_mutate_input():
    """detect_near_duplicates must not modify the caller's DataFrame."""
    df = _make_df(["text a", "text b"])
    original_cols = list(df.columns)
    _ = detect_near_duplicates(df, "text", NearDupConfig(), record_id_col=None)
    assert list(df.columns) == original_cols
    assert "near_dup_flag" not in df.columns
