# Annotation Workflow (Phase 2)

This is the operational runbook for producing the pilot gold dataset end to end:
from drawing a diversity-preserving sample out of the Phase 1 canonical data,
through independent human annotation, agreement measurement, adjudication, and
finally leakage-safe train/validation/test splits.

Run every command from the project root (`banking-tasci/`). Paths below are the
conventional defaults; adjust them if your layout differs.

## Prerequisites

- Phase 1 has produced `data/interim/prepared.csv` (the canonical, cleaned
  dataset). The sampler reads only this file.
- `docs/annotation_guidelines.md` is the labeling rulebook. Both annotators and
  the adjudicator must work from it — it defines the aspect categories,
  sentiment values, intent labels, span conventions, and the ambiguity rules.
- Python dependencies for the project are installed.
- **`streamlit` is required for step 2 and is not yet installed in this
  environment.** Install it before annotating:

  ```bash
  pip install streamlit
  ```

## A note on human effort

Steps **2 (annotate)** and **5 (adjudicate)** are manual human work. The tooling
is ready and every other step is fully automated, but the gold dataset does not
exist until two humans independently annotate the pilot sample and a lead
resolves their disagreements. Those two steps cannot be run unattended — plan for
annotator and adjudicator time.

---

## Step 1 — Generate the pilot sample

```bash
python scripts/create_annotation_sample.py \
  --input data/interim/prepared.csv \
  --output data/annotations/pilot_unannotated.jsonl \
  --size 600 \
  --seed 42
```

Draws a deterministic, diversity-preserving sample of 600 annotatable units from
`prepared.csv`. Review rows are expanded to one unit per sentence; tweet rows
become one unit each. Sampling is stratified by source and context availability
so the pilot mirrors the overall data composition, and the `--seed` makes the
draw fully reproducible — same input, size, and seed always yield the same
sample.

Outputs:

- `data/annotations/pilot_unannotated.jsonl` — the unannotated
  `Annotation_Record`s (empty aspects, no intent, `annotation_status="not_started"`).
- `outputs/annotation_sample_report.json` — the sample composition report:
  counts by source and region, context-availability counts, a text-length
  distribution summary, a rating distribution where available, the number of
  multi-sentence reviews represented, and the seed used.

No gold label is read or used during sampling — none exists at this stage.

---

## Step 2 — Annotate independently (two annotators)

```bash
streamlit run scripts/annotation_app.py
```

This launches a local Streamlit web app (no network calls, everything runs on
your machine). Requires `streamlit` — see Prerequisites.

Each annotator enters their **own** `annotator_id` in the sidebar (for example
`annotator_a` and `annotator_b`). The `annotator_id` alone determines the output
filename:

- Work saves to a per-annotator file `data/annotations/pilot_{annotator_id}.jsonl`
  — for example `data/annotations/pilot_annotator_a.jsonl` and
  `data/annotations/pilot_annotator_b.jsonl`.
- Because the path is derived solely from the entered id, **neither annotator can
  read or overwrite the other's file.** Two people annotate the same sample
  completely independently.
- On first use for a given id the app loads `pilot_unannotated.jsonl`; on later
  sessions it resumes from that annotator's own file, so progress is preserved.

For each record the annotator does the following, per the rules in
`docs/annotation_guidelines.md`:

1. Select the exact aspect **spans** by character offset (start/end into the
   current text).
2. Assign each span an aspect **category**.
3. Assign each span a per-aspect **sentiment**.
4. Choose the record's **dominant intent**.
5. Set the **ambiguity flag** (and an alternative intent) when the intent is
   genuinely ambiguous.

Marking a record "completed" requires a selected intent; otherwise it is saved
as `in_progress`. This is manual human labeling work — the two annotators must
each work through the full sample before continuing.

---

## Step 3 — Validate each annotator's file

Run the validator once per annotator file:

```bash
python scripts/validate_annotations.py \
  --input data/annotations/pilot_annotator_a.jsonl \
  --output outputs/annotation_validation_report_a.json
```

```bash
python scripts/validate_annotations.py \
  --input data/annotations/pilot_annotator_b.jsonl \
  --output outputs/annotation_validation_report_b.json
```

Each run checks every record against the schema and label rules (offsets in
bounds, no overlapping/duplicate spans, known categories/sentiments/intents,
required fields present, context consistency, completed records carry an intent,
no raw identifiers in text) and writes a JSON report containing:

