"""Evidence-based customer-feedback candidate filter for the South African
banking Twitter dataset.

Replaces the broad length-based catch-all with six explicit matching rules
that require both a banking-service reference and a customer-experience signal.

For performance on large corpora, phrase matching uses simple case-insensitive
substring matching on lower-cased text padded with spaces, rather than
compiled word-boundary regex patterns. Space-padding prevents short tokens like
'app' from matching inside longer words like 'happy'.

Rules
-----
A  banking_aspect + problem/dissatisfaction expression
B  banking_aspect + request/action expression
C  first_person_ownership + banking_aspect
D  positive_service_experience + bank/service reference
E  suggestion / warning / churn expression + banking reference
F  strongly specific multi-word banking-issue phrases (qualify independently)

These rules are sampling heuristics — they are NOT gold labels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Fast keyword matching using padded substring approach
# ---------------------------------------------------------------------------

def _pad(phrase: str) -> str:
    """Return a space-padded version of ``phrase`` for substring matching.

    By padding both sides with a space (and matching against a space-padded
    text), short tokens like ``app`` cannot match inside ``happy`` because
    `` app `` is not a substring of `` happy ``.
    Multi-word phrases match naturally since they contain spaces.
    """
    return f" {phrase.strip().lower()} "


def _any_kw(keywords: "list[str]", padded_text: str) -> bool:
    """Return True when any keyword (space-padded) is found in padded_text."""
    return any(_pad(kw) in padded_text for kw in keywords)


def _pad_text(text: str) -> str:
    """Lowercase and pad a text string for keyword matching."""
    return f" {text.lower()} "


# ---------------------------------------------------------------------------
# Keyword lists (plain strings, no regex)
# ---------------------------------------------------------------------------

BANKING_ASPECT_KW: list[str] = [
    "account", "transfer", "payment", "transaction", "beneficiary",
    "reversal", "refund", "atm", "card", "pin", "fees", "fee",
    "charges", "charge", "deductions", "deduction", "debit order",
    "mobile app", "banking app", "online banking", "internet banking",
    "mobile banking", "branch", "teller", "queue", "fraud", "scam",
    "unauthorised transaction", "unauthorized transaction",
    "customer service", "customer care", "support", "consultant",
    "loan", "credit", "savings", "balance", "statement", "deposit",
    "withdrawal",
]

PROBLEM_KW: list[str] = [
    "failed", "declined", "blocked", "frozen", "pending", "delayed",
    "reversed incorrectly", "debited but not credited", "not working",
    "cannot log in", "can't log in", "no response", "still waiting",
    "unresolved", "poor service", "terrible service", "bad service",
    "unfair charge", "money missing", "account hacked", "not received",
    "not credited", "not reversed", "not refunded", "disappointing",
    "disappointed", "terrible", "horrible", "worst", "pathetic",
    "useless", "incompetent", "frustrated", "unacceptable", "shocking",
    "disgusting", "embarrassing", "poor", "ignored", "error", "issue",
    "problem", "unable to", "cannot access", "can't access",
]

REQUEST_KW: list[str] = [
    "please help", "please assist", "assist me", "resolve this",
    "reverse the transaction", "reverse my", "refund me", "refund my",
    "investigate", "unblock my", "unfreeze my", "contact me",
    "respond to my", "explain this charge", "kindly", "need help",
    "can you help", "please fix", "please resolve", "please reverse",
    "please refund", "please credit", "please update", "please check",
    "please look into", "please advise", "urgently need", "i require",
    "i need",
]

FIRST_PERSON_KW: list[str] = [
    "my account", "my card", "my transfer", "my payment", "my transaction",
    "my balance", "my money", "my funds", "my loan", "my debit order",
    "i was charged", "i cannot access", "i can't access",
    "i visited the branch", "i have been waiting", "they debited me",
    "they deducted", "i received a deduction", "i was debited",
    "i tried to", "i attempted", "i opened", "i applied", "i called",
    "i went to", "i deposited", "i transferred", "we have not received",
    "we haven't received", "i have not received", "i haven't received",
    "i still",
]

POSITIVE_KW: list[str] = [
    "great service", "excellent service", "helpful staff",
    "resolved quickly", "thank you for helping",
    "impressed with the service", "good customer service",
    "efficient consultant", "best bank", "well done", "love the service",
    "fantastic service", "amazing service", "good service",
    "thank you for resolving", "happy with the service", "satisfied with",
    "professional service", "excellent support", "great support",
    "very helpful", "super helpful", "good experience", "great experience",
]

POSITIVE_CONTEXT_KW: list[str] = [
    "bank", "banks", "banking", "support", "branch", "transaction",
    "account", "card", "app", "consultant", "staff", "fnb", "absa",
    "nedbank", "capitec", "standard bank",
]

SUGGESTION_KW: list[str] = [
    "should improve", "please add", "consider adding",
    "it would be better", "you need to improve", "should provide",
    "please introduce", "would be great if", "why not add",
    "recommend adding", "suggestion", "suggest that", "i suggest",
    "would recommend",
]

WARNING_KW: list[str] = [
    "do not use", "avoid this bank", "stay away", "be careful",
    "beware", "be warned", "stay far", "would not recommend",
    "would not advise", "don't trust",
]

CHURN_KW: list[str] = [
    "closing my account", "switching banks", "moving to another bank",
    "leaving this bank", "cancelling my account", "no longer banking with",
    "taking my business elsewhere", "close my account",
    "switch to another bank", "cancel my account", "leaving your bank",
    "i am done with", "fed up with this bank", "goodbye to this bank",
]

BANKING_REFERENCE_KW: list[str] = [
    "bank", "banks", "banking", "account", "card", "transaction",
    "transfer", "payment", "service", "app", "branch", "atm",
    "fnb", "absa", "nedbank", "capitec", "standard bank",
]

SPECIFIC_ISSUE_KW: list[str] = [
    "debited but not credited", "failed transaction", "failed transfer",
    "failed payment", "delayed reversal", "blocked account",
    "unauthorised transaction", "unauthorized transaction",
    "card not working", "app not working", "poor customer service",
    "account was hacked", "account has been hacked",
    "money was deducted", "money not received", "funds not received",
    "transfer not received", "payment not received",
    "payment not reflected", "transaction not reflected",
    "debit order dispute", "pending transaction",
    "incorrect deduction", "double deduction", "double charge",
]

PROMOTIONAL_KW: list[str] = [
    "competition", "giveaway", "prize", "limited time", "special offer",
    "terms apply", "tag a friend", "apply now", "sign up today",
    "free data", "cashback offer", "t&c apply", "t&cs apply",
    "follow us", "open an account today", "new account offer",
    "zero fees offer", "we are hiring", "career opportunity",
]

UNRELATED_BANK_KW: list[str] = [
    "river bank", "blood bank", "food bank", "memory bank",
    "seed bank", "gene bank", "time bank", "piggy bank",
    "bank of england", "bank of canada", "bank of japan",
    "bank of china", "bank of india", "bank of france", "bank of america",
]

MIN_TEXT_LENGTH = 15
_MIN_ALPHA_CHARS = 15


# ---------------------------------------------------------------------------
# Candidate decision logic
# ---------------------------------------------------------------------------


@dataclass
class CandidateResult:
    """Outcome of candidate classification for one record."""
    is_candidate: bool
    rule_matched: str
    matched_strata: list[str]
    is_promotional: bool
    filter_reason: str


def classify_candidate(text: str) -> CandidateResult:
    """Apply the evidence-based candidate filter to ``text``."""
    if not text or not isinstance(text, str):
        return CandidateResult(False, "none", [], False, "empty_text")

    if len(text.strip()) < MIN_TEXT_LENGTH:
        return CandidateResult(False, "none", [], False, "too_short")

    # Count meaningful alpha characters
    stripped = re.sub(r"\[(?:USER|URL|EMAIL|PHONE|ACCOUNT_OR_REFERENCE|AMOUNT)\]", "", text)
    alpha_chars = sum(1 for c in stripped if c.isalpha())
    if alpha_chars < _MIN_ALPHA_CHARS:
        return CandidateResult(False, "none", [], False, "insufficient_meaningful_content")

    pt = _pad_text(text)

    # Unrelated bank meanings
    if _any_kw(UNRELATED_BANK_KW, pt):
        return CandidateResult(False, "none", [], False, "unrelated_bank_meaning")

    is_promo = _any_kw(PROMOTIONAL_KW, pt)

    # Evaluate rules
    has_aspect   = _any_kw(BANKING_ASPECT_KW, pt)
    has_problem  = _any_kw(PROBLEM_KW, pt)
    has_request  = _any_kw(REQUEST_KW, pt)
    has_fp       = _any_kw(FIRST_PERSON_KW, pt)
    has_positive = _any_kw(POSITIVE_KW, pt)
    has_pos_ctx  = _any_kw(POSITIVE_CONTEXT_KW, pt)
    has_suggest  = _any_kw(SUGGESTION_KW, pt)
    has_warning  = _any_kw(WARNING_KW, pt)
    has_churn    = _any_kw(CHURN_KW, pt)
    has_specific = _any_kw(SPECIFIC_ISSUE_KW, pt)
    has_bank_ref = _any_kw(BANKING_REFERENCE_KW, pt)

    if has_specific:                                    rule = "F"
    elif has_aspect and has_problem:                    rule = "A"
    elif has_aspect and has_request:                    rule = "B"
    elif has_fp and has_aspect:                         rule = "C"
    elif has_positive and has_pos_ctx:                  rule = "D"
    elif (has_suggest or has_warning or has_churn) and has_bank_ref:
                                                        rule = "E"
    else:
                                                        rule = "none"

    is_candidate = rule != "none"

    # Promotional precedence
    if is_promo and is_candidate and not (has_fp or has_problem or has_specific):
        return CandidateResult(False, "none", [], True, "promotional_precedes_candidate")

    # Build sampling strata
    strata: list[str] = []
    if is_candidate:
        if has_specific or (has_aspect and has_problem and any(
            _pad(kw) in pt for kw in ["transfer", "payment", "transaction",
                                       "reversal", "refund", "deposit", "withdrawal"]
        )):
            strata.append("transactions_candidate")
        if any(_pad(kw) in pt for kw in ["customer service", "customer care", "support",
                                          "consultant", "helpline", "call centre", "call center"
                                          ]) and (has_problem or has_request):
            strata.append("customer_support_candidate")
        if (any(_pad(kw) in pt for kw in ["my account", "account"]) and
                (has_problem or has_request or has_fp)):
            strata.append("accounts_candidate")
        if (any(_pad(kw) in pt for kw in ["my card", "card", "pin", "debit card",
                                            "credit card"]) and
                (has_problem or has_request or has_fp)):
            strata.append("cards_candidate")
        if (any(_pad(kw) in pt for kw in ["mobile app", "banking app", "online banking",
                                            "internet banking", "mobile banking",
                                            "app not working", "login", "e-wallet",
                                            "ewallet"]) and
                (has_problem or has_request or has_fp)):
            strata.append("digital_banking_candidate")
        if (any(_pad(kw) in pt for kw in ["fee", "fees", "charge", "charges",
                                            "deduction", "debit order", "service fee",
                                            "maintenance fee"]) and
                (has_problem or has_request or has_fp or has_specific)):
            strata.append("fees_candidate")
        if any(_pad(kw) in pt for kw in ["fraud", "scam", "unauthorised", "unauthorized",
                                           "hacked", "phishing", "identity theft",
                                           "suspicious"]):
            strata.append("fraud_security_candidate")
        if any(_pad(kw) in pt for kw in ["branch", "teller", "queue"]) and (
                has_problem or has_request or has_fp or has_positive):
            strata.append("branch_service_candidate")
        if has_positive and has_pos_ctx:
            strata.append("positive_feedback_candidate")
        if has_suggest and has_bank_ref:
            strata.append("suggestion_candidate")
        if has_warning and has_bank_ref:
            strata.append("warning_candidate")
        if has_churn and has_bank_ref:
            strata.append("churn_candidate")

        # Deduplicate
        seen: set[str] = set()
        strata = [s for s in strata if not (s in seen or seen.add(s))]  # type: ignore

    filter_reason = (
        f"rule_{rule}" if is_candidate
        else ("promotional" if is_promo else "no_candidate_rule_matched")
    )

    return CandidateResult(
        is_candidate=is_candidate,
        rule_matched=rule,
        matched_strata=strata,
        is_promotional=is_promo,
        filter_reason=filter_reason,
    )


def is_potential_zero_aspect(text: str) -> bool:
    """Return True when a record is bank-related but lacks specific aspect terms."""
    BANK_NAME_KW = [
        "fnb", "absa", "nedbank", "capitec", "standard bank", "standardbank",
        "bank", "banking", "[user]",
    ]
    SPECIFIC_ASPECT_KW = [
        "transfer", "payment", "account", "card", "fee", "fees", "fraud",
        "branch", "atm", "loan", "transaction", "balance", "deposit",
        "mobile app", "banking app", "online banking",
    ]
    pt = _pad_text(text)
    has_bank_ref = _any_kw(BANK_NAME_KW, pt)
    has_specific = _any_kw(SPECIFIC_ASPECT_KW, pt)
    return has_bank_ref and not has_specific and len(text) >= MIN_TEXT_LENGTH


# Provide dummy pattern-like objects for backward-compat imports
BANKING_ASPECT_PATTERNS = BANKING_ASPECT_KW
PROBLEM_PATTERNS = PROBLEM_KW
REQUEST_PATTERNS = REQUEST_KW
FIRST_PERSON_PATTERNS = FIRST_PERSON_KW
POSITIVE_PATTERNS = POSITIVE_KW
POSITIVE_CONTEXT_PATTERNS = POSITIVE_CONTEXT_KW
SUGGESTION_PATTERNS = SUGGESTION_KW
WARNING_PATTERNS = WARNING_KW
CHURN_PATTERNS = CHURN_KW
SPECIFIC_ISSUE_PATTERNS = SPECIFIC_ISSUE_KW
PROMOTIONAL_PATTERNS = PROMOTIONAL_KW
BANKING_REFERENCE_PATTERNS = BANKING_REFERENCE_KW
UNRELATED_BANK_PATTERNS = UNRELATED_BANK_KW


def _wb(phrase):  # kept for test compat — returns dummy; fast path uses _pad
    import re
    tokens = phrase.strip().split()
    escaped = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(r"(?<!\w)" + escaped + r"(?!\w)", re.IGNORECASE)


def _any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)
    """Return a case-insensitive pattern that matches ``phrase`` at word
    boundaries on both sides.  Spaces within the phrase are treated as
    one-or-more whitespace characters.

    Short single-token phrases (e.g. ``app``) are wrapped in look-around
    assertions that require a non-word character (space, punctuation, start/
    end of string) on either side, preventing substring matches inside
    longer words.
    """
    # Split the phrase into tokens and re-escape each individually,
    # then join with \s+ to allow flexible whitespace between words.
    # This avoids the escaping issue with spaces.
    stripped = phrase.strip()
    tokens = stripped.split()
    escaped_tokens = [re.escape(t) for t in tokens]
    inner = r"\s+".join(escaped_tokens)
    # Use word-boundary anchors
    return re.compile(r"(?<!\w)" + inner + r"(?!\w)", re.IGNORECASE)


def _any(patterns: "list[re.Pattern]", text: str) -> bool:
    return any(p.search(text) for p in patterns)


# ---------------------------------------------------------------------------
# Phrase lists
# ---------------------------------------------------------------------------

# --- Banking aspect and service terms ---
BANKING_ASPECT_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("account"),
    _wb("transfer"),
    _wb("payment"),
    _wb("transaction"),
    _wb("beneficiary"),
    _wb("reversal"),
    _wb("refund"),
    _wb("atm"),
    _wb("card"),
    _wb("pin"),
    _wb("fees"),
    _wb("fee"),
    _wb("charges"),
    _wb("charge"),
    _wb("deductions"),
    _wb("deduction"),
    _wb("debit order"),
    _wb("mobile app"),
    _wb("banking app"),
    _wb("online banking"),
    _wb("internet banking"),
    _wb("mobile banking"),
    _wb("branch"),
    _wb("teller"),
    _wb("queue"),
    _wb("fraud"),
    _wb("scam"),
    _wb("unauthorised transaction"),
    _wb("unauthorized transaction"),
    _wb("customer service"),
    _wb("customer care"),
    _wb("support"),
    _wb("consultant"),
    _wb("loan"),
    _wb("credit"),
    _wb("savings"),
    _wb("balance"),
    _wb("statement"),
    _wb("deposit"),
    _wb("withdrawal"),
]]

# --- Problem / dissatisfaction expressions ---
PROBLEM_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("failed"),
    _wb("declined"),
    _wb("blocked"),
    _wb("frozen"),
    _wb("pending"),
    _wb("delayed"),
    _wb("reversed incorrectly"),
    _wb("debited but not credited"),
    _wb("not working"),
    _wb("cannot log in"),
    _wb("can't log in"),
    _wb("no response"),
    _wb("still waiting"),
    _wb("unresolved"),
    _wb("poor service"),
    _wb("terrible service"),
    _wb("bad service"),
    _wb("unfair charge"),
    _wb("money missing"),
    _wb("account hacked"),
    _wb("not received"),
    _wb("error"),
    _wb("issue"),
    _wb("problem"),
    _wb("unable to"),
    _wb("cannot access"),
    _wb("can't access"),
    _wb("not credited"),
    _wb("not reversed"),
    _wb("not refunded"),
    _wb("disappointing"),
    _wb("disappointed"),
    _wb("terrible"),
    _wb("horrible"),
    _wb("worst"),
    _wb("pathetic"),
    _wb("useless"),
    _wb("incompetent"),
    _wb("frustrated"),
    _wb("unacceptable"),
    _wb("shocking"),
    _wb("disgusting"),
    _wb("embarrassing"),
    _wb("poor"),
    _wb("ignored"),
]]

# --- Request / action expressions ---
REQUEST_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("please help"),
    _wb("please assist"),
    _wb("assist me"),
    _wb("resolve this"),
    _wb("reverse the transaction"),
    _wb("reverse my"),
    _wb("refund me"),
    _wb("refund my"),
    _wb("investigate"),
    _wb("unblock my"),
    _wb("unfreeze my"),
    _wb("contact me"),
    _wb("respond to my"),
    _wb("explain this charge"),
    _wb("kindly"),
    _wb("need help"),
    _wb("can you help"),
    _wb("please fix"),
    _wb("please resolve"),
    _wb("please reverse"),
    _wb("please refund"),
    _wb("please credit"),
    _wb("please update"),
    _wb("please check"),
    _wb("please look into"),
    _wb("please advise"),
    _wb("urgently need"),
    _wb("i require"),
    _wb("i need"),
]]

# --- First-person ownership / experience expressions ---
FIRST_PERSON_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("my account"),
    _wb("my card"),
    _wb("my transfer"),
    _wb("my payment"),
    _wb("my transaction"),
    _wb("my balance"),
    _wb("my money"),
    _wb("my funds"),
    _wb("my loan"),
    _wb("my debit order"),
    _wb("i was charged"),
    _wb("i cannot access"),
    _wb("i can't access"),
    _wb("i visited the branch"),
    _wb("i have been waiting"),
    _wb("they debited me"),
    _wb("they deducted"),
    _wb("i received a deduction"),
    _wb("i was debited"),
    _wb("i tried to"),
    _wb("i attempted"),
    _wb("i opened"),
    _wb("i applied"),
    _wb("i called"),
    _wb("i went to"),
    _wb("i deposited"),
    _wb("i transferred"),
    _wb("we have not received"),
    _wb("we haven't received"),
    _wb("i have not received"),
    _wb("i haven't received"),
    _wb("i haven't been"),
    _wb("i still"),
]]

# --- Positive customer experience ---
POSITIVE_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("great service"),
    _wb("excellent service"),
    _wb("helpful staff"),
    _wb("resolved quickly"),
    _wb("thank you for helping"),
    _wb("impressed with the service"),
    _wb("good customer service"),
    _wb("efficient consultant"),
    _wb("best bank"),
    _wb("well done"),
    _wb("love the service"),
    _wb("fantastic service"),
    _wb("amazing service"),
    _wb("good service"),
    _wb("thank you for resolving"),
    _wb("happy with the service"),
    _wb("satisfied with"),
    _wb("professional service"),
    _wb("excellent support"),
    _wb("great support"),
    _wb("very helpful"),
    _wb("super helpful"),
    _wb("good experience"),
    _wb("great experience"),
]]

# Positive reference context (must co-occur with a positive expression)
POSITIVE_CONTEXT_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("bank"),
    _wb("banking"),
    _wb("support"),
    _wb("branch"),
    _wb("transaction"),
    _wb("account"),
    _wb("card"),
    _wb("app"),
    _wb("service"),
    _wb("consultant"),
    _wb("staff"),
    _wb("fnb"),
    _wb("absa"),
    _wb("nedbank"),
    _wb("capitec"),
    _wb("standard bank"),
]]

# --- Suggestion expressions ---
SUGGESTION_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("should improve"),
    _wb("please add"),
    _wb("consider adding"),
    _wb("it would be better"),
    _wb("you need to improve"),
    _wb("should provide"),
    _wb("please introduce"),
    _wb("would be great if"),
    _wb("why not add"),
    _wb("recommend adding"),
    _wb("suggestion"),
    _wb("suggest that"),
    _wb("I suggest"),
    _wb("would recommend"),
]]

# --- Warning expressions ---
WARNING_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("do not use"),
    _wb("avoid this bank"),
    _wb("stay away"),
    _wb("be careful"),
    _wb("beware"),
    _wb("be warned"),
    _wb("stay far"),
    _wb("would not recommend"),
    _wb("would not advise"),
    _wb("don't trust"),
]]

# --- Churn expressions ---
CHURN_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("closing my account"),
    _wb("switching banks"),
    _wb("moving to another bank"),
    _wb("leaving this bank"),
    _wb("cancelling my account"),
    _wb("no longer banking with"),
    _wb("taking my business elsewhere"),
    _wb("close my account"),
    _wb("switch to another bank"),
    _wb("cancel my account"),
    _wb("leaving your bank"),
    _wb("I am done with"),
    _wb("fed up with this bank"),
    _wb("goodbye to this bank"),
]]

# Banking reference for Rules D and E
BANKING_REFERENCE_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("bank"),
    _wb("banks"),
    _wb("banking"),
    _wb("account"),
    _wb("card"),
    _wb("transaction"),
    _wb("transfer"),
    _wb("payment"),
    _wb("service"),
    _wb("app"),
    _wb("branch"),
    _wb("atm"),
    _wb("fnb"),
    _wb("absa"),
    _wb("nedbank"),
    _wb("capitec"),
    _wb("standard bank"),
]]

# --- Rule F: strongly specific multi-word phrases (qualify independently) ---
SPECIFIC_ISSUE_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("debited but not credited"),
    _wb("failed transaction"),
    _wb("failed transfer"),
    _wb("failed payment"),
    _wb("delayed reversal"),
    _wb("blocked account"),
    _wb("unauthorised transaction"),
    _wb("unauthorized transaction"),
    _wb("card not working"),
    _wb("app not working"),
    _wb("poor customer service"),
    _wb("account was hacked"),
    _wb("account has been hacked"),
    _wb("account is hacked"),
    _wb("money was deducted"),
    _wb("money not received"),
    _wb("funds not received"),
    _wb("transfer not received"),
    _wb("payment not received"),
    _wb("payment not reflected"),
    _wb("transaction not reflected"),
    _wb("debit order dispute"),
    _wb("pending transaction"),
    _wb("incorrect deduction"),
    _wb("double deduction"),
    _wb("double charge"),
]]

# --- Promotional exclusion patterns ---
PROMOTIONAL_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("competition"),
    _wb("giveaway"),
    _wb("prize"),
    _wb("limited time"),
    _wb("special offer"),
    _wb("terms apply"),
    _wb("tag a friend"),
    _wb("apply now"),
    _wb("sign up today"),
    _wb("free data"),
    _wb("cashback offer"),
    _wb("t&c apply"),
    _wb("t&cs apply"),
    _wb("follow us"),
    _wb("open an account today"),
    _wb("new account offer"),
    _wb("zero fees offer"),
    _wb("recruitment"),
    _wb("we are hiring"),
    _wb("career opportunity"),
    re.compile(r"#\w*job\w*", re.IGNORECASE),
    re.compile(r"#\w*vacanc\w*", re.IGNORECASE),
]]

# Unrelated "bank" meanings (river, blood, food, etc.)
UNRELATED_BANK_PATTERNS: list[re.Pattern] = [p for p in [
    _wb("river bank"),
    _wb("blood bank"),
    _wb("food bank"),
    _wb("memory bank"),
    _wb("seed bank"),
    _wb("gene bank"),
    _wb("time bank"),
    _wb("piggy bank"),
    _wb("breaking bad"),   # common phrase "breaking the bank" but not SA banking
    re.compile(r"\bbank\s+of\s+(?:the\s+)?(?:england|canada|japan|china|india|france|america)\b", re.IGNORECASE),
]]

# Records that are mainly tags/usernames / too sparse
_MIN_ALPHA_CHARS = 15  # minimum meaningful alphabetic characters after [USER] replacement

# Minimum overall text length after anonymisation
MIN_TEXT_LENGTH = 15


# ---------------------------------------------------------------------------
# Candidate decision logic
# ---------------------------------------------------------------------------


@dataclass
class CandidateResult:
    """Outcome of candidate classification for one record."""
    is_candidate: bool
    rule_matched: str          # "A","B","C","D","E","F","zero_aspect","none"
    matched_strata: list[str]  # sampling-aid strata (NOT gold labels)
    is_promotional: bool
    filter_reason: str


def classify_candidate(text: str) -> CandidateResult:
    """Apply the evidence-based candidate filter to ``text``.

    Returns a :class:`CandidateResult` indicating whether the record
    qualifies as a customer-feedback candidate, which rule matched,
    which sampling strata were triggered, and whether the record
    appears promotional.

    This function is a pure function (no I/O, no side effects).
    """
    if not text or not isinstance(text, str):
        return CandidateResult(False, "none", [], False, "empty_text")

    # Very short texts are excluded regardless
    if len(text.strip()) < MIN_TEXT_LENGTH:
        return CandidateResult(False, "none", [], False, "too_short")

    # Count meaningful alpha characters (non-token, non-space)
    # [USER], [URL], etc. are tokens; strip them for length check
    stripped = re.sub(r"\[(?:USER|URL|EMAIL|PHONE|ACCOUNT_OR_REFERENCE|AMOUNT)\]", "", text)
    alpha_chars = sum(1 for c in stripped if c.isalpha())
    if alpha_chars < _MIN_ALPHA_CHARS:
        return CandidateResult(False, "none", [], False, "insufficient_meaningful_content")

    # Check for unrelated "bank" meanings early to avoid false matches
    is_unrelated_bank = _any(UNRELATED_BANK_PATTERNS, text)
    if is_unrelated_bank:
        return CandidateResult(False, "none", [], False, "unrelated_bank_meaning")

    # Promotional check
    is_promo = _any(PROMOTIONAL_PATTERNS, text)

    # Evaluate the six candidate rules
    has_aspect   = _any(BANKING_ASPECT_PATTERNS, text)
    has_problem  = _any(PROBLEM_PATTERNS, text)
    has_request  = _any(REQUEST_PATTERNS, text)
    has_fp       = _any(FIRST_PERSON_PATTERNS, text)
    has_positive = _any(POSITIVE_PATTERNS, text)
    has_pos_ctx  = _any(POSITIVE_CONTEXT_PATTERNS, text)
    has_suggest  = _any(SUGGESTION_PATTERNS, text)
    has_warning  = _any(WARNING_PATTERNS, text)
    has_churn    = _any(CHURN_PATTERNS, text)
    has_specific = _any(SPECIFIC_ISSUE_PATTERNS, text)
    has_bank_ref = _any(BANKING_REFERENCE_PATTERNS, text)

    rule = "none"
    if has_specific:                                   rule = "F"
    elif has_aspect and has_problem:                   rule = "A"
    elif has_aspect and has_request:                   rule = "B"
    elif has_fp and has_aspect:                        rule = "C"
    elif has_positive and has_pos_ctx:                 rule = "D"
    elif (has_suggest or has_warning or has_churn) and has_bank_ref:
                                                       rule = "E"

    is_candidate = (rule != "none")

    # Promotional precedence: a record matching both candidate and promo rules
    # is excluded UNLESS it contains a clear first-person banking experience.
    if is_promo and is_candidate and not (has_fp or has_problem or has_specific):
        is_candidate = False
        rule = "none"
        return CandidateResult(False, "none", [], True, "promotional_precedes_candidate")

    # Build candidate strata (sampling aids — NOT gold labels)
    strata: list[str] = []
    if is_candidate:
        if has_specific or (has_aspect and has_problem and any(
            p.search(text) for p in [
                _wb("transfer"), _wb("payment"), _wb("transaction"),
                _wb("reversal"), _wb("refund"), _wb("deposit"), _wb("withdrawal"),
            ]
        )):
            strata.append("transactions_candidate")
        if has_aspect and (has_problem or has_request) and any(
            p.search(text) for p in [
                _wb("customer service"), _wb("customer care"), _wb("support"),
                _wb("consultant"), _wb("helpline"), _wb("call centre"), _wb("call center"),
            ]
        ):
            strata.append("customer_support_candidate")
        if has_fp and any(p.search(text) for p in [
            _wb("my account"), _wb("account"),
        ]) and (has_problem or has_request):
            strata.append("accounts_candidate")
        if any(p.search(text) for p in [
            _wb("my card"), _wb("card"), _wb("pin"), _wb("debit card"), _wb("credit card"),
        ]) and (has_problem or has_request or has_fp):
            strata.append("cards_candidate")
        if any(p.search(text) for p in [
            _wb("mobile app"), _wb("banking app"), _wb("online banking"),
            _wb("internet banking"), _wb("mobile banking"), _wb("app not working"),
            _wb("login"), _wb("e-wallet"), _wb("ewallet"),
        ]) and (has_problem or has_request or has_fp):
            strata.append("digital_banking_candidate")
        if any(p.search(text) for p in [
            _wb("fee"), _wb("fees"), _wb("charge"), _wb("charges"),
            _wb("deduction"), _wb("debit order"), _wb("service fee"), _wb("maintenance fee"),
        ]) and (has_problem or has_request or has_fp or has_specific):
            strata.append("fees_candidate")
        if any(p.search(text) for p in [
            _wb("fraud"), _wb("scam"), _wb("unauthorised"), _wb("unauthorized"),
            _wb("hacked"), _wb("phishing"), _wb("identity theft"), _wb("suspicious"),
        ]):
            strata.append("fraud_security_candidate")
        if any(p.search(text) for p in [
            _wb("branch"), _wb("teller"), _wb("queue"),
        ]) and (has_problem or has_request or has_fp or has_positive):
            strata.append("branch_service_candidate")
        if has_positive and has_pos_ctx:
            strata.append("positive_feedback_candidate")
        if has_suggest and has_bank_ref:
            strata.append("suggestion_candidate")
        if has_warning and has_bank_ref:
            strata.append("warning_candidate")
        if has_churn and has_bank_ref:
            strata.append("churn_candidate")

        # Remove duplicates while preserving order
        seen: set[str] = set()
        strata = [s for s in strata if not (s in seen or seen.add(s))]  # type: ignore[func-returns-value]

    filter_reason = (
        f"rule_{rule}" if is_candidate
        else ("promotional" if is_promo else "no_candidate_rule_matched")
    )

    return CandidateResult(
        is_candidate=is_candidate,
        rule_matched=rule,
        matched_strata=strata,
        is_promotional=is_promo,
        filter_reason=filter_reason,
    )


def is_potential_zero_aspect(text: str) -> bool:
    """Return True when a record is a plausible zero-aspect training example.

    A zero-aspect record is one where the text is bank-related (contains a
    bank name, general banking reference, or directed at a bank account) but
    does not contain any identifiable specific aspect term.

    These records are useful for training the BIO aspect extractor's negative
    class. They are identified here as sampling candidates only — not as
    gold annotations.
    """
    BANK_NAME_OR_GENERAL = [
        _wb("fnb"), _wb("absa"), _wb("nedbank"), _wb("capitec"),
        _wb("standard bank"), _wb("standardbank"),
        _wb("bank"), _wb("banking"),
        re.compile(r"\[USER\]"),  # tweet was directed at someone (bank reply context)
    ]
    has_bank_ref = any(p.search(text) for p in BANK_NAME_OR_GENERAL)

    # Absence of specific aspect terms makes it potentially zero-aspect
    SPECIFIC_ASPECT = [
        _wb("transfer"), _wb("payment"), _wb("account"), _wb("card"),
        _wb("fee"), _wb("fees"), _wb("fraud"), _wb("branch"), _wb("atm"),
        _wb("loan"), _wb("transaction"), _wb("balance"), _wb("deposit"),
        _wb("mobile app"), _wb("banking app"), _wb("online banking"),
    ]
    has_specific_aspect = any(p.search(text) for p in SPECIFIC_ASPECT)

    return has_bank_ref and not has_specific_aspect and len(text) >= MIN_TEXT_LENGTH
