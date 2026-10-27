# Matched final U1/U2 training recommendation

Status: **prepared, not authorised for execution**.

Use the same strict-corpus checksum, 109,509/1,106 partition, pinned BERT/tokenizer revision, max length 128, masking probability 0.15, seed schedule, AdamW policy, learning rate 5e-5, weight decay 0.01, warmup ratio 0.06, effective batch 32, evaluation/checkpoint interval 500, and retention limit two. Match U1 and U2 primarily by corpus, partition, epoch count, effective batch, optimizer policy, seeds, and approximately equal processed tokens. Report U2's extra parameters, memory, storage, and runtime separately.

Provisional final schedule: three epochs per representation for each pre-registered seed, subject to separate authorisation after both one-epoch pilots pass. Use CUDA, preserve exact token/update reconciliation, and do not use downstream results to choose the matching policy. Projected CPU time is three times the verified one-epoch planning range and is not recommended.

Proposed output roots: `artifacts/runs/new_pipeline_v1/self_supervised/U1/final/` and `artifacts/runs/new_pipeline_v1/self_supervised/U2/final/`. Exact resume commands cannot yet be supplied because the current pilot CLI does not accept a checkpoint/resume argument; this is a readiness gap to close before any long run.
