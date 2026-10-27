#!/usr/bin/env python3
"""Focused gold-data quality audit script. Read-only on annotation and manifest files."""
import json, csv, sys
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent

# ---- Load adjudicated records ----
adj_path = ROOT / "data/annotations/pilot_adjudicated.jsonl"
records = [json.loads(l) for l in adj_path.read_text().splitlines() if l.strip()]
record_map = {r["record_id"]: r for r in records}

# ---- Load manifests ----
def read_manifest(p):
    lines = Path(p).read_text().splitlines()
    return [l.strip() for l in lines[1:] if l.strip()]

train_ids = set(read_manifest(ROOT / "data/processed/train_manifest.csv"))
val_ids   = set(read_manifest(ROOT / "data/processed/validation_manifest.csv"))
test_ids  = set(read_manifest(ROOT / "data/processed/test_manifest.csv"))

# ---- Load annotator files ----
ann_a_path = ROOT / "data/annotations/pilot_annotator_a.jsonl"
ann_b_path = ROOT / "data/annotations/pilot_annotator_b.jsonl"
records_a = [json.loads(l) for l in ann_a_path.read_text().splitlines() if l.strip()]
records_b = [json.loads(l) for l in ann_b_path.read_text().splitlines() if l.strip()]

# ---- Configured labels ----
INTENT_LABELS = ["complaint","compliment","request_for_assistance","suggestion","warning","churn_signal","general_feedback"]
CATEGORIES = ["customer_support","digital_banking","transactions","cards","accounts","fees","fraud_security","branch_service","general_service"]
SENTIMENTS = ["negative","neutral","positive"]
SOURCES = ["international_bank_tweets","bank_reviews"]

# ---- Thresholds (audit-only guidance) ----
SUFFICIENT = 20
LOW_SUPPORT = 10
CRITICAL_LOW = 1

def classify_support(n):
    if n >= SUFFICIENT: return "SUFFICIENT"
    if n >= LOW_SUPPORT: return "LOW_SUPPORT"
    if n >= CRITICAL_LOW: return "CRITICALLY_LOW_SUPPORT"
    return "ZERO_SUPPORT"

# ---- Helper: get records for a split ----
def get_recs(ids):
    return [record_map[i] for i in ids if i in record_map]

def intent_dist(recs):
    c = Counter(r.get("intent") for r in recs)
    return {lab: c.get(lab, 0) for lab in INTENT_LABELS}

def cat_dist(recs):
    c = Counter()
    for r in recs:
        for a in r.get("aspects", []):
            c[a.get("category")] += 1
    return {lab: c.get(lab, 0) for lab in CATEGORIES}

def sent_dist(recs):
    c = Counter()
    for r in recs:
        for a in r.get("aspects", []):
            c[a.get("sentiment")] += 1
    return {lab: c.get(lab, 0) for lab in SENTIMENTS}

def source_dist(recs):
    return dict(Counter(r.get("source") for r in recs))

def context_dist(recs):
    yes = sum(1 for r in recs if r.get("context_available"))
    no  = sum(1 for r in recs if not r.get("context_available"))
    return {"context_available_true": yes, "context_available_false": no}

# ---- Splits ----
train_recs = get_recs(train_ids)
val_recs   = get_recs(val_ids)
test_recs  = get_recs(test_ids)
intl_recs  = [r for r in records if r.get("region") == "international"]
sa_recs    = [r for r in records if r.get("region") != "international"]
ctx_recs   = [r for r in records if r.get("context_available")]
noctx_recs = [r for r in records if not r.get("context_available")]
tweet_recs = [r for r in records if r.get("source") == "international_bank_tweets"]
review_recs= [r for r in records if r.get("source") == "bank_reviews"]

# ---- Annotator file identity check ----
ids_a = {r["record_id"]: r.get("intent") for r in records_a}
ids_b = {r["record_id"]: r.get("intent") for r in records_b}
identical = ids_a == ids_b
diffs_a = {r["record_id"]: (r.get("intent"), r.get("aspects")) for r in records_a}
diffs_b = {r["record_id"]: (r.get("intent"), r.get("aspects")) for r in records_b}
n_diff = sum(1 for k in diffs_a if diffs_a[k] != diffs_b.get(k))

