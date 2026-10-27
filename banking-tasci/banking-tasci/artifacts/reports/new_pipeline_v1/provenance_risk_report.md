# Provenance risk report

Current Git state: `main`, no commit exists, marker `UNKNOWN_NO_COMMIT`. Source, configurations, tests, and governance documentation therefore lack commit-level provenance. The worktree also contains private/raw datasets and generated artifacts outside this repository directory.

`.gitignore` now excludes project environments, caches, credentials/key patterns, OS temporary files, annotation data, generated reports, and training runs/checkpoints. The future baseline commit should include `src/`, `scripts/`, `configs/`, `tests/`, `cluster/*.sh`, `docs/`, `README.md`, `pyproject.toml`, dependency lock/requirement files, and the top-level requirements/proposal documents after review. It should exclude `data/`, `artifacts/runs/`, generated reports, model weights/checkpoints, `.venv*`, `.cache/`, credentials, raw CSV/PDF inputs, and temporary files. Governance manifests, approvals, and freeze receipts should enter only after a privacy review confirms they contain no private text or local secrets.

Risk remains **HIGH** until an authorised, reviewed baseline commit is created. No commit was created in this session.
