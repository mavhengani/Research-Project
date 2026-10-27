"""TF-IDF + LinearSVC baselines for intent and aspect-sentiment classification
(Phase 3A, Requirements 34 and 38).

This module provides the classical (non-neural) baselines described in
``design.md`` (``SVM_Baseline``). It intentionally stays thin: it wires
``scikit-learn`` primitives (``TfidfVectorizer`` + ``LinearSVC``) into named
pipelines over the model-ready examples produced by
``banking_tasci.data.datasets`` and selects any modelling choice **only** by
validation macro-F1 (never the test split, Req 34.5).

Design guardrails baked into this module:

- **Graceful degradation (Req 34.8).** ``scikit-learn`` is imported LAZILY
  inside the functions that need it. Importing this module never fails when
  sklearn is absent; a clear ``ImportError`` is raised only if a builder is
  actually called without sklearn installed. This keeps the whole test suite
  importable/collectable on machines without sklearn.

- **Text-only features, no metadata leakage (Req 34.1, 34.4).** The intent
  baseline is fit on the CURRENT review text only. The context-aware variant
  (Req 34.2) is a *separately named* builder that joins the previous turn's
  text with the current text. Neither the primary nor the context builder
  ever consumes ``rating``/``region``/``source``/``bank``/``title`` or any
  test labels. Feature extraction always sees a flat list of ``str`` — never
  a dict of metadata.

- **Sentiment over marked text (Req 34.3, 38).** The sentiment baseline is
  fit on the ``[ASP] term [/ASP]``-marked text produced by
  ``datasets.mark_aspect`` / ``datasets.build_sentiment_examples`` — one
  instance per gold aspect.

- **Raw scores vs. probabilities (Req 34.6).** ``SvmArtifacts.decision_function``
  returns the *raw, uncalibrated* ``LinearSVC`` decision scores and is
  documented/labelled as such. Probabilities are available ONLY through the
  clearly-separate calibrated variant (:func:`build_calibrated_intent_pipeline`
  / :func:`build_calibrated_sentiment_pipeline`, which wrap the SVM in
  ``CalibratedClassifierCV``). Uncalibrated decision scores are never
  presented as probabilities.

- **Selection by validation macro-F1 only (Req 34.5).** :func:`fit_and_select`
  fits every candidate on the train split, scores each on the VALIDATION
  split via ``banking_tasci.training.loop.macro_f1``, and keeps the best. The
  test split is never passed in and is never consulted.

- **Reproducible artifacts (Req 34.7).** :func:`save_artifacts` persists the
  fitted vectoriser, label encoder, and model with ``joblib`` and the config
  and metrics as JSON; :func:`load_artifacts` reloads them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from banking_tasci.evaluation.metrics import classification_metrics


def macro_f1(y_true: list[int], y_pred: list[int], num_classes: int) -> float:
    return classification_metrics(y_true, y_pred, num_classes)["macro_f1"]

# ---------------------------------------------------------------------------
# Named pipeline steps (kept as constants so tests/callers never hard-code the
# strings and can reach into ``pipeline.named_steps``).
# ---------------------------------------------------------------------------
VECTORIZER_STEP = "tfidf"
CLASSIFIER_STEP = "clf"

# Fallback text used for the context-aware variant when a previous turn is
# absent; mirrors the ``[NO_CONTEXT]`` sentinel used elsewhere in the loaders.
_NO_CONTEXT = "[NO_CONTEXT]"

# Artifact filenames written by :func:`save_artifacts`.
VECTORIZER_FILE = "vectorizer.joblib"
LABEL_ENCODER_FILE = "label_encoder.joblib"
MODEL_FILE = "model.joblib"
CONFIG_FILE = "config.json"
METRICS_FILE = "metrics.json"
EXTRACTOR_FILE = "extractor.json"


# ---------------------------------------------------------------------------
# Lazy sklearn import (Req 34.8)
# ---------------------------------------------------------------------------


def _require_sklearn():
    """Import and return the sklearn symbols this module needs, LAZILY.

    Raising here (rather than at module import time) is what gives the
    graceful-degradation behaviour of Req 34.8: importing
    ``banking_tasci.models.svm_baseline`` never hard-fails when sklearn is
    missing; only actually *building/fitting* a pipeline does, and with a
    clear, actionable message.
    """
    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import LabelEncoder
        from sklearn.svm import LinearSVC
    except ImportError as exc:  # pragma: no cover - exercised only w/o sklearn
        raise ImportError(
            "scikit-learn is required for the SVM baselines "
            "(banking_tasci.models.svm_baseline). Install it with "
            "`pip install scikit-learn` to build or fit these pipelines."
        ) from exc
    return {
        "CalibratedClassifierCV": CalibratedClassifierCV,
        "TfidfVectorizer": TfidfVectorizer,
        "Pipeline": Pipeline,
        "LabelEncoder": LabelEncoder,
        "LinearSVC": LinearSVC,
    }


# ---------------------------------------------------------------------------
# Config helpers — cfg may be a Config, a plain dict, or None.
# ---------------------------------------------------------------------------


def _cfg_get(cfg: Any, key: str, default: Any) -> Any:
    """Read ``key`` from a ``Config``/dict-like ``cfg`` with a default.

    Tolerates ``cfg is None`` and both attribute-style (``Config``) and
    item-style (dict) access so callers can pass whatever config surface they
    have without the builders caring.
    """
    if cfg is None:
        return default
    try:
        if key in cfg:  # works for dict and Config (__contains__)
            value = cfg[key]
            return default if value is None else value
    except TypeError:
        pass
    value = getattr(cfg, key, None)
    return default if value is None else value


def _tfidf_kwargs(cfg: Any) -> dict:
    """Assemble ``TfidfVectorizer`` kwargs from ``cfg`` with sane defaults.

    Only text-vectorisation knobs are read here; no metadata field is ever
    referenced (Req 34.4).
    """
    return {
        "lowercase": bool(_cfg_get(cfg, "lowercase", True)),
        "ngram_range": tuple(_cfg_get(cfg, "ngram_range", (1, 2))),
        "min_df": _cfg_get(cfg, "min_df", 1),
        "max_df": _cfg_get(cfg, "max_df", 1.0),
        "max_features": _cfg_get(cfg, "max_features", None),
        "sublinear_tf": bool(_cfg_get(cfg, "sublinear_tf", True)),
    }


def _linear_svc_kwargs(cfg: Any) -> dict:
    """Assemble ``LinearSVC`` kwargs from ``cfg`` with sane defaults."""
    kwargs: dict[str, Any] = {
        "C": _cfg_get(cfg, "C", 1.0),
        "class_weight": _cfg_get(cfg, "class_weight", "balanced"),
    }
    seed = _cfg_get(cfg, "seed", None)
    if seed is not None:
        kwargs["random_state"] = int(seed)
    return kwargs


# ---------------------------------------------------------------------------
# Text extractors (Req 34.1, 34.2, 34.3) — every extractor returns a `str`,
# never a dict of metadata, so no forbidden feature can reach the vectoriser.
# ---------------------------------------------------------------------------


def intent_text(example: Any) -> str:
    """Return the CURRENT text of an intent example (primary baseline input,
    Req 34.1). Uses only ``example.text`` — no metadata."""
    return example.text


def intent_context_text(example: Any) -> str:
    """Return ``previous_text`` joined with the current text for the
    context-aware variant (Req 34.2).

    The previous turn is used only when it is present and the record actually
    had context available; otherwise the ``[NO_CONTEXT]`` sentinel is used so
    the feature string is always well-defined. Still text-only (Req 34.4).
    """
    previous = getattr(example, "previous_text", None)
    context_available = getattr(example, "context_available", False)
    if not context_available or not previous:
        previous = _NO_CONTEXT
    return f"{previous} {example.text}"


def sentiment_text(example: Any) -> str:
    """Return the ``[ASP] term [/ASP]``-marked text of a sentiment example
    (Req 34.3, 38). Uses only ``example.marked_text``."""
    return example.marked_text


# Maps a builder to the extractor it expects, so :func:`fit_and_select` can
# auto-select the right text field when the caller does not override it.
TextFn = Callable[[Any], str]


# ---------------------------------------------------------------------------
# Stable text-extractor registry (Req: reproducible reload).
#
# Persisting a *callable* is unsafe and non-portable (pickling lambdas/closures
# is fragile and a security risk). Instead we persist a stable STRING id and
# resolve it back to the correct function via this registry on reload. This
# guarantees a reloaded intent-context model still joins the previous turn, and
# a reloaded sentiment model still consumes the ``[ASP]``-marked text.
# ---------------------------------------------------------------------------
INTENT_CURRENT = "intent_current"
INTENT_CONTEXT = "intent_context"
SENTIMENT_ASPECT_MARKED = "sentiment_aspect_marked"

TEXT_EXTRACTOR_REGISTRY: "dict[str, TextFn]" = {
    INTENT_CURRENT: intent_text,
    INTENT_CONTEXT: intent_context_text,
    SENTIMENT_ASPECT_MARKED: sentiment_text,
}

# Reverse lookup (function identity -> stable id) used to record the extractor
# id from a resolved ``text_fn``.
_TEXT_FN_TO_NAME: "dict[int, str]" = {
    id(fn): name for name, fn in TEXT_EXTRACTOR_REGISTRY.items()
}


def extractor_name_for(text_fn: TextFn) -> str:
    """Return the stable registry id for a known extractor function.

    Raises ``ValueError`` for an unregistered callable so an anonymous/lambda
    extractor can never be silently persisted with a wrong or unstable id.
    """
    name = _TEXT_FN_TO_NAME.get(id(text_fn))
    if name is None:
        raise ValueError(
            "Cannot persist an unregistered text extractor. Use one of "
            f"{sorted(TEXT_EXTRACTOR_REGISTRY)} or add it to "
            "TEXT_EXTRACTOR_REGISTRY; anonymous lambdas are never persisted."
        )
    return name


def resolve_extractor(name: str) -> TextFn:
    """Return the extractor function for a stable registry id.

    Raises a helpful ``ValueError`` for an unknown id (Req: unknown extractor
    names raise a helpful error).
    """
    try:
        return TEXT_EXTRACTOR_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown text extractor id '{name}'. Known ids: "
            f"{sorted(TEXT_EXTRACTOR_REGISTRY)}. The saved artifact metadata "
            "may be from an incompatible version."
        ) from exc


# ---------------------------------------------------------------------------
# Artifacts (design.md: SvmArtifacts)
# ---------------------------------------------------------------------------


@dataclass
class SvmArtifacts:
    """A fitted SVM baseline plus everything needed to reproduce/reload it.

    Attributes:
        vectorizer: the fitted ``TfidfVectorizer`` (from the selected pipeline).
        label_encoder: maps class ids <-> labels; ``None`` when no label map
            was supplied.
        model: the fitted classifier (``LinearSVC`` or the calibrated wrapper).
        config: the plain-dict config used to build the pipeline(s).
        metrics: selection metrics, including per-candidate and selected
            validation macro-F1 (Req 34.5).
        pipeline: the full fitted sklearn ``Pipeline`` (vectoriser + clf).
        text_fn: the extractor mapping an example to its input string.
        text_extractor_name: the STABLE registry id of ``text_fn`` (persisted
            so a reloaded model uses the exact same feature transformation).
    """

    vectorizer: Any
    label_encoder: Any
    model: Any
    config: dict
    metrics: dict
    pipeline: Any = None
    text_fn: TextFn = field(default=intent_text)
    text_extractor_name: str = INTENT_CURRENT

    def __post_init__(self) -> None:
        # Keep ``text_fn`` and ``text_extractor_name`` consistent. If a caller
        # supplied a registered ``text_fn`` but left the default name, adopt the
        # name that matches the function so persistence records the truth.
        matched = _TEXT_FN_TO_NAME.get(id(self.text_fn))
        if matched is not None:
            self.text_extractor_name = matched
        elif self.text_extractor_name in TEXT_EXTRACTOR_REGISTRY:
            # A name was given without a matching function -> trust the name.
            self.text_fn = TEXT_EXTRACTOR_REGISTRY[self.text_extractor_name]

    def predict(self, examples_or_texts: Sequence[Any]) -> list:
        """Predict class ids for a sequence of examples or raw strings."""
        texts = self._as_texts(examples_or_texts)
        return list(self.pipeline.predict(texts))

    def decision_function(self, examples_or_texts: Sequence[Any]):
        """Return the RAW, UNCALIBRATED decision scores from the SVM.

        These are ``LinearSVC.decision_function`` margins — signed distances
        to the separating hyperplane. They are NOT probabilities and must not
        be presented as such (Req 34.6). Use a calibrated variant
        (:func:`build_calibrated_intent_pipeline` /
        :func:`build_calibrated_sentiment_pipeline`) if you need probabilities.
        """
        texts = self._as_texts(examples_or_texts)
        return self.pipeline.decision_function(texts)

    def predict_proba(self, examples_or_texts: Sequence[Any]):
        """Return calibrated class probabilities.

        Only available when the underlying model was built as a calibrated
        variant (``CalibratedClassifierCV``). For a plain ``LinearSVC`` this
        raises, by design, so uncalibrated scores are never mistaken for
        probabilities (Req 34.6).
        """
        if not hasattr(self.pipeline, "predict_proba"):
            raise AttributeError(
                "predict_proba is only available on a calibrated SVM variant. "
                "Build the pipeline with build_calibrated_intent_pipeline / "
                "build_calibrated_sentiment_pipeline; a plain LinearSVC only "
                "exposes raw decision scores via decision_function (Req 34.6)."
            )
        texts = self._as_texts(examples_or_texts)
        return self.pipeline.predict_proba(texts)

    def _as_texts(self, examples_or_texts: Sequence[Any]) -> list[str]:
        out: list[str] = []
        for item in examples_or_texts:
            out.append(item if isinstance(item, str) else self.text_fn(item))
        return out


# ---------------------------------------------------------------------------
# Pipeline builders (Req 34.1, 34.2, 34.3)
# ---------------------------------------------------------------------------


def _tfidf_svc_pipeline(cfg: Any):
    """Return an unfitted ``TfidfVectorizer -> LinearSVC`` pipeline.

    The pipeline's *input* is a flat sequence of ``str`` — never a dict of
    metadata — which structurally guarantees no ``rating``/``region``/
    ``source``/``bank``/``title`` feature can enter the vectoriser (Req 34.4).
    """
    sk = _require_sklearn()
    return sk["Pipeline"](
        [
            (VECTORIZER_STEP, sk["TfidfVectorizer"](**_tfidf_kwargs(cfg))),
            (CLASSIFIER_STEP, sk["LinearSVC"](**_linear_svc_kwargs(cfg))),
        ]
    )


def _tfidf_calibrated_pipeline(cfg: Any):
    """Return an unfitted TF-IDF -> calibrated-LinearSVC pipeline.

    Wraps ``LinearSVC`` in ``CalibratedClassifierCV`` so the classifier
    exposes ``predict_proba`` (Req 34.6). This is the ONLY route to
    probabilities in this module.
    """
    sk = _require_sklearn()
    n_folds = int(_cfg_get(cfg, "calibration_folds", 3))
    calibrated = sk["CalibratedClassifierCV"](
        sk["LinearSVC"](**_linear_svc_kwargs(cfg)),
        cv=n_folds,
    )
    return sk["Pipeline"](
        [
            (VECTORIZER_STEP, sk["TfidfVectorizer"](**_tfidf_kwargs(cfg))),
            (CLASSIFIER_STEP, calibrated),
        ]
    )


def build_intent_pipeline(cfg: Any = None):
    """Build the PRIMARY intent baseline: ``TfidfVectorizer`` + ``LinearSVC``
    over the CURRENT review text only (Req 34.1).

    Never uses ``rating``/``region``/``source``/``bank``/``title`` or test
    labels as features (Req 34.4). Pair with :func:`intent_text` when calling
    :func:`fit_and_select` (this is the auto-detected default for
    ``IntentExample`` inputs).
    """
    return _tfidf_svc_pipeline(cfg)


def build_intent_context_pipeline(cfg: Any = None):
    """Build the CONTEXT-AWARE intent variant (Req 34.2).

    Identical estimator to :func:`build_intent_pipeline`, but intended to be
    fed the previous turn's text joined with the current text via
    :func:`intent_context_text`. Still text-only — the join concatenates two
    text fields, never any metadata (Req 34.4). The distinct name makes the
    variant unambiguous in run configs and artifacts.
    """
    return _tfidf_svc_pipeline(cfg)


def build_sentiment_pipeline(cfg: Any = None):
    """Build the aspect-sentiment baseline: ``TfidfVectorizer`` + ``LinearSVC``
    over the ``[ASP] term [/ASP]``-marked text (Req 34.3, 38).

    Consumes the ``marked_text`` field produced by
    ``datasets.build_sentiment_examples`` (one instance per gold aspect). Pair
    with :func:`sentiment_text` in :func:`fit_and_select` (auto-detected for
    ``SentimentExample`` inputs).
    """
    return _tfidf_svc_pipeline(cfg)


def build_calibrated_intent_pipeline(cfg: Any = None):
    """Calibrated intent variant exposing ``predict_proba`` (Req 34.6).

    Separate, explicitly-named builder so calibrated probabilities are never
    conflated with the raw decision scores of the primary baseline.
    """
    return _tfidf_calibrated_pipeline(cfg)


def build_calibrated_sentiment_pipeline(cfg: Any = None):
    """Calibrated aspect-sentiment variant exposing ``predict_proba``
    (Req 34.6). Fed the same ``marked_text`` as :func:`build_sentiment_pipeline`."""
    return _tfidf_calibrated_pipeline(cfg)


# ---------------------------------------------------------------------------
# Fit + select by validation macro-F1 (Req 34.5)
# ---------------------------------------------------------------------------


def _auto_text_fn(examples: Sequence[Any]) -> TextFn:
    """Pick the correct text extractor from the example type.

    ``SentimentExample`` carries ``marked_text`` -> :func:`sentiment_text`;
    everything else uses the current-text extractor :func:`intent_text`. The
    context-aware variant must be requested explicitly via ``text_fn`` because
    it is not inferable from the example alone.
    """
    for example in examples:
        if hasattr(example, "marked_text"):
            return sentiment_text
        return intent_text
    return intent_text


def _num_classes(
    train_examples: Sequence[Any],
    val_examples: Sequence[Any],
    label_map: dict | None,
) -> int:
    """Determine the class count for macro-F1 averaging.

    Prefer the size of the supplied ``label_map`` (the fixed, shared label
    space); otherwise fall back to ``max(label_id) + 1`` observed across the
    train and validation examples.
    """
    if label_map:
        return len(label_map)
    max_id = -1
    for example in list(train_examples) + list(val_examples):
        max_id = max(max_id, int(example.label_id))
    return max_id + 1 if max_id >= 0 else 1


def _normalise_candidates(pipeline_or_candidates: Any) -> list[tuple[str, Any]]:
    """Normalise the ``fit_and_select`` first argument into ``[(name, pipe)]``.

    Accepts a single pipeline, a ``{name: pipeline}`` dict, or a list of
    ``(name, pipeline)`` tuples, so selection over one or many candidates
    shares one code path.
    """
    if isinstance(pipeline_or_candidates, dict):
        return list(pipeline_or_candidates.items())
    if isinstance(pipeline_or_candidates, (list, tuple)):
        items = list(pipeline_or_candidates)
        if items and isinstance(items[0], tuple):
            return [(str(name), pipe) for name, pipe in items]
    # A single pipeline object.
    return [("default", pipeline_or_candidates)]


def fit_and_select(
    pipeline_or_candidates: Any,
    train_examples: Sequence[Any],
    val_examples: Sequence[Any],
    *,
    text_fn: TextFn | None = None,
    label_map: dict | None = None,
    num_classes: int | None = None,
    config: dict | None = None,
) -> SvmArtifacts:
    """Fit candidate(s) on train and select the best by VALIDATION macro-F1.

    Selection consults ONLY the validation split (Req 34.5); the test split is
    never a parameter of this function and is never referenced. Each candidate
    is fit on ``train_examples`` and scored on ``val_examples`` via
    ``training.loop.macro_f1``; the candidate with the highest validation
    macro-F1 wins (ties broken by first-seen order).

    Args:
        pipeline_or_candidates: a single unfitted pipeline, a
            ``{name: pipeline}`` dict, or a list of ``(name, pipeline)``.
        train_examples: examples with ``.label_id`` used for fitting.
        val_examples: examples with ``.label_id`` used for selection only.
        text_fn: extractor mapping an example -> input string; defaults to the
            type-appropriate extractor (:func:`intent_text` /
            :func:`sentiment_text`). Pass :func:`intent_context_text` for the
            context-aware variant.
        label_map: optional ``label -> id`` map (fixes the class space and the
            persisted label encoder).
        num_classes: optional explicit class count for macro-F1 averaging.
        config: optional plain-dict config recorded in the artifacts.

    Returns:
        :class:`SvmArtifacts` for the SELECTED pipeline, with ``metrics``
        capturing every candidate's validation macro-F1 and the selection.
    """
    if not train_examples:
        raise ValueError("fit_and_select requires at least one training example")
    if not val_examples:
        raise ValueError(
            "fit_and_select requires a non-empty validation split; selection "
            "is by validation macro-F1 only (Req 34.5)"
        )

    resolved_text_fn = text_fn or _auto_text_fn(train_examples)
    n_classes = num_classes or _num_classes(train_examples, val_examples, label_map)

    train_texts = [resolved_text_fn(ex) for ex in train_examples]
    train_labels = [int(ex.label_id) for ex in train_examples]
    val_texts = [resolved_text_fn(ex) for ex in val_examples]
    val_labels = [int(ex.label_id) for ex in val_examples]

    candidates = _normalise_candidates(pipeline_or_candidates)

    per_candidate: dict[str, float] = {}
    best_name: str | None = None
    best_pipeline = None
    best_score = float("-inf")

    for name, pipeline in candidates:
        pipeline.fit(train_texts, train_labels)
        val_pred = [int(p) for p in pipeline.predict(val_texts)]
        score = macro_f1(val_labels, val_pred, n_classes)
        per_candidate[name] = score
        if score > best_score:
            best_score = score
            best_name = name
            best_pipeline = pipeline

    # Build a label encoder from the supplied label map (id -> label), if any.
    label_encoder = None
    if label_map:
        sk = _require_sklearn()
        label_encoder = sk["LabelEncoder"]()
        # Fit on labels ordered by their id so encoder.classes_[id] == label.
        ordered = [lbl for lbl, _ in sorted(label_map.items(), key=lambda kv: kv[1])]
        label_encoder.fit(ordered)

    vectorizer = best_pipeline.named_steps[VECTORIZER_STEP]
    model = best_pipeline.named_steps[CLASSIFIER_STEP]

    metrics = {
        "selection_metric": "val_macro_f1",
        "val_macro_f1": best_score,
        "selected_candidate": best_name,
        "candidates": per_candidate,
        "num_classes": n_classes,
        "n_train": len(train_examples),
        "n_val": len(val_examples),
    }

    return SvmArtifacts(
        vectorizer=vectorizer,
        label_encoder=label_encoder,
        model=model,
        config=dict(config or {}),
        metrics=metrics,
        pipeline=best_pipeline,
        text_fn=resolved_text_fn,
    )


# ---------------------------------------------------------------------------
# Persist / reload artifacts (Req 34.7)
# ---------------------------------------------------------------------------


def save_artifacts(artifacts: SvmArtifacts, out_dir) -> dict:
    """Persist the fitted vectoriser, label encoder, model, config, metrics.

    The sklearn objects (vectoriser, label encoder, and the full fitted
    pipeline that also embeds the model) are dumped with ``joblib``; the
    config and metrics are written as JSON so they are human-readable and
    diffable (Req 34.7). Returns the map of artifact name -> written path.
    """
    import joblib  # lazy: only needed when actually persisting

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    # The full fitted pipeline embeds both vectoriser and model; persist the
    # pipeline (authoritative) plus the individual pieces the design lists.
    joblib.dump(artifacts.pipeline, out_path / MODEL_FILE)
    written["model"] = out_path / MODEL_FILE

    joblib.dump(artifacts.vectorizer, out_path / VECTORIZER_FILE)
    written["vectorizer"] = out_path / VECTORIZER_FILE

    joblib.dump(artifacts.label_encoder, out_path / LABEL_ENCODER_FILE)
    written["label_encoder"] = out_path / LABEL_ENCODER_FILE

    (out_path / CONFIG_FILE).write_text(
        json.dumps(artifacts.config, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    written["config"] = out_path / CONFIG_FILE

    (out_path / METRICS_FILE).write_text(
        json.dumps(artifacts.metrics, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    written["metrics"] = out_path / METRICS_FILE

    # Persist the STABLE extractor id (never the callable) so the reloaded
    # model applies the identical feature transformation (Req: extractor id).
    (out_path / EXTRACTOR_FILE).write_text(
        json.dumps({"text_extractor_name": artifacts.text_extractor_name}, indent=2),
        encoding="utf-8",
    )
    written["extractor"] = out_path / EXTRACTOR_FILE

    return written


def load_artifacts(out_dir) -> SvmArtifacts:
    """Reload artifacts previously written by :func:`save_artifacts`.

    Restores the fitted pipeline (authoritative for prediction), the
    vectoriser, the label encoder, and the JSON config/metrics.
    """
    import joblib  # lazy

    out_path = Path(out_dir)
    pipeline = joblib.load(out_path / MODEL_FILE)
    vectorizer = joblib.load(out_path / VECTORIZER_FILE)
    label_encoder = joblib.load(out_path / LABEL_ENCODER_FILE)
    config = json.loads((out_path / CONFIG_FILE).read_text(encoding="utf-8"))
    metrics = json.loads((out_path / METRICS_FILE).read_text(encoding="utf-8"))

    # Restore the exact feature extractor from its stable id. Older artifacts
    # without an extractor file are treated as the primary intent extractor
    # (backward-compatible default), which matches the historical behaviour.
    extractor_path = out_path / EXTRACTOR_FILE
    if extractor_path.is_file():
        name = json.loads(extractor_path.read_text(encoding="utf-8")).get(
            "text_extractor_name", INTENT_CURRENT
        )
    else:
        name = INTENT_CURRENT
    text_fn = resolve_extractor(name)  # raises helpfully on an unknown id

    model = pipeline.named_steps.get(CLASSIFIER_STEP) if hasattr(pipeline, "named_steps") else None

    return SvmArtifacts(
        vectorizer=vectorizer,
        label_encoder=label_encoder,
        model=model,
        config=config,
        metrics=metrics,
        pipeline=pipeline,
        text_fn=text_fn,
        text_extractor_name=name,
    )
