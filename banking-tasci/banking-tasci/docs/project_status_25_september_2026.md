# Banking TASCI Project Status

**Status date:** 25 September 2026

## Verified Completed

- Combined Gold Version 2 contains 796 records: 600 international and 196 South
  African.
- Combined leakage-safe manifests exist with 556 train, 122 validation, and
  118 test records.
- The South African component was genuinely independently annotated and
  manually adjudicated. Pre-adjudication agreement was strong: intent Kappa
  0.8736, aspect-category Kappa 0.9904, aspect-sentiment Kappa 0.8750,
  exact-span agreement 0.8010, and token-level aspect F1 0.8966.
- The original 600-record component was technically validated but did not have
  genuine independent annotation.
- SVM intent and aspect-sentiment baselines completed on the cluster and have
  reloadable stored artifacts. The intent run used current-text-only input.

## SVM Results

| Task | Validation macro-F1 | Test accuracy | Test macro-F1 | Test weighted-F1 |
|---|---:|---:|---:|---:|
| Intent | 0.4612058704 | 0.6440677966 | 0.4283948604 | 0.6391079509 |
| Sentiment | 0.6474400365 | 0.5714285714 | 0.5061415921 | 0.5591080086 |

The completed intent run used `current_only`. The context-aware SVM intent
baseline has not been completed. The recorded subgroup results are
exploratory, particularly for small or imbalanced groups.

## Implemented but Not Artifact-Verified

- BiLSTM intent and aspect-level sentiment source code exists, including the
  shared training loop and checkpoint support, but no complete repository-
  verifiable BiLSTM run artifact set was found.
- BERT loading, BIO alignment, intent/sentiment heads, and current orchestration
  source code exist, but no completed BERT run artifact set was found.
- Evaluation utilities for BIO, classification, spans, subgroups, ablations,
  and end-to-end tuples exist.

## Known Data Limitations

- `pilot_unannotated.jsonl` is not pristine: its stored content is annotated and
  it is byte-identical to annotator A; the provenance audit is recorded in
  `outputs/pilot_annotation_input_provenance_audit.json`.
- The international annotator files share canonical label content and therefore
  do not establish independent human-reliability evidence.
- The combined data has documented minority-label and annotation-provenance
  limitations. Technical readiness is not equivalent to research readiness.
- The large South African prepared corpus is not fully human-labelled; only the
  196-record label-hidden input progressed to adjudicated gold.

## Outstanding

1. Complete and artifact-verify the context-aware SVM intent baseline.
2. Produce a complete artifact-backed BiLSTM intent and sentiment run.
3. Resolve BERT dependency, checkpoint, and GPU requirements, then preflight
   again before any training.
4. Decide whether data-quality and minority-class limitations permit formal
   reporting of baseline results.
5. Implement the proposed TASCI components and end-to-end inference only after
   baseline corrections are approved.

## Approval Criteria for the Next Stage

The project should not enter TASCI development until the context-aware SVM is
compared with current-only input, the BiLSTM artifacts are reload-verified, and
the research-quality implications of the annotation provenance and label
support are explicitly approved. BERT must remain untrained until its local
dependency/checkpoint/device preflight passes.

PROJECT PARTIALLY READY; SPECIFIC CORRECTIONS REQUIRED