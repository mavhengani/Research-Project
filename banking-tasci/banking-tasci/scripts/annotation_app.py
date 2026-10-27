"""Annotation_Interface: a local Streamlit app for annotating the pilot
sample with aspect spans, categories, sentiments, and intent (Requirement 18).

Usage (preferred — separate sessions per annotator):
    streamlit run scripts/annotation_app.py -- \\
        --input data/annotations/pilot_unannotated.jsonl \\
        --output data/annotations/pilot_annotator_a.jsonl \\
        --annotator-id annotator_a

    streamlit run scripts/annotation_app.py -- \\
        --input data/annotations/pilot_unannotated.jsonl \\
        --output data/annotations/pilot_annotator_b.jsonl \\
        --annotator-id annotator_b

When --output and --annotator-id are supplied on the CLI the app writes
exclusively to the given output path and pre-fills (and locks) the
annotator-ID field, making it impossible to accidentally overwrite another
annotator's file.

If no CLI arguments are supplied the app falls back to its original
behaviour: the annotator enters their ID in the sidebar and the output path
is derived as data/annotations/pilot_{annotator_id}.jsonl.

Reads `data/annotations/pilot_unannotated.jsonl` on first use for a given
`annotator_id`, or resumes from the target output file if one already exists.
Every save writes ONLY to the entered annotator's own output file —
another annotator's `pilot_*.jsonl` file is never read for writing nor
overwritten (Req 18.8).

Runs entirely locally: no network calls, no external API calls, no
CDN-hosted assets (Req 18.12). `streamlit` itself runs as a local web
server once installed.

Design note: every behavior that can be verified without a live UI
(offset validation, record loading/resuming, per-annotator save/no-
overwrite logic, progress calculation, aspect add/remove, record-id-
preserving updates) is implemented below as a plain, Streamlit-free
function so it can be unit-tested directly (see
`tests/test_annotation_app.py`). The Streamlit widgets live only inside
`main()`, which is invoked only when this file is run via
`streamlit run` (i.e. only under `if __name__ == "__main__"`), so
importing this module for testing never touches Streamlit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.data.annotations import (  # noqa: E402
    ASPECT_CATEGORIES,
    ASPECT_SENTIMENTS,
    INTENT_LABELS,
    AnnotationRecord,
    AspectSpan,
    read_jsonl,
    write_jsonl,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS_DIR = PROJECT_ROOT / "data" / "annotations"
DEFAULT_UNANNOTATED_PATH = ANNOTATIONS_DIR / "pilot_unannotated.jsonl"

NO_CONTEXT_MARKER = "[NO_CONTEXT]"


# ---------------------------------------------------------------------------
# CLI argument parsing (supports Streamlit's `--` separator)
# ---------------------------------------------------------------------------


def _parse_cli_args() -> "argparse.Namespace | None":
    """Parse arguments passed after `--` in a `streamlit run` invocation.

    When Streamlit forwards remaining arguments after `--`, they appear in
    `sys.argv`.  Returns a namespace with `input`, `output`, and
    `annotator_id` attributes when any of those are supplied, or None when
    the app was invoked with no arguments (legacy sidebar-only mode).
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--annotator-id", dest="annotator_id", default=None)

    # Use parse_known_args so Streamlit's own injected flags do not error.
    namespace, _ = parser.parse_known_args()

    # Return None when no relevant argument was supplied (legacy mode).
    if namespace.input is None and namespace.output is None and namespace.annotator_id is None:
        return None
    return namespace


# ---------------------------------------------------------------------------
# Pure logic (Streamlit-free, unit-tested in tests/test_annotation_app.py)
# ---------------------------------------------------------------------------


def annotator_output_path(annotator_id: str, annotations_dir: "str | Path" = ANNOTATIONS_DIR) -> Path:
    """Derive the per-annotator output path (Req 18.8).

    Deriving the filename directly from `annotator_id` is what guarantees
    two different annotators never write to the same file."""
    safe_id = annotator_id.strip()
    return Path(annotations_dir) / f"pilot_{safe_id}.jsonl"


