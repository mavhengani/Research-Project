"""Source-manifest generation for `new_pipeline_v1` (Requirements Sections 4, 16, 25).

Produces a checksummed, schema-aware manifest describing a source corpus file,
and compares the observed row count against the expected count declared in
``configs/new_pipeline_v1.yaml``.

**Evidentiary discipline (the central design constraint of this module).**
Requirements Section 36 states: "The audit must be evidence-based. Repository
code, configuration, manifests, tests, and executable commands are the
evidence. Assumptions are not evidence." Section 4.5 adds that counts "must be
validated using record identifiers and manifests, not only arithmetic
assumptions."

Accordingly this module **never** coerces data to match an expected count. When
observed != expected it records status ``REQUIRES_DATA_CONFIRMATION`` along with
both numbers and their difference, and the caller is expected to surface that
rather than resolve it silently. There is deliberately no sampling, truncation,
or row-dropping code path here.

This matters concretely for the South African corpus: the expected count is
100,768 but ``data/interim/south_africa_prepared.parquet`` holds 2,250,776 rows,
and no inspected flag combination reproduces 100,768 (see gap-analysis finding
R3). This module will report that mismatch, not hide it.

Reads are column-projected and, for parquet, metadata-only where possible, so
generating a manifest for the 2.25M-row / 202 MB parquet does not require
loading the whole file into memory.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "NO_COMMIT_MARKER",
    "STATUS_VERIFIED",
    "STATUS_MISMATCH",
    "STATUS_REQUIRES_DATA_CONFIRMATION",
    "STATUS_SOURCE_MISSING",
    "STATUS_FILE_MISSING",
    "STATUS_INVALID_SCHEMA",
    "STATUS_PRIVACY_FAILURE",
    "MANIFEST_STATUSES",
    "ManifestResult",
    "sha256_file",
    "git_commit",
    "build_manifest",
    "write_manifest",
]

STATUS_VERIFIED = "VERIFIED"
STATUS_MISMATCH = "MISMATCH"
STATUS_REQUIRES_DATA_CONFIRMATION = "REQUIRES_DATA_CONFIRMATION"
STATUS_SOURCE_MISSING = "SOURCE_MISSING"
STATUS_INVALID_SCHEMA = "INVALID_SCHEMA"
STATUS_PRIVACY_FAILURE = "PRIVACY_FAILURE"

# Backwards-compatible alias: earlier Phase 1 code and tests used
# FILE_MISSING. SOURCE_MISSING is the canonical name required by the
# Phase 2 status vocabulary; both refer to the same condition.
STATUS_FILE_MISSING = STATUS_SOURCE_MISSING

MANIFEST_STATUSES = (
    STATUS_VERIFIED,
    STATUS_MISMATCH,
    STATUS_REQUIRES_DATA_CONFIRMATION,
    STATUS_SOURCE_MISSING,
    STATUS_INVALID_SCHEMA,
    STATUS_PRIVACY_FAILURE,
)

# Read in chunks so checksumming a 200 MB+ parquet does not load it into RAM.
_HASH_CHUNK_BYTES = 1024 * 1024

# Distribution columns are only summarised when cardinality is sane; a
# free-text or high-cardinality column would produce a useless, enormous
# manifest section.
_MAX_DISTRIBUTION_CARDINALITY = 200


@dataclass
class ManifestResult:
    """A source manifest plus its verification verdict.

    ``expected_row_count`` and ``row_count`` are deliberately separate fields
    and are never reconciled: an expected value is never copied into the
    observed field, nor the reverse.
    """

    source_file: str
    exists: bool
    status: str
    pipeline_version: str
    row_count: int | None = None
    expected_row_count: int | None = None
    row_count_difference: int | None = None
    count_status: str | None = None
    unique_record_count: int | None = None
    duplicate_record_count: int | None = None
    sha256: str | None = None
    bytes: int | None = None
    schema: dict[str, str] = field(default_factory=dict)
    null_counts: dict[str, int] | None = None
    source: Any = None
    region: Any = None
    source_distribution: dict[str, int] | None = None
    region_distribution: dict[str, int] | None = None
    bank_distribution: dict[str, int] | None = None
    year_distribution: dict[str, int] | None = None
    context_availability: dict[str, int] | None = None
    duplicate_group_coverage: dict[str, Any] | None = None
    review_group_coverage: dict[str, Any] | None = None
    privacy_status: dict[str, Any] | None = None
    candidate_status: dict[str, Any] | None = None
    derived_selection: dict[str, Any] | None = None
    generation_command: str = ""
    generated_at: str = ""
    git_commit: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Explicit marker used when no commit exists, so provenance gaps are
# machine-detectable rather than buried in prose. A commit hash is NEVER
# invented (gap-analysis finding R2).
NO_COMMIT_MARKER = "UNKNOWN_NO_COMMIT"


def git_commit() -> str:
    """Current commit hash, or :data:`NO_COMMIT_MARKER` when unavailable.

    The repository currently has no commits, so this returns the marker. The
    marker is a single stable token so downstream tooling and audits can detect
    the provenance gap by equality rather than substring matching.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return NO_COMMIT_MARKER
    except Exception:  # pragma: no cover - defensive
        return NO_COMMIT_MARKER

    if result.returncode != 0:
        return NO_COMMIT_MARKER
    commit = result.stdout.strip()
    return commit or NO_COMMIT_MARKER


