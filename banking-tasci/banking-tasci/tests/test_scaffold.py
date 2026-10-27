"""Unit tests for Repository_Scaffolder idempotency and failure reporting.

Covers:
- Req 1.4: re-running scaffolding against an existing directory leaves
  existing file content unchanged.
- Req 1.5: a simulated creation failure aborts remaining setup and reports
  the specific failing path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.scaffold import (  # noqa: E402
    DIRECTORIES,
    ScaffoldError,
    ensure_directory,
    ensure_file,
    scaffold_project,
)


@pytest.fixture()
def source_csv_dir(tmp_path: Path) -> Path:
    """A fake source directory containing the two raw CSVs to be copied."""
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "sampledbanktweet.csv").write_text("text\nhello world\n", encoding="utf-8")
    (src_dir / "bank_reviews3.csv").write_text(
        "author,date,address,bank,rating,review_title_by_user,review,"
        "bank_image,rating_title_by_user,useful_count\n"
        "a,2020-01-01,addr,BankX,5,Great,Loved it,img,Great,1\n",
        encoding="utf-8",
    )
    return src_dir


def test_scaffold_creates_expected_structure(tmp_path: Path, source_csv_dir: Path) -> None:
    project_root = tmp_path / "banking-tasci"

    scaffold_project(root=project_root, source_csv_dir=source_csv_dir)

    for rel_dir in DIRECTORIES:
        assert (project_root / rel_dir).is_dir()

    for name in ("data/raw/.gitkeep", "data/interim/.gitkeep", "data/processed/.gitkeep", "data/annotations/.gitkeep"):
        assert (project_root / name).is_file()

    for name in ("pyproject.toml", "requirements.txt", ".gitignore", "Makefile"):
        assert (project_root / name).is_file()

    assert (project_root / "data" / "raw" / "sampledbanktweet.csv").read_text(encoding="utf-8") == (
        source_csv_dir / "sampledbanktweet.csv"
    ).read_text(encoding="utf-8")
    assert (project_root / "data" / "raw" / "bank_reviews3.csv").read_text(encoding="utf-8") == (
        source_csv_dir / "bank_reviews3.csv"
    ).read_text(encoding="utf-8")


def test_scaffold_is_idempotent_and_preserves_existing_content(tmp_path: Path, source_csv_dir: Path) -> None:
    """Req 1.4: re-running scaffolding leaves existing file content unchanged."""
    project_root = tmp_path / "banking-tasci"

    scaffold_project(root=project_root, source_csv_dir=source_csv_dir)

    # Simulate a user having edited a generated file and a raw CSV after
    # the first scaffold run.
    custom_marker = "# user customization\nDIALECT = 'custom'\n"
    (project_root / "requirements.txt").write_text(custom_marker, encoding="utf-8")

    custom_csv_content = "text\ncustomised content\n"
    (project_root / "data" / "raw" / "sampledbanktweet.csv").write_text(
        custom_csv_content, encoding="utf-8"
    )

    # Re-run scaffolding against the now-existing project directory.
    scaffold_project(root=project_root, source_csv_dir=source_csv_dir)

    assert (project_root / "requirements.txt").read_text(encoding="utf-8") == custom_marker
    assert (
        project_root / "data" / "raw" / "sampledbanktweet.csv"
    ).read_text(encoding="utf-8") == custom_csv_content


def test_ensure_directory_failure_reports_failing_path(tmp_path: Path) -> None:
    """Req 1.5: a creation failure reports the specific failing path."""
    # Create a plain file where scaffolding expects to create a directory,
    # so mkdir underneath it fails with a concrete OSError.
    blocking_file = tmp_path / "blocked"
    blocking_file.write_text("i am a file, not a directory", encoding="utf-8")
    target_dir = blocking_file / "nested"

    with pytest.raises(ScaffoldError) as exc_info:
        ensure_directory(target_dir)

    assert str(target_dir) == exc_info.value.path


def test_ensure_file_failure_reports_failing_path(tmp_path: Path) -> None:
    """Req 1.5: a simulated unwritable-path failure aborts and names the path."""
    # Make the parent directory read-only so writing a new file inside it
    # fails with PermissionError.
    parent_dir = tmp_path / "readonly_dir"
    parent_dir.mkdir()
    target_file = parent_dir / "some_file.txt"

    original_mode = parent_dir.stat().st_mode
    parent_dir.chmod(0o500)  # read + execute only, no write
    try:
        with pytest.raises(ScaffoldError) as exc_info:
            ensure_file(target_file, "content")
        assert str(target_file) == exc_info.value.path
    finally:
        parent_dir.chmod(original_mode)


def test_scaffold_project_aborts_remaining_setup_on_failure(tmp_path: Path, source_csv_dir: Path) -> None:
    """Req 1.5: a failure partway through aborts the remainder of setup."""
    project_root = tmp_path / "banking-tasci"
    project_root.mkdir()

    # Pre-create 'configs' as a file (not a directory) to force the first
    # directory-creation step to fail, so nothing past it should be created.
    (project_root / "configs").write_text("blocking file", encoding="utf-8")

    with pytest.raises(ScaffoldError) as exc_info:
        scaffold_project(root=project_root, source_csv_dir=source_csv_dir)

    assert str(project_root / "configs") == exc_info.value.path
    # Steps after 'configs' in DIRECTORIES should not have been created.
    assert not (project_root / "data" / "raw").exists()
    assert not (project_root / "pyproject.toml").exists()
