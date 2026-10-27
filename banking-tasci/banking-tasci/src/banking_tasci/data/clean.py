"""Pure cleaning-stage functions for the banking-tasci ingestion pipeline.

Each function here is a small, independent, pure transformation with no
side effects (no logging, no I/O) so they can be unit- and property-tested
in isolation. Counts of removed rows are returned to the caller, which is
responsible for logging them (Requirement 7.6 — logging happens one layer
up, in the Ingestion_Pipeline).

Requirements:
- 7.6: (indirectly) supplies the before/after counts the Ingestion_Pipeline
  logs when removing empty or exact-duplicate records.
- 7.7: near-duplicate detection groups records that are textually similar
  above a configurable threshold without silently deleting them.

Near-Duplicate Detection Algorithm
-----------------------------------
Standard Jaccard similarity over character-level *shingling* (k-grams) is
used, accelerated with **MinHash + LSH banding** so the comparison is
sub-quadratic in the number of records.

Step 1 — Shingling
  Each normalised text is converted to a set of overlapping k-character
  substrings (k = ``shingle_size``, default 4).  Character-level shingles
  work well on short social-media texts where word-level n-grams would be
  sparse.

Step 2 — MinHash signature
  Each shingle set is hashed ``num_perm`` times (default 128) using
  independent universal hash functions of the form
      h(x) = (a*x + b) mod LARGE_PRIME mod 2^32
  where (a, b) pairs are drawn deterministically from a seeded RNG so
  results are reproducible.  The minimum hash value across the shingle set
  forms one band of the signature.

Step 3 — LSH banding
  The ``num_perm`` hash values are split into ``num_bands`` bands of
  ``rows_per_band`` rows each.  Two records become *candidate pairs* when
  their signature vectors agree in at least one band (i.e., they hash to
  the same bucket in that band's hash table).  This gives a threshold-like
  recall:  the probability of detecting a true pair rises steeply around
  the target similarity threshold.

  For a target Jaccard threshold θ the recommended band/row split is:
      num_bands * rows_per_band = num_perm
      rows_per_band ≈ −1 / log10(θ)   (rule of thumb)

  The defaults (num_perm=128, num_bands=16, rows_per_band=8) target θ ≈ 0.7
  with high recall and low false-negative rate.

Step 4 — Candidate verification
  For every candidate pair the *exact* Jaccard similarity of their shingle
  sets is computed.  Only pairs whose Jaccard similarity ≥ ``threshold``
  are considered near-duplicates.  This eliminates LSH false positives.

Step 5 — Group assignment (union-find)
  Near-duplicate pairs are merged into groups with a path-compressed
  union-find structure so that transitively similar records belong to the
  same group.  Each group is assigned a stable ``near_dup_group_id``
  equal to the smallest ``record_id`` (lexicographic) in the group, or a
  deterministic index if ``record_id`` is absent.

Complexity
  O(n × num_perm) for hashing, O(n × num_bands) for LSH bucket insertion,
  O(|candidate_pairs| × shingle_set_size) for verification.  In practice
  |candidate_pairs| grows much more slowly than O(n²) for datasets with
  few true near-duplicates.  For 10,847 records with 128 permutations the
  memory overhead is ≈ 11 MB (128 int32 per record).

Configuration keys (passed through ``NearDupConfig`` or the
``near_dup`` sub-section of ``base.yaml``):
  - threshold          (float, default 0.7) – minimum Jaccard similarity.
  - shingle_size       (int,   default 4)   – character k-gram size.
  - num_perm           (int,   default 128) – number of MinHash permutations.
  - num_bands          (int,   default 16)  – LSH bands; rows = num_perm // num_bands.
  - action             (str,   default "flag") – one of:
      "flag"   – add ``near_dup_group_id`` and ``near_dup_flag`` columns;
                 all rows are kept.
      "keep_first" – within each near-dup group keep only the first row;
                     others are dropped and counted.
      "remove_all" – drop every row that has a near-duplicate match,
                     keeping none.
  - min_group_size     (int,   default 2)   – a "group" is only reported /
                     acted on when it contains at least this many records.
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Near-duplicate configuration
# ---------------------------------------------------------------------------


@dataclass
class NearDupConfig:
    """Algorithm knobs for near-duplicate detection.

    All fields have safe defaults so callers can construct ``NearDupConfig()``
    without any arguments and receive sensible behaviour (flag-only, no rows
    deleted).

    Attributes:
        threshold:      Minimum Jaccard similarity to call two records
                        near-duplicates. Range (0, 1]. Default 0.7.
        shingle_size:   Character k-gram size for shingling. Default 4.
        num_perm:       Number of MinHash permutations. Must be divisible
                        by num_bands. Default 128.
        num_bands:      Number of LSH bands. Default 16
                        (so rows_per_band = 128 // 16 = 8).
        action:         What to do with near-duplicates. One of:
                        "flag"        – keep all rows, add group columns.
                        "keep_first"  – keep first row per group, drop rest.
                        "remove_all"  – drop all rows that have any
                                        near-duplicate.
        min_group_size: Minimum group size to consider a match. Default 2.
        seed:           RNG seed for reproducible hash functions. Default 42.
    """

    threshold: float = 0.7
    shingle_size: int = 4
    num_perm: int = 128
    num_bands: int = 16
    action: str = "flag"
    min_group_size: int = 2
    seed: int = 42

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {self.threshold}")
        if self.shingle_size < 1:
            raise ValueError(f"shingle_size must be >= 1, got {self.shingle_size}")
        if self.num_perm < 1:
            raise ValueError(f"num_perm must be >= 1, got {self.num_perm}")
        if self.num_bands < 1:
            raise ValueError(f"num_bands must be >= 1, got {self.num_bands}")
        if self.num_perm % self.num_bands != 0:
            raise ValueError(
                f"num_perm ({self.num_perm}) must be divisible by "
                f"num_bands ({self.num_bands})"
            )
        if self.action not in ("flag", "keep_first", "remove_all"):
            raise ValueError(
                f"action must be 'flag', 'keep_first', or 'remove_all', "
                f"got '{self.action}'"
            )
        if self.min_group_size < 2:
            raise ValueError(f"min_group_size must be >= 2, got {self.min_group_size}")


@dataclass
class NearDupResult:
    """Output of :func:`detect_near_duplicates`.

    Attributes:
        df:                 The original DataFrame with two new columns
                            ``near_dup_group_id`` (str | None) and
                            ``near_dup_flag`` (bool).  Rows that are not
                            near-duplicates of anything have
                            ``near_dup_group_id = None`` and
                            ``near_dup_flag = False``.
        groups:             Mapping from group_id to the list of integer
                            positional indices (into ``df``) in that group.
                            Only groups with >= min_group_size members appear.
        num_groups:         Total number of near-duplicate groups found.
        num_flagged:        Total rows that are part of at least one group.
        pairs_compared:     Number of candidate pairs verified (exact Jaccard
                            computed).  This is a workload measure, not a
                            count of near-duplicate pairs.
        near_dup_pairs:     Number of verified pairs whose Jaccard similarity
                            exceeded the threshold.
    """

    df: pd.DataFrame
    groups: dict[str, list[int]]
    num_groups: int
    num_flagged: int
    pairs_compared: int
    near_dup_pairs: int


# ---------------------------------------------------------------------------
# Internal helpers: MinHash + LSH
# ---------------------------------------------------------------------------

# A large Mersenne prime used as the modulus for universal hash functions.
_LARGE_PRIME: int = (1 << 61) - 1
_HASH_MOD: int = 1 << 32  # keep final hashes in uint32 range


def _build_hash_params(num_perm: int, seed: int) -> "tuple[list[int], list[int]]":
    """Return (a_list, b_list) — independent linear hash coefficients.

    Uses a seeded LCG to generate reproducible, non-zero ``a`` values and
    arbitrary ``b`` values, all in [1, _LARGE_PRIME).
    """
    import random as _rnd

    rng = _rnd.Random(seed)
    a_list = [rng.randint(1, _LARGE_PRIME - 1) for _ in range(num_perm)]
    b_list = [rng.randint(0, _LARGE_PRIME - 1) for _ in range(num_perm)]
    return a_list, b_list


def _stable_hash(value: str) -> int:
    """Process-independent 64-bit hash of ``value``.

    Python's builtin ``hash()`` randomises string hashing per process (via
    ``PYTHONHASHSEED``), which previously made MinHash signatures - and
    therefore near-duplicate grouping - differ between runs on identical
    input. A borderline pair could land on either side of the similarity
    threshold depending only on which process happened to hash it, producing
    intermittent, irreproducible results.

    Blake2b with an 8-byte digest is stable across processes and runs, so
    near-duplicate detection is now genuinely deterministic for a given
    ``cfg.seed`` as its docstring already promised.
    """
    return int.from_bytes(
        hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(), "big"
    )


def _shingle(text: str, k: int) -> "frozenset[int]":
    """Return a frozenset of stable shingle hashes for all k-char substrings.

    Uses :func:`_stable_hash` rather than the builtin ``hash()`` so results
    are reproducible across processes.  ``frozenset`` ensures
    order-independence.  Empty or very-short texts that produce no k-grams
    return an empty frozenset.
    """
    if len(text) < k:
        return frozenset()
    return frozenset(_stable_hash(text[i: i + k]) for i in range(len(text) - k + 1))


def _minhash_signature(shingles: "frozenset[int]", a_list: list[int], b_list: list[int]) -> "list[int]":
    """Compute the MinHash signature vector for a shingle set.

    For each permutation i the signature value is:
        min over x in shingles of  (a_i * x + b_i) mod PRIME mod 2^32

    An empty shingle set produces an all-maximum signature so that it
    never falsely matches any other record.
    """
    num_perm = len(a_list)
    sig = [_HASH_MOD - 1] * num_perm  # initialise to max uint32
    for x in shingles:
        x_mod = x % _LARGE_PRIME
        for i in range(num_perm):
            h = ((a_list[i] * x_mod + b_list[i]) % _LARGE_PRIME) % _HASH_MOD
            if h < sig[i]:
                sig[i] = h
    return sig


def _lsh_candidate_pairs(
    signatures: "list[list[int]]",
    num_bands: int,
) -> "set[tuple[int, int]]":
    """Return candidate pairs (i, j) with i < j whose signatures share a
    band bucket.

    Each of the ``num_bands`` bands hashes a slice of the signature to a
    bucket key.  Two records that hash to the same bucket in any band are
    returned as a candidate pair.
    """
    rows_per_band = len(signatures[0]) // num_bands
    candidates: set[tuple[int, int]] = set()

    for band_idx in range(num_bands):
        start = band_idx * rows_per_band
        end = start + rows_per_band
        bucket: dict[tuple[int, ...], list[int]] = {}
        for rec_idx, sig in enumerate(signatures):
            key = tuple(sig[start:end])
            bucket.setdefault(key, []).append(rec_idx)
        for members in bucket.values():
            if len(members) < 2:
                continue
            for ii in range(len(members)):
                for jj in range(ii + 1, len(members)):
                    i, j = members[ii], members[jj]
                    candidates.add((min(i, j), max(i, j)))

    return candidates


def _jaccard(a: "frozenset[int]", b: "frozenset[int]") -> float:
    """Exact Jaccard similarity between two frozensets."""
    if not a and not b:
        return 1.0  # both empty → identical
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Union-Find for group assignment
# ---------------------------------------------------------------------------


class _UnionFind:
    """Path-compressed, rank-based union-find over integer indices."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1


