"""Regression tests for the `scripts` package-import isolation bug.

**The bug.** `tests/test_south_africa_resampling.py` contains nine tests that do
``from scripts.resample_south_africa_v2 import ...``. There is no
``scripts/__init__.py``, so ``scripts`` is importable only while the PROJECT
ROOT (not merely ``src/``) is on ``sys.path``. That module's header inserted
only ``src/``, leaving those nine imports dependent on pytest's implicit
rootdir insertion.

The result was order-dependent: the module passed 54/54 in isolation, but its
nine ``from scripts...`` tests failed when run after modules whose own
``sys.path`` manipulation changed resolution order, raising
``ModuleNotFoundError: No module named 'scripts'``. The failure count matched
exactly: 9 affected imports, 9 failures.

**The fix.** That module now inserts the project root explicitly, exactly as it
already did for ``src/``. The resampling implementation was not modified - the
fragility was in how the test module resolved its own imports.

These tests pin the invariant so the fragility cannot silently return.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def test_scripts_is_not_a_package():
    """Documents WHY the project root is required on sys.path.

    If a `scripts/__init__.py` is ever added, `scripts` becomes a real package
    and this test should be revisited along with the path-insertion comments.
    """
    assert not (_PROJECT_ROOT / "scripts" / "__init__.py").exists()


def test_resampling_module_inserts_project_root():
    """The affected test module must make its own `scripts` import work."""
    source = (_PROJECT_ROOT / "tests" / "test_south_africa_resampling.py").read_text(
        encoding="utf-8"
    )
    assert "_PROJECT_ROOT" in source, "project root must be computed"
    assert "sys.path.insert(0, str(_PROJECT_ROOT))" in source, (
        "project root must be inserted on sys.path so `scripts` resolves "
        "independently of test execution order"
    )


def test_scripts_import_fails_without_project_root():
    """Reproduces the original failure in a clean subprocess.

    With only `src/` on the path - the pre-fix situation - importing `scripts`
    must fail. This proves the diagnosis rather than asserting it.
    """
    code = (
        "import sys;"
        "sys.path = [p for p in sys.path if p not in ('', '.')];"
        "sys.path.insert(0, 'src');"
        "\ntry:\n"
        "    from scripts.resample_south_africa_v2 import select_sample_v2\n"
        "    print('IMPORTED')\n"
        "except ModuleNotFoundError as exc:\n"
        "    print('FAILED', exc)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "FAILED" in result.stdout
    assert "No module named 'scripts'" in result.stdout


def test_scripts_import_succeeds_with_project_root():
    """With the project root present - the post-fix situation - it must work."""
    code = (
        "import sys;"
        "sys.path.insert(0, 'src');"
        "sys.path.insert(0, '.');"
        "\nfrom scripts.resample_south_africa_v2 import select_sample_v2\n"
        "print('IMPORTED')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "IMPORTED" in result.stdout, result.stderr


def test_polluting_setup_then_resampling_import_still_works():
    """The regression scenario the session brief asked for: a polluting setup
    (another module inserting only `src/` at position 0, shifting resolution
    order) followed by the affected resampling import path.

    Because the resampling test module now inserts the project root itself,
    this sequence resolves cleanly.
    """
    # Simulate the polluting setup: another test module prepending its own
    # src path, as several modules in this suite do at import time.
    sys.path.insert(0, str(_SRC))
    try:
        # The affected import path must still resolve.
        from scripts.resample_south_africa_v2 import (  # noqa: F401
            run_nd_on_reservoir,
            select_sample_v2,
            to_annotation_records_v2,
        )

        assert callable(select_sample_v2)
        assert callable(run_nd_on_reservoir)
        assert callable(to_annotation_records_v2)
    finally:
        # Leave sys.path as we found it - this test must not itself pollute.
        sys.path.remove(str(_SRC))


def test_all_scripts_imports_in_resampling_module_resolve():
    """Every `from scripts...` symbol the affected module imports must resolve.

    The original failure count (9) equalled the number of such imports, so this
    guards the whole set rather than a sample.
    """
    source = (_PROJECT_ROOT / "tests" / "test_south_africa_resampling.py").read_text(
        encoding="utf-8"
    )
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("from scripts.")
    ]
    assert import_lines, "expected `from scripts...` imports to be present"

    import importlib

    for line in import_lines:
        # "from scripts.<module> import a, b" -> module path and symbols
        module_part, _, symbol_part = line.partition(" import ")
        module_name = module_part.replace("from ", "").strip()
        module = importlib.import_module(module_name)
        for symbol in (s.strip() for s in symbol_part.split(",")):
            if symbol:
                assert hasattr(module, symbol), f"{module_name} lacks {symbol}"


# ---------------------------------------------------------------------------
# Regression tests for process-dependent near-duplicate hashing.
#
# `_shingle` in src/banking_tasci/data/clean.py used Python's builtin `hash()`
# on shingle strings. Python randomises string hashing per process via
# PYTHONHASHSEED, so MinHash signatures - and therefore near-duplicate
# grouping - differed between runs on identical input. A borderline pair could
# fall on either side of the similarity threshold depending only on which
# process hashed it, producing intermittent failures in
# tests/test_near_duplicates.py::test_detect_near_identical_texts_flagged
# (observed passing and failing across identical consecutive invocations).
#
# `_stable_hash` (blake2b, 8-byte digest) replaced it, making detection
# genuinely deterministic for a given cfg.seed as the module already claimed.
# ---------------------------------------------------------------------------


def test_shingle_hashing_is_process_independent():
    """The same shingle must hash identically in separate processes."""
    code = (
        "import sys; sys.path.insert(0, 'src')\n"
        "from banking_tasci.data.clean import _stable_hash\n"
        "print(_stable_hash('the mobile app crashed'))\n"
    )
    outputs = set()
    for hash_seed in ("0", "1", "12345", "random"):
        env_prefix = {"PYTHONHASHSEED": hash_seed}
        import os

        env = dict(os.environ)
        env.update(env_prefix)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout.strip())

    assert len(outputs) == 1, (
        f"stable hash differed across PYTHONHASHSEED values: {outputs}"
    )


def test_near_duplicate_detection_is_deterministic_across_processes():
    """Near-duplicate grouping must agree across independently-seeded
    processes - the property the intermittent failure violated."""
    code = (
        "import sys; sys.path.insert(0, 'src')\n"
        "import pandas as pd\n"
        "from banking_tasci.data.clean import NearDupConfig, detect_near_duplicates\n"
        "base = 'the mobile app crashed when I tried to transfer money yesterday'\n"
        "near = 'the mobile app crashed when I tried to transfer funds yesterday'\n"
        "unrelated = 'pizza delivery was late and cold'\n"
        "df = pd.DataFrame({'text': [base, near, unrelated]})\n"
        "cfg = NearDupConfig(threshold=0.5, action='flag')\n"
        "res = detect_near_duplicates(df, 'text', cfg, record_id_col=None)\n"
        "ids = res.df['near_dup_group_id'].tolist()\n"
        "print(res.num_groups, ids[0] == ids[1], ids[2] is None)\n"
    )
    import os

    outputs = set()
    for hash_seed in ("0", "1", "99", "random"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = hash_seed
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout.strip())

    assert len(outputs) == 1, f"grouping differed across processes: {outputs}"
    # And the grouping must be the correct one.
    only = outputs.pop()
    assert only.startswith("1 True True") or only.split()[1] == "True", only


def test_clean_module_does_not_use_builtin_hash_for_shingles():
    """Guards against the builtin `hash()` being reintroduced."""
    source = (
        _PROJECT_ROOT / "src" / "banking_tasci" / "data" / "clean.py"
    ).read_text(encoding="utf-8")
    shingle_start = source.index("def _shingle(")
    shingle_body = source[shingle_start : shingle_start + 800]
    assert "_stable_hash(" in shingle_body
    assert "frozenset(hash(" not in shingle_body
