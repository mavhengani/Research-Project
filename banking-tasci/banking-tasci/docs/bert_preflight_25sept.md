# BERT Preflight: 25 September 2026

## Result

**BERT BLOCKED BY MISSING DEPENDENCY**

The preflight was local-only. It did not install packages, download a
checkpoint, call `from_pretrained`, train, or evaluate a model.

## Observed Checks

| Check | Result |
|---|---|
| `bert_aspect.yaml` | Present; task `aspect`; max length 128 |
| `bert_intent.yaml` | Present; task `intent`; max length 128 |
| `bert_sentiment.yaml` | Present; task `sentiment`; max length 128 |
| Configured local checkpoint | `models/pretrained/bert-base-uncased`; absent locally |
| `transformers` import | Failed: `ModuleNotFoundError` |
| PyTorch | 2.14.0 |
| CUDA | Unavailable; zero local CUDA devices |
| BERT helper module | Imports; model/tokenizer calls were not executed |
| BIO labels | `O=0`, `B-ASP=1`, `I-ASP=2` |
| Offline loading | Configured with `local_files_only` |
| Sentiment markers | `[ASP]` and `[/ASP]` configured |

The exact machine-readable result is in
`outputs/bert_preflight_25sept.json`.

## Required Before Training

The cluster or another approved environment must provide a compatible
`transformers` installation, the local pretrained checkpoint and tokenizer,
and a verified CUDA/PyTorch runtime. No package was installed and no model was
downloaded during this preflight.

The approved preparation plan is to install no packages blindly on the login
node; instead use the cluster's approved offline environment, record the
`transformers` and `tokenizers` versions, verify model/tokenizer SHA-256
checksums, confirm PyTorch/CUDA compatibility, and run a one-epoch smoke test
with `local_files_only=True`. No exact compatible version is claimed until that
environment is inspected.