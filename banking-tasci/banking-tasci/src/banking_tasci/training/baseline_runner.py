"""Post-readiness baseline training orchestration (Phase 3A, Part 11).

Reached ONLY after the supervised-training readiness gate passes (adjudicated
gold + leakage-safe manifests exist). Loads the split records, builds the
task-specific datasets, trains the selected baseline, selects on VALIDATION
macro-F1 (never test), evaluates on the held-out test split AFTER selection,
and writes all artifacts to a fresh run directory.

    Never fabricates labels, predictions, or metrics: every number comes from real
model outputs over real gold labels. BERT uses the local offline checkpoint and
the shared validation-selected training loop, just like the BiLSTM path.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from banking_tasci.data.annotations import AnnotationRecord, read_jsonl
from banking_tasci.data.datasets import (
    INTENT_MODE_CURRENT_ONLY,
    INTENT_MODE_PREVIOUS_PLUS_CURRENT,
    build_intent_examples,
    build_intent_label_map,
    build_sentiment_examples,
    build_sentiment_label_map,
)
from banking_tasci.evaluation.metrics import classification_metrics
from banking_tasci.training.reproducibility import RunArtifacts, new_run_dir, write_run

_SPLIT_MANIFESTS = {
    "train": "train_manifest.csv",
    "validation": "validation_manifest.csv",
    "test": "test_manifest.csv",
}


def _read_manifest_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rid = row.get("record_id")
            if rid:
                ids.append(str(rid))
    return ids


def load_split_records(
    annotations_path: "str | Path", split_dir: "str | Path"
) -> "dict[str, list[AnnotationRecord]]":
    """Return ``{split: [records]}`` by joining the adjudicated gold file to
    each split manifest's record ids (order preserved)."""
    records = read_jsonl(annotations_path)
    by_id = {
        str(getattr(r, "record_id", "")): r
        for r in records
        if isinstance(getattr(r, "record_id", None), str)
    }
    split_dir = Path(split_dir)
    out: dict[str, list[AnnotationRecord]] = {}
    for split, name in _SPLIT_MANIFESTS.items():
        ids = _read_manifest_ids(split_dir / name)
        out[split] = [by_id[i] for i in ids if i in by_id]
    return out


def _cfg_get(cfg, dotted: str, default=None):
    cur = cfg
    for part in dotted.split("."):
        try:
            if part in cur:
                cur = cur[part]
                continue
        except TypeError:
            pass
        cur = getattr(cur, part, None)
        if cur is None:
            return default
    return default if cur is None else cur


# ---------------------------------------------------------------------------
# SVM training
# ---------------------------------------------------------------------------


def _svm_cfg_dict(cfg) -> dict:
    svm = _cfg_get(cfg, "svm", {}) or {}
    # Config wraps nested dicts; normalise to a plain dict for the pipeline.
    try:
        return svm.to_dict()  # Config
    except AttributeError:
        return dict(svm)


def _train_svm(model_task: str, cfg, splits, run_dir: Path, seed, split_dir, logger) -> int:
    from banking_tasci.models.svm_baseline import (
        build_intent_context_pipeline,
        build_intent_pipeline,
        build_sentiment_pipeline,
        fit_and_select,
        intent_context_text,
        intent_text,
        save_artifacts,
        sentiment_text,
    )

    svm_cfg = _svm_cfg_dict(cfg)

    if model_task == "intent":
        label_map = build_intent_label_map()
        train_ex = build_intent_examples(splits["train"], label_map)
        val_ex = build_intent_examples(splits["validation"], label_map)
        test_ex = build_intent_examples(splits["test"], label_map)
        mode = _cfg_get(cfg, "intent_mode", INTENT_MODE_CURRENT_ONLY)
        if mode == INTENT_MODE_PREVIOUS_PLUS_CURRENT:
            pipeline = build_intent_context_pipeline(svm_cfg)
            text_fn = intent_context_text
        else:
            pipeline = build_intent_pipeline(svm_cfg)
            text_fn = intent_text
    else:  # sentiment
        label_map = build_sentiment_label_map()
        train_ex = build_sentiment_examples(splits["train"], label_map)
        val_ex = build_sentiment_examples(splits["validation"], label_map)
        test_ex = build_sentiment_examples(splits["test"], label_map)
        pipeline = build_sentiment_pipeline(svm_cfg)
        text_fn = sentiment_text

    id_to_label = {v: k for k, v in label_map.items()}
    artifacts = fit_and_select(
        pipeline, train_ex, val_ex, text_fn=text_fn, label_map=label_map,
        config={"model": "svm", "task": model_task, **svm_cfg},
    )

    # Evaluate on the held-out TEST split AFTER selection (never before).
    test_labels = [int(ex.label_id) for ex in test_ex]
    test_preds = [int(p) for p in artifacts.predict(test_ex)]
    metrics = {
        "selection": artifacts.metrics,
        "test": classification_metrics(
            test_labels, test_preds, num_classes=len(label_map), id_to_label=id_to_label
        ),
    }
    predictions = [
        {"record_id": ex.record_id, "gold": id_to_label[gold], "pred": id_to_label[pred]}
        for ex, gold, pred in zip(test_ex, test_labels, test_preds)
    ]

    save_artifacts(artifacts, run_dir / "svm")
    write_run(
        RunArtifacts(
            config={"model": "svm", "task": model_task, **svm_cfg},
            label_maps={model_task: label_map},
            metrics=metrics,
            predictions=predictions,
            split_dir=split_dir,
            seed=seed,
        ),
        run_dir,
    )
    logger.info("SVM %s baseline complete; artifacts in %s", model_task, run_dir)
    return 0


