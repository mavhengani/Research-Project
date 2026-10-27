# Data Dictionary

This document is the authoritative field-by-field reference for the two core
data schemas in the banking-tasci pipeline:

1. **Canonical_Record** — the Phase 1 ingestion output, one row per cleaned
   source record, written to `data/interim/prepared.csv`.
2. **Annotation_Record** — the Phase 2 JSONL annotation format (one JSON
   object per line), including its nested **Aspect_Span** objects.

It also briefly documents the **adjudicated record** extension and the
leakage-safe **split manifests** that reference these records.

Definitions here mirror the code exactly:

- Canonical_Record: `src/banking_tasci/data/ingest.py` (`CANONICAL_COLUMNS`,
  `ingest_tweets`, `ingest_reviews`).
- Annotation_Record / Aspect_Span: `src/banking_tasci/data/annotations.py`
  (`AnnotationRecord`, `AspectSpan`, `ASPECT_CATEGORIES`, `ASPECT_SENTIMENTS`,
  `INTENT_LABELS`, and the `validate_*` rules).
- Adjudication extension: `scripts/adjudicate_annotations.py`.
- Split manifests: `scripts/create_splits.py`.

---

## 1. Canonical_Record (Phase 1)

A Canonical_Record is a single normalised, de-duplicated, anonymised record
produced by the Ingestion_Pipeline from either the tweets source
(`sampledbanktweet.csv`) or the reviews source (`bank_reviews3.csv`). Every
Canonical_Record populates **all thirteen** `CANONICAL_COLUMNS` fields, in the
order below, regardless of source. The combined output is written to
`data/interim/prepared.csv`.

Two source-specific mapping rules apply:

- **Tweets:** `text` comes from the tweet body; `title` is `""`; `bank`,
  `rating`, `created_at`, `created_at_raw`, and `thread_id` are `null`.
- **Reviews:** `review` maps to `text`, `review_title_by_user` maps to
  `title`; `bank`, `rating`, and `created_at` (a strict ISO-8601-or-null value
  derived from the review `date`) are carried through as metadata.

| # | Field | Type | Nullable | Derivation / population | Allowed / example values | Notes |
|---|-------|------|----------|-------------------------|--------------------------|-------|
| 1 | `record_id` | string | No | `sha256(f"{source}:{normalised_text}")` hex digest, truncated to the first 16 characters (`make_record_id`). Computed from the **normalised** text, before anonymisation. | `"3a7f8b9476b7b2c4"` | Deterministic and stable: the same source + normalised text always yields the same id. Used as the join key by all downstream tooling and split manifests. |
| 2 | `source` | string | No | The configured source name for the sub-pipeline (`cfg.data.tweets_source_name` / `cfg.data.reviews_source_name`). | `"sampledbanktweet"`, `"bank_reviews"` | Also participates in the `record_id` hash, so identical text from two sources gets distinct ids. |
| 3 | `region` | string | No | The configured default region (`cfg.data.default_region`). | e.g. `"ZA"` | Carried as metadata; no per-record region inference in Phase 1. |
| 4 | `bank` | string | Yes | Reviews: from the source `bank` column (`null` when absent). Tweets: always `null`. | `"ExampleBank"`, `null` | Metadata only. |
| 5 | `rating` | number | Yes | Reviews: carried through unchanged from the source `rating` column. Tweets: always `null`. | e.g. `1`–`5`, `null` | **Metadata only. NEVER used to derive sentiment or any other field** (Req 7.5). Annotators/validators must not infer aspect `sentiment` from `rating`. |
| 6 | `title` | string | No | Reviews: normalised + anonymised `review_title_by_user` (empty string when absent). Tweets: always `""`. | `"Terrible service"`, `""` | Never `null`; absent titles become `""`. |
| 7 | `text` | string | No | Normalised then anonymised main content: tweet body, or review `review`. Normalisation happens before hashing; anonymisation happens after. | `"the app keeps crashing after the update"` | The anonymised value is what is stored; the pre-anonymisation normalised value is what fed `record_id`. |
| 8 | `previous_text` | string | No | Fixed sentinel at the Phase-1 ingestion layer. | `"[NO_CONTEXT]"` | **Always `"[NO_CONTEXT]"` at ingestion** (Req 7.4). Real preceding-sentence/thread context is only constructed later by the Context_Builder when building annotation records. |
| 9 | `context_available` | boolean | No | Fixed at the Phase-1 ingestion layer. | `false` | **Always `false` at ingestion** (Req 7.4). Set to `true` later only for sentence-level records that genuinely have a preceding sentence. |
| 10 | `thread_id` | string | Yes | Always `null` in Phase 1 (no thread metadata in the current sources). | `null` | Reserved for a future data source carrying reply-to relationships. |
| 11 | `created_at` | string (ISO 8601 date) or `null` | Yes | Reviews: a **strict** value — a valid parseable `date` becomes an ISO-8601 date string; a missing/empty or **unparseable** value becomes `null` (never an arbitrary raw string). Tweets: always `null`. | `"2026-08-20"`, `null` | Metadata only. Contract (Part 5): `created_at` is ALWAYS either a valid ISO date or `null`. |
| 12 | `created_at_raw` | string or `null` | Yes | Provenance field. When a review's source `date` was present but **could not be parsed**, the original raw string is preserved here (with `created_at = null`). When the date parsed cleanly, or was missing/empty, this is `null`. Tweets: always `null`. | `"Q1 2020"`, `null` | Preserves raw provenance for unparseable dates without polluting the typed `created_at`. |
| 13 | `split` | string | Yes | **Not populated by ingestion.** Left `null`; assigned later by the Split_Manager. | `null`, later `"train"` / `"validation"` / `"test"` | In practice the current Split_Manager emits separate `*_manifest.csv` files keyed by `record_id` rather than writing back into this column (see §4). |

