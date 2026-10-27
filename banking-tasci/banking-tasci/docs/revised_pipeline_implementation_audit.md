# Revised Pipeline Implementation Audit

**Date:** 28 September 2026  
**Scope:** Read-only comparison of the Banking TASCI repository against the revised learning design supplied for this audit.

## Audit limitation

`revised_proposal_no_abstract_citations.tex` was not found in the inspected
workspace or repository. The classifications below therefore use the 12-point
design stated in the audit request and direct repository evidence. No code,
data, annotations, manifests, models, or reports were changed by this audit.
No tests, model training, downloads, or cluster jobs were run.

## Current evidence baseline

Observed repository artifacts include:

- `combined_adjudicated_v2.jsonl`: 796 records;
- `data/processed/combined_v2/`: 556 train, 122 validation, 118 test records;
- genuine South African adjudication/agreement artifacts for 196 records;
- completed current-only and previous-plus-current SVM intent runs;
- completed SVM aspect-sentiment run;
- BiLSTM model/training infrastructure and synthetic smoke-test evidence, but no
  completed artifact-backed research run;
- BERT helper/configuration infrastructure, but no dependency/checkpoint in the
  local environment and no completed BERT run;
- no MLM corpus builder, MLM dataset, domain-adaptation trainer, or adapted-BERT
  artifact set;
- no complete TASCI implementation or structured end-to-end inference run.

The repository has data preparation, anonymisation, schema validation, exact and
near-duplicate utilities, annotation validation, agreement/adjudication, split
creation, readiness checks, baseline models, evaluation helpers, and cluster
scripts. Configuration presence is not treated as implementation evidence.

## Component classification

