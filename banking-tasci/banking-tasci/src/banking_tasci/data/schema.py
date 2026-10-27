"""Source CSV schema validation for the banking-tasci project.

Validates that loaded `sampledbanktweet.csv` and `bank_reviews3.csv`
dataframes contain their required columns before they reach the ingestion
pipeline.

Requirements:
- 5.1: verify a tweets dataframe contains the required column `text`.
- 5.2: verify a reviews dataframe contains its required columns, detecting
  any missing column(s) and marking validation as failed when one or more
  are absent.
- 5.3: raise an explicit exception naming the file and the missing
  column(s) when a required column is missing.
- 5.4: log the file name and row count when schema validation succeeds.
"""
from __future__ import annotations

import pandas as pd

from banking_tasci.logging_utils import get_logger

TWEET_REQUIRED_COLUMNS = ["text"]

REVIEW_REQUIRED_COLUMNS = [
    "author",
    "date",
    "address",
    "bank",
    "rating",
    "review_title_by_user",
    "review",
    "bank_image",
    "rating_title_by_user",
    "useful_count",
]


class SchemaValidationError(Exception):
    """Raised when required columns are missing from an input dataframe.

    Carries `file_path` and the sorted list of missing column names
    (Req 5.3).
    """

    def __init__(self, file_path: str, missing: list[str]):
        self.file_path = file_path
        self.missing = sorted(missing)
        message = f"{file_path}: missing required column(s): {', '.join(self.missing)}"
        super().__init__(message)


def missing_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    """Return the required columns not present in `df.columns`.

    Pure helper; order-preserved relative to `required`.
    """
    present = set(df.columns)
    return [column for column in required if column not in present]


def _validate_schema(df: pd.DataFrame, file_path: str, required: list[str]) -> None:
    missing = missing_columns(df, required)
    if missing:
        raise SchemaValidationError(file_path, missing)
    get_logger(__name__).info("%s: %d rows validated", file_path, len(df))


def validate_tweets_schema(df: pd.DataFrame, file_path: str) -> None:
    """Validate `df` against the required tweets schema (Req 5.1).

    Raises `SchemaValidationError` naming `file_path` and any missing
    column(s) (Req 5.3); logs the file name and row count on success
    (Req 5.4).
    """
    _validate_schema(df, file_path, TWEET_REQUIRED_COLUMNS)


def validate_reviews_schema(df: pd.DataFrame, file_path: str) -> None:
    """Validate `df` against the required reviews schema (Req 5.2).

    Raises `SchemaValidationError` naming `file_path` and any missing
    column(s) (Req 5.3); logs the file name and row count on success
    (Req 5.4).
    """
    _validate_schema(df, file_path, REVIEW_REQUIRED_COLUMNS)