# ---- 150 corrected general_feedback records ----
# From annotator_a_validation: 150 records had missing_intent
# They all appear as general_feedback in adjudicated
# We'll identify them by checking annotator_a file for null/missing intent AND adjudicated for general_feedback
corrected_gf_ids = []
for r in records_a:
    intent_a = r.get("intent")
    rid = r["record_id"]
    adj_r = record_map.get(rid)
    if adj_r and (intent_a is None or intent_a == "") and adj_r.get("intent") == "general_feedback":
        corrected_gf_ids.append(rid)

print(f"Corrected GF IDs found: {len(corrected_gf_ids)}")

# ---- Keyword scan for zero-count intents ----
SUGGESTION_KW = ["should improve","please add","you need to","it would be better","consider changing","would be nice","why not add","suggest","suggestion","recommend","recommendation"]
WARNING_KW    = ["do not use","avoid this bank","stay away","be careful","beware","warning","warn","dangerous","unsafe","do not open","don't trust"]
CHURN_KW      = ["closing my account","switching banks","leaving this bank","moving to another bank","will no longer bank","close my account","switch to another","cancel my account","leaving your bank","no longer a customer","looking for another bank","changed to","switched to","close account"]

def kw_match(text, keywords):
    t = text.lower()
    return [k for k in keywords if k in t]

suggestion_matches = [(r, kw_match(r.get("text",""), SUGGESTION_KW)) for r in records if kw_match(r.get("text",""), SUGGESTION_KW)]
warning_matches    = [(r, kw_match(r.get("text",""), WARNING_KW))    for r in records if kw_match(r.get("text",""), WARNING_KW)]
churn_matches      = [(r, kw_match(r.get("text",""), CHURN_KW))      for r in records if kw_match(r.get("text",""), CHURN_KW)]

# ---- Fee/fraud keyword scan ----
FEE_KW   = ["fee","fees","charge","charges","charged","maintenance fee","service fee","sms charge","transaction fee","deduction","levy","penalty"]
FRAUD_KW = ["fraud","fraudulent","scam","hacked","unauthorised","unauthorized","phishing","stolen","compromised","identity theft","suspicious transaction","security"]

def asp_cat_for_record(r):
    return [a.get("category") for a in r.get("aspects", [])]

fee_candidates   = [(r, kw_match(r.get("text",""), FEE_KW),   asp_cat_for_record(r)) for r in records if kw_match(r.get("text",""), FEE_KW)]
fraud_candidates = [(r, kw_match(r.get("text",""), FRAUD_KW), asp_cat_for_record(r)) for r in records if kw_match(r.get("text",""), FRAUD_KW)]

# ---- Sentiment per category ----
sent_per_cat = {}
for cat in CATEGORIES:
    c = Counter()
    for r in records:
        for a in r.get("aspects", []):
            if a.get("category") == cat:
                c[a.get("sentiment")] += 1
    sent_per_cat[cat] = {s: c.get(s, 0) for s in SENTIMENTS}

# ---- Neutral-as-default check ----
# Records where ALL aspects have neutral sentiment
all_neutral_records = [r for r in records if r.get("aspects") and all(a.get("sentiment")=="neutral" for a in r.get("aspects",[]))]
# Records where ALL aspects have same sentiment  
uniform_sent_records = [r for r in records if len(r.get("aspects",[])) > 1 and len(set(a.get("sentiment") for a in r.get("aspects",[]))) == 1]

# ---- Context-aware: verify context consistency ----
ctx_inconsistent = [r for r in records if r.get("context_available") == True and r.get("previous_text","") in ("", "[NO_CONTEXT]", None)]
noctx_inconsistent = [r for r in records if r.get("context_available") == False and r.get("previous_text","") not in ("", "[NO_CONTEXT]", None)]

# ---- Context intent distribution ----
ctx_intent = intent_dist(ctx_recs)
noctx_intent = intent_dist(noctx_recs)

