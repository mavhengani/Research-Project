"""Repository scaffolding logic for the banking-tasci project.

Creates the Phase 1 directory structure and placeholder files described in
KIRO_SPEC.md Section 6 / design.md, in an idempotent, fail-fast manner.

Requirements:
- 1.1: create the required directory structure
- 1.2: create .gitkeep placeholders in data subdirectories
- 1.3: create root pyproject.toml, requirements.txt, .gitignore, Makefile
- 1.4: leave existing files/directories unmodified on re-run
- 1.5: abort remaining setup and report the failing path on creation failure
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


class ScaffoldError(Exception):
    """Raised when scaffolding fails to create a required path.

    Carries the specific path that failed so the caller can report exactly
    where setup was aborted (Requirement 1.5).
    """

    def __init__(self, path: PathLike, reason: Exception):
        self.path = str(path)
        self.reason = reason
        super().__init__(f"Failed to create {self.path}: {reason}")


# Directories required by Requirement 1.1, plus the future-phase stub
# directories (models/, training/, evaluation/, inference/) called out in
# design.md's "Extensibility for Future Phases" section. Their contents are
# intentionally left unimplemented in Phase 1.
DIRECTORIES = [
    "configs",
    "data/raw",
    "data/interim",
    "data/processed",
    "data/annotations",
    "docs",
    "src/banking_tasci",
    "src/banking_tasci/data",
    "src/banking_tasci/models",
    "src/banking_tasci/training",
    "src/banking_tasci/evaluation",
    "src/banking_tasci/inference",
    "scripts",
    "cluster",
    "tests",
]

# Directories that receive a .gitkeep placeholder (Requirement 1.2).
GITKEEP_DIRS = [
    "data/raw",
    "data/interim",
    "data/processed",
    "data/annotations",
]

# Placeholder package files. Empty __init__.py files make the future-phase
# directories valid Python packages without implementing any of their
# eventual contents (models/, training/, evaluation/, inference/).
STUB_FILES: dict = {
    "src/banking_tasci/__init__.py": "",
    "src/banking_tasci/data/__init__.py": "",
    "src/banking_tasci/models/__init__.py": "",
    "src/banking_tasci/training/__init__.py": "",
    "src/banking_tasci/evaluation/__init__.py": "",
    "src/banking_tasci/inference/__init__.py": "",
}

# Source CSV files copied (never moved) into data/raw/ (Requirement 7.7).
SOURCE_CSV_FILES = [
    "sampledbanktweet.csv",
    "bank_reviews3.csv",
]

PYPROJECT_TOML = """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "banking-tasci"
version = "0.1.0"
description = "TASCI-style aspect/intent/sentiment pipeline for banking customer feedback"
requires-python = ">=3.10"
readme = "README.md"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""

REQUIREMENTS_TXT = """pandas
pyyaml
numpy
torch
pytest
hypothesis
"""

GITIGNORE = """__pycache__/
*.py[cod]
*.egg-info/
.eggs/
.venv/
venv/
.pytest_cache/
.hypothesis/
outputs/

# Data directories: keep placeholders, ignore generated/raw content
data/raw/*
!data/raw/.gitkeep
data/interim/*
!data/interim/.gitkeep
data/processed/*
!data/processed/.gitkeep
data/annotations/*
!data/annotations/.gitkeep
"""

MAKEFILE = """.PHONY: install test prepare-data

install:
\tpip install -r requirements.txt

test:
\tpytest -q

prepare-data:
\tpython scripts/prepare_data.py --tweets data/raw/sampledbanktweet.csv --reviews data/raw/bank_reviews3.csv --output data/interim/prepared.csv --report outputs/data_report.json
"""


def ensure_directory(path: Path) -> None:
    """Create `path` as a directory if it doesn't exist.

    Leaves an existing directory unmodified (Req 1.4). Raises ScaffoldError
    naming `path` if creation fails or the path exists as a non-directory
    (Req 1.5).
    """
    if path.exists():
        if not path.is_dir():
            raise ScaffoldError(path, ValueError(f"{path} exists but is not a directory"))
        return
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScaffoldError(path, exc) from exc


def ensure_file(path: Path, content: str = "") -> None:
    """Create `path` with `content` if it doesn't already exist.

    Leaves existing file content unmodified (Req 1.4). Raises ScaffoldError
    naming `path` on failure (Req 1.5).
    """
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ScaffoldError(path, exc) from exc


def ensure_copy(src: Path, dest: Path) -> None:
    """Copy `src` to `dest` if `dest` doesn't already exist.

    Never modifies `src` (Req 7.7). Leaves an existing `dest` unmodified
    (Req 1.4). Raises ScaffoldError naming `dest` on failure (Req 1.5).
    """
    if dest.exists():
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as exc:
        raise ScaffoldError(dest, exc) from exc


def scaffold_project(root: PathLike, source_csv_dir: PathLike) -> None:
    """Create the full Phase 1 project structure rooted at `root`.

    Idempotent: re-running against an existing `root` leaves existing
    files/directories unmodified (Req 1.4). Aborts on the first failure and
    raises a ScaffoldError identifying the failing path (Req 1.5); any steps
    after the failure are not attempted.
    """
    root = Path(root)
    source_csv_dir = Path(source_csv_dir)

    for rel_dir in DIRECTORIES:
        ensure_directory(root / rel_dir)

    for rel_dir in GITKEEP_DIRS:
        ensure_file(root / rel_dir / ".gitkeep")

    for rel_path, content in STUB_FILES.items():
        ensure_file(root / rel_path, content)

    ensure_file(root / "pyproject.toml", PYPROJECT_TOML)
    ensure_file(root / "requirements.txt", REQUIREMENTS_TXT)
    ensure_file(root / ".gitignore", GITIGNORE)
    ensure_file(root / "Makefile", MAKEFILE)

    for csv_name in SOURCE_CSV_FILES:
        ensure_copy(source_csv_dir / csv_name, root / "data" / "raw" / csv_name)
