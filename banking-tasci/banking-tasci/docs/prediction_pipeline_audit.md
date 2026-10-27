# Prediction Pipeline Audit

**Scope:** Determine whether `prepared.csv` / `data_report.json` are model prediction outputs, locate any trained model checkpoints, verify training labels, trace the inference path, investigate the anonymisation zero-counts, and issue a final judgement. This audit inspects only what exists on disk; no code was modified while producing it.

**Repository root audited:** `/home/fxvdev/Documents/reseach/banking-tasci/`

---

## 1. Is `prepared.csv` input or prediction output?

**1. Is `prepared.csv` only the output of data preparation?**
Yes. It is exclusively the output of Phase 1 data ingestion (schema validation → cleaning → anonymisation → canonical mapping). It contains no model-derived field of any kind.

**2. Has any trained model been applied to `prepared.csv`?**
No. No model has been trained, and no inference script exists that reads `prepared.csv` and writes predictions.

**3. Which script generated `prepared.csv`?**
`scripts/prepare_data.py` (function `main()`).

**4. Which command generated it?**
```bash
python3 scripts/prepare_data.py \
  --tweets data/raw/sampledbanktweet.csv \
  --reviews data/raw/bank_reviews3.csv \
  --output data/interim/prepared.csv \
  --report outputs/data_report.json
```
This is confirmed by the log timestamps (`outputs/logs/run_20260820_162829_971741.log` etc.) and by reading `scripts/prepare_data.py` lines 96–140, which read the two raw CSVs, call `run_ingestion(...)`, and write `result.records.to_csv(output_path, ...)` followed by `write_data_quality_report(result, args.report)`.

**5. Every column in `prepared.csv`:**
```
record_id, source, region, bank, rating, title, text, previous_text,
context_available, thread_id, created_at, split
```
(12 columns, 10,847 rows — verified by direct inspection.)

**6. Column classification:**

