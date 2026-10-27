# Phase 3A — Completion Report

**Author:** GitHub Copilot
**Scope:** Baseline implementation, robustness fixes, readiness validation, and
testing. No research training or evaluation was performed; no annotations,
checkpoints, predictions, or metrics were fabricated.

---

## 1. Initial audit findings

Full detail in `docs/github_copilot_phase_3a_initial_audit.md`. Summary of the
starting state:

- **SVM baseline:** implemented (`models/svm_baseline.py`), but artifact reload
  silently lost the task-specific text extractor.
- **BiLSTM / BERT baselines:** missing.
- **Neural data loaders:** implemented (`data/datasets.py` — intent/sentiment/BIO).
- **Training CLIs:** missing (`train_baselines.py`, `check_training_readiness.py`).
- **Evaluation:** missing (`evaluation/` was an empty stub).
- **Config loader:** implemented, but had **no inheritance cycle detection**.
- **Training loop:** implemented, but resume restored **weights only**.
- **`created_at`:** an inconsistent mix of ISO strings / raw strings / null.
- **Gold data / manifests / checkpoints:** absent (correctly) — the 600-record
  pilot is unannotated.

Starting test baseline: **264 passed**.

---

## 2. Files created and modified

### Created

| Path | Purpose |
| --- | --- |
| `docs/github_copilot_phase_3a_initial_audit.md` | Part 1 audit + requirement matrix. |
| `docs/github_copilot_phase_3a_completion_report.md` | This report. |
| `docs/cluster_guide.md` | Placeholder-safe cluster runbook (Part 14). |
| `scripts/check_training_readiness.py` | Supervised-readiness CLI (Part 6). |
| `scripts/train_baselines.py` | Unified baseline training CLI (Part 11). |
| `src/banking_tasci/training/supervised_gate.py` | 13-check readiness gate (Part 6). |
| `src/banking_tasci/training/baseline_runner.py` | Post-readiness training orchestration (Part 11). |
| `src/banking_tasci/models/bilstm_baseline.py` | BiLSTM intent + aspect-sentiment (Part 9). |
| `src/banking_tasci/models/bert_baseline.py` | BERT BIO/intent/sentiment, offline (Part 10). |
| `src/banking_tasci/evaluation/metrics.py` | Classification + BIO metrics (Part 12). |
| `configs/baselines/{svm,bilstm,bert}_*.yaml` | 7 baseline configs (Part 11). |
| `tests/test_created_at.py` | `created_at` contract (Part 5). |
| `tests/test_supervised_gate.py` | Readiness gate + leakage checks (Part 6). |
| `tests/test_intent_modes.py` | Intent `current_only` / `previous_plus_current` (Part 7). |
| `tests/test_bilstm_baseline.py` | Forward pass, overfit, checkpoint reload (Part 9). |
| `tests/test_bert_baseline.py` | BIO alignment/reconstruction + offline smoke (Part 10). |
| `tests/test_train_baselines_cli.py` | Blocked message + real SVM/BiLSTM runs (Part 11/13). |
| `tests/test_evaluation_metrics.py` | Metric correctness (Part 12). |
| `tests/test_rating_not_a_feature.py` | Proof `rating` is never an input feature (Part 13). |

### Modified

| Path | Change |
| --- | --- |
| `src/banking_tasci/config.py` | Inheritance **cycle detection** with a named chain (Part 2). |
| `src/banking_tasci/models/svm_baseline.py` | `TEXT_EXTRACTOR_REGISTRY`, stable extractor id persisted + restored (Part 3). |
| `src/banking_tasci/training/loop.py` | `warm_start` vs `full_resume`, structured checkpoints, RNG capture/restore (Part 4). |
| `src/banking_tasci/data/ingest.py` | Strict `created_at` (ISO-or-null) + `created_at_raw` provenance (Part 5). |
| `src/banking_tasci/data/datasets.py` | Explicit intent input modes + `render_intent_text` (Part 7). |
| `src/banking_tasci/evaluation/__init__.py` | Export the metrics API (Part 12). |
| `requirements.txt` | Add `scikit-learn`, `joblib`; note optional `transformers`. |
| `docs/data_dictionary.md` | `created_at` contract + `created_at_raw` + schema migration note (Part 5). |
| `tests/test_config.py` | Direct/indirect/self/diamond cycle tests (Part 2). |
| `tests/test_svm_baseline.py` | Extractor restoration + reload prediction equivalence (Part 3). |
| `tests/test_training_loop.py` | Warm-start / full-resume / checkpoint tests (Part 4). |

---

## 3. Robustness issues fixed

1. **Config inheritance cycles (Part 2).** `_load_merged_dict` threads a
   resolved-path chain and raises
   `ConfigError("Configuration inheritance cycle detected: a.yaml -> b.yaml -> a.yaml")`
   instead of recursing. Valid multi-level and diamond inheritance still work.
2. **SVM extractor reload (Part 3).** A stable id
   (`intent_current` / `intent_context` / `sentiment_aspect_marked`) is saved to
   `extractor.json` and resolved back via `TEXT_EXTRACTOR_REGISTRY` on load — no
   lambdas/callables are pickled. Unknown ids raise a helpful error; saved and
   reloaded models produce **identical predictions**.
3. **Training resume (Part 4).** Two explicit modes: `warm_start` (weights
   only, fresh run) and `full_resume` (weights + optimiser + epoch + best score
   + early-stopping counter + RNG, continuing from `epoch + 1`). Old weight-only
   checkpoints load as `warm_start`; a `full_resume` from one raises
   `CheckpointCompatibilityError`. Warm start is never described as a
   continuation.