# ---------------------------------------------------------------------------
# BiLSTM training
# ---------------------------------------------------------------------------


def _train_bilstm(model_task: str, cfg, splits, run_dir: Path, seed, split_dir, logger) -> int:
    from banking_tasci.models.bilstm_baseline import (
        INTENT_TASK, SENTIMENT_TASK, BiLSTMClassifier, BiLSTMConfig,
        build_vocab, collate_intent_batch, collate_sentiment_batch, encode,
        make_forward_fn,
    )
    from banking_tasci.training.loop import (
        TrainConfig,
        build_checkpoint,
        load_checkpoint,
        save_checkpoint,
        train_model,
    )

    bl = _cfg_get(cfg, "bilstm", {}) or {}
    tr = _cfg_get(cfg, "train", {}) or {}

    def g(section, key, default):
        try:
            return section[key] if key in section else default
        except TypeError:
            return getattr(section, key, default)

    if model_task == "intent":
        label_map = build_intent_label_map()
        train_ex = build_intent_examples(splits["train"], label_map)
        val_ex = build_intent_examples(splits["validation"], label_map)
        test_ex = build_intent_examples(splits["test"], label_map)
        vocab = build_vocab([ex.text for ex in train_ex])

        def batch_of(exs):
            seqs = [encode(ex.text, vocab) or [0] for ex in exs]
            return collate_intent_batch(seqs, [int(ex.label_id) for ex in exs])

        task, use_aspect = INTENT_TASK, False
    else:
        label_map = build_sentiment_label_map()
        train_ex = build_sentiment_examples(splits["train"], label_map)
        val_ex = build_sentiment_examples(splits["validation"], label_map)
        test_ex = build_sentiment_examples(splits["test"], label_map)
        vocab = build_vocab([ex.marked_text for ex in train_ex])

        def batch_of(exs):
            seqs, masks, labels = [], [], []
            for ex in exs:
                tokens = ex.marked_text.split()
                ids = [vocab.get(token, 0) for token in tokens] or [0]
                mask = [
                    1 if token not in ("[ASP]", "[/ASP]") and _in_marked(tokens, index) else 0
                    for index, token in enumerate(tokens)
                ] or [0]
                seqs.append(ids)
                masks.append(mask)
                labels.append(int(ex.label_id))
            return collate_sentiment_batch(seqs, labels, masks)

        task, use_aspect = SENTIMENT_TASK, True

    id_to_label = {value: key for key, value in label_map.items()}
    train_batches, val_batches = [batch_of(train_ex)], [batch_of(val_ex)]
    model = BiLSTMClassifier(BiLSTMConfig(
        vocab_size=len(vocab) + 1,
        num_classes=len(label_map),
        embedding_dim=int(g(bl, "embedding_dim", 100)),
        hidden_dim=int(g(bl, "hidden_dim", 128)),
        num_layers=int(g(bl, "num_layers", 1)),
        dropout=float(g(bl, "dropout", 0.3)),
        use_aspect_pooling=use_aspect,
    ))
    train_cfg = TrainConfig(
        epochs=int(g(tr, "epochs", 30)),
        learning_rate=float(g(tr, "learning_rate", 1e-3)),
        weight_decay=float(g(tr, "weight_decay", 0.0)),
        grad_clip=g(tr, "grad_clip", 1.0),
        early_stopping_patience=int(g(tr, "early_stopping_patience", 5)),
        device=str(g(tr, "device", "cpu")), seed=int(seed),
    )
    result = train_model(
        model, train_batches, val_batches, num_classes=len(label_map),
        cfg=train_cfg, forward_fn=make_forward_fn(task), label_mapping=label_map,
    )

    import torch
    model.load_state_dict(result.best_state_dict)
    test_batch = batch_of(test_ex)
    with torch.no_grad():
        logits, labels = make_forward_fn(task)(model, test_batch)
        preds, gold = torch.argmax(logits, dim=-1).tolist(), labels.tolist()
    metrics = {
        "best_val_macro_f1": result.best_val_macro_f1,
        "best_epoch": result.best_epoch,
        "history": result.history,
        "test": classification_metrics(gold, preds, num_classes=len(label_map), id_to_label=id_to_label),
    }
    predictions = [
        {"record_id": ex.record_id, "gold": id_to_label[gold_id], "pred": id_to_label[pred_id]}
        for ex, gold_id, pred_id in zip(test_ex, gold, preds)
    ]

    best_ckpt = build_checkpoint(
        model=model, optimizer=None, epoch=result.best_epoch,
        best_validation_macro_f1=result.best_val_macro_f1,
        epochs_without_improvement=result.epochs_without_improvement,
        training_config=train_cfg, label_mapping=label_map,
    )
    best_ckpt["optimizer_state_dict"] = result.best_optimizer_state_dict
    save_checkpoint(best_ckpt, run_dir / "best_checkpoint.pt")
    model.load_state_dict(result.last_state_dict)
    last_ckpt = build_checkpoint(
        model=model, optimizer=None, epoch=result.last_epoch,
        best_validation_macro_f1=result.best_val_macro_f1,
        epochs_without_improvement=result.epochs_without_improvement,
        training_config=train_cfg, label_mapping=label_map,
    )
    last_ckpt["optimizer_state_dict"] = result.last_optimizer_state_dict
    save_checkpoint(last_ckpt, run_dir / "last_checkpoint.pt")
    model.load_state_dict(result.best_state_dict)

    training_log = "\n".join(
        "epoch {epoch} | train_loss={train_loss:.6f} | val_macro_f1={val_macro_f1:.6f}".format(**row)
        for row in result.history
    ) + "\n"
    write_run(RunArtifacts(
        config={"model": "bilstm", "task": model_task, "seed": int(seed), "train": dict(train_cfg.__dict__)},
        label_maps={model_task: label_map}, metrics=metrics, predictions=predictions,
        split_dir=split_dir, seed=seed, training_log=training_log,
    ), run_dir)
    save_checkpoint(best_ckpt, run_dir / "best_checkpoint.pt")
    save_checkpoint(last_ckpt, run_dir / "last_checkpoint.pt")
    loaded_best = load_checkpoint(run_dir / "best_checkpoint.pt")
    reload_model = BiLSTMClassifier(model.cfg)
    reload_model.load_state_dict(loaded_best["model_state_dict"])
    reload_model.eval()
    with torch.no_grad():
        reloaded_logits, _ = make_forward_fn(task)(reload_model, test_batch)
        reloaded_preds = torch.argmax(reloaded_logits, dim=-1).tolist()
    (run_dir / "reload_verification.json").write_text(
        json.dumps(
            {
                "reloadable": True,
                "test_examples_checked": len(preds),
                "predictions_match_saved": reloaded_preds == preds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_bilstm_posthoc_artifacts(run_dir, task, label_map, test_ex, gold, preds, metrics, splits)
    logger.info("BiLSTM %s baseline complete; artifacts in %s", model_task, run_dir)
    return 0


def _in_marked(tokens: "list[str]", i: int) -> bool:
    """True when token index ``i`` lies between an [ASP] and the next [/ASP]."""
    depth = 0
    for j, tok in enumerate(tokens):
        if tok == "[ASP]":
            depth += 1
            continue
        if tok == "[/ASP]":
            depth -= 1
            continue
        if j == i:
            return depth > 0
    return False


def _write_bilstm_posthoc_artifacts(run_dir, task, label_map, test_examples, gold, preds, metrics, splits):
    id_to_label = {value: key for key, value in label_map.items()}
    (run_dir / "validation_metrics.json").write_text(json.dumps({
        "best_val_macro_f1": metrics["best_val_macro_f1"],
        "best_epoch": metrics["best_epoch"],
        "history": metrics["history"],
    }, indent=2), encoding="utf-8")
    (run_dir / "test_metrics.json").write_text(json.dumps(metrics["test"], indent=2), encoding="utf-8")
    labels = list(label_map)
    with (run_dir / "confusion_matrix.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["gold\\pred", *labels])
        for label, row in zip(labels, metrics["test"]["confusion_matrix"]):
            writer.writerow([label, *row])

    records_by_id = {record.record_id: record for record in splits["test"]}
    groups: dict[str, list[list[int]]] = {}
    for example, gold_id, pred_id in zip(test_examples, gold, preds):
        record = records_by_id[example.record_id]
        names = ["combined", "international" if record.region == "international" else "south_africa",
                 "context_available" if record.context_available else "no_context",
                 "reviews" if record.source == "bank_reviews" else "tweets"]
        for name in names:
            groups.setdefault(name, [[], []])
            groups[name][0].append(int(gold_id))
            groups[name][1].append(int(pred_id))
    subgroup_metrics = {
        name: classification_metrics(values[0], values[1], num_classes=len(label_map), id_to_label=id_to_label)
        for name, values in groups.items()
    }
    (run_dir / "subgroup_metrics.json").write_text(json.dumps({"task": task, "labels": labels, "groups": subgroup_metrics}, indent=2), encoding="utf-8")
    (run_dir / "cluster_job_metadata.json").write_text(json.dumps({
        "slurm_job_id": __import__("os").environ.get("SLURM_JOB_ID"),
        "partition": __import__("os").environ.get("SLURM_JOB_PARTITION"),
        "state": "COMPLETED",
        "readiness": "READY",
    }, indent=2), encoding="utf-8")
# NOTE: a second, divergent definition of `_write_bilstm_posthoc_artifacts`
# previously appeared here. It shadowed the definition above and took an extra
# leading `model` parameter that it never used, so the 8-argument call site in
# `_train_bilstm` bound `splits` into `metrics` and left `splits` unfilled,
# raising "TypeError: _write_bilstm_posthoc_artifacts() missing 1 required
# positional argument: 'splits'". It also omitted `cluster_job_metadata.json`
# (an artifact documented in docs/phase_3b_svm_baseline_report.md) and resolved
# test records with an O(n^2) linear scan. The duplicate was removed; the
# definition above is authoritative and matches the call site.


# BERT training (requires transformers + a LOCAL pretrained model)
# ---------------------------------------------------------------------------

def _train_bert(model_task: str, cfg, splits, run_dir: Path, seed, split_dir, logger) -> int:
    import torch
    from banking_tasci.models.bert_baseline import (
        BertBaselineConfig,
        INTENT_TASK,
        SENTIMENT_TASK,
        build_model,
        load_tokenizer,
    )
    from banking_tasci.training.loop import TrainConfig, build_checkpoint, save_checkpoint, train_model

    bert_cfg = _cfg_get(cfg, "bert", {}) or {}
    train_cfg = _cfg_get(cfg, "train", {}) or {}

    def g(section, key, default):
        try:
            return section[key] if key in section else default
        except TypeError:
            return getattr(section, key, default)

    label_map = (
        build_intent_label_map()
        if model_task == "intent"
        else build_sentiment_label_map()
    )
    if model_task == "intent":
        train_examples = build_intent_examples(splits["train"], label_map)
        val_examples = build_intent_examples(splits["validation"], label_map)
        test_examples = build_intent_examples(splits["test"], label_map)
        task = INTENT_TASK
        texts = lambda examples: [example.text for example in examples]
    else:
        train_examples = build_sentiment_examples(splits["train"], label_map)
        val_examples = build_sentiment_examples(splits["validation"], label_map)
        test_examples = build_sentiment_examples(splits["test"], label_map)
        task = SENTIMENT_TASK
        texts = lambda examples: [example.marked_text for example in examples]

    bert = BertBaselineConfig(
        pretrained_path=str(g(bert_cfg, "pretrained_path", "")),
        task=task,
        num_labels=len(label_map),
        max_seq_length=int(g(bert_cfg, "max_seq_length", 128)),
        local_files_only=bool(g(bert_cfg, "local_files_only", True)),
        add_marker_tokens=bool(g(bert_cfg, "add_marker_tokens", True)),
    )
    tokenizer = load_tokenizer(bert)
    model = build_model(bert, tokenizer)

    def batch_of(examples):
        encoded = tokenizer(
            texts(examples),
            padding=True,
            truncation=True,
            max_length=bert.max_seq_length,
            return_tensors="pt",
        )
        encoded["labels"] = torch.tensor(
            [int(example.label_id) for example in examples], dtype=torch.long
        )
        return encoded

    def forward(model_instance, batch):
        device = next(model_instance.parameters()).device
        labels = batch["labels"].to(device)
        inputs = {
            key: value.to(device)
            for key, value in batch.items()
            if key != "labels"
        }
        return model_instance(**inputs).logits, labels

    class_weights = None
    if bool(g(train_cfg, "class_weighted_loss", False)):
        counts = [0] * len(label_map)
        for example in train_examples:
            counts[int(example.label_id)] += 1
        total = sum(counts)
        class_weights = [
            total / (len(counts) * count) if count else 0.0
            for count in counts
        ]

    train_options = TrainConfig(
        epochs=int(g(train_cfg, "epochs", 4)),
        learning_rate=float(g(train_cfg, "learning_rate", 3e-5)),
        weight_decay=float(g(train_cfg, "weight_decay", 0.01)),
        grad_clip=g(train_cfg, "grad_clip", 1.0),
        early_stopping_patience=int(g(train_cfg, "early_stopping_patience", 2)),
        class_weights=class_weights,
        device=str(g(train_cfg, "device", "cpu")),
        seed=int(seed),
    )
    train_batches = [batch_of(train_examples)]
    val_batches = [batch_of(val_examples)]
    result = train_model(
        model,
        train_batches,
        val_batches,
        num_classes=len(label_map),
        cfg=train_options,
        forward_fn=forward,
        label_mapping=label_map,
    )

    model.load_state_dict(result.best_state_dict)
    model.eval()
    with torch.no_grad():
        logits, labels = forward(model, batch_of(test_examples))
        predictions_ids = torch.argmax(logits, dim=-1).tolist()
        gold_ids = labels.tolist()

    id_to_label = {value: key for key, value in label_map.items()}
    metrics = {
        "best_val_macro_f1": result.best_val_macro_f1,
        "best_epoch": result.best_epoch,
        "history": result.history,
        "test": classification_metrics(
            gold_ids,
            predictions_ids,
            num_classes=len(label_map),
            id_to_label=id_to_label,
        ),
    }
    predictions = [
        {"record_id": example.record_id, "gold": id_to_label[gold], "pred": id_to_label[pred]}
        for example, gold, pred in zip(test_examples, gold_ids, predictions_ids)
    ]
    checkpoint = build_checkpoint(
        model=model,
        optimizer=None,
        epoch=result.last_epoch,
        best_validation_macro_f1=result.best_val_macro_f1,
        epochs_without_improvement=result.epochs_without_improvement,
        training_config=train_options,
        label_mapping=label_map,
    )
    save_checkpoint(checkpoint, run_dir / "best_checkpoint.pt")
    training_log = "\n".join(
        "epoch {epoch} | train_loss={train_loss:.6f} | val_macro_f1={val_macro_f1:.6f}".format(**row)
        for row in result.history
    ) + "\n"
    write_run(
        RunArtifacts(
            config={"model": "bert", "task": model_task, "bert": dict(bert.__dict__)},
            label_maps={model_task: label_map},
            metrics=metrics,
            best_state_dict=result.best_state_dict,
            predictions=predictions,
            training_log=training_log,
            split_dir=split_dir,
            seed=seed,
        ),
        run_dir,
    )
    logger.info("BERT %s baseline complete; artifacts in %s", model_task, run_dir)
    return 0


def run_baseline(model, task, cfg, annotations_path, split_dir, runs_root, logger) -> int:
    """Dispatch to the model-specific trainer after readiness has passed."""
    splits = load_split_records(annotations_path, split_dir)
    seed = _cfg_get(cfg, "seed", 42)
    run_dir = new_run_dir(runs_root)
    logger.info("Run directory: %s", run_dir)

    if model == "svm":
        return _train_svm(task, cfg, splits, run_dir, seed, split_dir, logger)
    if model == "bilstm":
        return _train_bilstm(task, cfg, splits, run_dir, seed, split_dir, logger)
    if model == "bert":
        return _train_bert(task, cfg, splits, run_dir, seed, split_dir, logger)
    logger.error("unknown model '%s'", model)
    return 2

