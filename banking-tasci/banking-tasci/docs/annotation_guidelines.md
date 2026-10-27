# Banking TASCI Annotation Guidelines

## Purpose and scope

This document is the single authoritative reference for human annotators working on the
banking-tasci-pipeline gold dataset. It defines:

- The nine **aspect categories** used to classify aspect spans (Requirement 13).
- The rule that annotators must always record the **exact character span** of an aspect
  term, not a paraphrase or a broad category label (Requirement 13.3).
- The seven **customer intent** labels and how to distinguish between the ones that are
  easily confused (Requirement 15).
- The **aspect-level sentiment** rules, including why sentiment is never assigned once
  per review and never derived from a star rating (Requirement 14).

Read this document in full before annotating. When in doubt, prefer the tie-breaking
rules given below over inventing a new convention, and use the ambiguity/adjudication
mechanisms described at the end of this document rather than guessing.

> **The single most important rule in this document:** for every aspect you tag, you
> must record the **exact substring** of `text` that expresses the aspect — the precise
> `start`/`end` character offsets such that `text[start:end] == term`. Never record a
> category name, a summary, or a reworded version of the aspect as the `term`. The
> Annotation_Validator will reject any record where this does not hold exactly
> (case-sensitive, inclusive `start`, exclusive `end`). This is what allows the resulting
> data to train a token-level extractor rather than only a document-level classifier.

---

## How to use this document while annotating

For each aspect-bearing phrase you notice in a record's `text`:

1. Decide **which category** it belongs to using the definitions, inclusion/exclusion
   rules, and overlap guidance below.
2. Decide the **exact span** using the boundary-selection rules for that category (and
   the general boundary rules in the "General span boundary rules" section).
3. Decide the **sentiment** for that specific aspect span only, using the aspect-level
   sentiment rules.
4. Repeat for every distinct aspect in the record. A record may have zero, one, or many
   aspect spans, and spans must never overlap.

Then, for the record as a whole, decide the single dominant **intent** (with the
ambiguous-intent escape hatch if genuinely torn between two labels).

---

## General span boundary rules

These apply across all categories, in addition to the category-specific boundary rules
given later:

- Include descriptive modifiers that are part of the aspect noun phrase (e.g. include
  "mobile" in "mobile app", include "international" in "international transfer",
  include "maintenance" in "maintenance charge"). The modifier changes which banking
  feature is being discussed, so it belongs in the span.
- Exclude surrounding filler words that are not part of the aspect itself: articles
  ("the", "a"), possessives ("your", "my") unless they are morphologically fused to the
  term, degree/quantifier words used as sentiment ("very", "extremely", "so"), and
  sentence connectives ("but", "and", "because").
  - "the mobile app" → tag `mobile app`, not `the mobile app`.
  - "your card" → tag `card`, not `your card`.
  - "extremely slow customer support" → tag `customer support`, not `extremely slow
    customer support` (the sentiment-bearing adjective stays out of the span; sentiment
    is recorded separately via the `sentiment` field).
- Exclude sentiment-bearing adjectives/adverbs unless they are lexicalised as part of
  the banking term itself (e.g. "overdraft fee" is one term; "annoying overdraft fee"
  is the term `overdraft fee` with `sentiment=negative`).
- Prefer the shortest span that is still a complete, unambiguous noun phrase referring
  to a single banking concept. Do not extend the span to include a whole clause.
- If the same concept is referred to twice in one sentence (e.g. via a pronoun), only
  tag the explicit noun-phrase mention(s); do not tag bare pronouns ("it", "they") as
  aspect terms, since pronoun spans cannot be reliably validated as the term they refer
  to.
- Spans must never overlap, even partially. If two candidate spans would overlap,
  either narrow one of them or choose the single most specific span that captures the
  primary aspect being discussed (see the overlap tie-breaking rules per category
  below).
- Punctuation immediately adjacent to a term is never included in the span (e.g. in
  `"the app,"` tag `app`, not `app,`).

---

## Aspect categories

### 1. `customer_support`

**Definition:** Human-mediated help channels and the quality of interactions with bank
staff who are not physically at a branch counter — call centres, live chat agents,
email support, complaint-handling staff, and the general responsiveness/attitude of
"support" as a function, regardless of channel.

**Inclusion rules:**
- Phone/call-centre support ("call centre", "helpline", "customer service line").
- Chat/email support agents and their responsiveness or attitude.
- General references to "customer service" or "support" as a function/department.
- Complaint-handling and query-resolution turnaround by support staff.