| # | Required component | Status | Existing reusable code/evidence | Required gap |
|---:|---|---|---|---|
| 1 | International unlabelled-corpus builder | **PARTIAL** | `data/ingest.py`, `scripts/prepare_data.py`, canonical prepared data | A distinct large unlabelled-corpus export and manifest for domain adaptation |
| 2 | South African unlabelled-corpus builder | **IMPLEMENTED BUT UNTESTED** | `ingest_south_africa.py`, `prepare_south_africa_data.py`, v1/v2 preparation reports; large prepared corpus documented | Dedicated MLM text export, corpus checksum, and execution evidence |
| 3 | Source and region labelling | **COMPLETE AND TESTED** | Canonical schema, ingestion, annotation records, region/source fields, focused tests and reports | Preserve fields in new corpus manifests |
| 4 | Privacy validation | **COMPLETE AND TESTED** | `anonymise.py`, annotation privacy checks, South African privacy reports | Reapply validation to unlabelled MLM exports |
| 5 | Duplicate and near-duplicate isolation | **COMPLETE AND TESTED** | `clean.py`, exact duplicate removal, bounded near-duplicate scanning, focused tests | Define corpus-level train/adaptation/test isolation policy |
| 6 | Audited international 300-record sample | **NOT IMPLEMENTED** | Existing international pilot is 600, with documented provenance limitations | New 300-record human-audited sample and independent audit artifacts |
| 7 | South African 196-record gold data | **COMPLETE AND TESTED** | `south_african_adjudicated_v2.jsonl`, genuine agreement/adjudication reports | None for the stated 196-record component |
| 8 | New labelled 496-record dataset | **NOT IMPLEMENTED** | Existing combined gold is 796 = 600 international + 196 South African | New 300+196 gold creation and provenance decision |
| 9 | New 348/75/73 manifests | **NOT IMPLEMENTED** | Existing combined manifests are 556/122/118 | New manifests and leakage checks for 496 records |
| 10 | Masked-language-modelling dataset | **NOT IMPLEMENTED** | No MLM dataset class, masking pipeline, corpus manifest, or MLM script found | Text-only corpus loader, tokenizer/masking policy, train/validation split, checksums |
| 11 | Banking-domain BERT adaptation | **NOT IMPLEMENTED** | `bert_baseline.py` supports supervised heads and offline loading only | MLM trainer, optimizer/scheduler, validation loss, resume, GPU job, and evaluation |
| 12 | Adapted-model artifact writer | **NOT IMPLEMENTED** | Generic supervised `reproducibility.py` writer exists | Adapted checkpoint/tokenizer/config/environment/checksum artifact schema |
| 13 | SVM baselines | **COMPLETE AND TESTED** | `svm_baseline.py`, runner, configs, two completed SVM run directories and metrics | Re-run on revised 496-record manifests; preserve old runs |
| 14 | BiLSTM baselines | **PARTIAL** | BiLSTM model, shared loop, checkpoint path, smoke test, intent job script; no completed research run | Complete intent and sentiment runs on revised data and verify artifacts |
| 15 | BERT aspect extraction | **IMPLEMENTED BUT UNTESTED** | Local/offline BERT BIO alignment, ignored positions, span reconstruction | Dependency/checkpoint, revised data training, artifact-backed execution |
| 16 | BERT intent classification | **IMPLEMENTED BUT UNTESTED** | BERT sequence-classification helpers and dispatcher | Dependency/checkpoint, supervised run, metrics and comparison |
| 17 | BERT aspect sentiment | **IMPLEMENTED BUT UNTESTED** | Aspect markers and sequence-classification helpers | Dependency/checkpoint, supervised run, metrics and comparison |
| 18 | Self-attention aspect extractor | **NOT IMPLEMENTED** | BIO utilities and metrics only; no self-attention extractor model | New model module, config, loss, trainer, inference, tests |
| 19 | Contextual GRU intent classifier | **NOT IMPLEMENTED** | Context rendering and SVM/BiLSTM baselines; no GRU TASCI model | Current/previous encoders, attention/masking, classifier, ablation tests |
| 20 | GloVe loader | **NOT IMPLEMENTED** | No GloVe loader or OOV embedding initialization found | Embedding module, dimension/OOV config, checksum and loader tests |
| 21 | Transformer sentiment classifier | **PARTIAL** | BERT sentiment baseline exists; no TASCI Transformer sentiment head | Intent-conditioned Transformer sentiment implementation and tests |
| 22 | Intent projection and fusion | **NOT IMPLEMENTED** | No TASCI projection/fusion module found | Projection dimensions, fusion module, shape/loss/reload tests |
| 23 | No-intent ablation | **PARTIAL** | Generic ablation utilities exist; no TASCI no-intent execution path | Matched experiment runner/config/report |
| 24 | Current-only intent ablation | **PARTIAL** | Dataset rendering and SVM current/context variants exist; no TASCI ablation | TASCI current-only/control runner and paired comparison |
| 25 | Cross-domain transfer | **NOT IMPLEMENTED** | Regional/source subgroup evaluation exists; no transfer protocol or run | International-train/SA-test manifests, transfer trainer, report |
| 26 | Mixed-domain training | **PARTIAL** | Existing combined-v2 gold/manifests and SVM mixed run exist | Revised 496-record mixed-domain dataset and controlled comparison |
| 27 | Subgroup evaluation | **COMPLETE AND TESTED** | Regional/source/context evaluation helpers, SVM subgroup artifacts | Extend to revised runs and minimum-support policy |
| 28 | Complete model save and reload | **PARTIAL** | SVM reload and shared checkpoints tested; BiLSTM artifact path prepared | Unified TASCI/adapted-BERT artifact and prediction-equivalence checks |
| 29 | Checkpoint resume | **IMPLEMENTED BUT UNTESTED** | Shared loop supports warm/full resume and RNG metadata | Exercise full resume for each revised neural/MLM run |
| 30 | Final structured inference | **NOT IMPLEMENTED** | `evaluation/end_to_end.py` has tuple metrics; inference package is empty | Integrated aspect/intent/sentiment pipeline and structured output schema |

## Revised design status

### Existing reusable code

Retain and reuse the schema, anonymisation, ingestion, source/region metadata,
exact/near-duplicate utilities, annotation validation, agreement/adjudication,
manifest generation, readiness gate, fixed label maps, SVM pipelines, shared
PyTorch loop, checkpoint primitives, BERT BIO alignment, metrics, subgroup
helpers, and run-artifact conventions.