### Canonical_Record example

A review-sourced record as written to `data/interim/prepared.csv`
(shown here as JSON for clarity; the file itself is CSV with these columns):

```json
{
  "record_id": "3a7f8b9476b7b2c4",
  "source": "bank_reviews",
  "region": "ZA",
  "bank": "ExampleBank",
  "rating": 2,
  "title": "Slow and frustrating",
  "text": "The mobile app keeps crashing after the latest update and support never called me back.",
  "previous_text": "[NO_CONTEXT]",
  "context_available": false,
  "thread_id": null,
  "created_at": "2026-08-20",
  "created_at_raw": null,
  "split": null
}
```

### Schema migration note (Phase 3A, Part 5)

`created_at` was previously "best effort": a parseable date became an ISO
string, but an **unparseable** value was carried through as its original raw
string, producing an inconsistent column (a mix of ISO strings, arbitrary raw
strings, and `null`). Phase 3A tightens this to a single contract:

- `created_at` is now **strictly ISO-8601-or-`null`**;
- a new column, `created_at_raw`, preserves the original raw string **only**
  when the source `date` was present but unparseable.

**Migration impact:** `CANONICAL_COLUMNS` grew from 12 to 13 columns
(`created_at_raw` inserted immediately after `created_at`). Any consumer that
hard-codes a 12-column layout must be updated to the 13-column layout.
**`record_id` is unaffected** — it is `sha256(source + normalised_text)` and
has never depended on the date field, so re-preparing the data yields identical
ids. To migrate an existing `prepared.csv`, re-run
`python scripts/prepare_data.py ...`; no id remapping is required.

---

## 2. Annotation_Record (Phase 2)

An Annotation_Record is one JSON object per line in a JSONL file (e.g.
`data/annotations/pilot_unannotated.jsonl`, or a per-annotator
`data/annotations/pilot_{annotator_id}.jsonl`). Every tool in Phase 2
(Annotation_Sampler, Annotation_Interface, Annotation_Validator,
Agreement_Calculator, Adjudication_Tool, Split_Manager) reads and writes this
single schema. The Annotation_Validator reports violations but never mutates or
auto-corrects a record.

### Top-level fields

