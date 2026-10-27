# Phase 3A — Initial Repository Audit

**Author:** GitHub Copilot
**Scope:** Read-only inspection of the repository state at the start of Phase 3A
(baseline implementation, robustness fixes, readiness validation, testing).
**Method:** Direct inspection of `src/`, `scripts/`, `tests/`, `configs/`,
`docs/`, `data/`, and a full `pytest` run. No labels, checkpoints, predictions,
or metrics were fabricated.

> Note: `KIRO_SPEC.md` is referenced by several docstrings but is **not present**
> in the repository root. Requirement numbers below are taken from the docstrings
> and existing tests, which encode the same requirement identifiers.

---

## 1. Component presence (confirmed by inspection)

| Component | Status | Evidence |
| --- | --- | --- |
| SVM baseline | **IMPLEMENTED** (with a reload gap) | `src/banking_tasci/models/svm_baseline.py` (595 lines): TF-IDF + LinearSVC pipelines, `fit_and_select`, calibrated variants, `save_artifacts`/`load_artifacts`. Gap: reload does not restore the task-specific text extractor (Part 3). |
| BiLSTM baseline | **MISSING** | `src/banking_tasci/models/` contains only `svm_baseline.py` + empty `__init__.py`. No `bilstm_baseline.py`. |
| BERT baseline | **MISSING** | No `bert_baseline.py`. `transformers` is not installed in the environment. |
| Neural data loaders | **IMPLEMENTED** | `src/banking_tasci/data/datasets.py` (392 lines): `build_intent_examples`, `build_sentiment_examples`, `build_bio_examples` + label maps; BIO delegated to `data/bio.py`. |
| Training CLIs | **MISSING** | No `scripts/train_baselines.py`. `prepare_data.py` and the Phase 2 CLIs exist, but no baseline-training entry point. |
| Readiness CLI | **PARTIAL** | `src/banking_tasci/training/readiness.py` (module `assert_ready`/`check_readiness`) exists, but there is no `scripts/check_training_readiness.py` CLI with the granular checks required by Part 6. |
| Evaluation scripts | **MISSING** | `src/banking_tasci/evaluation/__init__.py` is a 0-byte stub. No metrics module. |
| Model checkpoints | **MISSING (correct)** | No `outputs/runs/`; no `.pt`/`.pth` files. Correct at this stage. |
| Gold annotation files | **BLOCKED BY GOLD DATA** | `data/annotations/` holds only `pilot_unannotated.jsonl` (600 records, `annotation_status="not_started"`). No `pilot_adjudicated.jsonl`. |
| Train/val/test manifests | **BLOCKED BY GOLD DATA** | `data/processed/` holds only `.gitkeep`. No `*_manifest.csv`. |

---

## 2. Supporting infrastructure (confirmed)

| Module | Status | Notes |
| --- | --- | --- |
| `config.py` | IMPLEMENTED | Deep-merge + `defaults`/`base` inheritance. **No cycle detection** (Part 2). |
| `training/loop.py` | IMPLEMENTED | Shared loop, macro-F1, early stopping, checkpoint by best val. Resume restores **weights only** (Part 4). |
| `training/readiness.py` | IMPLEMENTED | `assert_ready` raises a fixed blocked message. |
| `training/reproducibility.py` | IMPLEMENTED | Writes `outputs/runs/<run-id>/` artifacts. |
| `data/ingest.py` | IMPLEMENTED | `created_at` is an inconsistent mix (ISO / raw string / null) (Part 5). |
| `data/annotations.py`, `data/bio.py`, `data/context.py` | IMPLEMENTED | Phase 2 schema, validation, BIO conversion. |
| `seed.py`, `logging_utils.py`, `scaffold.py` | IMPLEMENTED | Phase 1 utilities. |

---

## 3. Requirement classification matrix

Legend: **IMPLEMENTED** = present and tested; **PARTIAL** = present but incomplete
for Phase 3A; **MISSING** = not present; **BLOCKED BY GOLD DATA** = cannot be
completed/validated until adjudicated gold + leakage-safe splits exist.

| Phase 3A requirement area | Classification | Rationale |
| --- | --- | --- |
| Config inheritance + deep-merge | IMPLEMENTED | `config.py` merges `defaults`/`base`; tests pass. |
| Config inheritance cycle detection | MISSING | No recursion guard; a cyclic `defaults` chain would recurse until failure. (Part 2) |
| Text feature extractors (intent/context/sentiment) | IMPLEMENTED | `svm_baseline.intent_text` / `intent_context_text` / `sentiment_text`. |
| SVM artifact save/reload | PARTIAL | Reload loses the text extractor; no stable extractor id persisted. (Part 3) |
| Training loop (loss/clip/early-stop/checkpoint) | IMPLEMENTED | `train_model` selects on val macro-F1; never touches test. |
| Warm-start vs full-resume semantics | PARTIAL | Only weight-restore resume exists; no optimizer/epoch/RNG resume. (Part 4) |
| `created_at` canonical contract | PARTIAL | Mixed ISO/raw/null values; needs one documented policy. (Part 5) |
| Readiness gate (module) | IMPLEMENTED | `assert_ready`/`check_readiness`. |
| Readiness CLI (`check_training_readiness.py`) | MISSING | Required granular checks + fixed blocked message. (Part 6) |
| Intent dataset builder | IMPLEMENTED | `build_intent_examples`; needs explicit `current_only`/`previous_plus_current` modes surfaced. (Part 7) |
| Sentiment dataset (one-per-aspect, marked text) | IMPLEMENTED | `build_sentiment_examples` + `mark_aspect`. |
| BIO dataset (offsets, -100, truncation report) | IMPLEMENTED | `build_bio_examples` + `data/bio.py`. |
| SVM baselines (intent/context/sentiment) | PARTIAL | Pipelines exist; extractor-id persistence + full save set needed. (Part 8) |
| BiLSTM baseline | MISSING | (Part 9) |
| BERT baseline | MISSING | (Part 10) |
| Baseline training CLI | MISSING | (Part 11) |
| Evaluation infrastructure | MISSING | (Part 12) |
| Cluster guide | MISSING | No `docs/cluster_guide.md`. (Part 14) |
| Actual baseline training results | BLOCKED BY GOLD DATA | Pilot unannotated; no adjudicated gold, no manifests. |

---

## 4. Test baseline

`python3 -m pytest -q` at the start of Phase 3A: **264 passed, 2 warnings**
(the warnings are pre-existing sklearn single-class kappa warnings in
`tests/test_agreement.py`, unrelated to Phase 3A).

Installed optional deps: `scikit-learn` 1.7.2, `torch` 2.13.0+cpu.
Not installed: `transformers` (BERT code + tests must degrade gracefully).

---

## 5. Gold-data blocker (unchanged)

The 600-record pilot in `data/annotations/pilot_unannotated.jsonl` is
**unannotated** (`annotation_status="not_started"`, null intent, empty aspects).
No adjudicated gold file and no split manifests exist. Therefore **no genuine
supervised training or evaluation can be run in Phase 3A**. All baseline
infrastructure below is built and unit-tested on tiny in-test synthetic
fixtures only; none of it is trained on research data.

