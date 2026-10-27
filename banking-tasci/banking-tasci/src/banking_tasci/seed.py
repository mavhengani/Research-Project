"""Seed_Utility: deterministic seeding of random, NumPy, and PyTorch.

Implements Requirements 3.1-3.4:
- 3.1: seed random, NumPy, and PyTorch (including CUDA generators when
  available) from a single integer seed.
- 3.2: seeding twice with the same seed reproduces identical sequences.
- 3.3: the seed value is read from loaded configuration, not a hard-coded
  literal in calling code (via `set_seed_from_config`).
- 3.4: a failure seeding one RNG does not prevent seeding the others, and
  the failed generator name(s) are reported via `SeedError`.
"""
from __future__ import annotations

import random
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from banking_tasci.config import Config


class SeedError(Exception):
    """Raised when one or more random number generators failed to seed.

    Attributes:
        failed: sorted list of generator names that failed to seed.
    """

    def __init__(self, failed: list[str]) -> None:
        self.failed = sorted(failed)
        super().__init__(
            f"Failed to seed the following generator(s): {', '.join(self.failed)}"
        )


def _seed_random(seed: int) -> None:
    random.seed(seed)


def _seed_numpy(seed: int) -> None:
    import numpy as np

    np.random.seed(seed)


def _seed_torch_cpu(seed: int) -> None:
    import torch

    torch.manual_seed(seed)


def _seed_torch_cuda(seed: int) -> None:
    import torch

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def set_seed(seed: int) -> dict[str, bool]:
    """Seed Python's `random`, NumPy, and PyTorch (CPU + CUDA) from `seed`.

    Each generator is seeded independently inside its own try/except block
    so that a failure seeding one generator (e.g. a missing dependency)
    does not prevent the others from being seeded.

    Returns a per-generator success map, e.g.
    ``{"random": True, "numpy": True, "torch_cpu": False, "torch_cuda": True}``.

    Raises:
        SeedError: if any generator failed to seed, listing the failed
            generator name(s). Raised only after every generator has been
            attempted.
    """
    generators: dict[str, Callable[[int], None]] = {
        "random": _seed_random,
        "numpy": _seed_numpy,
        "torch_cpu": _seed_torch_cpu,
        "torch_cuda": _seed_torch_cuda,
    }

    results: dict[str, bool] = {}
    for name, seed_fn in generators.items():
        try:
            seed_fn(seed)
            results[name] = True
        except Exception:
            results[name] = False

    failed = [name for name, ok in results.items() if not ok]
    if failed:
        raise SeedError(failed)

    return results


def set_seed_from_config(cfg: "Config") -> dict[str, bool]:
    """Convenience wrapper: `set_seed(require(cfg, "seed", ...))`.

    Reads the seed value from the loaded configuration (Requirement 3.3)
    rather than requiring a hard-coded literal in calling code.
    """
    from banking_tasci.config import require

    seed = require(cfg, "seed", "<config>")
    return set_seed(seed)
