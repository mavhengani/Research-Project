# TASCI Implementation Plan

**Status:** planning only; no TASCI component is implemented by this plan.

| Order | Component | Module path | Inputs/outputs | Configuration and tests | Dependency |
|---:|---|---|---|---|---|
| 1 | GloVe loader/OOV policy | `src/banking_tasci/models/embeddings.py` | vectors + vocabulary -> embedding matrix | path, dimension, OOV policy; loader/OOV tests | none |
| 2 | Self-attention BIO extractor | `src/banking_tasci/models/tasci_aspect.py` | token IDs/mask -> BIO logits/spans | hidden size, heads, dropout; shape/loss/span tests | embeddings and gold aspects |
| 3 | Current-only GRU intent | `src/banking_tasci/models/tasci_intent.py` | current sequence -> intent logits | embedding/hidden sizes; forward/checkpoint tests | embeddings |
| 4 | Previous-plus-current GRU | `src/banking_tasci/models/tasci_intent.py` | previous/current sequences -> intent logits | context lengths/separator; paired input tests | current-only GRU |
| 5 | No-context masking | `src/banking_tasci/models/tasci_intent.py` | context flag/mask -> safe representation | mask semantics; no-context leakage tests | context GRU |
| 6 | Transformer aspect encoder | `src/banking_tasci/models/tasci_aspect.py` | tokenized aspect text -> aspect vector | local checkpoint/max length; offline smoke tests | approved BERT environment |
| 7 | Intent projection | `src/banking_tasci/models/tasci_fusion.py` | intent hidden -> fusion vector | projection dimension; shape tests | intent model |
| 8 | Aspect-intent fusion | `src/banking_tasci/models/tasci_fusion.py` | aspect + intent vectors -> fused vector | fusion type/dimensions; ablation tests | steps 2-7 |
| 9 | Sentiment classifier | `src/banking_tasci/models/tasci_sentiment.py` | fused vector -> sentiment logits | class map/loss; forward/reload tests | fusion |
| 10 | No-intent ablation | `src/banking_tasci/evaluation/ablation.py` | matched predictions -> paired metrics | ablation config; paired split tests | sentiment model |
| 11 | Gold-intent experiment | `scripts/run_tasci_ablation.py` | gold intent + aspect -> sentiment result | experiment flag; leakage tests | labels and sentiment |
| 12 | Gold-aspect path | `src/banking_tasci/inference/pipeline.py` | gold spans -> sentiment result | aspect source flag; integration tests | sentiment model |
| 13 | Predicted-aspect inference | `src/banking_tasci/inference/pipeline.py` | raw text -> spans/intent/sentiment | structured output; end-to-end tests | all trained components |
| 14 | End-to-end pipeline | `src/banking_tasci/inference/pipeline.py` | records -> structured TASCI output | batch/error policy; integration tests | step 13 |
| 15 | Unified save/reload | `src/banking_tasci/training/reproducibility.py` | models/config/maps -> identical outputs | artifact schema; reload tests | complete model |
| 16 | Full checkpoint resume | `src/banking_tasci/training/loop.py` | structured state -> continuation | optimizer/RNG/epoch state; interruption tests | complete trainer |
| 17 | Regional/context reports | `src/banking_tasci/evaluation/regional.py` | predictions + metadata -> subgroup metrics | minimum support; report tests | end-to-end outputs |

All classification heads must use explicit label maps, raw logits with
cross-entropy loss, and masks that exclude padding. Test data is evaluated only
after validation-based selection. No component should be marked complete from
configuration presence alone.