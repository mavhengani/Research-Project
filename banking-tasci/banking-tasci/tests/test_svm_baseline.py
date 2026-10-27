"""Fit/predict wiring tests for the SVM baselines
(src/banking_tasci/models/svm_baseline.py), Phase 3A (Requirements 34, 38, 39.3).

These are ARCHITECTURE / WIRING sanity checks on tiny synthetic labelled
fixtures constructed in-test (~6-12 examples, >=2 classes). They deliberately
report NO research metric or accuracy — they only confirm the pipelines are
wired correctly:

- the intent pipeline fits current text only and predicts in-vocabulary labels
  (Req 34.1);
- the sentiment pipeline consumes ``[ASP]...[/ASP]``-marked text and predicts
  valid sentiment labels (Req 34.3, 38);
- selection uses validation macro-F1 (Req 34.5);
- no forbidden metadata feature (rating/region/source/bank/title) can enter the
  vectoriser — the pipeline's input is a flat list of text strings (Req 34.4);
- ``save_artifacts`` writes reloadable files (Req 34.7).

The whole module is guarded by ``pytest.importorskip("sklearn")`` so the suite
skips cleanly when scikit-learn is absent (Req 34.8).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import (  # noqa: E402
    ASPECT_SENTIMENTS,
    INTENT_LABELS,
    AnnotationRecord,
    AspectSpan,
)
from banking_tasci.data.datasets import (  # noqa: E402
    ASP_CLOSE,
    ASP_OPEN,
    build_intent_examples,
    build_intent_label_map,
    build_sentiment_examples,
    build_sentiment_label_map,
)
from banking_tasci.models.svm_baseline import (  # noqa: E402
    CLASSIFIER_STEP,
    INTENT_CONTEXT,
    INTENT_CURRENT,
    SENTIMENT_ASPECT_MARKED,
    VECTORIZER_STEP,
    SvmArtifacts,
    build_intent_context_pipeline,
    build_intent_pipeline,
    build_sentiment_pipeline,
    fit_and_select,
    intent_context_text,
    load_artifacts,
    resolve_extractor,
    save_artifacts,
    sentiment_text,
)


# ---------------------------------------------------------------------------
# Synthetic fixture builders. The only signal lives in `text`; metadata
# fields are constant across classes so they carry no class information and
# could never make the classifier work if they leaked in.
# ---------------------------------------------------------------------------


def _record(
    *,
    record_id: str,
    text: str,
    intent: str = "complaint",
    aspects: list[AspectSpan] | None = None,
    previous_text: str = "[NO_CONTEXT]",
    context_available: bool = False,
) -> AnnotationRecord:
    return AnnotationRecord(
        record_id=record_id,
        source="bank_reviews",
        region="local",
        text=text,
        previous_text=previous_text,
        context_available=context_available,
        aspects=aspects if aspects is not None else [],
        intent=intent,
        intent_ambiguous=False,
        alternative_intent=None,
        annotator_id="annotator_a",
        annotation_status="completed",
        notes="",
    )


def _intent_records() -> list[AnnotationRecord]:
    """~8 records over two clearly-separable intent classes (text signal only)."""
    complaint = INTENT_LABELS[INTENT_LABELS.index("complaint")]
    compliment = INTENT_LABELS[INTENT_LABELS.index("compliment")]
    rows = [
        ("r1", "the app keeps crashing and it is terrible", complaint),
        ("r2", "awful slow broken service i am angry", complaint),
        ("r3", "horrible experience the fees are unfair", complaint),
        ("r4", "the queue was slow and frustrating today", complaint),
        ("r5", "excellent friendly staff wonderful service", compliment),
        ("r6", "great fast helpful and lovely experience", compliment),
        ("r7", "amazing support thank you so much brilliant", compliment),
        ("r8", "wonderful helpful team fantastic branch visit", compliment),
    ]
    return [_record(record_id=rid, text=txt, intent=lbl) for rid, txt, lbl in rows]


def _sentiment_records() -> list[AnnotationRecord]:
    """Records whose gold aspects give a clear positive/negative signal in the
    marked term's surrounding text."""

    def span(text: str, term: str, sentiment: str) -> AnnotationRecord:
        start = text.index(term)
        end = start + len(term)
        aspect = AspectSpan(
            term=term, start=start, end=end, category="cards", sentiment=sentiment
        )
        return _record(
            record_id=f"s-{term}-{sentiment}",
            text=text,
            aspects=[aspect],
        )

    neg = "negative"
    pos = "positive"
    return [
        span("the fees are terrible and unfair", "fees", neg),
        span("awful fees that are far too high", "fees", neg),
        span("the fees felt horrible and excessive", "fees", neg),
        span("the staff were excellent and kind", "staff", pos),
        span("wonderful helpful staff at the branch", "staff", pos),
        span("the staff were friendly and great", "staff", pos),
    ]