def normalise_text(text: str) -> str:
    """Unicode-normalise (NFKC), collapse internal whitespace, strip ends.

    Any run of whitespace characters (spaces, tabs, newlines, etc.) is
    collapsed to a single space, and leading/trailing whitespace is
    stripped. Non-string input is coerced to `str` first so callers never
    need to guard against `NaN`/`None` themselves at this layer (though
    `drop_empty_rows` handles nulls explicitly before normalising).
    """
    normalised = unicodedata.normalize("NFKC", str(text))
    return " ".join(normalised.split())


def drop_empty_rows(df: pd.DataFrame, text_col: str) -> tuple[pd.DataFrame, int]:
    """Remove rows whose `text_col` is null or empty/whitespace-only.

    A row is considered empty when its `text_col` value is null (`NaN`/
    `None`) or, after `normalise_text`, reduces to the empty string.
    Returns the filtered dataframe (original index preserved for surviving
    rows) and the count of rows removed.
    """
    is_null = df[text_col].isna()
    normalised = df[text_col].where(~is_null, "").map(normalise_text)
    is_empty = is_null | (normalised == "")

    removed = int(is_empty.sum())
    filtered = df.loc[~is_empty].copy()
    return filtered, removed


def drop_exact_duplicates(df: pd.DataFrame, subset: list[str]) -> tuple[pd.DataFrame, int]:
    """Remove exact-duplicate rows on `subset` columns, keeping the first.

    Returns the filtered dataframe (original index preserved for surviving
    rows) and the count of rows removed.
    """
    is_duplicate = df.duplicated(subset=subset, keep="first")

    removed = int(is_duplicate.sum())
    filtered = df.loc[~is_duplicate].copy()
    return filtered, removed