4. **`created_at` contract (Part 5).** Now strictly ISO-8601-or-null;
   unparseable raw values are preserved in the new `created_at_raw` column.
   `record_id` is unchanged (it hashes source + text, never the date).

---

## 4. Architectures implemented

- **SVM (Part 8):** TF-IDF + LinearSVC for intent (current + context-aware) and
  aspect sentiment (`[ASP]`-marked text); selection by **validation** macro-F1;
  calibrated probabilities only when explicitly enabled, else raw decision
  scores; saves vectoriser, classifier, extractor id, label map, config, and
  validation metrics.
- **BiLSTM (Part 9):** embedding → mask-aware packed BiLSTM → dropout → linear
  head, raw logits. Sentiment uses an **aspect mask + pooled aspect
  representation**. CPU/CUDA, class weights, gradient clipping, early stopping,
  warm start / full resume — all via the shared loop.
- **BERT (Part 10):** token classification (BIO), sequence classification
  (intent), and aspect-marked sentiment. Configurable **local** pretrained path,
  `local_files_only=True` (offline), tokenizer offset alignment with the `-100`
  strategy for special/continuation subwords, truncation reporting, and
  BIO→char-span reconstruction. `transformers` is imported lazily.

---

## 5. CLI commands implemented

- `scripts/check_training_readiness.py --annotations ... --split-dir ...` — runs
  the 13 Part-6 checks; exits non-zero with the exact blocked message when not
  ready.
- `scripts/train_baselines.py --model {svm,bilstm,bert} --task {intent,sentiment,aspect} --config ...`
  — loads/validates config, runs the readiness gate **first**, and (only when
  ready) records seed/environment, writes a unique run directory, saves label
  maps/checkpoints, and evaluates the test split **after** selection.

All 7 commands were executed and each stopped with:

> Supervised training is blocked: adjudicated gold annotations and leakage-safe
> split manifests are missing.

---

## 6. Test results

`python3 -m pytest -q`: **327 passed, 1 skipped, 2 warnings**.

- The 1 skip is the `transformers`-gated BERT offline smoke test (`transformers`
  is not installed here); its BIO alignment/reconstruction logic is covered by
  pure-Python tests that run everywhere.
- The 2 warnings are pre-existing sklearn single-class kappa warnings in
  `tests/test_agreement.py`, unrelated to Phase 3A.

New coverage added for: config cycles (direct/indirect/self/diamond); SVM
extractor restoration + reload equivalence; warm-start and full-resume; the
`created_at` contract (valid/invalid/empty/timezone-aware) and record-id
stability; readiness failure on unannotated data and success on temporary gold
fixtures; intent modes; one-instance-per-aspect sentiment; BIO alignment and
reconstruction; truncation handling; SVM/BiLSTM synthetic fitting; BiLSTM
forward pass + tiny-batch overfit; BERT BIO alignment; neural checkpoint reload
equivalence; split-leakage checks; and proof that `rating` is not an input
feature.

---

## 7. Readiness-validator result

At the current stage the gate correctly **blocks**:

```text
[FAIL] adjudicated_file_exists — missing gold file: data/annotations/pilot_adjudicated.jsonl
[PASS] not_the_unannotated_pilot
[FAIL] split_manifests_exist — missing manifests: [train/validation/test]_manifest.csv
[FAIL] ... (record-dependent checks: gold annotation file absent)
Supervised training is blocked: adjudicated gold annotations and leakage-safe split manifests are missing.
```

---

## 8. Missing gold-data blocker

The 600-record pilot (`data/annotations/pilot_unannotated.jsonl`) is
**unannotated** (`annotation_status="not_started"`, null intent, empty aspects).
There is no `pilot_adjudicated.jsonl` and no `data/processed/*_manifest.csv`.
Consequently **no baseline was trained on research data** and **no research
metrics exist**. Every number produced by the test suite comes from tiny
synthetic in-test fixtures, which are never reported as research results.

To unblock (per `docs/phase_2_completion_report.md` §7–8): two annotators
complete the pilot independently → agreement → adjudication → validation →
`create_splits.py` → the readiness gate passes → `train_baselines.py` trains for
real.

---

## 9. Cluster instructions

`docs/cluster_guide.md` covers: scp/rsync transfer; offline venv + wheelhouse
install; local BERT asset transfer (`local_files_only`); scheduler detection;
Slurm and PBS templates; a CPU smoke test (which correctly stops at the gate);
GPU submission; checkpoint resume (`warm_start` / `full_resume`); and result
retrieval. All scheduler/partition/queue/GPU/module/path specifics are
`<PLACEHOLDER>`s; no credentials are stored (interactive
`ssh rmavhengani@146.141.21.100`).

---

## 10. Unresolved issues / notes

- `transformers` is not installed in the current environment, so the BERT
  offline smoke test skips. Install it from a wheelhouse on the cluster to
  exercise it; the pure-Python BERT alignment/reconstruction logic is already
  fully tested.
- The BERT **full fine-tuning orchestration** in `baseline_runner._train_bert`
  is intentionally guarded (requires a local pretrained model + gold data). The
  model, tokenizer, alignment, and offline-loading code are implemented and
  unit-tested; only the end-to-end fine-tune loop awaits gold data + a local
  model on the cluster.
- `KIRO_SPEC.md` is referenced by docstrings but is not present in the repo;
  requirement identifiers were taken from docstrings/tests, which encode them.
- The full TASCI proposed model was **not** implemented (out of scope for
  Phase 3A).

---

## Final status

Phase 3A baseline implementation and robustness work is complete.
Research training and evaluation remain blocked because the 600-record
pilot has not yet been manually annotated, independently reviewed,
adjudicated, validated, and divided into leakage-safe train, validation,
and test manifests.

