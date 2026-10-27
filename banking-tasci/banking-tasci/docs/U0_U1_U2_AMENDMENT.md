# Self-Supervised Representation Amendment: U0/U1/U2 Comparative Pipeline

> **Execution state — 20 October 2026:** the matched U1/U2 smoke matrix passes. One-epoch pilots have not started. Cluster authentication is unavailable after the one safe authorised check; local storage and checkpoint gates pass, but the long CPU execution-window and pilot-resume CLI gates remain open. Final adaptation remains unauthorised.

Amendment ID: `NEW_PIPELINE_V1_SSL_U0_U1_U2_2026-10-20` • Approval status: authorised requirements amendment.

The prior original-BERT versus MLM-adapted-BERT comparison is superseded by U0 (original BERT, no adaptation), U1 (dynamic token MLM on the strict corpus), and U2 (contiguous span MLM plus span-boundary objective on the same corpus). U1/U2 share the exact base revision, tokenizer, partition, corpus checksum, maximum length, seed schedule, optimiser family, interval policy, and future downstream splits. U2 must report additional head parameters, storage, runtime and memory.

U2 uses non-overlapping spans of length 1–10 (configured mean target 3), clips at sequence boundaries, masks approximately 15% eligible tokens, and computes `L = L_span_MLM + 0.5 * L_SBO`. Its project-specific SBO concatenates the left boundary state, right boundary state, and learned within-span relative-position embedding before prediction; losses are mean-normalised across valid span-token targets. This is not claimed as a verbatim reproduction of the published SpanBERT implementation. It is not permitted to fall back silently to token MLM.

Smoke gates are 3,000 shared IDs and 50 updates. U1 requires finite MLM loss; U2 requires finite combined, span-MLM, and SBO loss plus span statistics. Pilots and final adaptation remain separately authorised. Downstream compares U0/U1/U2 alongside TF-IDF/SVM and BiLSTM for target, category, intent, sentiment and integrated TASCI.

Affected files: central config, self-supervised configs, training masking strategies, experiment matrix, gap analysis, migration plan and handover. Research decisions pending: final span distribution, matched-training policy (updates/tokens/compute), and CUDA resource allocation.
