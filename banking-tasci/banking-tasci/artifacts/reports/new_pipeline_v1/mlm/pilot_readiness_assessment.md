# MLM pilot readiness assessment

Status: **LOCAL_PILOT_LONG_BUT_RESUMABLE**. The 50-step CPU smoke completed with checkpoint/reload/resume verification. A one-epoch pilot remains unexecuted.

The benchmarked CPU batch took about 2.4 seconds at batch size 8. A one-epoch pilot at an effective batch size of 32 would require approximately 3,422 training steps for the 109,509-record MLM training partition. CPU wall-time is uncertain because batching changes throughput; the conservative batch-8 extrapolation is about 2.3 hours before monitoring and checkpoint overhead. Plan for materially longer elapsed time, substantial checkpoint storage, interruption handling, and resume from verified checkpoints.

Use CUDA for a practical pilot if a cluster is available. Do not run this command without separate authorisation:

```sh
HF_HOME=.cache/huggingface .venv-mlm/bin/python scripts/train_mlm.py \
  --config configs/mlm/new_pipeline_v1_banking_bert.yaml --mode pilot
```

The current entry point deliberately supports only validate-only, analysis, partitioning, and the authorised smoke gate; `pilot` is therefore not executable.