# ---------------------------------------------------------------------------
# Req 34.1 — intent pipeline predicts valid in-vocabulary labels.
# ---------------------------------------------------------------------------


def test_intent_pipeline_predicts_valid_labels():
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    assert len(examples) >= 6

    # Split train/val (selection by validation macro-F1 only, Req 34.5).
    train = examples[:6]
    val = examples[6:]

    artifacts = fit_and_select(
        build_intent_pipeline(cfg=None),
        train,
        val,
        label_map=label_map,
    )
    assert isinstance(artifacts, SvmArtifacts)

    valid_ids = set(label_map.values())
    preds = artifacts.predict(val)
    assert preds, "expected at least one prediction"
    assert all(int(p) in valid_ids for p in preds)


def test_intent_context_variant_is_text_only_and_predicts():
    """The context-aware variant joins previous_text + current text (Req 34.2)
    and still only ever sees text strings (Req 34.4)."""
    label_map = build_intent_label_map()
    recs = _intent_records()
    # Give a couple of records a real previous turn to exercise the join.
    recs[0] = _record(
        record_id="rc1",
        text=recs[0].text,
        intent=recs[0].intent,
        previous_text="earlier the app was fine",
        context_available=True,
    )
    examples = build_intent_examples(recs, label_map)
    train, val = examples[:6], examples[6:]

    artifacts = fit_and_select(
        build_intent_context_pipeline(cfg=None),
        train,
        val,
        text_fn=intent_context_text,
        label_map=label_map,
    )
    valid_ids = set(label_map.values())
    assert all(int(p) in valid_ids for p in artifacts.predict(val))


# ---------------------------------------------------------------------------
# Req 34.3 / 38 — sentiment pipeline consumes marked text.
# ---------------------------------------------------------------------------


def test_sentiment_pipeline_consumes_marked_text_and_predicts():
    label_map = build_sentiment_label_map()
    examples = build_sentiment_examples(_sentiment_records(), label_map)
    assert len(examples) == 6

    # Every input the sentiment baseline sees is the [ASP]...[/ASP] marked text.
    for ex in examples:
        assert ASP_OPEN in ex.marked_text and ASP_CLOSE in ex.marked_text

    train, val = examples[:4], examples[4:]
    artifacts = fit_and_select(
        build_sentiment_pipeline(cfg=None),
        train,
        val,
        label_map=label_map,
    )
    # The selected extractor pulls marked_text (not raw text).
    assert artifacts.text_fn(examples[0]) == examples[0].marked_text

    valid_ids = set(label_map.values())
    preds = artifacts.predict(val)
    assert preds and all(int(p) in valid_ids for p in preds)


# ---------------------------------------------------------------------------
# Req 34.5 — selection uses validation macro-F1.
# ---------------------------------------------------------------------------


