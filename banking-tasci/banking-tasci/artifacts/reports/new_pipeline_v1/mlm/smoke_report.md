# MLM CPU smoke report

Status: **PASS** for model loading, finite CPU forward/backward propagation, checkpoint-25 and checkpoint-50 creation, offline reload, and five-step resume to global step 55.

- Model: `bert-base-uncased`, snapshot `86b5e0934494bd15c9632b12f734a8a67f723594`
- Device: CPU; MPS unavailable
- Strict corpus: 110,615 records; SHA-256 `5ea719ec528510ddd8566410a1b533ff294093c2ce87538f472dae789cf9e3ea`
- MLM partition: 109,509 training IDs and 1,106 monitoring IDs
- Smoke sample: 3,000 unique training IDs; no monitor or frozen-gold overlap
- Settings: max length 128, dynamic masking 0.15, batch size 8, learning rate 5e-5, 50 smoke steps, checkpoints at 25 and 50
- Reload: PASS; finite loss 3.4529356956481934
- Resume: PASS; checkpoint 50 resumed and reached step 55

The run experienced tool-session interruption after checkpoint writes. Recovery used the immutable saved checkpoint rather than restarting or overwriting the strict corpus. The recovery-only metrics file does not preserve the original 50-step loss series, so it must not be used to infer convergence or throughput.

No downstream ABSA result is implied by this smoke result.
