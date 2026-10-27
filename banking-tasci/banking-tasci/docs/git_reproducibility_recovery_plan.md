# Git Reproducibility Recovery Plan

**Status:** proposal only; no Git history or repository root was changed.

## Intended Root

The project directory is currently nested inside the parent worktree
`/Users/rotondwa_janti/Documents/Research Project`. The intended clean root
should be explicitly approved before Git initialization or history migration.

## Track

Track source code, tests, scripts, configuration templates, cluster scripts,
documentation, and small machine-readable provenance manifests. Track checksums
and metadata for large external artifacts rather than the artifacts themselves.

## Keep External or Ignored

- raw CSV/parquet source data;
- prepared large datasets and annotation exports where policy requires external
  storage;
- model weights and pretrained checkpoints;
- `outputs/runs/`, logs, predictions, and generated confusion matrices unless a
  curated result bundle is explicitly archived;
- local virtual environments, caches, compiled files, and temporary files.

## Never Track

Passwords, private keys, SSH configuration, access tokens, credentials, local
environment files containing secrets, and raw customer identifiers.

## Proposed `.gitignore` Topics

Ignore `.venv/`, `__pycache__/`, `.pytest_cache/`, `.hypothesis/`, raw/interim
large data, pretrained model directories, generated run outputs/logs, and local
editor/system files. Preserve small schemas, checksums, and provenance reports.

## Clean Baseline Procedure

After approval: create or select the intended repository root, review all
untracked files manually, add only approved source/config/test/docs files,
create one baseline commit, and record its ID in future run metadata. Do not
initialize, commit, push, or delete files automatically during this recovery
plan.

## Future Runs

Every run should record the commit ID, effective config, environment versions,
data checksums, split-manifest checksums, model/checkpoint checksums, job ID,
partition/node, and artifact inventory. If no valid commit exists, record an
explicit `unknown` value rather than implying reproducibility.