# Cluster pilot staging and recovery — 20 October 2026

Password authentication succeeded in the researcher's terminal. Slurm uses
`select/linear` with no configured GRES. No verified GPU request or Linux MLM
environment exists yet. Do not submit the old GPU wrapper. No pilot was run.

The new pilot checkpoint format saves model, optimiser, linear warm-up scheduler,
Python/PyTorch/CUDA RNG state, completed update, next corpus offset, token count,
loss history and monitoring history. Files are checksummed before atomic directory
publication. Resume rejects completed runs, incompatible metadata/policy, corrupt
files and a checkpoint older than the latest published checkpoint. Existing smoke
checkpoints are preserved and cannot be used as pilot recovery checkpoints.

The pilot CLI now accepts:

```sh
python scripts/train_self_supervised.py \
  --config configs/self_supervised/u1_banking_mlm_bert.yaml \
  --mode pilot --execute-authorized --resume-from <latest-pilot-checkpoint>
```

The recovery helper passes a tiny-model uninterrupted-versus-resumed next-update
test, including dropout and scheduler state. A full BERT/CUDA interrupted pilot
has not been exercised. GPU bitwise reproducibility has not been established.

`outputs/cluster_staging/pilot_assets_20261020.tar` contains the exact strict
corpus, strict manifests, shared partition files and pinned cached BERT/tokenizer
snapshot. It contains 13 files, with individual SHA-256 checksums. Symlinks in
the Hugging Face cache are dereferenced, so the archive is portable. It excludes
the Mac Python environment, annotation text, smoke checkpoints and credentials.

Archive SHA-256:
`a6abe93f89036aa65fd3758d1e67ba2cd3224dc11ab4d34defed74140dc1aa34`.

Stage assets in a new isolated project directory under the verified
`/datasets/rmavhengani` storage. After extraction, run `sha256sum -c
pilot_assets.sha256` from that project root. Set
`BANKING_TASCI_CORPUS_PATH` to its absolute
`data/processed/new_pipeline_v1/strict_unlabelled.jsonl` path. This explicitly
relocates the input without rewriting the protected manifest; the corpus
checksum remains mandatory. Run both representation validate-only commands
after installing the pinned Linux-compatible environment. Do not copy `.venv-mlm`
from macOS. Do not run model loading, dependency builds or training on the login
node. Confirm the administrator-supported GPU allocation/environment first.

Tests: 14 passed in the focused recovery/masking invocation. No smoke or pilot
workload was run. `FULL_SUITE_NOT_RUN_CREDIT_SAVING`.
