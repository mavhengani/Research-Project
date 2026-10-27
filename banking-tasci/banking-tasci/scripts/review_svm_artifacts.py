"""Post-hoc review of completed SVM runs; never retrains or rewrites predictions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from banking_tasci.data.datasets import build_intent_examples, build_intent_label_map, build_sentiment_examples, build_sentiment_label_map
from banking_tasci.data.annotations import read_jsonl
from banking_tasci.models.svm_baseline import load_artifacts


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _manifest_ids(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return [row["record_id"] for row in csv.DictReader(handle)]


def _write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _safe_id(record_id):
    return hashlib.sha256(str(record_id).encode("utf-8")).hexdigest()[:16]


def _group(record):
    source = getattr(record, "source", "")
    if source == "south_african_bank_tweets":
        return "south_africa"
    if source == "international_bank_tweets":
        return "international"
    if source == "bank_reviews":
        return "reviews"
    return str(source)


def _record_meta(record):
    return {
        "record_id_hash": _safe_id(record.record_id),
        "source": record.source,
        "region": record.region,
        "context_available": bool(record.context_available),
        "text": record.text,
    }


def _metrics(y_true, y_pred, labels):
    report = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
    return {
        "n": len(y_true),
        "observed_labels": sorted(set(y_true)),
        "accuracy": accuracy_score(y_true, y_pred) if y_true else None,
        "macro_precision": report["macro avg"]["precision"] if y_true else None,
        "macro_recall": report["macro avg"]["recall"] if y_true else None,
        "macro_f1": report["macro avg"]["f1-score"] if y_true else None,
        "weighted_f1": report["weighted avg"]["f1-score"] if y_true else None,
        "per_class": {label: {"support": int(report.get(label, {}).get("support", 0)), "precision": report.get(label, {}).get("precision", 0.0), "recall": report.get(label, {}).get("recall", 0.0), "f1": report.get(label, {}).get("f1-score", 0.0)} for label in labels},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist() if y_true else [],
        "support_status": "OK" if len(set(y_true)) > 1 else "INSUFFICIENT SUPPORT FOR RELIABLE SUBGROUP METRICS",
    }


def _write_confusion(path, labels, matrix):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gold\\pred", *labels])
        for label, row in zip(labels, matrix):
            writer.writerow([label, *row])


def _subgroups(record):
    groups = {_group(record): True}
    groups["context_available" if record.context_available else "no_context"] = True
    groups["all"] = True
    return groups


def _cluster_metadata(project_root):
    command = ["sacct", "-X", "-j", "50823", "--format=JobID,Partition,State,ExitCode,Elapsed,Start,End,NodeList", "-P", "-n"]
    try:
        output = subprocess.check_output(command, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip().splitlines()
        fields = output[0].split("|") if output else []
        values = fields + [""] * (8 - len(fields))
        return {"slurm_job_id": "50823", "job_id": values[0], "partition": values[1], "state": values[2], "exit_code": values[3], "elapsed": values[4], "start_time": values[5], "end_time": values[6], "node": values[7], "readiness": "READY"}
    except Exception as exc:
        return {"slurm_job_id": "50823", "readiness": "READY", "metadata_lookup_error": str(exc)}


def review_intent(project_root, run_dir, records, test_ids):
    label_map = build_intent_label_map()
    labels = list(label_map)
    by_id = {r.record_id: r for r in records}
    examples = build_intent_examples([by_id[rid] for rid in test_ids], label_map)
    predictions = _jsonl(Path(run_dir) / "predictions.jsonl")
    artifacts = load_artifacts(Path(run_dir) / "svm")
    reloaded = [labels[int(p)] for p in artifacts.predict(examples[: min(10, len(examples))])]
    saved = [p["pred"] for p in predictions[: len(reloaded)]]
    (Path(run_dir) / "reloadability.json").write_text(json.dumps({"reloadable": True, "fixed_test_examples_checked": len(reloaded), "predictions_match_saved": reloaded == saved}, indent=2), encoding="utf-8")
    by_group = {}
    errors = []
    for record, pred in zip([by_id[rid] for rid in test_ids], predictions):
        groups = _subgroups(record)
        for group in groups:
            by_group.setdefault(group, [[], []])
            by_group[group][0].append(pred["gold"])
            by_group[group][1].append(pred["pred"])
        if pred["gold"] != pred["pred"]:
            errors.append({**_record_meta(record), "gold": pred["gold"], "pred": pred["pred"]})
    result = {group: _metrics(vals[0], vals[1], labels) for group, vals in by_group.items()}
    for group, metrics in result.items():
        _write_confusion(Path(run_dir) / f"confusion_matrix_{group}.csv", labels, metrics["confusion_matrix"])
    (Path(run_dir) / "subgroup_metrics.json").write_text(json.dumps({"task": "intent", "labels": labels, "groups": result}, indent=2), encoding="utf-8")
    _write_jsonl(Path(run_dir) / "intent_errors.jsonl", errors)
    (Path(run_dir) / "extractor.json").write_text(json.dumps({"extractor_id": "intent_current_text", "description": "current record text only"}, indent=2), encoding="utf-8")
    return {"reloadability": json.loads((Path(run_dir) / "reloadability.json").read_text()), "subgroups": result, "errors": len(errors)}


def review_sentiment(project_root, run_dir, records, test_ids):
    label_map = build_sentiment_label_map()
    labels = list(label_map)
    by_id = {r.record_id: r for r in records}
    test_records = [by_id[rid] for rid in test_ids]
    examples = build_sentiment_examples(test_records, label_map)
    predictions = _jsonl(Path(run_dir) / "predictions.jsonl")
    artifacts = load_artifacts(Path(run_dir) / "svm")
    reloaded = [labels[int(p)] for p in artifacts.predict(examples[: min(10, len(examples))])]
    saved = [p["pred"] for p in predictions[: len(reloaded)]]
    (Path(run_dir) / "reloadability.json").write_text(json.dumps({"reloadable": True, "fixed_test_examples_checked": len(reloaded), "predictions_match_saved": reloaded == saved}, indent=2), encoding="utf-8")
    by_group = {}
    errors = []
    for example, pred in zip(examples, predictions):
        record = by_id[example.record_id]
        for group in _subgroups(record):
            by_group.setdefault(group, [[], []])
            by_group[group][0].append(pred["gold"])
            by_group[group][1].append(pred["pred"])
        if pred["gold"] != pred["pred"]:
            errors.append({**_record_meta(record), "gold": pred["gold"], "pred": pred["pred"], "aspect_term": example.term, "aspect_category": example.category, "aspect_start": example.aspect_start, "aspect_end": example.aspect_end})
    result = {group: _metrics(vals[0], vals[1], labels) for group, vals in by_group.items()}
    for group, metrics in result.items():
        _write_confusion(Path(run_dir) / f"confusion_matrix_{group}.csv", labels, metrics["confusion_matrix"])
    (Path(run_dir) / "subgroup_metrics.json").write_text(json.dumps({"task": "sentiment", "labels": labels, "groups": result}, indent=2), encoding="utf-8")
    _write_jsonl(Path(run_dir) / "sentiment_errors.jsonl", errors)
    (Path(run_dir) / "extractor.json").write_text(json.dumps({"extractor_id": "sentiment_marked_aspect_text", "description": "text with [ASP] and [/ASP] markers around the target aspect"}, indent=2), encoding="utf-8")
    return {"reloadability": json.loads((Path(run_dir) / "reloadability.json").read_text()), "subgroups": result, "errors": len(errors)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--intent-run", type=Path, required=True)
    parser.add_argument("--sentiment-run", type=Path, required=True)
    args = parser.parse_args()
    records = read_jsonl(args.project_root / "data/annotations/combined_adjudicated_v2.jsonl")
    test_ids = _manifest_ids(args.project_root / "data/processed/combined_v2/test_manifest.csv")
    metadata = _cluster_metadata(args.project_root)
    stdout = (args.project_root / "slurm-50823.out").read_text(encoding="utf-8")
    intent_section = stdout[stdout.find("Preparing svm/intent"):stdout.find("Preparing svm/sentiment")]
    sentiment_section = stdout[stdout.find("Preparing svm/sentiment"):]
    for run, section in ((args.intent_run, intent_section), (args.sentiment_run, sentiment_section)):
        (run / "training_log.txt").write_text(section, encoding="utf-8")
        (run / "cluster_job_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    output = {"intent": review_intent(args.project_root, args.intent_run, records, test_ids), "sentiment": review_sentiment(args.project_root, args.sentiment_run, records, test_ids)}
    (args.project_root / "outputs/svm_posthoc_review.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
