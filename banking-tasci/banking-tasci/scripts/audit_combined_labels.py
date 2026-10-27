"""audit_combined_labels.py — Phase 3B Step 3.

Reports counts for ALL configured labels (including zeros) across:
  - full combined dataset
  - pilot source only
  - SA source only
  - international region
  - south_africa region
  - context-available records
  - no-context records

Reports intent, aspect_category, and sentiment distributions.
Writes outputs/combined_gold_distribution_v2.json.
STOPS and reports if any intent or sentiment class has ZERO training examples
in the combined dataset.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import (  # noqa: E402
    ASPECT_CATEGORIES,
    ASPECT_SENTIMENTS,
    INTENT_LABELS,
    AnnotationRecord,
    read_jsonl,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

COMBINED_GOLD = PROJECT_ROOT / "data" / "annotations" / "combined_adjudicated_v2.jsonl"
PROVENANCE_FILE = PROJECT_ROOT / "outputs" / "combined_gold_provenance.json"
OUTPUT_FILE = PROJECT_ROOT / "outputs" / "combined_gold_distribution_v2.json"

# Thresholds for research readiness classification
THRESHOLD_SUFFICIENT = 20
THRESHOLD_LOW = 10
THRESHOLD_CRITICAL = 1


def _load_provenance() -> dict[str, str]:
    if PROVENANCE_FILE.is_file():
        data = json.loads(PROVENANCE_FILE.read_text(encoding="utf-8"))
        return data.get("provenance", {})
    return {}


def _intent_distribution(records: list[AnnotationRecord]) -> dict[str, int]:
    counts: Counter = Counter({label: 0 for label in INTENT_LABELS})
    for r in records:
        intent = getattr(r, "intent", None)
        if intent in INTENT_LABELS:
            counts[intent] += 1
    return dict(counts)


def _aspect_category_distribution(records: list[AnnotationRecord]) -> dict[str, int]:
    counts: Counter = Counter({cat: 0 for cat in ASPECT_CATEGORIES})
    for r in records:
        aspects = getattr(r, "aspects", None) or []
        for a in aspects:
            cat = getattr(a, "category", None)
            if cat in ASPECT_CATEGORIES:
                counts[cat] += 1
    return dict(counts)


def _sentiment_distribution(records: list[AnnotationRecord]) -> dict[str, int]:
    counts: Counter = Counter({sent: 0 for sent in ASPECT_SENTIMENTS})
    for r in records:
        aspects = getattr(r, "aspects", None) or []
        for a in aspects:
            sent = getattr(a, "sentiment", None)
            if sent in ASPECT_SENTIMENTS:
                counts[sent] += 1
    return dict(counts)


def _classify_support(count: int) -> str:
    if count == 0:
        return "zero"
    elif count < THRESHOLD_CRITICAL:
        return "critical"
    elif count < THRESHOLD_LOW:
        return "critical"
    elif count < THRESHOLD_SUFFICIENT:
        return "low"
    else:
        return "sufficient"


def main() -> int:
    print("Step 3: Auditing combined labels...")

    if not COMBINED_GOLD.is_file():
        print(f"ERROR: Combined gold file not found: {COMBINED_GOLD}", file=sys.stderr)
        return 1

    records = read_jsonl(COMBINED_GOLD)
    provenance = _load_provenance()

    # Partition by source file.
    pilot_records = [r for r in records if provenance.get(str(getattr(r, "record_id", ""))) == "pilot_adjudicated.jsonl"]
    sa_records = [r for r in records if provenance.get(str(getattr(r, "record_id", ""))) == "south_african_adjudicated.jsonl"]

    # Partition by region.
    intl_records = [r for r in records if getattr(r, "region", None) == "international"]
    sa_region_records = [r for r in records if getattr(r, "region", None) == "south_africa"]

    # Partition by context availability.
    ctx_records = [r for r in records if getattr(r, "context_available", None) is True]
    no_ctx_records = [r for r in records if not getattr(r, "context_available", None)]

    def _section(recs: list[AnnotationRecord]) -> dict:
        return {
            "count": len(recs),
            "intent": _intent_distribution(recs),
            "aspect_category": _aspect_category_distribution(recs),
            "sentiment": _sentiment_distribution(recs),
        }

    report = {
        "combined": _section(records),
        "by_source": {
            "pilot_adjudicated": _section(pilot_records),
            "south_african_adjudicated": _section(sa_records),
        },
        "by_region": {
            "international": _section(intl_records),
            "south_africa": _section(sa_region_records),
        },
        "by_context": {
            "context_available": _section(ctx_records),
            "no_context": _section(no_ctx_records),
        },
    }

    # --- Zero-class check ---
    combined_intents = report["combined"]["intent"]
    combined_sentiments = report["combined"]["sentiment"]

    zero_intents = [label for label in INTENT_LABELS if combined_intents.get(label, 0) == 0]
    zero_sentiments = [label for label in ASPECT_SENTIMENTS if combined_sentiments.get(label, 0) == 0]

    # Research readiness classification per intent class
    intent_support_class = {
        label: _classify_support(combined_intents.get(label, 0)) for label in INTENT_LABELS
    }
    sentiment_support_class = {
        label: _classify_support(combined_sentiments.get(label, 0)) for label in ASPECT_SENTIMENTS
    }

    report["research_readiness"] = {
        "intent_support_classification": intent_support_class,
        "sentiment_support_classification": sentiment_support_class,
        "zero_intent_classes": zero_intents,
        "zero_sentiment_classes": zero_sentiments,
        "thresholds": {
            "sufficient": f">= {THRESHOLD_SUFFICIENT}",
            "low": f"{THRESHOLD_LOW}-{THRESHOLD_SUFFICIENT - 1}",
            "critical": f"1-{THRESHOLD_LOW - 1}",
            "zero": "0",
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  Distribution report written to: {OUTPUT_FILE}")

    # Print summary to stdout.
    print(f"\n  Combined dataset: {len(records)} records")
    print(f"    By source: pilot={len(pilot_records)}, sa={len(sa_records)}")
    print(f"    By region: international={len(intl_records)}, south_africa={len(sa_region_records)}")
    print(f"    By context: available={len(ctx_records)}, no-context={len(no_ctx_records)}")

    print("\n  INTENT distribution (combined):")
    for label in INTENT_LABELS:
        count = combined_intents.get(label, 0)
        cls = intent_support_class[label]
        print(f"    {label}: {count} [{cls}]")

    print("\n  SENTIMENT distribution (combined):")
    for label in ASPECT_SENTIMENTS:
        count = combined_sentiments.get(label, 0)
        cls = sentiment_support_class[label]
        print(f"    {label}: {count} [{cls}]")

    print("\n  ASPECT CATEGORY distribution (combined):")
    for cat in ASPECT_CATEGORIES:
        count = report["combined"]["aspect_category"].get(cat, 0)
        print(f"    {cat}: {count}")

    if zero_intents:
        print(f"\n  WARNING: Zero training examples for intent classes: {zero_intents}", file=sys.stderr)
        print("  STOPPING — cannot proceed to training without at least one example per intent class.", file=sys.stderr)
        return 1

    if zero_sentiments:
        print(f"\n  WARNING: Zero training examples for sentiment classes: {zero_sentiments}", file=sys.stderr)
        print("  STOPPING — cannot proceed to training without at least one example per sentiment class.", file=sys.stderr)
        return 1

    print("\nStep 3 COMPLETE. All intent and sentiment classes have at least one example.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
