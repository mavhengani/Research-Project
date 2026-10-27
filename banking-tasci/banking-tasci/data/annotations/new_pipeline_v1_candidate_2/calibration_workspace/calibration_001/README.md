# Candidate 2 calibration workspace

Status: `in_progress` (0/50 completed). Human labels must be supplied by Rotondwa Mavhengani.

Approved source: `data/annotations/new_pipeline_v1_candidate_2/batches/calibration_001.jsonl`  
Approved SHA-256: `7665366000c4b95b6c57fac91a2bd786098f16848001bf59a5c2c5a0b8700e66`

Validate the current working copy without treating it as completed gold:

```sh
.venv/bin/python scripts/validate_new_pipeline_annotations.py \
  --input data/annotations/new_pipeline_v1_candidate_2/calibration_workspace/calibration_001/working_annotations.jsonl \
  --source data/annotations/new_pipeline_v1_candidate_2/batches/calibration_001.jsonl \
  --batch-manifest artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json \
  --json-report artifacts/reports/new_pipeline_v1/calibration/incremental_validation.json \
  --markdown-report artifacts/reports/new_pipeline_v1/calibration/incremental_validation.md
```

Before replacing the working file, verify its observed SHA-256 and create a dated backup in `backups/`. Restore by atomically copying the latest valid backup to `working_annotations.jsonl`, then verify it against `immutable_reference.json`. Never edit the approved source batch.
