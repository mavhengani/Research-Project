# South African Filter History

**Status date:** 2026-09-25

The South African preparation has two distinct candidate-filter versions. Their
candidate counts are not contradictory because they use different rules.

## Version 1

Version 1 used the broad, length-based catch-all rule: sufficiently long,
non-promotional text was treated as a candidate. The preparation report records
2,086,851 candidates out of 2,250,776 cleaned canonical rows, approximately
92.7 percent. The v1 quality review found that 131/200 sampled records were
classified as suitable customer feedback and identified the catch-all rule as
the principal problem.

## Version 2

Version 2, implemented by `scripts/resample_south_africa_v2.py`, removed the
length-only catch-all and applied evidence-based banking/problem/request/
positive/suggestion-warning-churn/specific-phrase rules. The resampling report
records 100,768 candidates out of 2,250,776 rows, approximately 4.5 percent.

Version 2 selected a 200-record sample with seed 42. The separate annotation
input preparation then removed four records:

| Record ID | Reason |
|---|---|
| `00928e359abca8da` | news or general discussion |
| `eaa9f960b5ac40b5` | too short or low information |
| `20ac4cd2ff9ab6a7` | too short or low information |
| `1a5b1e35ccf125e8` | too short or low information |

The resulting label-hidden annotation input contains 196 records. The source
200-record v2 sample remains preserved as
`data/annotations/south_african_unannotated_v2.jsonl`; the 196-record input is
`data/annotations/south_african_annotation_input.jsonl`.

## Interpretation

`2,086,851` describes the v1 broad candidate pool. `100,768` describes the v2
evidence-based candidate pool. They must not be presented as two measurements
of the same filter version.