| Field | Type | Nullable | Allowed values / semantics |
|-------|------|----------|----------------------------|
| `record_id` | string | No | The originating Canonical_Record's `record_id`. Join key across annotators, agreement, adjudication, and splits. |
| `source` | string | No | Carried over from the Canonical_Record (`"sampledbanktweet"`, `"bank_reviews"`). |
| `region` | string | No | Carried over from the Canonical_Record. |
| `text` | string | No | The (already anonymised) text unit being annotated. For multi-sentence reviews this is a single sentence. All Aspect_Span offsets are relative to this string. |
| `previous_text` | string | No | The immediately preceding sentence within the SAME review, the thread parent for a genuine reply, or `"[NO_CONTEXT]"`. Must be consistent with `context_available` (see rule below). |
| `context_available` | boolean | No | `true` only when `previous_text` is real context; `false` requires `previous_text == "[NO_CONTEXT]"`. |
| `aspects` | array of Aspect_Span | No | May be empty (`[]`) when the text mentions no annotatable aspect. Spans must not overlap and must not be exact duplicates. |
| `intent` | string \| null | Yes | One of the seven `INTENT_LABELS` (below), or `null` when not yet assigned. Must be non-null when `annotation_status == "completed"`. |
| `intent_ambiguous` | boolean | No | `true` when the annotator judged intent to be genuinely ambiguous between two labels. Preserved through validation, never auto-resolved. |
| `alternative_intent` | string \| null | Yes | The second candidate intent label; set (non-null, one of `INTENT_LABELS`) when `intent_ambiguous == true`, otherwise `null`. |
| `annotator_id` | string | No | Identifier of the annotator. `""` for unannotated sample records. Kept distinct per annotator so two annotators' files never overwrite each other. |
| `annotation_status` | string | No | Workflow state (see allowed values below). |
| `notes` | string | No | Free-text annotator notes (e.g. explaining a flagged contradiction). `""` when none. |

#### `annotation_status` values used in the pipeline

- `"not_started"` — the default for freshly sampled, unannotated records
  (emitted by the Annotation_Sampler). Bypasses the completed-intent check.
- `"completed"` — annotation is finished. The Annotation_Validator **rejects**
  a `completed` record whose `intent` is `null` or `""` (Req 15.5 / 19.11).
- `"needs_adjudication"` — the adjudication-flag value referenced in the
  annotation guidelines. Set by an annotator when the same aspect term receives
  irreconcilable contradictory sentiment within one record and cannot be
  resolved. Rather than inventing a sentiment or using a `mixed` label, the
  annotator flags the record here (and explains in `notes`) so the
  Adjudication_Tool can resolve it later.

(`in_progress` may be used transiently by the interface, but the three values
above are the ones that carry pipeline meaning.)

### Aspect_Span sub-fields

Each object in `aspects` describes one annotated aspect term inside `text`.

| Field | Type | Nullable | Allowed values / semantics |
|-------|------|----------|----------------------------|
| `term` | string | No | The exact surface substring of the aspect. Must equal `text[start:end]`, case-sensitive. |
| `start` | integer | No | Character offset, **inclusive**. Must satisfy `0 <= start < end`. |
| `end` | integer | No | Character offset, **exclusive**. Must satisfy `start < end <= len(text)`. |
| `category` | string | No | One of the nine `ASPECT_CATEGORIES` (below). |
| `sentiment` | string | No | One of `positive` / `negative` / `neutral` — **no `mixed`**. |

#### Offset semantics

- `start` is inclusive, `end` is exclusive (Python slice semantics).
- The invariant `text[start:end] == term` must hold **exactly**, including
  case. The validator reports `offset_mismatch` when it does not.
- Offsets must be in-bounds and ordered: `start >= 0`, `end <= len(text)`,
  `start < end`. Out-of-bounds, negative, non-integer, or `start >= end`
  offsets are reported as `invalid_offset`.
- Two spans may not **overlap** (`start_i < end_j and start_j < end_i` →
  `overlapping_spans`), and two spans may not share identical `start`/`end`
  (→ `duplicate_span`).

#### Aspect `category` — the nine allowed values

```
customer_support   digital_banking   transactions
cards              accounts          fees
fraud_security     branch_service    general_service
```

#### Aspect `sentiment` — the three allowed values

```
positive   negative   neutral
```

There is no `mixed` sentiment. Differing opinions about different aspects are
represented as separate Aspect_Spans, each with its own independent
`sentiment`. Aspect `sentiment` is **never** derived from the source record's
`rating`.

#### `intent` — the seven allowed labels