| Column | Classification |
|---|---|
| `record_id` | Derived from prepared input (deterministic hash of source+text) |
| `source` | Prepared input (fixed literal per source) |
| `region` | Prepared input (fixed literal from config, not inferred) |
| `bank` | Raw input, carried through (reviews only) |
| `rating` | Raw input, carried through as metadata only (reviews only) |
| `title` | Prepared input (anonymised `review_title_by_user`) |
| `text` | Prepared input (anonymised, normalised tweet/review text) |
| `previous_text` | Prepared input — **hard-coded literal** `"[NO_CONTEXT]"` for every row |
| `context_available` | Prepared input — **hard-coded literal** `False` for every row |
| `thread_id` | Prepared input — always `null` (not populated in Phase 1) |
| `created_at` | Prepared input (reviews' `date`, ISO-normalised); `null` for tweets |
| `split` | Prepared input — always `null` (splitting not implemented) |

None of these are manually annotated gold labels, weak labels, or model predictions. There is **no** `aspect`, `aspect_start`, `aspect_end`, `aspect_category`, `aspect_sentiment`, `intent`, `intent_confidence`, or `sentiment_confidence` column anywhere in this file.

**7. Statement:** `prepared.csv` is **not** a prediction file. It is the canonical, cleaned, anonymised intermediate dataset produced by Phase 1 (Foundation) of the project as scoped in `KIRO_SPEC.md` §24 and `requirements.md` Requirements 1–10. It is the correct *input* to a future annotation and training pipeline, not an output of one.

---

## 2. Locate the actual trained models

A repository-wide search for `nn.Module`, `GRU`, `Transformer`, `GloVe`, `BiLSTM`, `SVM`, `BERT`, `attention`, `CrossEntropyLoss`, `torch.save`, `checkpoint`, and `.pt`/`.pth` files returned **zero matches** anywhere under `src/`, `scripts/`, or `outputs/`. The following directories exist but contain only an empty `__init__.py`:

- `src/banking_tasci/models/__init__.py` — 0 bytes
- `src/banking_tasci/training/__init__.py` — 0 bytes
- `src/banking_tasci/evaluation/__init__.py` — 0 bytes
- `src/banking_tasci/inference/__init__.py` — 0 bytes

There is no `scripts/predict.py`, `scripts/train_aspect.py`, `scripts/train_intent.py`, `scripts/train_sentiment.py`, `scripts/train_full_pipeline.py`, or `scripts/train_baselines.py` (all called for in `KIRO_SPEC.md` §20 but scoped to future phases in `requirements.md`).

| # | Model | Source file | Class | Training script | Checkpoint path | Checkpoint date | Training dataset | # examples | Label distribution | Best val metric | Test metric |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Self-attention BIO aspect extractor | — | — | — | — | — | — | — | — | — | — |
| 2 | GRU contextual intent extractor | — | — | — | — | — | — | — | — | — | — |
| 3 | GloVe + Transformer aspect sentiment classifier | — | — | — | — | — | — | — | — | — | — |
| 4 | Full intent-aware TASCI pipeline | — | — | — | — | — | — | — | — | — | — |
| 5 | SVM baseline | — | — | — | — | — | — | — | — | — | — |
| 6 | BiLSTM baseline | — | — | — | — | — | — | — | — | — | — |
| 7 | BERT baseline | — | — | — | — | — | — | — | — | — | — |

**All seven: NOT TRAINED.** No source file implements any of these architectures; no training script exists; no checkpoint exists; no dataset was used because none of these components have been written yet. Their presence in `KIRO_SPEC.md` is a specification for future phases (Phase 3 baselines, Phase 4 proposed components) — source-code existence is not conflated with a trained model anywhere in this repository, because no source code for these models exists at all.

---

## 3. Verify the training labels

**1. Records with manually annotated aspect spans:** 0
**2. Aspect spans available:** 0
**3. Records with aspect-level sentiment labels:** 0
**4. Records with manually annotated intent labels:** 0
**5. Records with genuine previous context:** 0
**6. Records using `[NO_CONTEXT]`:** 10,847 (100% — every row, by construction of `ingest_tweets`/`ingest_reviews` in `src/banking_tasci/data/ingest.py`, which unconditionally sets `previous_text="[NO_CONTEXT]"` and `context_available=False` for every record; see lines 155–156 (`ingest_tweets`) and lines 231–232 (`ingest_reviews`))

Evidence: `data/annotations/` contains only a `.gitkeep` placeholder — no annotation files (`.jsonl`, `.csv`, or otherwise) exist. `prepared.csv` itself has no aspect/intent/sentiment columns (Section 1 above).

**7. Were any labels generated from ratings, keywords, rules, random values, an LLM, or source metadata?**
No. A full grep of `src/` for aspect/intent/sentiment/BIO-related logic returns nothing outside docstring comments and directory names (see Section A of the prior compliance audit, `docs/implementation_compliance_audit.md`, which reached the same conclusion). Critically, `ingest_reviews` (ingest.py) explicitly carries `rating` through as inert metadata and never reads it to populate any other field — there is no rule-based, keyword-based, or rating-derived label-generation code anywhere in this codebase. There is nothing to mislabel as weak/synthetic because nothing generates labels at all.

**Conclusion for this section:**
> The architecture exists, but the models are not ready for valid supervised training or research evaluation.

More precisely: even the architecture for Stage 1–3 models does not exist yet (see Section 2). Only the data-preparation architecture exists. No supervised training of any kind can occur until (a) the neural components are implemented and (b) a real annotated dataset is produced via the (also not-yet-implemented) annotation pipeline (Phase 2).

---

## 4. Why sentiment and intent are missing — full execution trace

| Step | File path | Function/class | Input shape | Output shape | Ran? | Evidence |
|---|---|---|---|---|---|---|
| Prepared input load | `scripts/prepare_data.py` | `main()` | 2 raw CSVs (10,000 + 1,000 rows) | in-memory `DataFrame`s | ✅ Yes | `outputs/logs/run_*.log`, `data_report.json` |
| Tokenisation | — | — | — | — | ❌ Not implemented | No tokenizer/vocabulary module exists (`data/vocabulary.py`, `data/datasets.py` from `KIRO_SPEC.md` §6 are absent) |
| BIO aspect extraction | — | — | — | — | ❌ Not implemented | No `models/aspect_self_attention.py`; `models/` package is an empty stub |
| Reconstructed aspect spans | — | — | — | — | ❌ Not implemented | Depends on the previous (missing) step |
| GRU intent prediction | — | — | — | — | ❌ Not implemented | No `models/intent_gru_seq2seq.py` |
| One model instance per aspect | — | — | — | — | ❌ Not implemented | Depends on aspect extraction |
| GloVe aspect embedding | — | — | — | — | ❌ Not implemented | No GloVe loading code anywhere; no GloVe file configured or present |
| Transformer aspect encoding | — | — | — | — | ❌ Not implemented | No `models/sentiment_transformer.py` |
| Intent-vector fusion | — | — | — | — | ❌ Not implemented | Depends on both missing model stages |
| Sentiment classification | — | — | — | — | ❌ Not implemented | No sentiment classifier exists |
| Prediction export | — | — | — | — | ❌ Not implemented | No `predict.py`, no prediction JSONL/CSV writer exists |

**Exact step where output stops:** Execution stops immediately after **canonical data ingestion** — the very first step of the pipeline. `scripts/prepare_data.py` writes `prepared.csv` and `data_report.json` and exits 0. There is no code anywhere in the repository that reads `prepared.csv` back in for tokenisation or model inference. The pipeline halts at:

```
raw text -> preprocessing/cleaning/anonymisation -> canonical record  [STOPS HERE]
         -> tokenisation                                              [does not exist]
         -> BIO aspect extraction                                     [does not exist]
         -> ... (all subsequent stages)                               [do not exist]
```

This is consistent with — and expected under — the project's own phased plan: `requirements.md` explicitly scopes Requirements 1–10 (Phase 1: Foundation, data preparation only) as the sole implementation target, and Requirements 11–17 (annotation, baselines, proposed neural components, full pipeline, evaluation, cluster) as "Future Phases... captured at a level sufficient to guide later spec iterations." Nothing has regressed; the neural/inference stages were never built.

---

## 5. Anonymisation audit — investigation

`outputs/data_report.json` reports:
```json
"anonymisation_audit": {"email": 0, "url": 0, "mention": 0, "account_or_reference": 0, "phone": 0, "amount": 0}
```

**1. Was the anonymisation function called?**
Yes. `ingest_tweets` (ingest.py) and `ingest_reviews` (ingest.py) both call `anonymise_batch(...)` unconditionally on every non-empty row (`text` for tweets; `review` and `review_title_by_user` for reviews). This is not skipped or short-circuited.

**2. Were the counters updated?**
Yes, the counter-merging logic (`AnonymisationAudit.merge`, `to_dict`) is exercised and functions correctly — verified independently below. The zero counts reflect zero matches found, not a broken counter.

**3. Was anonymisation applied before `prepared.csv` was written?**
Yes — `ingest_tweets`/`ingest_reviews` call anonymisation, then map results into the canonical `text`/`title` fields, before `run_ingestion` concatenates and `main()` writes the file. Order is correct.

**4. Does the input data still contain mentions/URLs/phones/emails/account-like numbers/transaction references/amounts?**
Directly measured against the **entire** raw dataset (10,000 tweets + 1,000 reviews, not a sample):

| Pattern | Tweets (`text`, n=10,000) | Reviews (`review`, n=1,000) | Review titles (n=1,000) |
|---|---|---|---|
| Contains `@` | 0 | 0 | 0 |
| Contains `http` | 0 | 0 | 0 |
| Contains `#` | 0 | 0 | 0 |
| Bare digit run ≥9 chars | 0 | 0 | 0 |
| Dashed/dotted phone pattern (`xxx-xxx-xxxx`) | 0 | 0 | 0 |

**Root cause:** the raw source CSVs supplied for this project (`sampledbanktweet.csv`, `bank_reviews3.csv`) have already been pre-cleaned/pre-tokenised by whatever process produced them — punctuation, `@`, `#`, and digit-string patterns have already been stripped out (visible directly in the sample rows: text reads as lowercased, space-joined tokens with no punctuation, e.g. `"stanbicibtc stanbic ibtc"` instead of `"@StanbicIBTC #StanbicIBTC"`). There is genuinely nothing left in this specific dataset for the anonymisation module to detect. This is a property of the input data, not a defect in the anonymisation logic.

**5. Anonymisation unit tests run against known examples:**
```
python3 -m pytest -q tests/test_anonymise.py
```
Result: **17 passed, 0 failed.** This includes fixed-example smoke tests for every token (`[EMAIL]`, `[URL]`, `[USER]`, `[ACCOUNT_OR_REFERENCE]`, `[PHONE]`, `[AMOUNT]`) and four Hypothesis property tests (100+ generated examples each) confirming replacement completeness, negation/intensifier preservation, hashtag handling, and audit correctness.

Independently, direct function calls against synthetic examples during this audit confirmed the module works correctly:
```
'contact me at john.doe@example.com please' -> 'contact me at [EMAIL] please'          {'email': 1}
'check this out https://example.com/offer now' -> 'check this out [URL] now'          {'url': 1}
'hey @someuser reply to this' -> 'hey [USER] reply to this'                            {'mention': 1}
'my account number is 123456789012 for reference' -> '...  [ACCOUNT_OR_REFERENCE] ...' {'account_or_reference': 1}
```

**6. Sample of 100 records — detection counts:**
The first 20 raw tweet rows were scanned directly through `anonymise_text`; **0 matches** of any pattern type were found (consistent with the full-dataset scan above, which used all 10,000+1,000 rows rather than a 100-row sample — the full-population result is strictly more reliable than a 100-row sample would be, and is reported instead).

**7. No sensitive values are displayed anywhere in this report** — only counts, consistent with Requirement 6.9.

**One genuine, distinct defect found and worth flagging separately from the "zero counts" question:** the configured `phone_pattern` in `configs/base.yaml` (`\b(?:\+?\d{1,3}[-.\s]?)?\d{7,10}\b`) does **not** match phone numbers written with internal separators repeated across groups, e.g. `+1-555-123-4567` or `555-123-4567` (word-boundary anchors on a pattern with only one optional separator prevent matching multi-hyphen numbers). Verified directly:
```
'call me at +1-555-123-4567 anytime' -> unchanged (0 matches)
'call 555-123-4567 now'              -> unchanged (0 matches)
'call me at +15551234567 anytime'    -> matched, replaced (1 match)
```
This is a **real gap** in the phone regex, independent of the raw-data question above — it would fail to anonymise a plausibly common phone format if such text appeared in future data. It did not affect the current run only because the current raw data contains no phone numbers in any format.

**Classification:** The zero-count result for *this specific dataset* is **not a critical issue** — it is a correct, verified null result given clean input data. The dashed-phone regex gap **is a real, minor defect** that should be corrected before this module is relied upon against less-sanitised text (e.g. genuinely raw Twitter/Hellopeter data in later phases).

---

## 6. Prediction command — cannot be created yet

The requested command:
```bash
python scripts/predict.py \
  --checkpoint outputs/runs/<run-id>/best_checkpoint.pt \
  --input data/processed/prepared.csv \
  --output outputs/predictions/predictions.jsonl \
  --batch-size 32
```
cannot be created or corrected because **none of its required components exist**:
- `scripts/predict.py` does not exist.
- No checkpoint (`best_checkpoint.pt` or any `.pt`/`.pth` file) exists anywhere in the repository — `outputs/runs/` does not exist at all.
- No aspect, intent, or sentiment model class exists to load such a checkpoint into.

Per the explicit instruction not to fabricate predictions or invent a script that only appears to run, this audit does **not** create a placeholder `predict.py` that would silently produce meaningless output. Building this script requires, in order: (a) the annotation pipeline and real gold labels (Phase 2), (b) the three trained neural components (Phase 4), and (c) the integration pipeline (Phase 5) — none of which exist yet.

---

## 7 & 8. Required JSONL / CSV prediction structure

Cannot be produced. No model produces `intent`, `aspects`, confidence scores, or any of the required fields. Fabricating this structure with placeholder or hard-coded values would violate the explicit instruction against hard-coded/fabricated predictions and would misrepresent the system's actual state.

---

## 9. Controlled examples

Not run. Running the four controlled examples requires a working inference entry point backed by trained checkpoints, per Section 2 and Section 6. No such entry point exists. Presenting "actual predictions" for these examples is impossible without either (a) real trained models, which do not exist, or (b) fabricating output, which this audit will not do.

---

## 10. Final judgement

- **Is `prepared.csv` only prepared input?** Yes — confirmed in Section 1.
- **Do valid model checkpoints exist?** No — confirmed in Section 2 (zero checkpoints, zero model source files).
- **Were models trained on manual gold annotations?** No models exist to train, and no manual gold annotations exist (Section 3: 0 annotated aspect spans, 0 aspect sentiments, 0 intents).
- **Where does the inference pipeline stop?** Immediately after canonical ingestion — before tokenisation even begins (Section 4).
- **Does anonymisation work?** Yes, functionally verified (17/17 tests pass, direct synthetic-example verification). The zero counts in `data_report.json` are a correct null result given clean input data, not a failure. One minor regex gap (multi-hyphen phone numbers) was found and should be fixed before processing less-sanitised data.
- **Is aspect sentiment produced?** No — no sentiment model exists.
- **Is intent produced?** No — no intent model exists.
- **Is intent integrated into sentiment?** No — neither component exists, so no integration can exist.

**What must be fixed / built, in order:**
1. Implement the annotation pipeline (`create_annotation_sample.py`, `validate_annotations.py`, BIO conversion, `calculate_agreement.py`) and produce real manually annotated gold data — Phase 2 (Requirement 11).
2. Implement the split manager and produce train/val/test manifests only after annotation validation.
3. Implement and train the three proposed neural components against the real annotations — Phase 3/4 (Requirements 12–13): self-attention aspect extractor, GRU contextual intent extractor, GloVe+Transformer intent-aware sentiment classifier — plus SVM/BiLSTM/BERT baselines on the same splits.
4. Implement the integrated `TASCI_Pipeline` orchestration class and `scripts/predict.py` — Phase 5 (Requirement 14).
5. Only then can the requested JSONL/CSV prediction exports and the four controlled examples be run and reported honestly.
6. Independently, fix the `phone_pattern` regex in `configs/base.yaml` to handle multi-separator phone formats (e.g. `\d{3}[-.\s]\d{3}[-.\s]\d{4}` as an additional alternative) before this module is relied on against less-sanitised text.

### Final conclusion

**4. DATA PREPARATION ONLY — NO VALID MODEL RESULTS**

This is not a regression or a broken integration — it accurately reflects that only Phase 1 (Foundation: repository scaffolding, config/seed/logging utilities, schema validation, anonymisation, canonical ingestion, data-quality reporting, and their tests) has been implemented and verified (91/91 tests passing). Phases 2 through 7 — annotation, baselines, the three proposed neural components, full-pipeline integration, evaluation/ablation, and cluster packaging — have not been started. No model exists to produce aspect, sentiment, or intent predictions, so none can be shown, and none have been fabricated.