def load_session_records(
    annotator_id: str,
    unannotated_path: "str | Path" = DEFAULT_UNANNOTATED_PATH,
    annotations_dir: "str | Path" = ANNOTATIONS_DIR,
    explicit_output_path: "str | Path | None" = None,
) -> list[AnnotationRecord]:
    """Resume from the annotator's own file if it already exists, else
    start fresh from the shared unannotated sample (Req 18.8, resuming
    behavior described in the task).

    When `explicit_output_path` is provided (CLI mode), that path is used
    as the resume/output file instead of the derived annotator path.  This
    allows different annotators to write to arbitrary, non-colliding paths
    while still never reading from or writing to each other's files.

    When starting fresh, every record's `annotator_id` is set to the
    entered `annotator_id`; `record_id`, `source`, `region`, `text`,
    `previous_text`, and `context_available` are left exactly as loaded."""
    if explicit_output_path is not None:
        existing_path = Path(explicit_output_path)
    else:
        existing_path = annotator_output_path(annotator_id, annotations_dir)

    if existing_path.exists():
        return read_jsonl(existing_path)

    records = read_jsonl(unannotated_path)
    for record in records:
        record.annotator_id = annotator_id
    return records


def validate_span(text: str, start: Any, end: Any) -> "str | None":
    """Return an error message when `start`/`end` is out of bounds for
    `text` or `start >= end`; return `None` when the span is valid
    (Req 18.11)."""
    if not isinstance(text, str):
        return "Record has no text to select a span from."
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool):
        return "Start and end must be integers."
    if start < 0 or end > len(text):
        return f"Span [{start}:{end}] is out of bounds for text of length {len(text)}."
    if start >= end:
        return "Start must be less than end."
    return None


def add_aspect(
    pending_aspects: list[dict],
    text: str,
    start: Any,
    end: Any,
    category: str,
    sentiment: str,
) -> "tuple[list[dict], str | None]":
    """Validate the requested span and, if valid, return a NEW list with
    the aspect appended plus `None`; otherwise return the unchanged list
    plus an error message (Req 18.2, 18.3, 18.4, 18.5, 18.11). Never
    mutates `pending_aspects` in place."""
    error = validate_span(text, start, end)
    if error is not None:
        return pending_aspects, error
    if category not in ASPECT_CATEGORIES:
        return pending_aspects, f"'{category}' is not a valid aspect category."
    if sentiment not in ASPECT_SENTIMENTS:
        return pending_aspects, f"'{sentiment}' is not a valid aspect sentiment."

    term = text[start:end]
    new_aspect = {"term": term, "start": start, "end": end, "category": category, "sentiment": sentiment}
    return pending_aspects + [new_aspect], None


def remove_aspect(pending_aspects: list[dict], index: int) -> list[dict]:
    """Return a NEW list with the aspect at `index` removed (Req 18.5's
    "way to remove an already-added aspect"). Out-of-range `index` returns
    the list unchanged rather than raising."""
    if index < 0 or index >= len(pending_aspects):
        return list(pending_aspects)
    return pending_aspects[:index] + pending_aspects[index + 1 :]


def resolve_annotation_status(want_completed: bool, intent: Any) -> "tuple[str, str | None]":
    """Decide the `annotation_status` to save, mirroring
    `annotations.check_completed_intent`: `annotation_status="completed"`
    requires a non-null, non-empty `intent`. Returns `(status, warning)`;
    `warning` is `None` unless the annotator asked for "completed" without
    a usable intent, in which case the record is saved as `"in_progress"`
    instead and a warning is returned for the UI to display."""
    if want_completed:
        if intent is None or intent == "":
            return "in_progress", "Cannot mark as completed without selecting an intent. Saved as in_progress instead."
        return "completed", None
    return "in_progress", None