**Exclusion rules:**
- Staff physically located at a branch counter → `branch_service`, not
  `customer_support` (see overlap rule below).
- The banking app's chatbot as a *feature* of the app (e.g. "the app's chat feature
  keeps crashing") → `digital_banking`, because the complaint is about the software, not
  a human agent. If the complaint is about what a human agent said *through* the chat
  feature, tag `customer_support`.
- General praise/complaint about "the bank" as a whole with no specific support channel
  named → does not get an aspect span at all (leave `aspects` empty for that portion, or
  tag a more specific aspect if one is present elsewhere in the text).

**Positive examples (phrase → category):**
- "call centre" → `customer_support`
- "the support team was very responsive" → term is `support team`
- "customer service" → `customer_support`
- "the agent on live chat resolved it quickly" → term is `agent on live chat`

**Difficult / negative examples:**
- "the teller at the branch was rude" → this is `branch_service` (teller = branch
  counter staff), not `customer_support`, even though "rude staff" sounds like a support
  complaint.
- "the app's help section is useless" → this is `digital_banking` (a static in-app help
  page is a software feature), not `customer_support`, unless a live human agent is
  described.
- "nobody ever answers" with no channel named → too vague to tag as a specific aspect
  span; only tag if a channel (phone, chat, email) or the word "support"/"service" is
  explicitly present in the text.

**Boundary-selection rules:** Include the channel name if given ("call centre",
"customer service", "support team", "live chat agent"). Exclude adjectives describing
quality ("rude", "slow", "helpful") — those drive `sentiment`, not the span.

**Common terms:** call centre, helpline, customer service, customer support, support
team, live chat, chat agent, complaints department, hotline, support ticket, email
support.

**Overlap guidance:** `customer_support` vs. `branch_service` — the tie-breaker is
*physical location*. If the interaction happened at a physical branch (teller, branch
manager, "in-branch"), use `branch_service`. If it happened over phone/chat/email/app
messaging with no branch visit implied, use `customer_support`. `customer_support` vs.
`digital_banking` — if the complaint is about software/UX (the chat widget crashing,
the help page not loading), use `digital_banking`; if it's about what a human said or
did through that channel, use `customer_support`.

---

### 2. `digital_banking`

**Definition:** The bank's software and digital self-service channels: mobile app,
online/web banking, USSD banking, digital onboarding, biometric login, push
notifications, and other app/website features and their technical behaviour
(crashes, bugs, load times, UX).

**Inclusion rules:**
- Mobile app and its features (login, biometric/fingerprint login, notifications,
  in-app transfers screen, app crashes/bugs/slowness).
