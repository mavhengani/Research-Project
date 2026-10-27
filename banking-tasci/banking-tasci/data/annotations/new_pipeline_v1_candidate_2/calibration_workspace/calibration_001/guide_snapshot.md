# Candidate 2 calibration instructions

Use only `data/annotations/new_pipeline_v1_candidate_2/batches/calibration_001.jsonl` after its checksum is independently verified against the Candidate 2 batch manifest. Do not use the legacy-looking `data/annotations/new_pipeline_v1/batches/` copy: it is not the approved Candidate 2 membership.

The batch remains generated and label-hidden. No annotation may begin until the researcher explicitly opens the calibration workflow.

Before submission, preserve every immutable source field, set an allowed primary intent and Boolean `public_warning`, use `ENTITY#ATTRIBUTE` categories, and validate target and opinion offsets. Store a dated backup outside the batch path before editing. Run:

```sh
.venv/bin/python scripts/validate_new_pipeline_annotations.py \
  --input <submission.jsonl> \
  --source data/annotations/new_pipeline_v1_candidate_2/batches/calibration_001.jsonl \
  --batch-manifest artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json \
  --json-report artifacts/reports/new_pipeline_v1/annotation_validation.json \
  --markdown-report artifacts/reports/new_pipeline_v1/annotation_validation.md \
  --completed-gold
```

Use the decision log template for ambiguous cases. Refine the guide only after documented calibration discussion; freeze it only through the existing explicit calibration-guide gate. Main and final batches remain blocked until that gate passes.