def build_updated_record(
    original: AnnotationRecord,
    *,
    aspects: list[AspectSpan],
    intent: Any,
    intent_ambiguous: bool,
    alternative_intent: Any,
    annotator_id: str,
    notes: str,
    annotation_status: str,
) -> AnnotationRecord:
    """Build the record to save, preserving `record_id`, `source`,
    `region`, `text`, `previous_text`, `context_available` from `original`
    unchanged; only the annotator-editable fields are replaced (per the
    task's structural notes)."""
    return AnnotationRecord(
        record_id=original.record_id,
        source=original.source,
        region=original.region,
        text=original.text,
        previous_text=original.previous_text,
        context_available=original.context_available,
        aspects=aspects,
        intent=intent,
        intent_ambiguous=intent_ambiguous,
        alternative_intent=alternative_intent,
        annotator_id=annotator_id,
        annotation_status=annotation_status,
        notes=notes,
    )


def update_record_in_list(
    records: list[AnnotationRecord], record_id: Any, updated: AnnotationRecord
) -> list[AnnotationRecord]:
    """Return a NEW list with the record whose `record_id` matches
    replaced by `updated`, so saving an already-present record replaces
    its line rather than duplicating it (Req 18.8). Raises `ValueError`
    if no record with `record_id` is found, since that indicates a
    programming error (the record must already be part of the session's
    working set before it can be updated)."""
    new_records = list(records)
    for idx, record in enumerate(new_records):
        if record.record_id == record_id:
            new_records[idx] = updated
            return new_records
    raise ValueError(f"No record with record_id={record_id!r} found to update")