# ---- Compile full distribution ----
distribution = {
    "total_records": len(records),
    "total_aspects": sum(len(r.get("aspects",[])) for r in records),
    "zero_aspect_records": sum(1 for r in records if not r.get("aspects")),
    "annotator_files_identical": identical,
    "n_differences_between_annotators": n_diff,
    "corrected_general_feedback_count": len(corrected_gf_ids),
    "corrected_general_feedback_ids": corrected_gf_ids,
    "splits": {
        "train": len(train_recs), "validation": len(val_recs), "test": len(test_recs)
    },
    "intent": {
        "full": intent_dist(records),
        "train": intent_dist(train_recs),
        "validation": intent_dist(val_recs),
        "test": intent_dist(test_recs),
        "international": intent_dist(intl_recs),
        "south_african": intent_dist(sa_recs),
        "context_available": ctx_intent,
        "no_context": noctx_intent,
        "tweets": intent_dist(tweet_recs),
        "reviews": intent_dist(review_recs),
    },
    "aspect_category": {
        "full": cat_dist(records),
        "train": cat_dist(train_recs),
        "validation": cat_dist(val_recs),
        "test": cat_dist(test_recs),
        "international": cat_dist(intl_recs),
        "south_african": cat_dist(sa_recs),
        "context_available": cat_dist(ctx_recs),
        "no_context": cat_dist(noctx_recs),
        "tweets": cat_dist(tweet_recs),
        "reviews": cat_dist(review_recs),
    },
    "sentiment": {
        "full": sent_dist(records),
        "train": sent_dist(train_recs),
        "validation": sent_dist(val_recs),
        "test": sent_dist(test_recs),
        "international": sent_dist(intl_recs),
        "south_african": sent_dist(sa_recs),
        "context_available": sent_dist(ctx_recs),
        "no_context": sent_dist(noctx_recs),
        "tweets": sent_dist(tweet_recs),
        "reviews": sent_dist(review_recs),
    },
    "region": dict(Counter(r.get("region") for r in records)),
    "source": source_dist(records),
    "context": context_dist(records),
    "sentiment_per_category": sent_per_cat,
    "all_neutral_records_count": len(all_neutral_records),
    "uniform_sentiment_multi_aspect_count": len(uniform_sent_records),
    "ctx_inconsistent_count": len(ctx_inconsistent),
    "noctx_inconsistent_count": len(noctx_inconsistent),
    "keyword_scan": {
        "suggestion_keyword_matches": len(suggestion_matches),
        "warning_keyword_matches": len(warning_matches),
        "churn_keyword_matches": len(churn_matches),
        "fee_keyword_matches": len(fee_candidates),
        "fraud_keyword_matches": len(fraud_candidates),
    },
    "intent_support_classification": {
        lab: {"count": intent_dist(train_recs)[lab], "support": classify_support(intent_dist(train_recs)[lab])}
        for lab in INTENT_LABELS
    },
    "category_support_classification": {
        cat: {"count": cat_dist(train_recs)[cat], "support": classify_support(cat_dist(train_recs)[cat])}
        for cat in CATEGORIES
    },
    "sentiment_support_classification": {
        s: {"count": sent_dist(train_recs)[s], "support": classify_support(sent_dist(train_recs)[s])}
        for s in SENTIMENTS
    },
}

# Print key stats to stdout for review
print(json.dumps({
    "intent_full": distribution["intent"]["full"],
    "category_full": distribution["aspect_category"]["full"],
    "sentiment_full": distribution["sentiment"]["full"],
    "region": distribution["region"],
    "annotator_files_identical": identical,
    "corrected_gf": len(corrected_gf_ids),
    "suggestion_kw": len(suggestion_matches),
    "warning_kw": len(warning_matches),
    "churn_kw": len(churn_matches),
    "fee_kw": len(fee_candidates),
    "fraud_kw": len(fraud_candidates),
    "ctx_inconsistent": len(ctx_inconsistent),
    "noctx_inconsistent": len(noctx_inconsistent),
    "all_neutral_count": len(all_neutral_records),
    "intent_train_support": distribution["intent_support_classification"],
    "category_train_support": distribution["category_support_classification"],
}, indent=2))

# ---- Write gold_label_distribution.json ----
out_dist = ROOT / "outputs/gold_label_distribution.json"
out_dist.write_text(json.dumps(distribution, indent=2, default=str), encoding="utf-8")
print(f"\nWrote: {out_dist}")

# ---- Write general_feedback_review_queue.jsonl ----
out_gf = ROOT / "outputs/general_feedback_review_queue.jsonl"

# Also add keyword-matched records for suggestion/warning/churn with their current intent
kw_review_ids = set()
kw_review_entries = {}

for r, kws in suggestion_matches:
    kw_review_ids.add(r["record_id"])
    reasons = kw_review_entries.get(r["record_id"], {"reasons": []})
    reasons["reasons"].append(f"suggestion keyword match: {kws[:3]}")
    kw_review_entries[r["record_id"]] = reasons

for r, kws in warning_matches:
    kw_review_ids.add(r["record_id"])
    reasons = kw_review_entries.get(r["record_id"], {"reasons": []})
    reasons["reasons"].append(f"warning keyword match: {kws[:3]}")
    kw_review_entries[r["record_id"]] = reasons