def test_selection_uses_validation_macro_f1():
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    train, val = examples[:6], examples[6:]

    # Provide two named candidates so selection has something to choose from.
    candidates = {
        "unigram": build_intent_pipeline(cfg={"ngram_range": (1, 1)}),
        "bigram": build_intent_pipeline(cfg={"ngram_range": (1, 2)}),
    }
    artifacts = fit_and_select(candidates, train, val, label_map=label_map)

    metrics = artifacts.metrics
    assert metrics["selection_metric"] == "val_macro_f1"
    assert "val_macro_f1" in metrics
    assert set(metrics["candidates"]) == {"unigram", "bigram"}
    # The selected candidate must be the argmax over validation macro-F1.
    best = max(metrics["candidates"].items(), key=lambda kv: kv[1])[0]
    assert metrics["selected_candidate"] == best
    assert metrics["val_macro_f1"] == metrics["candidates"][best]


def test_fit_and_select_requires_validation_split():
    """Selection is by validation macro-F1 only; an empty val split is an
    error (the test split must never stand in for it, Req 34.5)."""
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    with pytest.raises(ValueError):
        fit_and_select(build_intent_pipeline(), examples, [], label_map=label_map)


# ---------------------------------------------------------------------------
# Req 34.4 — no forbidden metadata feature enters the vectoriser.
# ---------------------------------------------------------------------------


def test_no_metadata_feature_enters_vectorizer():
    """Structural guarantee: the fitted vectoriser's vocabulary is built purely
    from the token text of the examples — never from rating/region/source/bank/
    title. We assert (a) the pipeline input is a flat list of str and (b) the
    learned vocabulary is a subset of the whitespace tokens of the example
    texts, so no metadata value could have leaked into the features."""
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    train, val = examples[:6], examples[6:]

    artifacts = fit_and_select(
        build_intent_pipeline(cfg={"ngram_range": (1, 1)}),
        train,
        val,
        label_map=label_map,
    )

    vectorizer = artifacts.pipeline.named_steps[VECTORIZER_STEP]
    vocab = set(vectorizer.vocabulary_.keys())

    # Every vocabulary term must come from the (lowercased) example texts.
    text_tokens: set[str] = set()
    for ex in train:
        text_tokens.update(ex.text.lower().split())
    assert vocab.issubset(text_tokens)

    # Forbidden metadata values must NOT appear as features.
    forbidden = {"bank_reviews", "local", "annotator_a", "bank_reviews3"}
    assert vocab.isdisjoint(forbidden)


# ---------------------------------------------------------------------------
# Req 34.6 — raw decision scores vs. calibrated probabilities.
# ---------------------------------------------------------------------------


def test_decision_scores_are_raw_and_no_uncalibrated_proba():
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    train, val = examples[:6], examples[6:]
    artifacts = fit_and_select(build_intent_pipeline(), train, val, label_map=label_map)

    # Raw decision scores are available and labelled as such.
    scores = artifacts.decision_function(val)
    assert scores is not None
    # A plain LinearSVC must NOT expose probabilities (uncalibrated scores are
    # never presented as probabilities, Req 34.6).
    with pytest.raises(AttributeError):
        artifacts.predict_proba(val)


# ---------------------------------------------------------------------------
# Req 34.7 — save_artifacts writes reloadable files.
# ---------------------------------------------------------------------------


def test_save_and_reload_artifacts(tmp_path):
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    train, val = examples[:6], examples[6:]
    artifacts = fit_and_select(
        build_intent_pipeline(),
        train,
        val,
        label_map=label_map,
        config={"model": "svm", "task": "intent"},
    )

    out_dir = tmp_path / "svm_run"
    written = save_artifacts(artifacts, out_dir)

    for name in ("model", "vectorizer", "label_encoder", "config", "metrics"):
        assert written[name].exists(), f"missing artifact: {name}"

    reloaded = load_artifacts(out_dir)
    assert reloaded.config == {"model": "svm", "task": "intent"}
    assert reloaded.metrics["selection_metric"] == "val_macro_f1"

    # Reloaded pipeline predicts identically to the in-memory one.
    texts = [ex.text for ex in val]
    original = list(artifacts.pipeline.predict(texts))
    restored = list(reloaded.pipeline.predict(texts))
    assert original == restored


