# U1/U2 one-epoch pilot resource review

Status: **PILOT_PREPARED_NOT_EXECUTED**.

Both pilots use 109,509 training records, 1,106 monitoring records, max length 128, masking probability 0.15, seed 42, microbatch 8, gradient accumulation 4, and effective batch size 32. One epoch requires 3,423 optimiser updates. Checkpoints and evaluation occur every 500 updates, with only the latest two checkpoints retained.

Measured CPU smoke throughput was 0.790 updates/s for U1 and 0.729 updates/s for U2 at batch 8. Four microbatches are required per effective-batch-32 update. Naive CPU projections are about 4.81 hours for U1 and 5.22 hours for U2; allowing 50% for monitoring, checkpointing, data loading and longer sequences gives approximately 7.22 and 7.82 hours. Local disk currently has about 43 GiB available. Smoke storage was 2.9 GiB for U1 and 3.5 GiB for U2, so checkpoint retention must remain capped.

Classification: **LOCAL_PILOT_LONG_BUT_RESUMABLE**, with CUDA recommended. U2 is expected to use more memory and storage because of its SBO head. These estimates are planning evidence, not pilot results.

Pilot execution is implemented in the shared CLI with full-monitor evaluation, gradient accumulation, two-checkpoint retention, reload validation, and completion evidence. It has been compiled and unit-tested but not executed. Submit it only after separate pilot approval. No matching policy may be changed after downstream test results are viewed.
