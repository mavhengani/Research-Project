# Candidate 2 annotation-package review

- Recommendation: **READY_FOR_RESEARCHER_APPROVAL**
- Pipeline version: `new_pipeline_v1`
- Records / unique IDs: 1000 / 1000
- Source distribution: `{'international_review': 250, 'international_tweet': 250, 'south_africa_tweet': 500}`
- Region distribution: `{'international': 500, 'south_africa': 500}`
- Context experiment status: BLOCKED_NO_VERIFIED_CONTEXT_DATA; package remains eligible for no-context annotation
- Context-available records: 0
- Candidate-1 preserved: **True** (17/17 artifact checksums match)

## Checksums

- Sample plan: `ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d`
- Annotation package manifest: `5d3a34dacfe6597757b5926db5fdf952407fa83e8f6a2ab65ef85d6af2c5a4b4`
- Batch manifest: `2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5`

## Source, group, and batch evidence

- Bank distribution: `{'Axis Bank': 27, 'Canara Bank': 7, 'Citibank': 3, 'HDFC Bank': 60, 'IDBI': 3, 'IndusInd Bank': 4, 'Kotak': 19, 'None': 321, 'Punjab National Bank': 5, 'SBI': 51, 'absa': 100, 'capitec': 100, 'fnb': 100, 'nedbank': 100, 'standard_bank': 100}`
- Invalid privacy status records: 0
- Missing/blank text records: 0
- Prefilled labels: intent=0, public_warning=0, non-empty opinions=0
- Records not `not_started`: 0
- v2 rule distribution (sampling provenance only): `{'A': 153, 'B': 100, 'C': 193, 'D': 32, 'E': 14, 'F': 8}`

| Linkage field | Coverage | Records with value | Groups | Cross-batch violations | Verified |
|---|---|---:|---:|---:|---|
| duplicate_group | verified_none | 0 | 0 | 0 | True |
| leakage_group | present | 1000 | 1000 | 0 | True |
| review_id | present | 250 | 250 | 0 | True |
| thread_id | unavailable | 0 | 0 | 0 | False |
| conversation_id | unavailable | 0 | 0 | 0 | False |

- International reviews with deterministic review IDs: 250/250
- Calibration diversity: `{'international_review': 12, 'international_tweet': 13, 'south_africa_tweet': 25}`; context `{'False': 50}`

| Batch | Type | Records | Source distribution | Region distribution | SHA-256 matches |
|---|---|---:|---|---|---|
| calibration_001 | calibration | 50 | `{'international_review': 12, 'international_tweet': 13, 'south_africa_tweet': 25}` | `{'international': 25, 'south_africa': 25}` | True |
| main_001 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_002 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_003 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_004 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_005 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_006 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_007 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_008 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| main_009 | main | 100 | `{'international_review': 25, 'international_tweet': 25, 'south_africa_tweet': 50}` | `{'international': 50, 'south_africa': 50}` | True |
| final_001 | final | 50 | `{'international_review': 13, 'international_tweet': 12, 'south_africa_tweet': 25}` | `{'international': 25, 'south_africa': 25}` | True |
## Issues requiring resolution or researcher consideration

- None reported by automated static checks.

This report is evidence only. A READY recommendation is not approval; approval and identity freeze require separate explicit researcher actions.
