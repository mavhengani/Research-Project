#!/usr/bin/env python3
"""Validate strict-corpus inputs and print an MLM training plan.

This command deliberately does not load a model, download assets, tokenize data,
or train. A later separately authorised training command must implement those
operations after reviewing this plan and its immutable corpus references.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from banking_tasci.config import load_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/new_pipeline_v1.yaml")
    parser.add_argument("--strict-manifest", default="artifacts/manifests/new_pipeline_v1/strict_unlabelled/strict_unlabelled_manifest.json")
    args = parser.parse_args(argv)
    config = load_config(ROOT / args.config)
    manifest_path = ROOT / args.strict_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus_path = ROOT / manifest["corpus_path"] if not Path(manifest["corpus_path"]).is_absolute() else Path(manifest["corpus_path"])
    checksum = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    if manifest.get("record_count") != config.domain_adaptation.expected_records or checksum != manifest.get("corpus_checksum"):
        raise SystemExit("strict corpus manifest validation failed; MLM plan not prepared")
    print(json.dumps({
        "pipeline_version": config.pipeline_version,
        "status": "MLM_TRAINING_NOT_STARTED",
        "training_enabled": config.domain_adaptation.training_enabled,
        "training_gate": config.domain_adaptation.training_gate,
        "strict_corpus": str(corpus_path),
        "strict_corpus_checksum": checksum,
        "record_count": manifest["record_count"],
        "base_model": config.domain_adaptation.base_model,
        "max_length": config.domain_adaptation.max_length,
        "masking_probability": config.domain_adaptation.masking_probability,
        "seed": config.domain_adaptation.seed,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
