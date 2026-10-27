"""Versioned record/opinion schema and taxonomy loader for `new_pipeline_v1`.

This module implements the annotation schema required by
``NEW_PIPELINE_REQUIREMENTS.md`` Sections 8-12, and loads the canonical
entity-attribute taxonomy from ``configs/taxonomies/banking_entity_attribute_v1.yaml``.

**It deliberately does NOT modify or import the legacy schema.**
``banking_tasci.data.annotations`` keeps its own ``AnnotationRecord`` /
``AspectSpan`` dataclasses and its legacy label constants
(``ASPECT_CATEGORIES``, ``ASPECT_SENTIMENTS``, ``INTENT_LABELS``), which
remain the correct way to read and validate the existing 796-record
intermediate-generation gold corpus. The two schemas coexist; this one is
selected by ``pipeline_version: new_pipeline_v1`` configuration.

Key differences from the legacy schema (gap-analysis findings R13-R17):

===========================  ==========================  ==========================
Concern                      Legacy (``annotations.py``)  ``new_pipeline_v1`` (here)
===========================  ==========================  ==========================
Opinion list field name      ``aspects``                 ``opinions``
Target representation        ``term``/``start``/``end``  ``target``/``target_start``/
                                                         ``target_end``/``target_type``
Implicit targets             not representable           ``target_type="implicit"``
                                                         with null target fields
Category shape               flat (``"cards"``)          ``ENTITY#ATTRIBUTE``
                                                         (``"CARD#FEES"``)
Entity/attribute split       none                        explicit ``entity`` +
                                                         ``attribute``
Opinion phrase               none                        ``opinion_phrase`` +
                                                         offsets
Sentiment labels             3 (no ``conflict``)         4 (incl. ``conflict``)
Primary intents              7 (incl. ``warning``)       6 (``warning`` removed)
Warning                      a primary intent            separate
                                                         ``public_warning`` bool
===========================  ==========================  ==========================

Offset semantics (Requirements 8.3): ``start`` is inclusive, ``end`` is
exclusive, so ``text[start:end] == <span text>``.

Requirements covered:

- 8.1  record-level fields
- 8.2  opinion-level fields
- 8.3  explicit targets and offset matching
- 8.4  implicit targets and null-field rules
- 8.5  explicit opinion phrases and offset matching
- 8.6  zero-opinion records (``opinions == []``)
- 8.7  multi-opinion records, no document-level sentiment override
- 9    canonical taxonomy, loaded from one file only
- 9.14 ``GENERAL``-attribute rule and monitoring hook
- 10   sentiment labels including ``conflict``
- 11   six primary intents
- 11.7 ``public_warning`` as a separate flag, never a primary intent
- 12   context fields and ``[NO_CONTEXT]`` handling
- 14   validation checks and machine-readable error reporting
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "PIPELINE_VERSION",
    "SCHEMA_VERSION",
    "PRIMARY_INTENTS",
    "SENTIMENT_LABELS",
    "TARGET_TYPES",
    "PRIVACY_STATUSES",
    "ANNOTATION_STATUSES",
    "NO_CONTEXT",
    "CATEGORY_SEPARATOR",
    "GENERAL_ATTRIBUTE",
    "Taxonomy",
    "load_taxonomy",
    "Opinion",
    "NewPipelineRecord",
    "SchemaValidationIssue",
    "validate_record",
    "validate_all",
    "compose_category",
    "split_category",
    "record_from_dict",
    "record_to_dict",
    "read_jsonl",
    "write_jsonl",
]

PIPELINE_VERSION = "new_pipeline_v1"
SCHEMA_VERSION = "new_pipeline_schema_v1"

# --- Requirements Section 11: exactly six primary intents. --------------------
# 'warning' is intentionally absent. Requirements Section 27 explicitly
# prohibits "seven primary intents including warning"; Section 11.7 requires
# warning to be carried by the separate `public_warning` boolean instead.
PRIMARY_INTENTS: tuple[str, ...] = (
    "complaint",
    "request_for_assistance",
    "praise_or_appreciation",
    "suggestion_or_feature_request",
    "exit_or_switch_intention",
    "general_feedback",
)

# --- Requirements Section 10: four sentiment labels, including 'conflict'. ----
SENTIMENT_LABELS: tuple[str, ...] = ("positive", "neutral", "negative", "conflict")

# --- Requirements Sections 8.3 / 8.4. ----------------------------------------
TARGET_TYPES: tuple[str, ...] = ("explicit", "implicit")

PRIVACY_STATUSES: tuple[str, ...] = ("anonymised", "not_required", "pending_review")

ANNOTATION_STATUSES: tuple[str, ...] = (
    "not_started",
    "in_progress",
    "completed",
    "needs_review",
)

# --- Requirements Section 12. -------------------------------------------------
NO_CONTEXT = "[NO_CONTEXT]"

CATEGORY_SEPARATOR = "#"
GENERAL_ATTRIBUTE = "GENERAL"

_DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "taxonomies"
    / "banking_entity_attribute_v1.yaml"
)

# Sentinel distinguishing "key absent from the JSON object" from "key present
# with an explicit null". Section 8.1 permits null values for unavailable
# source fields but requires the keys to remain structurally present, so this
# distinction is load-bearing for validation.
_MISSING = object()


# =============================================================================
# Taxonomy
# =============================================================================


@dataclass(frozen=True)
class Taxonomy:
    """The canonical entity-attribute taxonomy (Requirements Section 9).

    Loaded from exactly one YAML file. No other module may define its own
    category list; Section 9 forbids duplicating independent category lists
    across scripts.
    """

    version: str
    entities: dict[str, tuple[str, ...]]
    semantics: dict[str, str]
    general_attribute: str = GENERAL_ATTRIBUTE
    separator: str = CATEGORY_SEPARATOR

    @property
    def categories(self) -> tuple[str, ...]:
        """Every valid ``ENTITY#ATTRIBUTE`` category, sorted deterministically."""
        out: list[str] = []
        for entity in sorted(self.entities):
            for attribute in self.entities[entity]:
                out.append(f"{entity}{self.separator}{attribute}")
        return tuple(sorted(out))

    def is_valid_entity(self, entity: Any) -> bool:
        return isinstance(entity, str) and entity in self.entities

    def is_valid_pair(self, entity: Any, attribute: Any) -> bool:
        """True when ``attribute`` is approved for ``entity`` (Requirements 14)."""
        if not self.is_valid_entity(entity):
            return False
        return isinstance(attribute, str) and attribute in self.entities[entity]

    def is_valid_category(self, category: Any) -> bool:
        return isinstance(category, str) and category in set(self.categories)

    def semantic_for(self, category: str) -> str | None:
        """Natural-language rendering of a category (Requirements Section 19).

        For example ``"APP#RELIABILITY"`` -> ``"mobile application, reliability"``.
        Used by the text-category pair condition so categories are represented
        semantically rather than as arbitrary numeric IDs.
        """
        return self.semantics.get(category)