- `valid_count` / `invalid_count`,
- `errors_by_type` with the affected record IDs per error type,
- label distributions over the valid records (aspect category, sentiment,
  intent),
- total aspect count, zero-aspect count, and ambiguous-intent count.

The validator **never auto-corrects** anything — it only reads and classifies.
A file containing invalid records is still a successful validation *run*; fix the
flagged records in the annotation app and re-validate.

---

## Step 4 — Calculate inter-annotator agreement

```bash
python scripts/calculate_agreement.py \
  --annotator-a data/annotations/pilot_annotator_a.jsonl \
  --annotator-b data/annotations/pilot_annotator_b.jsonl \
  --output outputs/inter_annotator_agreement.json
```

Restricts all metrics to the records both annotators labeled (matched by
`record_id`) and computes:

- **Cohen's Kappa** for intent, aspect category, and aspect sentiment
  (category/sentiment kappa is measured over spans both annotators marked at the
  same offsets).
- **Exact span-agreement rate** — the fraction of joint records where both
  annotators' span sets match exactly.
- **Token-level precision / recall / F1** over aspect spans expanded to
  whitespace tokens (annotator A as reference, B as hypothesis).
- Disagreement counts broken down by type and a ranking of the most-contested
  records.

Outputs:

- `outputs/inter_annotator_agreement.json` — the metrics report.
- `outputs/annotation_disagreements.jsonl` — one entry per disagreeing record
  with both annotators' values preserved verbatim.

This tool only measures; it never resolves anything. Read the kappa scores as a
quality gate: a **low kappa signals the guidelines need refinement before
scaling annotation** to the full dataset. Revise `docs/annotation_guidelines.md`,
re-annotate, and re-measure until agreement is acceptable.

---

## Step 5 — Adjudicate disagreements

```bash
python scripts/adjudicate_annotations.py \
  --annotator-a data/annotations/pilot_annotator_a.jsonl \
  --annotator-b data/annotations/pilot_annotator_b.jsonl \
  --adjudicator-id lead_annotator \
  --output data/annotations/pilot_adjudicated.jsonl
```

Identifies every jointly annotated record with a field-level disagreement and
presents them one at a time to a human adjudicator. For each disputed field the
adjudicator picks annotator A's value, annotator B's value, or (for intent) types
a new final value, and can attach a note. This is interactive human work driven
from the terminal.

The output `data/annotations/pilot_adjudicated.jsonl` is the resolved gold set:
it contains every jointly annotated record. Records the annotators already agreed
on pass through unchanged; disputed records carry the adjudicated value plus an
`adjudication` sub-object that **preserves both annotators' original values**,
the adjudicator id, and the notes. Nothing is discarded.

---

## Step 6 — Validate the adjudicated file

```bash
python scripts/validate_annotations.py \
  --input data/annotations/pilot_adjudicated.jsonl \
  --output outputs/annotation_validation_report_adjudicated.json
```

Run the same validator against the adjudicated gold set. This **must pass**
(no invalid records) before splitting — the split step depends on a clean,
schema-valid gold file.

---

## Step 7 — Create splits

```bash
python scripts/create_splits.py \
  --input data/annotations/pilot_adjudicated.jsonl \
  --output-dir data/processed \
  --train-ratio 0.70 \
  --validation-ratio 0.15 \
  --test-ratio 0.15 \
  --seed 42
```

Partitions the adjudicated gold set into train/validation/test manifests.

- It **refuses to run** (non-zero exit, no manifest written) if any record fails
  validation — hence step 6 must pass first.
- It **groups review sentences to prevent leakage**: all sentences originating
  from the same review (their shared `source_record_id`) are assigned to a single
  split, so no review is spread across train and test. Tweets, which have no
  parent, are grouped by their own `record_id`.
- Assignment is stratified by intent and preserves source/region distributions
  across splits where feasible, and is deterministic given the `--seed`.

Outputs in `data/processed/`:

- `train_manifest.csv`, `validation_manifest.csv`, `test_manifest.csv` — each
  listing the `record_id`s in that split.
- `split_report.json` — split sizes and distributions by source, region, intent,
  sentiment, and context availability.

At this point the pilot gold dataset and its splits exist and are ready for
downstream modeling.
