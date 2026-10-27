#!/usr/bin/env python3
"""Compatibility alias for the uniform annotation batch review CLI."""
from __future__ import annotations
import warnings
from annotation_review import main


def _run() -> int:
    warnings.warn("review_new_pipeline_annotations.py is a compatibility alias; use annotation_review.py", DeprecationWarning, stacklevel=2)
    return main()


if __name__ == "__main__":
    raise SystemExit(_run())