for r, kws in churn_matches:
    kw_review_ids.add(r["record_id"])
    reasons = kw_review_entries.get(r["record_id"], {"reasons": []})
    reasons["reasons"].append(f"churn_signal keyword match: {kws[:3]}")
    kw_review_entries[r["record_id"]] = reasons

gf_queue_ids = set(corrected_gf_ids) | kw_review_ids
with open(out_gf, "w", encoding="utf-8") as f:
    for rid in sorted(gf_queue_ids):
        r = record_map.get(rid)
        if not r:
            continue
        reasons = []
        if rid in set(corrected_gf_ids):
            reasons.append("assigned during missing-intent correction")
        kw_info = kw_review_entries.get(rid, {}).get("reasons", [])
        reasons.extend(kw_info)
        entry = {
            "record_id": rid,
            "source": r.get("source",""),
            "region": r.get("region",""),
            "text": r.get("text",""),
            "previous_text": r.get("previous_text",""),
            "context_available": r.get("context_available", False),
            "current_intent": r.get("intent",""),
            "original_intent_known": rid in set(corrected_gf_ids),
            "annotation_notes": r.get("notes",""),
            "review_reason": "; ".join(reasons) if reasons else "annotation provenance unavailable",
            "human_review_decision": "",
            "human_review_notes": "",
        }
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print(f"Wrote: {out_gf} ({len(gf_queue_ids)} entries)")

