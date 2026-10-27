# U1/U2 smoke runbook

Status: prepared, not executed. The two runs use the same 3,000 training-partition identities and remain independent gates.

After explicit execution authorisation, run U1 with:

```sh
HF_HOME=.cache/huggingface .venv-mlm/bin/python scripts/train_self_supervised.py \
  --config configs/self_supervised/u1_banking_mlm_bert.yaml --mode smoke --execute-authorized
```

Run U2 separately with:

```sh
HF_HOME=.cache/huggingface .venv-mlm/bin/python scripts/train_self_supervised.py \
  --config configs/self_supervised/u2_banking_span_bert.yaml --mode smoke --execute-authorized
```

The execution flag is wired to the shared, representation-safe driver. It must be used only after explicit smoke execution authorisation. Without it, both commands stop before model loading or updates. U2 records total, span-MLM, and SBO losses plus span statistics.