### Incompatible or insufficient existing code

The existing 796-record combined gold and 556/122/118 manifests do not satisfy
the proposed 496-record and 348/75/73 design. They must remain unchanged but
must not be relabelled as the revised dataset. The current BERT code is a
supervised baseline, not an MLM adaptation trainer. Existing BERT configs point
to a local checkpoint that is absent locally. Existing TASCI configs are
configuration surfaces, not implementations. The current international pilot
also carries documented independence limitations.

### Code that must remain unchanged

Do not overwrite `combined_adjudicated_v2.jsonl`, any annotation files,
`data/processed/combined_v2/` manifests, completed SVM run directories,
genuine South African agreement/adjudication artifacts, or historical reports.
Create versioned revised-data paths and new run directories.

## New modules required

Recommended new modules/scripts are:

- `src/banking_tasci/data/mlm_corpus.py`: corpus records, source/region metadata,
  privacy and duplicate guards;
- `src/banking_tasci/data/mlm_dataset.py`: tokenizer, masking policy, and
  adaptation split handling;
- `src/banking_tasci/models/bert_mlm.py`: local model loading and MLM head;
- `src/banking_tasci/training/mlm_runner.py`: validation-loss training,
  checkpoint/resume, and deterministic logging;
- `scripts/prepare_mlm_corpus.py` and `scripts/train_domain_adaptation.py`;
- `scripts/create_revised_gold.py` and `scripts/create_revised_splits.py`;
- adapted-model artifact/checksum utilities;
- TASCI modules for aspect attention, GRU context, fusion, sentiment, and
  inference.

## New configurations required

Add versioned configs for:

- international and South African unlabelled corpora;
- corpus deduplication/isolation and privacy policy;
- 300-record international audit sample;
- 496-record gold and 348/75/73 splits;
- MLM tokenizer/model, masking probability, sequence length, optimizer,
  scheduler, epochs, warmup, device, checkpoint, and offline flags;
- original-BERT versus adapted-BERT experiments;
- TASCI component dimensions, masks, label maps, ablations, transfer, and
  mixed-domain experiments.

## New data artifacts required

- versioned unlabelled international corpus and manifest;
- versioned unlabelled South African corpus and manifest;
- source/region/privacy/duplicate audit reports;
- audited international 300-record annotation input and gold;
- revised 496-record adjudicated gold;
- revised 348/75/73 leakage-safe manifests;
- MLM train/validation corpus manifests and checksums;
- original and adapted BERT checkpoints/tokenizers with SHA-256 manifests;
- per-run config, environment, commit identifier, metrics, predictions,
  subgroup reports, confusion matrices, and reload checks.

## Recommended execution order

1. Locate and archive the revised proposal outside the repository audit path, or
   provide its exact path; do not infer missing design details.
2. Freeze existing gold, manifests, SVM runs, and historical reports.
3. Build and audit separate unlabelled international/South African corpora.
4. Define duplicate isolation and MLM corpus splits before tokenization.
5. Create and independently audit the 300-record international sample.
6. Combine it with the unchanged 196-record South African gold only after
   provenance approval; create new 496-record gold and 348/75/73 manifests.
7. Implement MLM dataset/trainer and prepare approved offline BERT assets.
8. Train banking-domain adaptation and verify adapted checkpoint reload.
9. Run revised SVM, BiLSTM, original-BERT, and adapted-BERT baselines.
10. Implement TASCI incrementally, testing each component and ablation.
11. Run current/context, intent/no-intent, transfer, and mixed-domain studies.
12. Produce final structured inference and research reports.

## Final assessment

The repository is a strong foundation for data preparation, annotation, leakage-
safe supervised baselines, and evaluation. It is not yet aligned with the
revised learning design because the unlabelled MLM/adaptation stage, revised
496-record dataset/splits, original-versus-adapted BERT comparison, transfer/
mixed-domain experiments, and full TASCI pipeline are missing.

REVISED PIPELINE AUDIT COMPLETE. NO CODE HAS BEEN CHANGED.