def _distribution(values: Any) -> dict[str, int] | None:
    """Value counts for a low-cardinality column, else ``None``."""
    counts = Counter()
    for value in values:
        counts[str(value)] += 1
    if len(counts) > _MAX_DISTRIBUTION_CARDINALITY:
        return None
    return dict(sorted(counts.items()))


def _year_distribution(values: Any) -> dict[str, int] | None:
    """Year counts derived from the leading four characters of a date value."""
    counts = Counter()
    for value in values:
        text = str(value)
        year = text[:4]
        counts[year if year.isdigit() else "unknown"] += 1
    if len(counts) > _MAX_DISTRIBUTION_CARDINALITY:
        return None
    return dict(sorted(counts.items()))


def _parquet_metadata(path: Path) -> tuple[int, dict[str, str], list[str]]:
    """Row count and schema from parquet footer metadata only (no data read)."""
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(path)
    row_count = parquet_file.metadata.num_rows
    arrow_schema = parquet_file.schema_arrow
    schema = {name: str(arrow_schema.field(name).type) for name in arrow_schema.names}
    return row_count, schema, list(arrow_schema.names)


def _read_columns(path: Path, columns: list[str], is_parquet: bool):
    """Read only the requested columns, returning a pandas DataFrame."""
    import pandas as pd

    if not columns:
        return pd.DataFrame()
    if is_parquet:
        import pyarrow.parquet as pq

        return pq.read_table(path, columns=columns).to_pandas()
    return pd.read_csv(path, usecols=columns)


def _csv_metadata(path: Path) -> tuple[int, dict[str, str], list[str]]:
    """Row count and dtypes for a CSV, read in chunks to bound memory."""
    import pandas as pd

    row_count = 0
    dtypes: dict[str, str] = {}
    names: list[str] = []
    for chunk in pd.read_csv(path, chunksize=100_000, low_memory=False):
        if not names:
            names = list(chunk.columns)
            dtypes = {name: str(chunk[name].dtype) for name in names}
        row_count += len(chunk)
    return row_count, dtypes, names