- Online/web banking portal.
- USSD/*120# style banking menus.
- Digital onboarding / account opening via app or website.
- OTP delivery mechanics as part of the digital flow (but see overlap with
  `fraud_security` below).

**Exclusion rules:**
- The underlying transaction itself (a transfer failing) → `transactions`, even if
  performed through the app. Only tag `digital_banking` for the *app/software* aspect
  ("the app crashed", "the transfer screen froze"); tag `transactions` for the
  transaction outcome aspect ("my transfer failed").
- Human agents reached via in-app chat → `customer_support` for the agent interaction.
- Card-related app screens (e.g. "card management" tab) where the complaint is actually
  about the physical card or its blocking/replacement → `cards`.

**Positive examples:**
- "mobile app" → `digital_banking`
- "the online banking portal is always down" → term is `online banking portal`
- "USSD banking" → `digital_banking`
- "app keeps crashing" → term is `app`

**Difficult / negative examples:**
- "the app said my transfer failed" → tag `transfer` (or `transfer failed`, per
  transaction boundary rules) as `transactions`; only tag `digital_banking` too if the
  app's behaviour itself (freezing, crashing) is separately described.
- "I couldn't log in" with no app/website named → ambiguous; if context clearly implies
  digital channel (e.g. review is about the app), tag `log in` as `digital_banking`;
  otherwise leave untagged.
- "the app blocked my card by mistake" → the *action* (blocking a card) is about the
  card/account state, so tag `card` as `cards`; tag `app` separately as
  `digital_banking` only if the app's behaviour is independently criticised.

**Boundary-selection rules:** Include the specific feature/screen name when present
("biometric login", "transfer screen", "USSD menu"). Use just "app" or "online banking"
when no more specific feature is named.

**Common terms:** mobile app, app, online banking, internet banking, web portal, USSD,
*120# menu, push notification, biometric login, fingerprint login, digital onboarding,
app update, in-app.

**Overlap guidance:** `digital_banking` vs. `transactions` — tag the software behaviour
as `digital_banking` and the transaction outcome as `transactions`; they can co-occur as
two separate spans in the same sentence. `digital_banking` vs. `fraud_security` — if the
complaint is about OTP/2FA mechanics failing to arrive or being confusing, tag
`digital_banking`; if the complaint is about an OTP being used fraudulently or a
security breach, tag `fraud_security`.

---

### 3. `transactions`

**Definition:** Movement of money and the outcomes of banking operations: transfers,
payments, deposits, withdrawals, ATM cash transactions, statement/balance discrepancies
tied to a specific transaction, and transaction speed/success/failure.

**Inclusion rules:**
- Transfers (EFT, wire, inter-bank, international transfer).
- Payments (bill payments, POS payments, recurring payments).
- Deposits and withdrawals, including ATM withdrawals.
- Failed, delayed, reversed, or duplicated transactions.
- Balance not reflecting a specific completed transaction.

**Exclusion rules:**
- The ATM machine itself malfunctioning (screen frozen, out of service) with no
  transaction outcome mentioned → could be `branch_service`/`digital_banking` depending
  on framing; if a specific withdrawal/deposit attempt is described, prefer
  `transactions`.
- Recurring account-level charges (monthly fee, maintenance fee) → `fees`, not
  `transactions`, even though a fee is technically "money moving."
- Card being declined at checkout due to the *card being blocked/expired* (a card-state
  issue) → `cards`; card being declined because insufficient balance during a purchase
  attempt → `transactions` (the failed payment itself) with `card` optionally tagged
  separately as `cards` if the physical card's role is separately discussed.

**Positive examples:**
- "failed transfer" → `transactions`
- "my deposit never showed up" → term is `deposit`
- "international transfer" → `transactions`
- "ATM withdrawal" → `transactions`

**Difficult / negative examples:**
- "monthly service fee" → this is `fees`, not `transactions`, despite involving money
  movement — it's a recurring charge, not a discrete transaction event.
- "the ATM ate my card" → this is about the *card* being physically retained, so tag
  `card` as `cards`; only add a `transactions` span if a specific withdrawal attempt and
  its failure are also described.
- "my balance is wrong" with no transaction named → too vague; only tag `transactions`
  if a specific transaction is identified as the cause (e.g. "my balance is wrong after
  that transfer").

**Boundary-selection rules:** Include the transaction type modifier ("international
transfer", "ATM withdrawal", "bill payment"). Include "failed"/"declined" only if it is
tightly bound to the noun as a compound (e.g. tag `failed transfer` as one span when the
text reads that way) rather than splitting sentiment-bearing words out — but prefer
`transfer` alone with `sentiment=negative` when "failed" functions as a predicate
("the transfer failed") rather than a noun modifier ("a failed transfer"). Follow the
literal surface form: if the text says "failed transfer", the natural noun phrase span
is `failed transfer`; if it says "the transfer failed", tag `transfer` and record
`sentiment=negative`.

**Common terms:** transfer, EFT, wire transfer, payment, deposit, withdrawal, ATM
withdrawal, POS payment, bill payment, standing order, recurring payment, transaction,
reversal, duplicate charge.

**Overlap guidance:** `transactions` vs. `fees`: tag discrete money-movement events as
`transactions` and recurring/one-off account charges as `fees`. `transactions` vs.
`digital_banking`: tag the transaction outcome as `transactions` even when performed via
the app; tag the app's own behaviour separately as `digital_banking` if criticised.

---

### 4. `cards`

**Definition:** Physical or virtual payment cards themselves and their lifecycle:
issuance, activation, blocking/freezing, replacement, expiry, PIN, and card-specific
features (contactless, virtual card), as distinct from the transactions performed with
them.

**Inclusion rules:**
- Debit/credit card issuance, activation, replacement, expiry.
- Card blocking/freezing/unblocking (as a state of the card itself).
- PIN issues (PIN reset, PIN not working) when framed as a card issue.
- Contactless/virtual card features.
- Card being lost, stolen, or damaged (the object, not the fraud investigation).

**Exclusion rules:**
- A payment made with the card failing due to insufficient funds → `transactions`.
- The card being blocked *because of* a fraud investigation → prefer `fraud_security`
  when fraud is the explicit reason given; prefer `cards` when only the blocking
  mechanic itself is discussed with no fraud context. See the tie-break rule below.
- Card-related fees (annual card fee, replacement card fee) → `fees`, not `cards`.

**Positive examples:**
- "card" → `cards`
- "my card was blocked" → term is `card`
- "new card" → term is `new card`
- "PIN reset" → `cards`

**Difficult / negative examples:**
- "card fraud" — see explicit tie-break rule in the overlap section below; default is
  `fraud_security` when "fraud" is the head noun/explicit theme.
- "card fee" → this is `fees`, not `cards` — the aspect being complained about is the
  charge, not the card object.
- "declined at the till" with no mention of the card or balance → too vague; tag `card`
  as `cards` only if the card itself is named as the cause (e.g. "my card was
  declined").

**Boundary-selection rules:** Include state modifiers that describe the card's
condition ("blocked card", "expired card", "new card") as part of the span when they
form the natural noun phrase; otherwise tag just `card` with `sentiment=negative` when
the state is expressed as a separate predicate ("my card got blocked").

**Common terms:** debit card, credit card, card, PIN, contactless, virtual card,
replacement card, card activation, blocked card, expired card, card freeze.

**Overlap guidance:** `cards` vs. `fraud_security` — **explicit tie-break rule**: if the
text explicitly frames the issue as fraud, an unauthorised transaction, or a security
investigation (words like "fraud", "unauthorised", "scam", "stolen and used"), tag it
`fraud_security`. If the text only describes the card's physical/administrative state
(blocked, lost, expired, replaced) with no fraud framing, tag it `cards`. When both are
explicitly present ("my card was stolen and someone used it fraudulently"), tag two
spans: `card` (`cards`) for the physical loss and the fraud-specific phrase (e.g.
"used it fraudulently") as `fraud_security`.

---

### 5. `accounts`

**Definition:** The bank account itself as an entity: opening, closing, freezing/
blocking of the *account* (not a card), account types (savings, cheque/current),
account statements, account balance visibility, and account-level access issues.

**Inclusion rules:**
- Account opening/closing.
- Account being blocked, frozen, or restricted (account-level, not card-level).
- Account type (savings account, current/cheque account, joint account).
- Account statements and balance inquiries as an account-management activity.
- Account number / account details management.

**Exclusion rules:**
- Card blocking → `cards`, not `accounts`, unless the text explicitly says the *account*
  (not the card) was frozen.
- A single transaction's balance discrepancy → `transactions`, not `accounts`, unless
  the complaint is about ongoing account-level access/visibility rather than one
  transaction.
- Account-related fees (monthly account maintenance fee) → `fees`.

**Positive examples:**
- "blocked account" → `accounts`
- "closing my account" → term is `account`
- "savings account" → `accounts`
- "opening a new account" → term is `account`

**Difficult / negative examples:**
- "my card is blocked" → `cards`, not `accounts` — do not conflate card-level and
  account-level blocking.
- "account maintenance fee" → `fees`, not `accounts` — the aspect is the charge.
- "I can't see my balance" → could be `accounts` (account visibility) or
  `digital_banking` (app/portal malfunction) depending on framing; if the complaint
  names the app/portal, tag `digital_banking`; if it's about the account access itself
  with no channel named, tag `accounts`.

**Boundary-selection rules:** Include the account-type modifier when present ("savings
account", "joint account", "current account"). Use "account" alone when no type is
specified.

**Common terms:** account, savings account, current account, cheque account, joint
account, account opening, account closure, frozen account, account statement, account
number.

**Overlap guidance:** `accounts` vs. `cards` — tie-break on whether the text names the
*account* or the *card* as the thing being blocked/restricted; default to whichever
noun is explicitly used. `accounts` vs. `fees` — recurring charges tied to holding the
account are `fees`; the account's existence/state/access is `accounts`.

---

### 6. `fees`

**Definition:** Any monetary charge levied by the bank that is not the transfer/payment
amount itself: monthly/maintenance fees, transaction fees, ATM withdrawal fees,
overdraft fees, card fees, hidden or unexpected charges, and interest rates framed as a
cost.

**Inclusion rules:**
- Monthly/maintenance account fees.
- Transaction fees, transfer fees, ATM fees.
- Overdraft fees, penalty fees, late-payment fees.
- Card issuance/replacement fees.
- Complaints about "hidden charges" or unexpected deductions.
- Interest rates when discussed as a cost to the customer.

**Exclusion rules:**
- The transaction amount itself (the money being transferred/withdrawn) →
  `transactions`, not `fees`.
- Fraudulent/unauthorised deductions → `fraud_security`, not `fees`, since the issue is
  unauthorised access, not a disclosed charge.
- Interest earned on a savings account (a benefit, not a cost) — still tag `fees` as the
  category (interest rate is still a pricing aspect) but note the `sentiment` may be
  positive.

**Positive examples:**
- "maintenance charge" → `fees`
- "hidden fees" → `fees`
- "overdraft fee" → term is `overdraft fee`
- "ATM withdrawal fee" → `fees`

**Difficult / negative examples:**
- "they took money from my account without telling me" with no fee context and framed
  as unauthorised → this is `fraud_security`, not `fees`, if the customer frames it as
  unauthorised/fraudulent; it is `fees` if framed as an undisclosed but legitimate
  charge ("hidden fee").
- "the transfer fee is separate from the amount I sent" → tag `transfer fee` as `fees`
  and, if separately discussed, the sent amount as `transactions`.
- "interest rate" on a loan discussed as a fair pricing question rather than a
  complaint → still `fees`; category assignment does not depend on sentiment polarity.

**Boundary-selection rules:** Include the fee-type modifier ("maintenance fee",
"overdraft fee", "ATM fee"). Use "fee"/"charge" alone only when no type is specified in
the text.

**Common terms:** fee, charge, maintenance fee, monthly fee, overdraft fee, ATM fee,
transfer fee, penalty fee, late fee, hidden charge, interest rate, annual fee.

**Overlap guidance:** `fees` vs. `transactions` — the fee/charge itself is `fees`; the
principal amount moved is `transactions`. `fees` vs. `fraud_security` — a disclosed but
disliked charge is `fees`; an undisclosed, unauthorised, or unexplained deduction the
customer frames as fraud/theft is `fraud_security`.

---

### 7. `fraud_security`

**Definition:** Unauthorised access, fraud, scams, phishing, data breaches, and the
bank's security measures (2FA/OTP as a security control, fraud investigations, dispute
resolution for unauthorised transactions).

**Inclusion rules:**
- Fraudulent or unauthorised transactions/charges.
- Phishing, scam, or social-engineering incidents involving the bank's name or systems.
- Account takeover, identity theft tied to the bank.
- Fraud investigation process and outcomes.
- Security features framed as protection (2FA, OTP, biometric security, fraud alerts).

**Exclusion rules:**
- OTP/2FA mechanics failing to arrive due to an app/SMS bug with no fraud implication →
  `digital_banking`.
- A card simply being lost (no unauthorised use mentioned) → `cards`.
- A disclosed fee the customer merely finds unfair (no claim of fraud) → `fees`.

**Positive examples:**
- "fraud investigation" → `fraud_security`
- "someone used my card without permission" → term is `card` tagged `fraud_security`
  when framed as unauthorised use (per the `cards` tie-break rule above), or tag the
  explicit phrase describing the unauthorised use.
- "phishing scam" → `fraud_security`
- "unauthorised transaction" → `fraud_security`

**Difficult / negative examples:**
- "I didn't get my OTP" with no mention of fraud → `digital_banking`, not
  `fraud_security` — this is a delivery/mechanics complaint, not a security incident.
- "the bank charged me twice" with no claim it was unauthorised → `fees` or
  `transactions`, not `fraud_security`, unless the customer explicitly frames it as
  fraudulent or unauthorised.
- "my card was declined for security reasons" with no fraud claim, just a routine
  security block → could be `cards` (the block itself) or `fraud_security` (if framed
  as the bank's proactive fraud-prevention action); prefer `fraud_security` when the
  bank's security process is the subject, `cards` when the customer is only annoyed the
  card stopped working.

**Boundary-selection rules:** Include the specific incident type when named ("fraud
investigation", "phishing scam", "unauthorised transaction"). Tag the phrase that most
directly names the security/fraud concept rather than a generic surrounding noun.

**Common terms:** fraud, scam, phishing, unauthorised transaction, security breach,
identity theft, fraud investigation, dispute, chargeback, 2FA, OTP (security context),
fraud alert, account takeover.

**Overlap guidance:** See the explicit tie-break rules under `cards` and `fees` above.
General rule: `fraud_security` wins the tie whenever the text explicitly uses
fraud/security/unauthorised framing; otherwise defer to the more concrete category
(`cards`, `fees`, `transactions`, `digital_banking`).

---

### 8. `branch_service`

**Definition:** In-person experiences at a physical bank branch: branch staff (tellers,
branch managers), queues/waiting times, branch opening hours, branch facilities, and
in-branch processes.

**Inclusion rules:**
- Branch staff conduct, competence, and attitude (teller, branch manager, security
  guard at the branch).
- Queue length and waiting time at a branch.
- Branch opening hours, branch closures, branch location/accessibility.
- In-branch processes (opening an account in person, in-branch document verification).

**Exclusion rules:**
- Phone/chat/email support staff → `customer_support`, not `branch_service`.
- ATM issues when the ATM is discussed independently of a branch visit (e.g. a
  standalone ATM at a mall) → `transactions` or leave general, not automatically
  `branch_service`; if the ATM is explicitly located at/inside the branch and the
  complaint is about the branch experience broadly, `branch_service` is acceptable.
- The bank's general reputation with no branch or staff mentioned → not a
  `branch_service` aspect.

**Positive examples:**
- "branch staff" → `branch_service`
- "long queue at the branch" → term is `queue`
- "the teller was helpful" → term is `teller`
- "branch opening hours" → `branch_service`

**Difficult / negative examples:**
- "the call centre staff were rude" → `customer_support`, not `branch_service` — no
  physical branch involved.
- "the ATM outside was broken" with no branch context → ambiguous; only tag
  `branch_service` if the branch itself is the subject of the sentence.
- "head office never responds" → this is closer to `customer_support` (a non-branch,
  non-local escalation channel) than `branch_service`, since "head office" is not a
  local branch experience.

**Boundary-selection rules:** Include the role/facility name ("branch staff", "the
teller", "branch manager", "queue", "branch"). Exclude location descriptors unrelated to
the aspect itself.

**Common terms:** branch, teller, branch manager, queue, waiting time, branch hours,
in-branch, counter staff, branch closure.

**Overlap guidance:** `branch_service` vs. `customer_support` — tie-break strictly on
physical presence at a branch, as described under `customer_support` above.

---

### 9. `general_service`

**Definition:** The catch-all category for overall service-quality remarks about the
bank that do not name a specific channel, product, or feature covered by the other
eight categories — e.g. general professionalism, general reliability, overall
experience, or broad trust/loyalty statements that are not tied to a specific aspect.

**Inclusion rules:**
- Broad statements about "the bank" or "this bank" being good/bad/professional/reliable
  with no more specific aspect named.
- General statements about overall experience, value for money as a whole (not one
  specific fee), or general trust in the institution.
- Cross-cutting service-quality remarks that don't map cleanly to a single other
  category (e.g. "everything about this bank feels outdated").

**Exclusion rules:**
- **Always prefer a more specific category first.** `general_service` should be a last
  resort, used only when no other category's inclusion rules apply. Do not use it as a
  shortcut when a specific channel/product/feature is actually named in the text.
- Do not use `general_service` merely because a sentence is short or vague — if it
  contains no aspect at all (e.g. "great!" with no named aspect), leave it untagged
  rather than forcing a `general_service` span onto a single adjective.
- Annotate "bank", "banking service", or the bank's name as `general_service` only when
  the phrase is the explicit target of an opinion. Do not annotate a bank mention used
  only to address or identify the institution.

**Positive examples:**
- "this bank is unprofessional" → term is `bank` tagged `general_service`.
- "FNB, please help me." → do not tag `FNB`; it is only the addressee.
- "This bank provides terrible service." → term is `bank` tagged `general_service`.
- "Capitec announced a new partnership." → leave aspects empty; no customer opinion is
  expressed.
- "overall experience was poor" → term is `overall experience`.
- "I don't trust this bank anymore" → term is `bank`.

**Difficult / negative examples:**
- "the app and the staff were both bad" → do NOT tag this as one `general_service` span
  — split it into `app` (`digital_banking`) and `staff` (`branch_service` or
  `customer_support` depending on context), since two specific aspects are actually
  named.
- "good service" with no channel named → if truly no channel/product is identifiable
  from context, `general_service` is appropriate for the term `service`; but check
  surrounding sentences (via `previous_text`) for an implied channel first.
- A one-word exclamation with no noun phrase ("terrible!", "love it") → leave untagged;
  there is no extractable term.

**Boundary-selection rules:** Tag the smallest noun phrase referring to the bank/service
as a whole ("bank", "service", "experience"). Never extend the span to cover the whole
sentence.

**Common terms:** bank, service, experience, overall, this bank, the institution.

**Overlap guidance:** `general_service` never overlaps with a more specific category by
design — if any of the other eight categories' inclusion rules apply, use that category
instead. `general_service` is only correct when the text genuinely does not name a
specific channel, product, or feature.

---

## Reminder: exact-span extraction, not just categorisation

Across all nine categories above, the annotation task is **not** "does this review
mention digital banking?" — it is "what is the exact substring of `text` that is the
aspect term, and which category and sentiment does that specific substring get?" Two
records mentioning "the app" must both have `term="app"` (or whatever exact substring
appears, e.g. "the app" if that is genuinely the more natural boundary per the rules
above) with matching `start`/`end` offsets into `text`. Never write a `term` value that
is not a verbatim, case-sensitive substring of the record's `text` field — the
Annotation_Validator checks `text[start:end] == term` exactly and will reject any
mismatch rather than silently correcting it.

---

## Customer intent labels

Every completed Annotation_Record has exactly one dominant `intent` value, chosen from:
`complaint`, `compliment`, `request_for_assistance`, `suggestion`, `warning`,
`churn_signal`, `general_feedback`.

Assign the intent that reflects the **primary purpose** of the message as a whole, not
just its tone. A message can contain elements of several intents (e.g. complain *and*
ask for help) — pick the one that best captures what the customer most wants to
communicate or achieve. Use the ambiguous-intent mechanism (below) when you genuinely
cannot decide.

### `complaint`
**Primary purpose:** express dissatisfaction or report poor service/experience, with no
explicit request for the bank to act and no explicit statement of leaving.
**Example:** "Your mobile app is always offline."

### `compliment`
**Primary purpose:** express satisfaction or praise for the bank, a product, or staff.
**Example:** "The teller at my branch was incredibly helpful and quick."

### `request_for_assistance`
**Primary purpose:** ask the bank to take a specific action (fix something, respond,
process something), regardless of whether dissatisfaction is also expressed.
**Example:** "Please help me reverse this failed transaction."

### `suggestion`
**Primary purpose:** propose an improvement or new feature, without necessarily
reporting a current problem.
**Example:** "It would be great if the app supported fingerprint login."

### `warning`
**Primary purpose:** advise other customers/readers to avoid or be cautious of a
service — addressed to the public, not to the bank.
**Example:** "Do not use this bank for international transfers."

### `churn_signal`
**Primary purpose:** explicitly indicate the customer is leaving, closing their account,
or switching to another bank.
**Example:** "I am closing my account because of this service."

### `general_feedback`
**Primary purpose:** describe an experience or opinion without a clear request,
complaint, compliment, warning, or churn intention — often mixed, mild, or purely
descriptive.
**Example:** "I've been banking here for five years and it's been about average."

### Distinguishing the commonly confused labels

**`complaint` vs. `request_for_assistance`:** When both dissatisfaction and a request
are present, select the intent representing the main communicative purpose. Use
`request_for_assistance` when the customer explicitly asks the bank to take action.
Use `complaint` when the main purpose is to report dissatisfaction and no clear action
is requested. If both intents remain genuinely plausible, select the best label and
use the ambiguity fields.
- "Your mobile app is always offline." → `complaint` (no ask).
- "Your service is terrible." → `complaint` (no action requested).
- "Your service is terrible. Please unblock my account." → `request_for_assistance`,
  alternative intent `complaint`, with `intent_ambiguous=true` when both are genuinely
  plausible.

**`complaint` vs. `churn_signal`:** A complaint stays a complaint unless the customer
explicitly says they are leaving, have left, or will switch banks. Frustration alone,
even severe, is `complaint` — only tag `churn_signal` when leaving/closing/switching is
explicitly stated.
- "This bank is useless." → `complaint`.
- "I am closing my account because of this service." → `churn_signal`.

**`complaint` vs. `warning`:** A `warning` is addressed outward, to other potential
customers/readers ("don't use", "avoid", "stay away"), rather than describing the
speaker's own experience/dissatisfaction only. If the message is phrased as advice to
others, tag `warning`; if it's phrased as the speaker's own grievance with no
advisory framing, tag `complaint`.
- "This bank charged me twice and never explained why." → `complaint`.
- "Do not use this bank for international transfers." → `warning`.

**`request_for_assistance` vs. `suggestion`:** A request asks the bank to fix or
process something specific *now*; a suggestion proposes a hypothetical future
improvement with no urgent unresolved issue.
- "Please help me reverse this failed transaction." → `request_for_assistance`.
- "It would be great if the app supported fingerprint login." → `suggestion`.

**`general_feedback` as the fallback:** Use `general_feedback` only when none of the
other six labels' primary-purpose test is met — the message neither vents a specific
grievance, nor compliments, nor asks for action, nor proposes a change, nor warns
others, nor signals leaving. Purely descriptive or mixed-but-mild reviews belong here.

### Ambiguous intent

Annotators must not force artificial certainty. When a record's intent is genuinely
ambiguous between two labels even after applying the primary-purpose test above:

1. Set `intent` to the single most likely label (your best judgment).
2. Set `intent_ambiguous` to `true`.
3. Set `alternative_intent` to the second-most-likely label.

This is preserved through validation — the Annotation_Validator does not collapse or
discard the ambiguity flag or `alternative_intent`. Do not leave `intent_ambiguous`
false just because you were forced to pick one label; use it whenever you were
genuinely torn, so ambiguous cases remain visible for later review/adjudication rather
than being silently absorbed into one label.

This mechanism — a single best-guess `intent` plus `intent_ambiguous=true` and a
non-null `alternative_intent` — is exactly the `AnnotationRecord` schema implemented in
`src/banking_tasci/data/annotations.py`. Annotators never invent a new field or
convention for ambiguity; use these three fields exactly as defined there, and never
force a single unflagged label when you are genuinely torn between two.

---

## Aspect-level sentiment rules

1. **Sentiment is assigned separately to each aspect span**, never once for the whole
   review. Every `Aspect_Span` carries its own independent `sentiment` value.
2. **Never use the review's star rating as the aspect sentiment.** A 1-star review can
   still contain a positively-discussed aspect ("even though everything else was bad,
   the branch staff were great"), and a 5-star review can contain a negative aspect
   mention. Read the text; ignore the `rating` field when assigning aspect sentiment.
3. **Never apply one document-level sentiment to every aspect term in a review.** Assess
   each aspect independently from its own local context in the sentence.
4. **Allowed values are only `positive`, `negative`, or `neutral`.** There is no
   `mixed` value at the aspect level — `mixed` is rejected by the Annotation_Validator.
5. **Represent mixed-opinion reviews via separate aspect-sentiment pairs**, not one
   mixed label. For example: "The mobile app is slow, but customer support was
   helpful." must be recorded as two Aspect_Spans:
   - `mobile app` → `digital_banking`, `sentiment=negative`
   - `customer support` → `customer_support`, `sentiment=positive`
6. **Contradictory sentiment for the same aspect term within one record:** if the same
   aspect term (e.g. "app" mentioned twice) genuinely receives contradictory sentiment
   in the same record and you cannot resolve which one reflects the customer's actual
   view, do not invent a resolution and do not use `mixed`. Instead, flag the record via
   `annotation_status` (e.g. set it to `needs_adjudication`) so a human adjudicator can
   resolve it later, and note the contradiction in `notes`. Resolution of that flag
   happens later in the pipeline via the **Adjudication_Tool**
   (`scripts/adjudicate_annotations.py`), which surfaces exactly this kind of
   disagreement to a human adjudicator and writes a resolved record that preserves both
   original values. Never resolve the contradiction yourself by picking one sentiment
   at annotation time — leave it flagged and let adjudication handle it.

---

## Summary checklist for every record

- [ ] Every aspect span's `term` is a verbatim, case-sensitive substring of `text` at
      exactly `[start, end)`.
- [ ] No two aspect spans overlap.
- [ ] Each aspect span has exactly one category from the fixed list of nine.
- [ ] Each aspect span has exactly one sentiment from `positive`/`negative`/`neutral`
      (never `mixed`, never derived from `rating`).
- [ ] The record has exactly one `intent` from the fixed list of seven, chosen by
      primary purpose.
- [ ] If genuinely torn between two intents, `intent_ambiguous=true` and
      `alternative_intent` is set rather than guessing.
- [ ] If the same aspect term has irreconcilable contradictory sentiment,
      `annotation_status` reflects the need for adjudication instead of inventing a
      label.