```
complaint              compliment    request_for_assistance
suggestion             warning       churn_signal
general_feedback
```

#### The `intent_ambiguous` + `alternative_intent` mechanism

When an annotator is genuinely torn between two intent labels, they set the
primary judgment in `intent`, set `intent_ambiguous = true`, and record the
second candidate in `alternative_intent` (a non-null `INTENT_LABELS` value).
The Annotation_Validator preserves this ambiguity through validation — it does
**not** collapse the record into a single unambiguous label or discard
`alternative_intent`. When `intent_ambiguous` is `false`, `alternative_intent`
should be `null`.

### The extra `source_record_id` leakage-grouping field

Sentence-level records produced from a multi-sentence review carry an
additional `source_record_id` field pointing at the originating review's
`record_id`. This is not part of the core `AnnotationRecord` schema
(`annotations.write_jsonl` emits only the standard fields), but the
Context_Builder attaches it and downstream leakage grouping relies on it: the
Split_Manager groups by `source_record_id` (falling back to a record's own
`record_id` when absent) so that all sentences originating from the same review
are assigned to the same split and never leak across train/validation/test.

### Annotation_Record example

A completed sentence-level review annotation with two aspects and an ambiguous
intent:

```json
{
  "record_id": "3a7f8b9476b7b2c4",
  "source": "bank_reviews",
  "region": "ZA",
  "text": "The mobile app keeps crashing and support never called me back.",
  "previous_text": "I have been a customer for ten years.",
  "context_available": true,
  "aspects": [
    {
      "term": "mobile app",
      "start": 4,
      "end": 14,
      "category": "digital_banking",
      "sentiment": "negative"
    },
    {
      "term": "support",
      "start": 34,
      "end": 41,
      "category": "customer_support",
      "sentiment": "negative"
    }
  ],
  "intent": "complaint",
  "intent_ambiguous": true,
  "alternative_intent": "churn_signal",
  "annotator_id": "annotator_a",
  "annotation_status": "completed",
  "notes": "Torn between complaint and churn_signal given the tone.",
  "source_record_id": "3a7f8b9476b7b2c4"
}
```

A freshly sampled, unannotated record looks like this instead: `aspects` is
`[]`, `intent` and `alternative_intent` are `null`, `intent_ambiguous` is
`false`, `annotator_id` is `""`, `annotation_status` is `"not_started"`, and
`notes` is `""`.

---

## 3. Adjudicated record extension

The Adjudication_Tool (`scripts/adjudicate_annotations.py`) reads two
annotators' JSONL files and writes a single resolved gold set to
`data/annotations/pilot_adjudicated.jsonl`. Every jointly annotated record
appears in the output:

- **Agreed records** pass through carrying the agreed value, with **no**
  `adjudication` sub-object.
- **Disputed records** carry the adjudicated final value for each disputed
  field, plus an `adjudication` sub-object that preserves both annotators'
  originals — nothing is silently discarded.

The `adjudication` object has one entry per disputed field (e.g. `intent`,
`aspects`), each of the shape:

```json
{
  "adjudication": {
    "intent": {
      "annotator_a_value": "complaint",
      "annotator_b_value": "warning",
      "final_value": "churn_signal",
      "adjudicator_id": "lead",
      "notes": "both missed the churn cue"
    }
  }
}
```

The `adjudication` key is written **alongside** the standard Annotation_Record
fields. `annotations.read_jsonl` ignores unknown keys, so the adjudicated file
remains a valid Annotation_Record JSONL that downstream tooling can consume
directly.

---

## 4. Split manifests

The Split_Manager (`scripts/create_splits.py`) partitions the validated,
adjudicated annotation set into leakage-safe splits and writes three CSV
manifests to its `--output-dir`:

- `train_manifest.csv`
- `validation_manifest.csv`
- `test_manifest.csv`

Each manifest is simply a list of `record_id` values (a `record_id` column)
referencing the adjudicated Annotation_Records — the manifests contain no
annotation payload themselves. Whole leakage groups (keyed by
`source_record_id`, or the record's own `record_id` when absent) are assigned
to a single split so that sentences from the same review, thread, or
duplicate/author group never span multiple splits. A companion
`split_report.json` summarises split sizes and distributions.