def save_annotator_file(
    records: list[AnnotationRecord],
    annotator_id: str,
    annotations_dir: "str | Path" = ANNOTATIONS_DIR,
    explicit_output_path: "str | Path | None" = None,
) -> Path:
    """Write `records` to the annotator's output file only (Req 18.8).

    When `explicit_output_path` is provided (CLI mode), writes to that path.
    Otherwise derives the path from `annotator_id` so this function
    structurally cannot write to another annotator's file."""
    if explicit_output_path is not None:
        path = Path(explicit_output_path)
    else:
        path = annotator_output_path(annotator_id, annotations_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(records, path)
    return path


def compute_progress(records: list[AnnotationRecord]) -> "tuple[int, int]":
    """Return `(completed_count, total_count)` based on which records
    already have `annotation_status="completed"` (Req 18.10)."""
    total = len(records)
    completed = sum(1 for record in records if getattr(record, "annotation_status", None) == "completed")
    return completed, total


def clamp_index(index: int, total: int) -> int:
    """Clamp a navigation index to the valid `[0, total - 1]` range (or
    `0` when `total <= 0`), used by the Previous/Next navigation
    (Req 18.9)."""
    if total <= 0:
        return 0
    return max(0, min(index, total - 1))


def aspect_dicts_from_record(record: AnnotationRecord) -> list[dict]:
    """Convert `record.aspects` (a list of `AspectSpan`) into the plain
    dict shape used by the editable `pending_aspects` UI state."""
    aspects = record.aspects if isinstance(record.aspects, list) else []
    return [
        {"term": a.term, "start": a.start, "end": a.end, "category": a.category, "sentiment": a.sentiment}
        for a in aspects
        if isinstance(a, AspectSpan)
    ]


def aspect_spans_from_dicts(pending_aspects: list[dict]) -> list[AspectSpan]:
    """Convert the editable `pending_aspects` dict list back into
    `AspectSpan` objects for saving."""
    return [
        AspectSpan(
            term=a["term"], start=a["start"], end=a["end"], category=a["category"], sentiment=a["sentiment"]
        )
        for a in pending_aspects
    ]


# ---------------------------------------------------------------------------
# Streamlit UI (only touched when run via `streamlit run`)
# ---------------------------------------------------------------------------


def main() -> None:
    import streamlit as st

    # Parse CLI args (passed after `--` in `streamlit run ... -- --arg val`).
    _cli = _parse_cli_args()
    _cli_input = Path(_cli.input) if _cli and _cli.input else DEFAULT_UNANNOTATED_PATH
    _cli_output = Path(_cli.output) if _cli and _cli.output else None
    _cli_annotator_id = _cli.annotator_id if _cli and _cli.annotator_id else None

    st.set_page_config(page_title="Banking TASCI Annotation Interface", layout="wide")

    st.sidebar.title("Annotator")

    # When --annotator-id is supplied via CLI, lock it so the annotator
    # cannot accidentally overwrite another person's file by changing it.
    if _cli_annotator_id:
        st.sidebar.text_input("Annotator ID (locked)", value=_cli_annotator_id, disabled=True)
        annotator_id = _cli_annotator_id
    else:
        annotator_id = st.sidebar.text_input(
            "Annotator ID", value=st.session_state.get("annotator_id", "")
        ).strip()

    st.title("Banking TASCI Annotation Interface")

    if not annotator_id:
        st.sidebar.warning("Enter an annotator ID to begin.")
        st.info("Enter your annotator ID in the sidebar to load the pilot sample.")
        return

    # Session key incorporates the output path so different CLI invocations
    # don't share the same Streamlit session state.
    _session_key = f"{annotator_id}::{_cli_output}"
    if st.session_state.get("_session_key") != _session_key or "records" not in st.session_state:
        try:
            loaded = load_session_records(
                annotator_id,
                _cli_input,
                ANNOTATIONS_DIR,
                explicit_output_path=_cli_output,
            )
        except FileNotFoundError:
            st.error(
                f"Input sample not found at `{_cli_input}`. "
                "Run `scripts/create_annotation_sample.py` first to generate the "
                "pilot sample, then reload this page."
            )
            return
        st.session_state._session_key = _session_key
        st.session_state.annotator_id = annotator_id
        st.session_state.records = loaded
        st.session_state.current_index = 0
        st.session_state.pending_aspects = None
        st.session_state.pending_aspects_index = None

    records: list[AnnotationRecord] = st.session_state.records
    total = len(records)
    if total == 0:
        st.error(f"No records found. Ensure {_cli_input} exists (run create_annotation_sample.py first).")
        return

    current_index = clamp_index(st.session_state.current_index, total)
    st.session_state.current_index = current_index

    completed, total_count = compute_progress(records)
    st.sidebar.metric("Progress", f"{completed} / {total_count} completed")
    st.sidebar.write(f"Record {current_index + 1} of {total_count}")
    if _cli_output:
        st.sidebar.caption(f"Output: `{_cli_output}`")

    nav_col1, nav_col2 = st.sidebar.columns(2)
    if nav_col1.button("Previous", disabled=current_index == 0, use_container_width=True):
        st.session_state.current_index = clamp_index(current_index - 1, total)
        st.session_state.pending_aspects = None
        st.rerun()
    if nav_col2.button("Next", disabled=current_index >= total - 1, use_container_width=True):
        st.session_state.current_index = clamp_index(current_index + 1, total)
        st.session_state.pending_aspects = None
        st.rerun()

    record = records[current_index]

    if st.session_state.get("pending_aspects") is None or st.session_state.get("pending_aspects_index") != current_index:
        st.session_state.pending_aspects = aspect_dicts_from_record(record)
        st.session_state.pending_aspects_index = current_index

    st.caption(f"Record ID: `{record.record_id}`  |  Source: {record.source}  |  Region: {record.region}")

    prev_col, text_col = st.columns(2)
    with prev_col:
        st.subheader("Previous context (read-only)")
        prev_text = record.previous_text if record.previous_text else NO_CONTEXT_MARKER
        if prev_text == NO_CONTEXT_MARKER:
            st.markdown(
                "<div style='color:#999; font-style:italic; padding:0.6em; "
                "border:1px dashed #ccc; border-radius:4px;'>[NO_CONTEXT]</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='color:#777; padding:0.6em; border:1px solid #ddd; "
                f"border-radius:4px; background-color:#f5f5f5;'>{prev_text}</div>",
                unsafe_allow_html=True,
            )
    with text_col:
        st.subheader("Current text")
        st.markdown(
            f"<div style='padding:0.6em; border:1px solid #333; border-radius:4px;'>{record.text}</div>",
            unsafe_allow_html=True,
        )

    text = record.text if isinstance(record.text, str) else ""

    st.divider()
    st.subheader("Aspect spans")

    if not st.session_state.pending_aspects:
        st.caption("No aspects recorded yet.")
    for idx, aspect in enumerate(st.session_state.pending_aspects):
        cols = st.columns([4, 2, 2, 1])
        cols[0].write(f"\u201c{aspect['term']}\u201d  [{aspect['start']}:{aspect['end']}]")
        cols[1].write(aspect["category"])
        cols[2].write(aspect["sentiment"])
        if cols[3].button("Remove", key=f"remove_aspect_{current_index}_{idx}"):
            st.session_state.pending_aspects = remove_aspect(st.session_state.pending_aspects, idx)
            st.rerun()

    st.markdown("**Add a new aspect span**")
    span_cols = st.columns([1, 1, 2, 2, 1])
    max_offset = max(len(text), 0)
    start = span_cols[0].number_input(
        "Start", min_value=0, max_value=max_offset, value=0, step=1, key=f"span_start_{current_index}"
    )
    end = span_cols[1].number_input(
        "End", min_value=0, max_value=max_offset, value=0, step=1, key=f"span_end_{current_index}"
    )
    category = span_cols[2].selectbox("Category", ASPECT_CATEGORIES, key=f"span_category_{current_index}")
    sentiment = span_cols[3].selectbox("Sentiment", ASPECT_SENTIMENTS, key=f"span_sentiment_{current_index}")

    preview_error = validate_span(text, int(start), int(end))
    if preview_error is not None:
        span_cols[4].caption(" ")
        st.caption(f"Preview: {preview_error}")
    else:
        st.caption(f"Preview: text[{int(start)}:{int(end)}] = \u201c{text[int(start):int(end)]}\u201d")

    if st.button("Add aspect", key=f"add_aspect_{current_index}"):
        new_list, error = add_aspect(
            st.session_state.pending_aspects, text, int(start), int(end), category, sentiment
        )
        if error is not None:
            st.error(error)
        else:
            st.session_state.pending_aspects = new_list
            st.rerun()

    st.divider()
    st.subheader("Intent")
    intent_options = ["(none)"] + INTENT_LABELS
    current_intent = record.intent if record.intent in INTENT_LABELS else "(none)"
    intent_choice = st.selectbox(
        "Dominant intent", intent_options, index=intent_options.index(current_intent), key=f"intent_{current_index}"
    )
    intent = None if intent_choice == "(none)" else intent_choice

    ambiguous = st.checkbox(
        "Intent is ambiguous", value=bool(record.intent_ambiguous), key=f"ambiguous_{current_index}"
    )
    alternative_intent = None
    if ambiguous:
        current_alt = record.alternative_intent if record.alternative_intent in INTENT_LABELS else "(none)"
        alt_choice = st.selectbox(
            "Alternative intent",
            intent_options,
            index=intent_options.index(current_alt),
            key=f"alt_intent_{current_index}",
        )
        alternative_intent = None if alt_choice == "(none)" else alt_choice

    notes = st.text_area("Notes", value=record.notes or "", key=f"notes_{current_index}")

    st.divider()
    mark_completed = st.checkbox(
        "Mark as completed", value=(record.annotation_status == "completed"), key=f"mark_completed_{current_index}"
    )

    if st.button("Save", type="primary", key=f"save_{current_index}"):
        status, warning = resolve_annotation_status(mark_completed, intent)
        updated = build_updated_record(
            record,
            aspects=aspect_spans_from_dicts(st.session_state.pending_aspects),
            intent=intent,
            intent_ambiguous=ambiguous,
            alternative_intent=alternative_intent,
            annotator_id=annotator_id,
            notes=notes,
            annotation_status=status,
        )
        st.session_state.records = update_record_in_list(records, record.record_id, updated)
        save_annotator_file(
            st.session_state.records,
            annotator_id,
            ANNOTATIONS_DIR,
            explicit_output_path=_cli_output,
        )
        if warning is not None:
            st.warning(warning)
        else:
            st.success(f"Saved record {record.record_id} as {status}.")
        st.rerun()


if __name__ == "__main__":
    main()
