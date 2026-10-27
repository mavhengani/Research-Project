"""Anonymisation of sensitive substrings for the banking-tasci project.

Replaces personally identifying or sensitive substrings (emails, URLs,
mentions, account/reference numbers, phone numbers, and — when enabled —
transaction amounts) with fixed placeholder tokens, rewrites hashtags in
place (stripping the leading `#`), and never touches negation or
intensifier words. Never surfaces an original replaced value anywhere
(audit report, logs, or exception messages) — only counts.

Requirements:
- 6.1: replace email addresses with `[EMAIL]`.
- 6.2: replace URLs with `[URL]`.
- 6.3: replace user mentions with `[USER]`.
- 6.4: replace account/reference-number matches with `[ACCOUNT_OR_REFERENCE]`.
- 6.5: replace phone-number matches with `[PHONE]`.
- 6.6: replace transaction amounts with `[AMOUNT]` when enabled.
- 6.7: preserve negation and intensifier words unchanged.
- 6.8: retain a hashtag's alphanumeric body, without the leading `#`.
- 6.9: (via ingest.py's batch usage) audit reports counts only.
- 6.10: halt processing and raise AnonymisationError if a detected span
  cannot be substituted, rather than returning partially-anonymised text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from banking_tasci.config import Config

REPLACEMENT_TOKENS = {
    "email": "[EMAIL]",
    "url": "[URL]",
    "mention": "[USER]",
    "account_or_reference": "[ACCOUNT_OR_REFERENCE]",
    "phone": "[PHONE]",
    "amount": "[AMOUNT]",
}

# Fixed order in which sensitive-pattern replacements are applied. `amount`
# is appended conditionally (only when cfg.anonymise.replace_amounts is
# true) so it always runs last, per design.md.
_ALWAYS_ORDER = ["email", "url", "mention", "account_or_reference", "phone"]

# Fixed, well-known regexes for patterns the spec does not ask to be
# configurable. Account/reference and phone patterns come from `cfg`
# instead (Requirement 6.4 / 6.5's "configured pattern" language).
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+")
MENTION_PATTERN = re.compile(r"@\w+")
AMOUNT_PATTERN = re.compile(r"[$£€]\s?\d+(?:,\d{3})*(?:\.\d{1,2})?")
HASHTAG_PATTERN = re.compile(r"#(\w+)")

# Words that must never be matched/touched by any replacement pattern
# (Requirement 6.7). Exposed as constants so tests can draw from the same
# canonical list.
NEGATION_WORDS = ["not", "no", "never", "n't", "cannot", "none", "neither"]
INTENSIFIER_WORDS = ["very", "extremely", "really", "so", "too", "quite"]

# Unicode Private Use Area start: used to mask hashtag bodies with single,
# non-word, non-digit characters while other patterns run, so a
# digit-heavy hashtag body (e.g. "#123456789") can never be mistaken for
# an account/reference or phone match (Requirement 6.8).
_HASHTAG_MASK_BASE = 0xE000

# A separate Private Use Area range (disjoint from the hashtag range above,
# which is bounded by len(bodies) and in practice stays far below this
# offset) used to mask amount-prefixed and ISO-8601-date-shaped digit
# substrings before the phone pattern runs, so they can never be
# misclassified as `[PHONE]` (Requirement 11.7).
_GUARD_MASK_BASE = 0xE800

# Matches a currency symbol immediately followed by a digit run (with
# optional thousands separators and decimal portion) — e.g. "$1,250.00",
# "£42", "€1.250,00". The leading currency symbol is included in the mask
# so it cannot combine with adjacent digits to form a phone-like match.
_AMOUNT_GUARD_PATTERN = re.compile(r"[$£€]\s?\d+(?:[,.]\d+)*")

# Matches an ISO-8601-style date, e.g. "2020-03-21".
_ISO_DATE_GUARD_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class AnonymisationError(Exception):
    """Raised when a detected sensitive span could not be replaced.

    Processing of that text halts immediately; no partially-anonymised
    result is returned (Req 6.10). The message never includes the
    original matched value — only the pattern name and match count.
    """


@dataclass
class AnonymisationAudit:
    """Counts of replacements performed, by pattern type. Never carries
    original replaced values (Req 6.9)."""

    counts: dict[str, int] = field(default_factory=lambda: {key: 0 for key in REPLACEMENT_TOKENS})

    def merge(self, other: "AnonymisationAudit") -> "AnonymisationAudit":
        """Return a new audit with counts summed key-by-key."""
        merged = dict(self.counts)
        for key, value in other.counts.items():
            merged[key] = merged.get(key, 0) + value
        return AnonymisationAudit(merged)

    def to_dict(self) -> dict[str, int]:
        """Return a plain dict copy of the counts (counts only, Req 6.9)."""
        return dict(self.counts)


def _mask_hashtags(text: str) -> tuple[str, list[str]]:
    """Replace each `#body` hashtag with a unique single-character mask.

    Masking runs before any other pattern so hashtag bodies (which may be
    all-digit, e.g. `#123456789`) can never be caught by the account/
    reference or phone regexes. Returns the masked text and the list of
    stripped hashtag bodies, indexed by mask position (Req 6.8).
    """
    bodies: list[str] = []

    def _mask(match: re.Match) -> str:
        bodies.append(match.group(1))
        return chr(_HASHTAG_MASK_BASE + len(bodies) - 1)

    masked = HASHTAG_PATTERN.sub(_mask, text)
    return masked, bodies


def _unmask_hashtags(text: str, bodies: list[str]) -> str:
    """Restore masked hashtag bodies (without their leading `#`)."""
    if not bodies:
        return text
    mask_chars = "".join(chr(_HASHTAG_MASK_BASE + i) for i in range(len(bodies)))
    mask_pattern = re.compile("[" + mask_chars + "]")

    def _unmask(match: re.Match) -> str:
        return bodies[ord(match.group(0)) - _HASHTAG_MASK_BASE]

    return mask_pattern.sub(_unmask, text)


def _mask_guarded_substrings(text: str) -> tuple[str, list[str]]:
    """Replace each amount-prefixed or ISO-8601-date-shaped substring with a
    unique single-character mask from a Private Use Area range disjoint
    from the hashtag mask range.

    Runs before the phone pattern (and before account/reference, email,
    URL, and mention, since it runs first overall) so those substrings can
    never be misclassified as `[PHONE]`, regardless of `replace_amounts`
    configuration (Req 11.7). Uses the same technique as `_mask_hashtags`.
    Returns the masked text and the list of stripped original substrings,
    indexed by mask position.
    """
    bodies: list[str] = []

    def _mask(match: re.Match) -> str:
        bodies.append(match.group(0))
        return chr(_GUARD_MASK_BASE + len(bodies) - 1)

    # Amount guard first, then date guard, so an amount-shaped substring is
    # masked before the (non-overlapping) date pattern is even attempted.
    masked = _AMOUNT_GUARD_PATTERN.sub(_mask, text)
    masked = _ISO_DATE_GUARD_PATTERN.sub(_mask, masked)
    return masked, bodies


def _unmask_guarded_substrings(text: str, bodies: list[str]) -> str:
    """Restore masked amount/date substrings to their original form."""
    if not bodies:
        return text
    mask_chars = "".join(chr(_GUARD_MASK_BASE + i) for i in range(len(bodies)))
    mask_pattern = re.compile("[" + mask_chars + "]")

    def _unmask(match: re.Match) -> str:
        return bodies[ord(match.group(0)) - _GUARD_MASK_BASE]

    return mask_pattern.sub(_unmask, text)


def _apply_replacement(pattern: "re.Pattern[str]", token: str, text: str) -> tuple[str, int]:
    """Substitute every match of `pattern` in `text` with `token`.

    Isolated as its own function (rather than inlined) so a replacement
    failure can be simulated by mocking this function in tests, exercising
    the AnonymisationError path (Req 6.10) without needing a genuinely
    broken regex.
    """
    return pattern.subn(token, text)


def _replacement_patterns(cfg: "Config") -> dict[str, "re.Pattern[str]"]:
    return {
        "email": EMAIL_PATTERN,
        "url": URL_PATTERN,
        "mention": MENTION_PATTERN,
        "account_or_reference": re.compile(cfg.anonymise.account_reference_pattern),
        "phone": re.compile(cfg.anonymise.phone_pattern),
        "amount": AMOUNT_PATTERN,
    }


def _run_replacement_step(
    key: str, working: str, patterns: dict[str, "re.Pattern[str]"], counts: dict[str, int]
) -> str:
    """Apply the `key` pattern's replacement to `working`, updating `counts`
    in place and returning the (possibly unchanged) resulting text.

    Isolated so both the fixed-order loop and the conditional amount step
    share identical failure handling (Req 6.10).
    """
    pattern = patterns[key]
    token = REPLACEMENT_TOKENS[key]
    if not pattern.search(working):
        return working
    try:
        new_working, replaced_count = _apply_replacement(pattern, token, working)
    except Exception as exc:  # noqa: BLE001 - convert any failure to AnonymisationError
        raise AnonymisationError(
            f"Failed to substitute detected '{key}' span(s)"
        ) from exc
    if replaced_count == 0 or token not in new_working:
        raise AnonymisationError(
            f"Detected a '{key}' span but it could not be substituted"
        )
    counts[key] += replaced_count
    return new_working


def anonymise_text(text: str, cfg: "Config") -> tuple[str, AnonymisationAudit]:
    """Anonymise a single text, returning the result and a per-call audit.

    Applies email, URL, mention, account/reference, and phone replacement
    (always), then amount replacement only when
    `cfg.anonymise.replace_amounts` is true — in that fixed order, so a
    later pattern never re-matches text a prior pattern already replaced.
    Hashtags are rewritten in place (`#` stripped, body kept) rather than
    replaced with a token, and are protected from every other pattern
    while they run. Negation/intensifier words contain no `@`, digits, or
    currency symbols, so no fixed or configured pattern here can match
    them (Req 6.7).

    Before the fixed-order patterns run, amount-prefixed digit substrings
    (preceded by `$`, `£`, or `€`) and ISO-8601-date-shaped substrings are
    masked (same private-use-area technique as hashtags), so the phone
    pattern can never see and misclassify them as `[PHONE]` (Req 11.7).
    They are unmasked again immediately after the phone step so the
    (conditionally last) amount pattern still sees the original
    currency-symbol-plus-digits text when `replace_amounts` is enabled.

    Raises AnonymisationError immediately (without returning a partial
    result) if a detected span cannot be substituted (Req 6.10).
    """
    counts = {key: 0 for key in REPLACEMENT_TOKENS}

    working, hashtag_bodies = _mask_hashtags(text)
    working, guard_bodies = _mask_guarded_substrings(working)

    patterns = _replacement_patterns(cfg)

    for key in _ALWAYS_ORDER:
        working = _run_replacement_step(key, working, patterns, counts)

    # Restore amount/date substrings now that the phone pattern has already
    # run without seeing them, so the amount pattern (if enabled) can still
    # match them normally (Req 11.7).
    working = _unmask_guarded_substrings(working, guard_bodies)

    if getattr(getattr(cfg, "anonymise", None), "replace_amounts", False):
        working = _run_replacement_step("amount", working, patterns, counts)

    anonymised = _unmask_hashtags(working, hashtag_bodies)
    return anonymised, AnonymisationAudit(counts)


def anonymise_batch(texts: Iterable[str], cfg: "Config") -> tuple[list[str], AnonymisationAudit]:
    """Anonymise each text in `texts`; return anonymised texts plus one
    combined `AnonymisationAudit` (counts only — never includes original
    matched substrings, whether called as a batch or via `anonymise_text`
    directly) (Req 6.9).
    """
    anonymised_texts: list[str] = []
    combined = AnonymisationAudit()
    for text in texts:
        anonymised, audit = anonymise_text(text, cfg)
        anonymised_texts.append(anonymised)
        combined = combined.merge(audit)
    return anonymised_texts, combined
