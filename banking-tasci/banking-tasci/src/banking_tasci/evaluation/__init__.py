"""Evaluation metrics and reporting for the banking-tasci tasks.

Phase 3A (Part 12):
    classification_metrics, bio_token_metrics, bio_span_metrics,
    SpanMetrics, label_distribution

Phase 3A.1 (new modules):
    end_to_end  – span/sentiment/intent tuple metrics
    regional    – region/source/context grouping
    ablation    – ablation condition comparison
    reports     – JSON, Markdown, CSV, JSONL serialisers
"""
from banking_tasci.evaluation.metrics import (
    SpanMetrics,
    bio_span_metrics,
    bio_token_metrics,
    classification_metrics,
    label_distribution,
)

__all__ = [
    # Phase 3A
    "classification_metrics",
    "bio_token_metrics",
    "bio_span_metrics",
    "SpanMetrics",
    "label_distribution",
    # Phase 3A.1 sub-modules (import directly from the sub-module)
    # banking_tasci.evaluation.end_to_end
    # banking_tasci.evaluation.regional
    # banking_tasci.evaluation.ablation
    # banking_tasci.evaluation.reports
]
