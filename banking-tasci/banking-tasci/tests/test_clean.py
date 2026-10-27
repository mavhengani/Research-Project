"""Unit tests for `src/banking_tasci/data/clean.py` cleaning-stage functions.

Requirements:
- 7.6: cleaning stage functions must return correct filtered dataframes and
  removed counts for the Ingestion_Pipeline to log.
"""
import sys
from pathlib import Path

import pandas as pd

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.clean import (  # noqa: E402
    drop_empty_rows,
    drop_exact_duplicates,
    normalise_text,
)


def test_normalise_text_collapses_internal_whitespace():
    assert normalise_text("hello   \t world\n\nagain") == "hello world again"


def test_normalise_text_strips_ends():
    assert normalise_text("   padded text   ") == "padded text"


def test_normalise_text_nfkc_normalises_unicode():
    # U+FF21 FULLWIDTH LATIN CAPITAL LETTER A + U+FF22 FULLWIDTH LATIN
    # CAPITAL LETTER B normalise to plain ASCII "AB" under NFKC.
    assert normalise_text("\uff21\uff22") == "AB"


def test_normalise_text_nfkc_normalises_combining_characters():
    # "e" + combining acute accent (U+0065 U+0301) NFKC-normalises to the
    # single precomposed character U+00E9 ("é").
    decomposed = "e\u0301"
    assert normalise_text(decomposed) == "\u00e9"


def test_drop_empty_rows_removes_null_and_whitespace_only():
    df = pd.DataFrame(
        {
            "text": ["hello", None, "   ", "world", ""],
            "id": [1, 2, 3, 4, 5],
        }
    )

    filtered, removed = drop_empty_rows(df, "text")

    assert removed == 3
    assert list(filtered["id"]) == [1, 4]


def test_drop_empty_rows_keeps_all_when_none_empty():
    df = pd.DataFrame({"text": ["a", "b", "c"]})

    filtered, removed = drop_empty_rows(df, "text")

    assert removed == 0
    assert len(filtered) == 3


def test_drop_exact_duplicates_keeps_first_occurrence():
    df = pd.DataFrame(
        {
            "text": ["hello", "world", "hello"],
            "source": ["tweets", "tweets", "tweets"],
            "id": [1, 2, 3],
        }
    )

    filtered, removed = drop_exact_duplicates(df, ["text", "source"])

    assert removed == 1
    assert list(filtered["id"]) == [1, 2]


def test_drop_exact_duplicates_no_duplicates_returns_unchanged_count():
    df = pd.DataFrame({"text": ["a", "b", "c"], "source": ["x", "y", "z"]})

    filtered, removed = drop_exact_duplicates(df, ["text", "source"])

    assert removed == 0
    assert len(filtered) == 3
