# Pilot Annotation Input Provenance Audit

**Audit date:** 2026-09-25  
**Method:** read-only SHA-256, JSONL count, and canonical-content comparison

## Finding

`data/annotations/pilot_unannotated.jsonl` is not a pristine unannotated input.
It contains 600 records with `annotation_status: "completed"`, 426 non-empty
aspect lists, and 150 null intent values. Its bytes are identical to
`pilot_annotator_a.jsonl`. Its canonical content hash, after removing
annotator-only metadata, is also identical to `pilot_annotator_b.jsonl`.

The file name is therefore stale or the file was overwritten during the prior
annotation workflow. No file was restored, renamed, or modified by this audit.
The authoritative original gold file remains
`data/annotations/pilot_adjudicated.jsonl`.

## Evidence

| File | Bytes | SHA-256 | Records | Completed | Non-empty aspects | Null intent |
|---|---:|---|---:|---:|---:|---:|
| `pilot_unannotated.jsonl` | 415055 | `00c75e...08608f` | 600 | 600 | 426 | 150 |
| `pilot_annotator_a.jsonl` | 415055 | `00c75e...08608f` | 600 | 600 | 426 | 150 |
| `pilot_annotator_b.jsonl` | 415055 | `0f820a...d5440f` | 600 | 600 | 426 | 150 |
| `pilot_adjudicated.jsonl` | 444259 | `4707b5...83594b` | 600 | 600 | 426 | 0 |

The complete hashes and canonical hashes are recorded in
`outputs/pilot_annotation_input_provenance_audit.json`.

## Interpretation

The three non-adjudicated files share the canonical label content hash
`c02aff53...c00e8c`; only their raw bytes differ where annotator metadata differs.
This means the two annotator files do not provide independent label-content
evidence for the international pilot. The adjudicated file has a different
canonical hash because it contains the adjudicated label corrections.

The audit is descriptive only. It does not restore the pilot input or change
any annotation artifact.