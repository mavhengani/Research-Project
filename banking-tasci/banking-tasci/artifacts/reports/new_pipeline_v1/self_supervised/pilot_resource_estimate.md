# U1/U2 one-epoch pilot resource estimate

Status: `PILOT_ESTIMATE_LIMITED_BY_SMOKE_INSTRUMENTATION` (2026-10-20).

The smoke evidence proves execution, checkpoint reload and five-step continuation. It does not contain per-step timestamps or phase durations, so a true post-warm-up median/mean, tokens/s, evaluation duration, checkpoint-write duration, reload duration and resume duration cannot be extracted. The eligible pool was 3,000 IDs, while the run actually processed 440 examples from 440 unique IDs in 55 batches/optimizer steps and applied 55 dynamic masking events.

| Condition | Total-wall average per smoke step | Total-wall examples/s | Pilot baseline incl. 7 monitor passes | +20% | +50% |
|---|---:|---:|---:|---:|---:|
| U1 | 1.266s | 6.32 | 5.16h | 6.19h | 7.73h |
| U2 | 1.372s | 5.83 | 5.59h | 6.70h | 8.38h |

The proxy uses 3,423 optimizer updates, four microbatches per update, 139 monitor microbatches at each of seven evaluations, seven checkpoint writes including the final checkpoint, and the observed total smoke average. Checkpoint/reload and data-loading variation are not separately measured and are covered only by the 20% and 50% ranges. Sequential planning is therefore about 12.89–16.11 hours.
