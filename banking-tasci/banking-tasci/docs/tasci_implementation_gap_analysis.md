# TASCI Implementation Gap Analysis

**Date:** 25 September 2026  
**Scope:** analysis only; no TASCI implementation or training was performed.

The repository contains baseline models, data loaders, evaluation helpers, and
configuration templates. It does not contain a complete implementation of the
proposed TASCI architecture. The gaps below are based on the current source,
not on proposal claims alone.

| Required component | Current implementation | Missing functionality | Required input/output | Tests/configuration | Baseline dependency |
|---|---|---|---|---|---|
| Self-attention BIO aspect extractor | BIO alignment and metrics exist; no model class | Self-attention encoder, BIO head, training/inference orchestration | Gold text/aspects -> BIO logits and character spans | Add model, BIO loss/config, alignment and reload tests | Gold aspect data and a verified baseline protocol |
| GRU previous/current intent model | Context rendering and SVM/BiLSTM baselines exist; no GRU intent model | GRU encoder using current plus genuine previous text | Intent examples -> logits/labels | Add GRU config, forward, masking, checkpoint tests | Context-aware SVM comparison and context data |
| No-context masking | `[NO_CONTEXT]` sentinel and `context_available` flag exist | Architecture-level masking semantics for a GRU | Context flag/text -> masked representation | Add no-context forward and leakage tests | Context-aware baseline |
| GloVe loading/OOV | No GloVe loader or embedding initialization found | Vector file loading, vocabulary alignment, OOV policy | GloVe file + vocabulary -> embedding matrix | Add loader, dimension, OOV, reproducibility tests/config | None, but tokenizer/vocabulary contract required |
| Transformer aspect encoder | BERT baseline helpers exist; no TASCI aspect encoder | Transformer representation integrated with aspect task | Tokenized aspect/text -> aspect representation | Add encoder config, shape, truncation, reload tests | BERT preflight and approved checkpoint |
| Intent projection | No TASCI intent projection module found | Project intent representation to fusion dimension | Intent hidden state -> projected vector | Add shape and checkpoint tests/config | GRU intent model |
| Aspect-intent fusion | No fusion module found | Combine aspect and intent representations | Two hidden vectors -> fused representation | Add fusion ablation and shape tests/config | Aspect encoder and intent projection |
| Sentiment head | SVM/BiLSTM sentiment heads exist independently | TASCI sentiment head consuming fused representation | Fused aspect-intent vector -> sentiment logits | Add head/loss/reload tests/config | Fusion and gold aspect/sentiment labels |
| No-intent ablation | Evaluation ablation utilities exist; no TASCI model condition | Controlled sentiment path without intent fusion | Same examples -> no-intent sentiment metrics | Add matched ablation config and test | Complete integrated model |
| Current-only intent ablation | Dataset rendering supports current-only; no TASCI ablation runner | Matched current-only versus context-aware TASCI experiment | Same split -> paired metrics | Add experiment config/report test | GRU intent model |
| Gold-aspect evaluation | Span/end-to-end metric helpers exist | Evaluation path that supplies gold aspects to sentiment | Gold spans + text -> sentiment/end-to-end metrics | Add fixture and report tests/config | Aspect labels and sentiment model |
| Predicted-aspect inference | BIO span reconstruction helper exists; no end-to-end wiring | Pass predicted spans into sentiment and intent stages | Raw text -> predicted aspects -> outputs | Add integration tests/config | Trained aspect extractor |
| End-to-end pipeline | Tuple metrics exist; `inference/` is effectively empty | Batch orchestration, structured prediction output, failure handling | Raw records -> aspects, intent, sentiment | Add CLI, schema, integration, reload tests | All three TASCI components |
| Model save/reload | Shared checkpoints and SVM reload exist | Unified save/reload for multi-component TASCI | Model/config/label maps -> identical reload predictions | Add complete artifact and prediction-equivalence tests | Implemented model components |
| Checkpoint resume | Shared training loop supports structured full resume | Multi-component optimizer/state coordination and last/best artifact policy | Structured checkpoint -> faithful continuation | Add interrupted-run integration test/config | Complete TASCI trainer |
| Regional/context subgroup evaluation | Regional evaluation and report writers exist | TASCI-specific predictions and matched subgroup reports | Predictions + metadata -> regional/context metrics | Add report fixtures and minimum-support policy | End-to-end predictions |

## Configuration Gap

`configs/aspect.yaml`, `configs/intent.yaml`, `configs/sentiment.yaml`, and
`configs/full_pipeline.yaml` are templates/configuration surfaces, not evidence
that the corresponding TASCI modules are implemented or trained. They need
concrete model, tokenizer/embedding, checkpoint, device, and experiment
settings once the architecture is approved.

## Dependency Order

The practical dependency order is: approve data quality and baseline results;
complete context-aware SVM and BiLSTM verification; resolve BERT preflight if it
is a required comparator; implement and test the aspect extractor and GRU;
implement fusion/sentiment; then add ablations, end-to-end inference, reload,
resume, and subgroup reporting.