@lru_cache(maxsize=4)
def _load_taxonomy_cached(resolved_path: str) -> Taxonomy:
    path = Path(resolved_path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read taxonomy file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Cannot parse taxonomy file {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Taxonomy file {path} must contain a top-level mapping")

    version = raw.get("taxonomy_version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"Taxonomy file {path} is missing a 'taxonomy_version' string")

    entities_raw = raw.get("entities")
    if not isinstance(entities_raw, dict) or not entities_raw:
        raise ValueError(f"Taxonomy file {path} is missing a non-empty 'entities' mapping")

    separator = raw.get("category_separator", CATEGORY_SEPARATOR)
    general_attribute = raw.get("general_attribute", GENERAL_ATTRIBUTE)

    entities: dict[str, tuple[str, ...]] = {}
    semantics: dict[str, str] = {}

    for entity, body in entities_raw.items():
        if not isinstance(body, dict):
            raise ValueError(
                f"Taxonomy file {path}: entity '{entity}' must map to a mapping"
            )
        attributes_raw = body.get("attributes")
        if not isinstance(attributes_raw, dict) or not attributes_raw:
            raise ValueError(
                f"Taxonomy file {path}: entity '{entity}' has no 'attributes' mapping"
            )
        entities[entity] = tuple(attributes_raw.keys())

        entity_semantic = body.get("semantic", entity)
        for attribute, attribute_semantic in attributes_raw.items():
            category = f"{entity}{separator}{attribute}"
            semantics[category] = f"{entity_semantic}, {attribute_semantic}"

    return Taxonomy(
        version=version,
        entities=entities,
        semantics=semantics,
        general_attribute=general_attribute,
        separator=separator,
    )


def load_taxonomy(path: "str | Path | None" = None) -> Taxonomy:
    """Load the canonical taxonomy (cached per resolved path).

    Defaults to ``configs/taxonomies/banking_entity_attribute_v1.yaml``,
    resolved relative to this file so it works regardless of CWD.
    """
    resolved = Path(path).resolve() if path is not None else _DEFAULT_TAXONOMY_PATH
    return _load_taxonomy_cached(str(resolved))


def compose_category(entity: str, attribute: str, separator: str = CATEGORY_SEPARATOR) -> str:
    """Build ``ENTITY#ATTRIBUTE`` (Requirements Section 14 composition rule)."""
    return f"{entity}{separator}{attribute}"


def split_category(category: str, separator: str = CATEGORY_SEPARATOR) -> tuple[str, str] | None:
    """Inverse of :func:`compose_category`; ``None`` when not well-formed."""
    if not isinstance(category, str):
        return None
    parts = category.split(separator)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


# =============================================================================
# Schema
# =============================================================================


@dataclass
class Opinion:
    """One opinion structure (Requirements Section 8.2).

    A record may carry zero (8.6), one, or many (8.7) of these. Sentiment is
    attached here, per-opinion - never as a single document-level label that
    overwrites target-level sentiment.
    """

    target: Any = None
    target_start: Any = None
    target_end: Any = None
    target_type: Any = None
    entity: Any = None
    attribute: Any = None
    category: Any = None
    opinion_phrase: Any = None
    opinion_start: Any = None
    opinion_end: Any = None
    sentiment: Any = None
    annotation_notes: Any = None


@dataclass
class NewPipelineRecord:
    """One annotation record (Requirements Section 8.1).

    Fields unavailable from a given source may be ``None``, but every key must
    remain structurally present (Section 8.1).
    """

    record_id: Any = None
    source: Any = None
    region: Any = None
    bank: Any = None
    review_id: Any = None
    thread_id: Any = None
    conversation_id: Any = None
    publish_year: Any = None
    text: Any = None
    previous_text: Any = None
    context_available: Any = None
    duplicate_group: Any = None
    leakage_group: Any = None
    privacy_status: Any = None
    primary_intent: Any = None
    public_warning: Any = None
    opinions: Any = field(default_factory=list)
    annotation_status: Any = None
    annotation_version: Any = None
    annotation_notes: Any = None


RECORD_FIELDS: tuple[str, ...] = (
    "record_id",
    "source",
    "region",
    "bank",
    "review_id",
    "thread_id",
    "conversation_id",
    "publish_year",
    "text",
    "previous_text",
    "context_available",
    "duplicate_group",
    "leakage_group",
    "privacy_status",
    "primary_intent",
    "public_warning",
    "opinions",
    "annotation_status",
    "annotation_version",
    "annotation_notes",
)

OPINION_FIELDS: tuple[str, ...] = (
    "target",
    "target_start",
    "target_end",
    "target_type",
    "entity",
    "attribute",
    "category",
    "opinion_phrase",
    "opinion_start",
    "opinion_end",
    "sentiment",
    "annotation_notes",
)

# Fields that must be present and non-null on every record regardless of
# source availability. Everything else in RECORD_FIELDS may legitimately be
# null (Section 8.1) but must still be a present key.
_REQUIRED_NON_NULL = ("record_id", "source", "region", "text")


@dataclass(frozen=True)
class SchemaValidationIssue:
    """One validation problem (Requirements Section 14 reporting fields).

    Carries a stable ``rule_id`` and actionable ``fix_guidance``. Never carries
    the record's raw ``text`` or any other potentially sensitive field value.
    """

    rule_id: str
    severity: str  # "error" | "warning"
    record_id: str
    message: str
    fix_guidance: str
    opinion_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "record_id": self.record_id,
            "message": self.message,
            "fix_guidance": self.fix_guidance,
            "opinion_index": self.opinion_index,
        }


def _rid(record: NewPipelineRecord) -> str:
    value = getattr(record, "record_id", None)
    if isinstance(value, str) and value:
        return value
    if value is not None and value is not _MISSING:
        return str(value)
    return "<unknown>"


def _is_int(value: Any) -> bool:
    """True for a genuine int. ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool)


# --- individual checks -------------------------------------------------------


def _check_required_fields(record: NewPipelineRecord) -> list[SchemaValidationIssue]:
    issues: list[SchemaValidationIssue] = []
    rid = _rid(record)

    for name in RECORD_FIELDS:
        if getattr(record, name, _MISSING) is _MISSING:
            issues.append(
                SchemaValidationIssue(
                    rule_id="missing_mandatory_key",
                    severity="error",
                    record_id=rid,
                    message=f"Record is missing the required key '{name}'.",
                    fix_guidance=(
                        f"Add '{name}' to the record. It may be null when the source "
                        f"does not provide it, but the key must be present "
                        f"(Requirements 8.1)."
                    ),
                )
            )

    for name in _REQUIRED_NON_NULL:
        value = getattr(record, name, _MISSING)
        if value is _MISSING:
            continue  # already reported above
        if value is None or (isinstance(value, str) and not value.strip()):
            issues.append(
                SchemaValidationIssue(
                    rule_id="required_field_null",
                    severity="error",
                    record_id=rid,
                    message=f"Field '{name}' must not be null or empty.",
                    fix_guidance=f"Populate '{name}' with a non-empty value.",
                )
            )

    opinions = getattr(record, "opinions", _MISSING)
    if opinions is not _MISSING and not isinstance(opinions, list):
        issues.append(
            SchemaValidationIssue(
                rule_id="opinions_not_a_list",
                severity="error",
                record_id=rid,
                message="Field 'opinions' must be a list.",
                fix_guidance=(
                    "Use [] for a zero-opinion record (Requirements 8.6), or a list "
                    "of opinion objects."
                ),
            )
        )

    return issues


def _check_intent_and_warning(record: NewPipelineRecord) -> list[SchemaValidationIssue]:
    """Requirements 11 (six intents) and 11.7 (`public_warning` is separate)."""
    issues: list[SchemaValidationIssue] = []
    rid = _rid(record)

    intent = getattr(record, "primary_intent", _MISSING)
    if intent is not _MISSING and intent is not None:
        if intent not in PRIMARY_INTENTS:
            # Give a targeted message for the specific prohibited legacy case.
            if intent == "warning":
                guidance = (
                    "'warning' is not a primary intent (Requirements 11.7). Set the "
                    "dominant communicative intent in 'primary_intent' and set "
                    "'public_warning' to true instead."
                )
            else:
                guidance = (
                    "Use one of: " + ", ".join(PRIMARY_INTENTS) + " (Requirements 11)."
                )
            issues.append(
                SchemaValidationIssue(
                    rule_id="intent_not_allowed",
                    severity="error",
                    record_id=rid,
                    message=f"primary_intent '{intent}' is not an approved value.",
                    fix_guidance=guidance,
                )
            )

    warning = getattr(record, "public_warning", _MISSING)
    if warning is not _MISSING and warning is not None and not isinstance(warning, bool):
        issues.append(
            SchemaValidationIssue(
                rule_id="public_warning_not_boolean",
                severity="error",
                record_id=rid,
                message="public_warning must be a boolean.",
                fix_guidance="Set public_warning to true or false (Requirements 11.7).",
            )
        )

    status = getattr(record, "annotation_status", _MISSING)
    if status is not _MISSING and status is not None and status not in ANNOTATION_STATUSES:
        issues.append(
            SchemaValidationIssue(
                rule_id="annotation_status_not_allowed",
                severity="error",
                record_id=rid,
                message=f"annotation_status '{status}' is not an approved value.",
                fix_guidance="Use one of: " + ", ".join(ANNOTATION_STATUSES) + ".",
            )
        )

    # A completed record must carry a primary intent (every record receives one
    # primary communicative intent, Requirements Section 11).
    if status == "completed":
        if intent in (_MISSING, None, ""):
            issues.append(
                SchemaValidationIssue(
                    rule_id="completed_without_intent",
                    severity="error",
                    record_id=rid,
                    message="annotation_status is 'completed' but primary_intent is null.",
                    fix_guidance=(
                        "Assign one of the six primary intents before marking a record "
                        "completed (Requirements 11)."
                    ),
                )
            )

    return issues


def _check_privacy_status(record: NewPipelineRecord) -> list[SchemaValidationIssue]:
    issues: list[SchemaValidationIssue] = []
    rid = _rid(record)
    status = getattr(record, "privacy_status", _MISSING)
    if status is not _MISSING and status is not None and status not in PRIVACY_STATUSES:
        issues.append(
            SchemaValidationIssue(
                rule_id="privacy_status_not_allowed",
                severity="error",
                record_id=rid,
                message=f"privacy_status '{status}' is not an approved value.",
                fix_guidance="Use one of: " + ", ".join(PRIVACY_STATUSES) + ".",
            )
        )
    return issues


def _check_context(record: NewPipelineRecord) -> list[SchemaValidationIssue]:
    """Requirements Section 12 context-field consistency."""
    issues: list[SchemaValidationIssue] = []
    rid = _rid(record)

    available = getattr(record, "context_available", _MISSING)
    previous = getattr(record, "previous_text", _MISSING)

    if available is _MISSING or previous is _MISSING:
        return issues  # structural problem already reported

    if available is not None and not isinstance(available, bool):
        issues.append(
            SchemaValidationIssue(
                rule_id="context_available_not_boolean",
                severity="error",
                record_id=rid,
                message="context_available must be a boolean.",
                fix_guidance="Set context_available to true or false (Requirements 12).",
            )
        )
        return issues

    if available is True:
        if previous is None or previous == NO_CONTEXT or (
            isinstance(previous, str) and not previous.strip()
        ):
            issues.append(
                SchemaValidationIssue(
                    rule_id="context_available_without_text",
                    severity="error",
                    record_id=rid,
                    message=(
                        "context_available is true but previous_text is null, empty, "
                        f"or '{NO_CONTEXT}'."
                    ),
                    fix_guidance=(
                        "Supply genuine preceding text, or set context_available to "
                        "false. Never use the previous physical dataset row as context "
                        "(Requirements 12)."
                    ),
                )
            )
    elif available is False:
        # Requirements 12 allows a consistent null representation in the data
        # schema; the model input uses [NO_CONTEXT]. Both are accepted here,
        # anything else is a genuine inconsistency.
        if previous is not None and previous != NO_CONTEXT:
            issues.append(
                SchemaValidationIssue(
                    rule_id="no_context_with_text",
                    severity="error",
                    record_id=rid,
                    message=(
                        "context_available is false but previous_text carries content."
                    ),
                    fix_guidance=(
                        f"Set previous_text to null or '{NO_CONTEXT}' when no verified "
                        f"preceding context exists (Requirements 12)."
                    ),
                )
            )

    return issues


def _check_opinion(
    record: NewPipelineRecord,
    opinion: Opinion,
    index: int,
    taxonomy: Taxonomy,
) -> list[SchemaValidationIssue]:
    """Validate one opinion (Requirements 8.2-8.5, 9, 10, 14)."""
    issues: list[SchemaValidationIssue] = []
    rid = _rid(record)
    text = getattr(record, "text", None)

    def add(rule_id: str, message: str, fix: str, severity: str = "error") -> None:
        issues.append(
            SchemaValidationIssue(
                rule_id=rule_id,
                severity=severity,
                record_id=rid,
                message=message,
                fix_guidance=fix,
                opinion_index=index,
            )
        )

    for name in OPINION_FIELDS:
        if getattr(opinion, name, _MISSING) is _MISSING:
            add(
                "missing_mandatory_key",
                f"Opinion is missing the required key '{name}'.",
                f"Add '{name}' to the opinion (it may be null) (Requirements 8.2).",
            )

    # --- target type (Requirements 8.3 / 8.4) ---
    target_type = opinion.target_type
    if target_type not in TARGET_TYPES:
        add(
            "target_type_not_allowed",
            f"target_type '{target_type}' is not an approved value.",
            "Use 'explicit' or 'implicit' (Requirements 8.3, 8.4).",
        )
    elif target_type == "explicit":
        issues.extend(_check_explicit_target(rid, opinion, index, text))
    else:  # implicit
        issues.extend(_check_implicit_target(rid, opinion, index))

    # --- entity / attribute / category (Requirements 9, 14) ---
    entity, attribute, category = opinion.entity, opinion.attribute, opinion.category

    if not taxonomy.is_valid_entity(entity):
        add(
            "entity_not_allowed",
            f"entity '{entity}' is not in the canonical taxonomy.",
            f"Use an entity from taxonomy {taxonomy.version}.",
        )
    elif not taxonomy.is_valid_pair(entity, attribute):
        add(
            "entity_attribute_pair_not_allowed",
            f"attribute '{attribute}' is not approved for entity '{entity}'.",
            (
                f"Valid attributes for '{entity}': "
                + ", ".join(taxonomy.entities[entity])
                + f" (taxonomy {taxonomy.version})."
            ),
        )

    # category == entity + "#" + attribute (Requirements Section 14)
    if isinstance(entity, str) and isinstance(attribute, str):
        expected = compose_category(entity, attribute, taxonomy.separator)
        if category != expected:
            add(
                "category_composition_mismatch",
                f"category '{category}' does not equal '{expected}'.",
                (
                    "Set category to entity + '"
                    + taxonomy.separator
                    + "' + attribute (Requirements Section 14)."
                ),
            )
    if category is not None and not taxonomy.is_valid_category(category):
        add(
            "category_not_in_taxonomy",
            f"category '{category}' is not a canonical taxonomy category.",
            f"Use a category defined in taxonomy {taxonomy.version}.",
        )

    # Requirements 9.14: GENERAL is permitted but must be monitored.
    if attribute == taxonomy.general_attribute:
        add(
            "general_attribute_used",
            f"Opinion uses the {taxonomy.general_attribute} attribute.",
            (
                "Permitted only when the text evaluates the entity without enough "
                "evidence for a more specific attribute. Annotation reports must "
                "monitor excessive use (Requirements 9.14)."
            ),
            severity="warning",
        )

    # --- sentiment (Requirements 10) ---
    if opinion.sentiment not in SENTIMENT_LABELS:
        add(
            "sentiment_not_allowed",
            f"sentiment '{opinion.sentiment}' is not an approved value.",
            "Use one of: " + ", ".join(SENTIMENT_LABELS) + " (Requirements 10).",
        )

    # --- explicit opinion phrase (Requirements 8.5) ---
    issues.extend(_check_opinion_phrase(rid, opinion, index, text))

    return issues


def _check_explicit_target(
    rid: str, opinion: Opinion, index: int, text: Any
) -> list[SchemaValidationIssue]:
    """Requirements 8.3: ``text[target_start:target_end] == target``."""
    issues: list[SchemaValidationIssue] = []

    def add(rule_id: str, message: str, fix: str) -> None:
        issues.append(
            SchemaValidationIssue(
                rule_id=rule_id,
                severity="error",
                record_id=rid,
                message=message,
                fix_guidance=fix,
                opinion_index=index,
            )
        )

    target, start, end = opinion.target, opinion.target_start, opinion.target_end

    if not isinstance(target, str) or not target:
        add(
            "explicit_target_missing_text",
            "An explicit target requires a non-empty 'target' string.",
            "Populate 'target', or set target_type to 'implicit' (Requirements 8.4).",
        )
        return issues

    if not _is_int(start) or not _is_int(end):
        add(
            "explicit_target_offsets_not_integers",
            "An explicit target requires integer target_start and target_end.",
            "Provide integer character offsets (start inclusive, end exclusive).",
        )
        return issues

    if not isinstance(text, str):
        return issues  # record-level text problem already reported

    if start < 0 or end > len(text) or start >= end:
        add(
            "explicit_target_offsets_out_of_bounds",
            f"target offsets [{start}:{end}] are invalid for this text.",
            "Use 0 <= target_start < target_end <= len(text).",
        )
        return issues

    if text[start:end] != target:
        add(
            "explicit_target_offset_mismatch",
            f"text[{start}:{end}] does not match the recorded target.",
            (
                "Correct the offsets or the target string so "
                "text[target_start:target_end] == target (Requirements 8.3)."
            ),
        )

    return issues


def _check_implicit_target(
    rid: str, opinion: Opinion, index: int
) -> list[SchemaValidationIssue]:
    """Requirements 8.4: implicit targets null out target and both offsets."""
    issues: list[SchemaValidationIssue] = []

    for name in ("target", "target_start", "target_end"):
        value = getattr(opinion, name, None)
        if value is not None:
            issues.append(
                SchemaValidationIssue(
                    rule_id="implicit_target_field_not_null",
                    severity="error",
                    record_id=rid,
                    message=f"Implicit target requires '{name}' to be null.",
                    fix_guidance=(
                        "For target_type 'implicit', set target, target_start and "
                        "target_end to null. Entity, attribute, category, sentiment "
                        "and any explicit opinion phrase remain annotated "
                        "(Requirements 8.4)."
                    ),
                    opinion_index=index,
                )
            )
    return issues


def _check_opinion_phrase(
    rid: str, opinion: Opinion, index: int, text: Any
) -> list[SchemaValidationIssue]:
    """Requirements 8.5: ``text[opinion_start:opinion_end] == opinion_phrase``.

    Where no explicit phrase is available, the phrase and both offsets may all
    be null. A partially-populated phrase is an error.
    """
    issues: list[SchemaValidationIssue] = []
    phrase = opinion.opinion_phrase
    start, end = opinion.opinion_start, opinion.opinion_end

    def add(rule_id: str, message: str, fix: str) -> None:
        issues.append(
            SchemaValidationIssue(
                rule_id=rule_id,
                severity="error",
                record_id=rid,
                message=message,
                fix_guidance=fix,
                opinion_index=index,
            )
        )

    all_null = phrase is None and start is None and end is None
    if all_null:
        return issues  # legitimate: no explicit phrase available

    if phrase is None or start is None or end is None:
        add(
            "opinion_phrase_partially_populated",
            "opinion_phrase and its offsets must be either all null or all populated.",
            "Supply opinion_phrase, opinion_start and opinion_end together, or null all three.",
        )
        return issues

    if not isinstance(phrase, str) or not phrase:
        add(
            "opinion_phrase_not_a_string",
            "opinion_phrase must be a non-empty string when present.",
            "Provide the phrase text or null all three phrase fields.",
        )
        return issues

    if not _is_int(start) or not _is_int(end):
        add(
            "opinion_phrase_offsets_not_integers",
            "opinion_start and opinion_end must be integers when present.",
            "Provide integer character offsets (start inclusive, end exclusive).",
        )
        return issues

    if not isinstance(text, str):
        return issues

    if start < 0 or end > len(text) or start >= end:
        add(
            "opinion_phrase_offsets_out_of_bounds",
            f"opinion phrase offsets [{start}:{end}] are invalid for this text.",
            "Use 0 <= opinion_start < opinion_end <= len(text).",
        )
        return issues

    if text[start:end] != phrase:
        add(
            "opinion_phrase_offset_mismatch",
            f"text[{start}:{end}] does not match the recorded opinion_phrase.",
            (
                "Correct the offsets or the phrase so "
                "text[opinion_start:opinion_end] == opinion_phrase (Requirements 8.5)."
            ),
        )

    return issues


def validate_record(
    record: NewPipelineRecord, taxonomy: Taxonomy | None = None
) -> list[SchemaValidationIssue]:
    """Validate one record against Requirements Sections 8-12 and 14.

    Collects every issue found rather than stopping at the first, and never
    mutates ``record``. A zero-opinion record (``opinions == []``) is valid
    (Requirements 8.6); a multi-opinion record is valid (8.7).
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()

    issues: list[SchemaValidationIssue] = []
    issues.extend(_check_required_fields(record))
    issues.extend(_check_intent_and_warning(record))
    issues.extend(_check_privacy_status(record))
    issues.extend(_check_context(record))

    opinions = getattr(record, "opinions", None)
    if isinstance(opinions, list):
        for index, opinion in enumerate(opinions):
            if not isinstance(opinion, Opinion):
                issues.append(
                    SchemaValidationIssue(
                        rule_id="opinion_not_an_object",
                        severity="error",
                        record_id=_rid(record),
                        message=f"Opinion at index {index} is not a valid opinion object.",
                        fix_guidance="Each item in 'opinions' must be an opinion mapping.",
                        opinion_index=index,
                    )
                )
                continue
            issues.extend(_check_opinion(record, opinion, index, taxonomy))

    return issues


def validate_all(
    records: list[NewPipelineRecord], taxonomy: Taxonomy | None = None
) -> tuple[list[NewPipelineRecord], dict[str, list[SchemaValidationIssue]], list[SchemaValidationIssue]]:
    """Validate a corpus.

    Returns ``(valid_records, {record_id: [errors]}, corpus_level_issues)``.
    A record with only ``warning``-severity issues is still returned as valid,
    matching Requirements Section 14's distinction between errors and warnings.
    Corpus-level issues currently cover duplicate ``record_id`` detection.
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()

    valid: list[NewPipelineRecord] = []
    invalid: dict[str, list[SchemaValidationIssue]] = {}

    seen: dict[str, int] = {}
    corpus_issues: list[SchemaValidationIssue] = []

    for record in records:
        rid = _rid(record)
        seen[rid] = seen.get(rid, 0) + 1

        issues = validate_record(record, taxonomy)
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            invalid.setdefault(rid, []).extend(errors)
        else:
            valid.append(record)

    for rid, count in sorted(seen.items()):
        if count > 1:
            corpus_issues.append(
                SchemaValidationIssue(
                    rule_id="duplicate_record_id",
                    severity="error",
                    record_id=rid,
                    message=f"record_id appears {count} times; it must be unique.",
                    fix_guidance=(
                        "Assign immutable, unique record identifiers "
                        "(Requirements 13.4, 14)."
                    ),
                )
            )

    return valid, invalid, corpus_issues


# =============================================================================
# JSONL I/O
# =============================================================================


def _opinion_from_dict(data: dict) -> Opinion:
    return Opinion(**{name: data.get(name, _MISSING) for name in OPINION_FIELDS})


def record_from_dict(data: dict) -> NewPipelineRecord:
    """Build a record from a JSON object.

    Absent keys are retained internally as a sentinel so validation can
    distinguish "key missing" from "key present and null" (Requirements 8.1).
    """
    values: dict[str, Any] = {
        name: data.get(name, _MISSING) for name in RECORD_FIELDS if name != "opinions"
    }
    raw_opinions = data.get("opinions", _MISSING)
    if isinstance(raw_opinions, list):
        values["opinions"] = [
            _opinion_from_dict(item) if isinstance(item, dict) else item
            for item in raw_opinions
        ]
    else:
        values["opinions"] = raw_opinions
    return NewPipelineRecord(**values)


def _plain(value: Any) -> Any:
    return None if value is _MISSING else value


def record_to_dict(record: NewPipelineRecord) -> dict:
    """Serialise a record, emitting every schema key (nulls included)."""
    out: dict[str, Any] = {}
    for name in RECORD_FIELDS:
        if name == "opinions":
            continue
        out[name] = _plain(getattr(record, name, None))

    opinions = getattr(record, "opinions", None)
    serialised: list[dict] = []
    if isinstance(opinions, list):
        for opinion in opinions:
            if isinstance(opinion, Opinion):
                serialised.append(
                    {name: _plain(getattr(opinion, name, None)) for name in OPINION_FIELDS}
                )
    out["opinions"] = serialised

    # Keep key order aligned with RECORD_FIELDS for stable, diffable output.
    return {name: out[name] for name in RECORD_FIELDS}


def read_jsonl(path: "str | Path") -> list[NewPipelineRecord]:
    """Read one record per non-blank line.

    A structurally incomplete line is still returned as a record (with missing
    keys flagged internally) so ``validate_all`` can report it, rather than the
    read itself raising.
    """
    records: list[NewPipelineRecord] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(record_from_dict(json.loads(line)))
    return records


def write_jsonl(records: list[NewPipelineRecord], path: "str | Path") -> None:
    """Write one JSON object per line in canonical schema key order."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record_to_dict(record), ensure_ascii=False) + "\n")