# ---------------------------------------------------------------------------
# Near-duplicate detection (Requirement 7.7)
# ---------------------------------------------------------------------------


def detect_near_duplicates(
    df: pd.DataFrame,
    text_col: str,
    cfg: "NearDupConfig | None" = None,
    record_id_col: "str | None" = "record_id",
) -> NearDupResult:
    """Detect near-duplicate rows in ``df[text_col]`` using MinHash + LSH.

    This function **never silently deletes rows** when ``cfg.action == "flag"``
    (the default).  Two additional columns are appended to a copy of ``df``:

    - ``near_dup_flag``     (bool)  – True when the row is a member of a
                                      near-duplicate group.
    - ``near_dup_group_id`` (str)   – Stable group identifier, or ``None``
                                      for rows with no near-duplicate match.

    When ``cfg.action == "keep_first"`` the first row (lowest positional
    index) of each group is retained and all others are dropped from the
    returned DataFrame; the count of dropped rows is reflected in
    ``NearDupResult``.

    When ``cfg.action == "remove_all"`` every row that belongs to any
    near-duplicate group is dropped.

    The algorithm is documented in the module docstring.  The result is
    deterministic for a given ``cfg.seed``.

    Parameters
    ----------
    df:
        Input DataFrame.  Must contain ``text_col``.  Not mutated.
    text_col:
        Name of the column containing text to compare.
    cfg:
        Near-duplicate algorithm configuration.  ``None`` uses defaults
        (threshold=0.7, action="flag").
    record_id_col:
        Column name to use for stable group ids.  When ``None`` or the
        column is absent, positional string indices are used instead.

    Returns
    -------
    NearDupResult
        Contains the annotated/filtered DataFrame, group membership dict,
        and count statistics.  The returned DataFrame always has a
        reset integer index regardless of the input index.
    """
    if cfg is None:
        cfg = NearDupConfig()

    result_df = df.copy().reset_index(drop=True)
    n = len(result_df)

    # Initialise annotation columns; will be overwritten for matched rows.
    result_df["near_dup_flag"] = False
    result_df["near_dup_group_id"] = None

    if n < 2:
        return NearDupResult(
            df=result_df,
            groups={},
            num_groups=0,
            num_flagged=0,
            pairs_compared=0,
            near_dup_pairs=0,
        )

    # ---- Step 1: build shingle sets -----------------------------------------
    texts: list[str] = result_df[text_col].fillna("").tolist()
    shingle_sets: list[frozenset[int]] = [
        _shingle(t, cfg.shingle_size) for t in texts
    ]

    # ---- Step 2: MinHash signatures -----------------------------------------
    a_list, b_list = _build_hash_params(cfg.num_perm, cfg.seed)
    signatures: list[list[int]] = [
        _minhash_signature(s, a_list, b_list) for s in shingle_sets
    ]

    # ---- Step 3: LSH candidate pairs ----------------------------------------
    candidates = _lsh_candidate_pairs(signatures, cfg.num_bands)

    # ---- Step 4: exact Jaccard verification ----------------------------------
    pairs_compared = 0
    near_dup_pairs = 0
    uf = _UnionFind(n)

    for i, j in candidates:
        pairs_compared += 1
        sim = _jaccard(shingle_sets[i], shingle_sets[j])
        if sim >= cfg.threshold:
            near_dup_pairs += 1
            uf.union(i, j)

    # ---- Step 5: build groups via union-find roots ---------------------------
    root_to_members: dict[int, list[int]] = {}
    for idx in range(n):
        root = uf.find(idx)
        root_to_members.setdefault(root, []).append(idx)

    # Determine stable group id (smallest record_id string or positional str).
    use_id_col = (
        record_id_col is not None
        and record_id_col in result_df.columns
    )

    groups: dict[str, list[int]] = {}
    for root, members in root_to_members.items():
        if len(members) < cfg.min_group_size:
            continue  # singleton or below threshold — not a near-dup group
        # Stable group id: lex-minimum record_id in the group.
        if use_id_col:
            ids = [str(result_df.at[m, record_id_col]) for m in members]
            group_id = min(ids)
        else:
            group_id = str(min(members))
        groups[group_id] = sorted(members)

    # Annotate the DataFrame.
    for group_id, members in groups.items():
        for m in members:
            result_df.at[m, "near_dup_flag"] = True
            result_df.at[m, "near_dup_group_id"] = group_id

    num_flagged = int(result_df["near_dup_flag"].sum())

    # ---- Step 6: apply action -----------------------------------------------
    if cfg.action == "keep_first":
        drop_indices: list[int] = []
        for members in groups.values():
            drop_indices.extend(members[1:])  # keep members[0], drop rest
        if drop_indices:
            result_df = result_df.drop(index=drop_indices).reset_index(drop=True)
    elif cfg.action == "remove_all":
        flagged_indices = result_df.index[result_df["near_dup_flag"]].tolist()
        if flagged_indices:
            result_df = result_df.drop(index=flagged_indices).reset_index(drop=True)

    return NearDupResult(
        df=result_df,
        groups=groups,
        num_groups=len(groups),
        num_flagged=num_flagged,
        pairs_compared=pairs_compared,
        near_dup_pairs=near_dup_pairs,
    )