# ---- Write aspect_category_review_queue.jsonl ----
out_asp = ROOT / "outputs/aspect_category_review_queue.jsonl"
with open(out_asp, "w", encoding="utf-8") as f:
    written = set()
    # Fee candidates: aspects on records with fee keywords, where category is NOT fees
    for r, kws, cats in fee_candidates:
        for a in r.get("aspects", []):
            if a.get("category") != "fees":
                key = (r["record_id"], a.get("aspect_term", a.get("term","")), a.get("start",0))
                if key not in written:
                    written.add(key)
                    entry = {
                        "record_id": r["record_id"],
                        "text": r.get("text",""),
                        "aspect_term": a.get("term",""),
                        "aspect_start": a.get("start",0),
                        "aspect_end": a.get("end",0),
                        "current_category": a.get("category",""),
                        "current_sentiment": a.get("sentiment",""),
                        "review_reason": f"possible fees review; fee keywords in text: {kws[:3]}",
                        "human_review_category": "",
                        "human_review_sentiment": "",
                        "human_review_notes": "",
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Also records with fee keywords but zero aspects
        if not r.get("aspects"):
            key = (r["record_id"], "__no_aspect__", 0)
            if key not in written:
                written.add(key)
                entry = {
                    "record_id": r["record_id"],
                    "text": r.get("text",""),
                    "aspect_term": "",
                    "aspect_start": 0,
                    "aspect_end": 0,
                    "current_category": "(no aspect annotated)",
                    "current_sentiment": "",
                    "review_reason": f"possible fees review; fee keywords in text but no aspect annotated: {kws[:3]}",
                    "human_review_category": "",
                    "human_review_sentiment": "",
                    "human_review_notes": "",
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Fraud candidates
    for r, kws, cats in fraud_candidates:
        for a in r.get("aspects", []):
            if a.get("category") != "fraud_security":
                key = (r["record_id"], a.get("term",""), a.get("start",0))
                if key not in written:
                    written.add(key)
                    entry = {
                        "record_id": r["record_id"],
                        "text": r.get("text",""),
                        "aspect_term": a.get("term",""),
                        "aspect_start": a.get("start",0),
                        "aspect_end": a.get("end",0),
                        "current_category": a.get("category",""),
                        "current_sentiment": a.get("sentiment",""),
                        "review_reason": f"possible fraud_security review; fraud keywords in text: {kws[:3]}",
                        "human_review_category": "",
                        "human_review_sentiment": "",
                        "human_review_notes": "",
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if not r.get("aspects"):
            key = (r["record_id"], "__no_aspect__fraud__", 0)
            if key not in written:
                written.add(key)
                entry = {
                    "record_id": r["record_id"],
                    "text": r.get("text",""),
                    "aspect_term": "",
                    "aspect_start": 0,
                    "aspect_end": 0,
                    "current_category": "(no aspect annotated)",
                    "current_sentiment": "",
                    "review_reason": f"possible fraud_security review; fraud keywords in text but no aspect annotated: {kws[:3]}",
                    "human_review_category": "",
                    "human_review_sentiment": "",
                    "human_review_notes": "",
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

print(f"Wrote: {out_asp} ({len(written)} entries)")

# ---- Write independent_annotation_sample_100.jsonl ----
import random
random.seed(42)

out_sample = ROOT / "outputs/independent_annotation_sample_100.jsonl"

# Stratified sample: proportional by intent across observed intents,
# plus records from review queues, with context/source balance
by_intent = defaultdict(list)
for r in records:
    by_intent[r.get("intent","unknown")].append(r)

# Targets based on proportional distribution
targets = {
    "complaint": 29,
    "compliment": 6,
    "request_for_assistance": 20,
    "general_feedback": 45,  # includes 10 from corrected GF batch for review
}

# Force include some from review queues for coverage
corrected_gf_set = set(corrected_gf_ids)
kw_review_set = kw_review_ids

sample_ids = set()
sample_records = []

# From each intent bucket, stratify: include some with aspects, some without, some with context
for intent, n in targets.items():
    pool = sorted(by_intent[intent], key=lambda r: r["record_id"])
    random.shuffle(pool)
    
    # Prioritise: corrected GF, kw-matched, context-available, multi-aspect
    priority = [r for r in pool if r["record_id"] in corrected_gf_set or r["record_id"] in kw_review_set]
    rest = [r for r in pool if r not in priority]
    ordered = priority + rest
    
    added = 0
    for r in ordered:
        if added >= n:
            break
        if r["record_id"] not in sample_ids:
            sample_ids.add(r["record_id"])
            sample_records.append(r)
            added += 1

with open(out_sample, "w", encoding="utf-8") as f:
    for r in sample_records:
        # Strip gold labels — present only fields the independent annotator should see
        entry = {
            "record_id": r["record_id"],
            "source": r.get("source",""),
            "region": r.get("region",""),
            "text": r.get("text",""),
            "previous_text": r.get("previous_text",""),
            "context_available": r.get("context_available", False),
            "aspects": [],
            "intent": None,
            "intent_ambiguous": False,
            "alternative_intent": None,
            "annotator_id": "",
            "annotation_status": "not_started",
            "notes": "",
        }
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

print(f"Wrote: {out_sample} ({len(sample_records)} records)")

# ---- Print summary for audit report ----
print("\n=== FULL AUDIT SUMMARY ===")
print(f"Total records: {len(records)}")
print(f"Total aspects: {distribution['total_aspects']}")
print(f"Annotator files identical: {identical}, diffs: {n_diff}")
print(f"Corrected GF records: {len(corrected_gf_ids)}")
print(f"SA records: {len(sa_recs)}")
print(f"Context available: {len(ctx_recs)}, No context: {len(noctx_recs)}")
print(f"Ctx inconsistent: {len(ctx_inconsistent)}, Noctx inconsistent: {len(noctx_inconsistent)}")
print("\nIntent support (train):")
for lab in INTENT_LABELS:
    n = distribution["intent_support_classification"][lab]["count"]
    s = distribution["intent_support_classification"][lab]["support"]
    print(f"  {lab}: {n} [{s}]")
print("\nCategory support (train):")
for cat in CATEGORIES:
    n = distribution["category_support_classification"][cat]["count"]
    s = distribution["category_support_classification"][cat]["support"]
    print(f"  {cat}: {n} [{s}]")
print("\nSentiment per category (full):")
for cat in CATEGORIES:
    d = sent_per_cat[cat]
    print(f"  {cat}: neg={d['negative']} neu={d['neutral']} pos={d['positive']}")
print(f"\nAll-neutral multi-aspect records: {len(all_neutral_records)}")
print(f"Uniform-sentiment multi-aspect records: {len(uniform_sent_records)}")

# Additional detail: intent of keyword-matched records
print(f"\nSuggestion KW matches ({len(suggestion_matches)}) current intents:")
print(Counter(r.get("intent") for r, kws in suggestion_matches))
print(f"Warning KW matches ({len(warning_matches)}) current intents:")
print(Counter(r.get("intent") for r, kws in warning_matches))
print(f"Churn KW matches ({len(churn_matches)}) current intents:")
print(Counter(r.get("intent") for r, kws in churn_matches))

# Which corrected GF records are in kw review
cross_corr_kw = corrected_gf_set & kw_review_ids
print(f"\nCorrected GF records ALSO in keyword review: {len(cross_corr_kw)}")
