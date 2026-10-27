# U2 Banking Span-BERT smoke report

Status: **PASS**

- Run: `artifacts/runs/new_pipeline_v1/self_supervised/U2/20261020T132709Z_c7e540ad`
- Objective: span MLM plus project-specific boundary/relative-position SBO, λ=0.5
- Model revision: `86b5e0934494bd15c9632b12f734a8a67f723594`
- Sample: the same 3,000 identities as U1; checksum `e4c21733c09cd1b9d9b8a86b80f077476bf9f3e46554f0c884985f04adb1e0de`
- Updates: 50, followed by a verified five-step resume to 55
- Initial combined loss: 12.55711555480957
- Step-50 combined loss: 8.742860794067383
- Step-55 combined loss: 9.35959529876709
- Final SBO loss: 8.049352645874023
- Final-batch realised masking: 14.652%
- Final-batch spans: 13; mean length 3.077; invalid 0; truncated 0
- Runtime: 75.43 seconds on CPU
- Reload: PASS
- Resume: PASS; original checkpoint unchanged
- Storage: approximately 3.5 GB

U1 and U2 self-supervised losses are not directly comparable because their objectives differ. This smoke run does not establish downstream superiority.
