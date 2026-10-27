"""Tests for Seed_Utility (`banking_tasci.seed`).

Covers:
- Req 3.1/3.2: `set_seed` independently seeds random/NumPy/PyTorch and is
  deterministic/reproducible (Property 3, property-based).
- Req 3.3: `set_seed_from_config` reads the seed from a `Config` object
  rather than a hard-coded literal.
- Req 3.4: a simulated failure seeding one RNG still seeds the remaining
  RNGs, and `SeedError` lists the failed generator name(s).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import Config  # noqa: E402
from banking_tasci import seed as seed_module  # noqa: E402
from banking_tasci.seed import SeedError, set_seed, set_seed_from_config  # noqa: E402

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False

try:
    import torch

    _HAS_TORCH = True
except ImportError:  # pragma: no cover
    _HAS_TORCH = False


def _draw_sequence() -> tuple:
    """Draw a fixed sequence of values from random/NumPy/(torch if available)."""
    values: list = [random.random(), random.randint(0, 1_000_000)]
    if _HAS_NUMPY:
        values.append(tuple(np.random.rand(3).tolist()))
        values.append(int(np.random.randint(0, 1_000_000)))
    if _HAS_TORCH:
        values.append(torch.rand(3).tolist())
    return tuple(values)


# Feature: banking-tasci-pipeline, Property 3: Seeding is deterministic and reproducible
@settings(max_examples=100)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_set_seed_is_deterministic_and_reproducible(seed: int) -> None:
    set_seed(seed)
    first = _draw_sequence()

    set_seed(seed)
    second = _draw_sequence()

    assert first == second


def test_set_seed_returns_success_map_with_expected_generators() -> None:
    result = set_seed(123)

    assert result["random"] is True
    assert "numpy" in result
    assert "torch_cpu" in result
    assert "torch_cuda" in result


def test_set_seed_from_config_reads_seed_from_config_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """Req 3.3: seed comes from a Config object, not a hard-coded literal."""
    captured: dict = {}

    def fake_set_seed(seed_value: int) -> dict:
        captured["seed"] = seed_value
        return {"random": True, "numpy": True, "torch_cpu": True, "torch_cuda": True}

    monkeypatch.setattr(seed_module, "set_seed", fake_set_seed)

    cfg = Config({"seed": 987})
    result = seed_module.set_seed_from_config(cfg)

    assert captured["seed"] == 987
    assert result["random"] is True


def test_set_seed_from_config_uses_different_seeds_from_different_configs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirms behavior is driven by config content, not a literal constant."""
    seen_seeds: list = []

    def fake_set_seed(seed_value: int) -> dict:
        seen_seeds.append(seed_value)
        return {"random": True, "numpy": True, "torch_cpu": True, "torch_cuda": True}

    monkeypatch.setattr(seed_module, "set_seed", fake_set_seed)

    set_seed_from_config(Config({"seed": 1}))
    set_seed_from_config(Config({"seed": 2}))

    assert seen_seeds == [1, 2]


def test_set_seed_continues_seeding_remaining_generators_on_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 3.4: a failure seeding one RNG still seeds the remaining RNGs,
    and SeedError lists the failed generator name(s)."""
    calls: list[str] = []

    def failing_numpy(_seed: int) -> None:
        calls.append("numpy")
        raise RuntimeError("simulated numpy seeding failure")

    def ok_random(seed_value: int) -> None:
        calls.append("random")
        random.seed(seed_value)

    def ok_torch_cpu(_seed: int) -> None:
        calls.append("torch_cpu")

    def ok_torch_cuda(_seed: int) -> None:
        calls.append("torch_cuda")

    monkeypatch.setattr(seed_module, "_seed_numpy", failing_numpy)
    monkeypatch.setattr(seed_module, "_seed_random", ok_random)
    monkeypatch.setattr(seed_module, "_seed_torch_cpu", ok_torch_cpu)
    monkeypatch.setattr(seed_module, "_seed_torch_cuda", ok_torch_cuda)

    with pytest.raises(SeedError) as exc_info:
        set_seed(42)

    # All generators were attempted despite the numpy failure.
    assert set(calls) == {"random", "numpy", "torch_cpu", "torch_cuda"}
    assert exc_info.value.failed == ["numpy"]