def build_manifest(
    source_file: "str | Path",
    *,
    pipeline_version: str,
    expected_row_count: int | None = None,
    source: Any = None,
    region: Any = None,
    generation_command: str = "",
    bank_column: str = "bank",
    year_column: str = "created_at",
    duplicate_group_column: str = "near_dup_group_id",
    candidate_column: str = "customer_feedback_candidate",
    record_id_column: str = "record_id",
    source_column: str = "source",
    region_column: str = "region",
    context_column: str = "context_available",
    review_group_column: str = "review_id",
    required_columns: "tuple[str, ...] | None" = None,
    derived_selection: "dict[str, Any] | None" = None,
) -> ManifestResult:
    """Build a manifest for one source file.

    Records: source file, row count, checksum, schema, source, region, bank and
    year distributions where available, duplicate-group coverage, privacy
    status, candidate-status field, generation command, and pipeline version
    (the full field set required by this session's Step 6).

    ``status`` is:

    - ``FILE_MISSING`` when the file does not exist;
    - ``VERIFIED`` when ``expected_row_count`` is ``None`` or matches exactly;
    - ``REQUIRES_DATA_CONFIRMATION`` on any mismatch.

    A mismatch is reported, never corrected. No rows are sampled or dropped.
    """
    path = Path(source_file)
    notes: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not path.is_file():
        return ManifestResult(
            source_file=str(source_file),
            exists=False,
            status=STATUS_SOURCE_MISSING,
            count_status=STATUS_SOURCE_MISSING,
            pipeline_version=pipeline_version,
            expected_row_count=expected_row_count,
            generation_command=generation_command,
            generated_at=now,
            git_commit=git_commit(),
            notes=[f"Source file does not exist: {path}"],
        )

    is_parquet = path.suffix.lower() in {".parquet", ".pq"}

    if is_parquet:
        row_count, schema, names = _parquet_metadata(path)
    elif path.suffix.lower() in {".csv", ".tsv"}:
        row_count, schema, names = _csv_metadata(path)
    else:
        return ManifestResult(
            source_file=str(source_file),
            exists=True,
            status=STATUS_REQUIRES_DATA_CONFIRMATION,
            count_status=STATUS_REQUIRES_DATA_CONFIRMATION,
            pipeline_version=pipeline_version,
            expected_row_count=expected_row_count,
            bytes=path.stat().st_size,
            sha256=sha256_file(path),
            generation_command=generation_command,
            generated_at=now,
            git_commit=git_commit(),
            notes=[f"Unsupported file extension for row counting: {path.suffix}"],
        )

    # Required-schema gate (INVALID_SCHEMA). Checked before any summarising so
    # a structurally wrong file is rejected rather than partially described.
    if required_columns:
        missing = [c for c in required_columns if c not in names]
        if missing:
            return ManifestResult(
                source_file=str(source_file),
                exists=True,
                status=STATUS_INVALID_SCHEMA,
                count_status=STATUS_INVALID_SCHEMA,
                pipeline_version=pipeline_version,
                row_count=row_count,
                expected_row_count=expected_row_count,
                sha256=sha256_file(path),
                bytes=path.stat().st_size,
                schema=schema,
                source=source,
                region=region,
                generation_command=generation_command,
                generated_at=now,
                git_commit=git_commit(),
                notes=[
                    "Required column(s) missing: " + ", ".join(missing),
                    "Schema gate failed; no distribution summaries were computed.",
                ],
            )

    # Only project the columns we actually summarise.
    wanted = [
        c
        for c in (
            bank_column,
            year_column,
            duplicate_group_column,
            candidate_column,
            record_id_column,
            source_column,
            region_column,
            context_column,
            review_group_column,
        )
        if c in names
    ]
    frame = _read_columns(path, wanted, is_parquet) if wanted else None

    bank_distribution = None
    year_distribution = None
    duplicate_group_coverage = None
    review_group_coverage = None
    candidate_status = None
    source_distribution = None
    region_distribution = None
    context_availability = None
    unique_record_count = None
    duplicate_record_count = None
    null_counts = None

    if frame is not None and not frame.empty:
        null_counts = {
            column: int(frame[column].isna().sum()) for column in frame.columns
        }

        if record_id_column in frame.columns:
            ids = frame[record_id_column]
            unique_record_count = int(ids.nunique(dropna=True))
            duplicate_record_count = int(row_count - unique_record_count)
            if duplicate_record_count > 0:
                notes.append(
                    f"{duplicate_record_count} duplicate value(s) in "
                    f"'{record_id_column}'; identifiers are expected to be unique."
                )
        else:
            notes.append(
                f"No '{record_id_column}' column; unique/duplicate record counts "
                f"unavailable."
            )

        if source_column in frame.columns:
            source_distribution = _distribution(frame[source_column].fillna("unknown"))

        if region_column in frame.columns:
            region_distribution = _distribution(frame[region_column].fillna("unknown"))

        if context_column in frame.columns:
            column = frame[context_column]
            true_count = int(column.fillna(False).astype(bool).sum())
            context_availability = {
                "column": context_column,
                "context_available_true": true_count,
                "context_available_false": int(row_count - true_count),
            }

        if review_group_column in frame.columns:
            column = frame[review_group_column]
            non_null = column.notna() & (column.astype(str).str.len() > 0)
            grouped = int(non_null.sum())
            review_group_coverage = {
                "column": review_group_column,
                "records_with_group": grouped,
                "records_without_group": int(row_count - grouped),
                "distinct_groups": int(column[non_null].nunique()),
                "coverage_fraction": round(grouped / row_count, 6) if row_count else 0.0,
            }

    if frame is not None and not frame.empty:
        if bank_column in frame.columns:
            bank_distribution = _distribution(frame[bank_column].fillna("unknown"))
            if bank_distribution is None:
                notes.append(
                    f"'{bank_column}' cardinality exceeded "
                    f"{_MAX_DISTRIBUTION_CARDINALITY}; distribution omitted."
                )
        else:
            notes.append(f"No '{bank_column}' column; bank distribution unavailable.")

        if year_column in frame.columns:
            year_distribution = _year_distribution(frame[year_column].fillna("unknown"))
            if year_distribution is None:
                notes.append(
                    f"'{year_column}' produced excessive year cardinality; omitted."
                )
        else:
            notes.append(f"No '{year_column}' column; year distribution unavailable.")

        if duplicate_group_column in frame.columns:
            column = frame[duplicate_group_column]
            non_null = column.notna() & (column.astype(str).str.len() > 0)
            grouped = int(non_null.sum())
            distinct = int(column[non_null].nunique())
            duplicate_group_coverage = {
                "column": duplicate_group_column,
                "records_with_group": grouped,
                "records_without_group": int(row_count - grouped),
                "distinct_groups": distinct,
                "coverage_fraction": round(grouped / row_count, 6) if row_count else 0.0,
            }
        else:
            notes.append(
                f"No '{duplicate_group_column}' column; duplicate-group coverage "
                f"unavailable."
            )

        if candidate_column in frame.columns:
            column = frame[candidate_column]
            true_count = int(column.fillna(False).astype(bool).sum())
            candidate_status = {
                "column": candidate_column,
                "true_count": true_count,
                "false_or_null_count": int(row_count - true_count),
            }
            # The specific, load-bearing warning for finding R3: a candidate
            # flag exists but does not by itself define the required corpus.
            if expected_row_count is not None and true_count != expected_row_count:
                notes.append(
                    f"'{candidate_column}' is True for {true_count} records, which does "
                    f"not equal the expected {expected_row_count}. This flag alone does "
                    f"not define the required corpus."
                )
        else:
            notes.append(
                f"No '{candidate_column}' column; candidate status unavailable."
            )

    # Privacy status is reported structurally (which privacy-relevant columns
    # are present/absent), not re-derived. Actual anonymisation evidence lives
    # in the ingestion reports produced by data/anonymise.py.
    privacy_status = {
        "username_column_present": any(
            c in names for c in ("username", "user_name", "screen_name", "author")
        ),
        "raw_text_column_present": "text" in names,
        "privacy_status_column_present": "privacy_status" in names,
        "note": (
            "Structural check only. Anonymisation evidence is recorded by the "
            "ingestion pipeline (see outputs/*_data_report.json 'anonymisation_counts')."
        ),
    }

    # --- privacy gate (PRIVACY_FAILURE) -----------------------------------
    # A raw username/handle column surviving into a prepared source is a
    # privacy regression (Requirements Section 6.3), and outranks any count
    # verdict: a privacy-failing source must never be reported VERIFIED.
    privacy_failed = bool(privacy_status.get("username_column_present"))
    if privacy_failed:
        notes.append(
            "A raw username/handle column is present. Requirements Section 6.3 "
            "requires usernames and handles to be anonymised or removed in "
            "prepared sources."
        )

    # --- count verdict ----------------------------------------------------
    # expected and observed are kept strictly separate; neither is ever
    # copied into the other, and no data is sampled to close a gap.
    if expected_row_count is None:
        count_status = STATUS_VERIFIED
        difference = None
    elif row_count == expected_row_count:
        count_status = STATUS_VERIFIED
        difference = 0
    else:
        difference = row_count - expected_row_count
        # A derived-selection record explains HOW the expected count is
        # reproduced from this source, so the mismatch is understood rather
        # than unexplained. The raw file still does not itself contain the
        # expected number of rows, so this is never VERIFIED.
        count_status = (
            STATUS_REQUIRES_DATA_CONFIRMATION
            if derived_selection
            else STATUS_MISMATCH
        )
        notes.append(
            f"Observed {row_count} rows but expected {expected_row_count} "
            f"(difference {difference:+d}). Reported, not corrected: no sampling or "
            f"row-dropping is performed to reach an expected count."
        )
        if derived_selection:
            notes.append(
                "A derived-selection record is attached: the expected count is "
                "reproducible from this source via the documented selection "
                "process rather than being the raw row count."
            )

    status = STATUS_PRIVACY_FAILURE if privacy_failed else count_status

    return ManifestResult(
        source_file=str(source_file),
        exists=True,
        status=status,
        count_status=count_status,
        pipeline_version=pipeline_version,
        row_count=row_count,
        expected_row_count=expected_row_count,
        row_count_difference=difference,
        unique_record_count=unique_record_count,
        duplicate_record_count=duplicate_record_count,
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
        schema=schema,
        null_counts=null_counts,
        source=source,
        region=region,
        source_distribution=source_distribution,
        region_distribution=region_distribution,
        bank_distribution=bank_distribution,
        year_distribution=year_distribution,
        context_availability=context_availability,
        duplicate_group_coverage=duplicate_group_coverage,
        review_group_coverage=review_group_coverage,
        privacy_status=privacy_status,
        candidate_status=candidate_status,
        derived_selection=derived_selection,
        generation_command=generation_command or " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        generated_at=now,
        git_commit=git_commit(),
        notes=notes,
    )


def write_manifest(result: ManifestResult, path: "str | Path") -> Path:
    """Write a manifest as indented JSON, creating parent directories."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["environment"] = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out