# ---------------------------------------------------------------------------
# Part 3 — stable text-extractor persistence and reload equivalence.
# ---------------------------------------------------------------------------


def test_intent_current_extractor_id_is_persisted_and_restored(tmp_path):
    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    train, val = examples[:6], examples[6:]
    artifacts = fit_and_select(build_intent_pipeline(), train, val, label_map=label_map)
    assert artifacts.text_extractor_name == INTENT_CURRENT

    out_dir = tmp_path / "intent_current"
    save_artifacts(artifacts, out_dir)
    reloaded = load_artifacts(out_dir)
    assert reloaded.text_extractor_name == INTENT_CURRENT
    # Predictions via the example objects (not raw text) must be identical.
    assert artifacts.predict(val) == reloaded.predict(val)


def test_intent_context_extractor_id_is_restored_and_predicts_equally(tmp_path):
    label_map = build_intent_label_map()
    recs = _intent_records()
    recs[0] = _record(
        record_id="rc1",
        text=recs[0].text,
        intent=recs[0].intent,
        previous_text="earlier the app was fine",
        context_available=True,
    )
    examples = build_intent_examples(recs, label_map)
    train, val = examples[:6], examples[6:]
    artifacts = fit_and_select(
        build_intent_context_pipeline(),
        train,
        val,
        text_fn=intent_context_text,
        label_map=label_map,
    )
    assert artifacts.text_extractor_name == INTENT_CONTEXT

    out_dir = tmp_path / "intent_context"
    save_artifacts(artifacts, out_dir)
    reloaded = load_artifacts(out_dir)
    # The reloaded extractor must STILL join previous_text + current text, so it
    # behaves as the context model, not a current-text-only model.
    assert reloaded.text_extractor_name == INTENT_CONTEXT
    assert reloaded.text_fn is intent_context_text
    assert artifacts.predict(val) == reloaded.predict(val)


def test_sentiment_extractor_id_is_restored_and_marks_aspect(tmp_path):
    label_map = build_sentiment_label_map()
    examples = build_sentiment_examples(_sentiment_records(), label_map)
    train, val = examples[:4], examples[4:]
    artifacts = fit_and_select(build_sentiment_pipeline(), train, val, label_map=label_map)
    assert artifacts.text_extractor_name == SENTIMENT_ASPECT_MARKED

    out_dir = tmp_path / "sentiment"
    save_artifacts(artifacts, out_dir)
    reloaded = load_artifacts(out_dir)
    assert reloaded.text_extractor_name == SENTIMENT_ASPECT_MARKED
    assert reloaded.text_fn is sentiment_text
    # The reloaded extractor pulls marked_text (aspect stays marked).
    assert reloaded.text_fn(examples[0]) == examples[0].marked_text
    assert artifacts.predict(val) == reloaded.predict(val)


def test_unknown_extractor_metadata_raises_helpful_error(tmp_path):
    import json as _json

    from banking_tasci.models.svm_baseline import EXTRACTOR_FILE

    label_map = build_intent_label_map()
    examples = build_intent_examples(_intent_records(), label_map)
    train, val = examples[:6], examples[6:]
    artifacts = fit_and_select(build_intent_pipeline(), train, val, label_map=label_map)

    out_dir = tmp_path / "corrupt"
    save_artifacts(artifacts, out_dir)
    # Corrupt the extractor metadata with an unknown id.
    (out_dir / EXTRACTOR_FILE).write_text(
        _json.dumps({"text_extractor_name": "not_a_real_extractor"}), encoding="utf-8"
    )
    with pytest.raises(ValueError) as exc_info:
        load_artifacts(out_dir)
    assert "not_a_real_extractor" in str(exc_info.value)


def test_resolve_extractor_rejects_unknown_id():
    with pytest.raises(ValueError):
        resolve_extractor("nope")


