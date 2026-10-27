# South African Banking Twitter Dataset — Source Data Analysis

**Date:** 2026-09-05  
**Scope:** Static inspection of the archive at `data/raw/archive/`. No data was cleaned, labelled, or processed. No records were printed. This document is for planning purposes only.

---

## 1. Dataset Source and Provenance

The archive contains Twitter (now X) posts collected by mentioning or tagging five major South African retail banks. The collection covers the period 2006–2023 across two separate collection runs:

- **Base collection** (`tweets_from_*`): 18 annual parquet files, 4,544,948 total rows
- **Updated search-terms collection** (`updated_search_terms_tweets_from_*`): 18 annual parquet files, 1,317,576 total rows
- **Combined raw total**: approximately 5,862,524 rows (before deduplication)

The dataset is not accompanied by any README, licence file, or data-card. Three Excel files are present in the archive root, but they cannot be parsed without the `openpyxl` dependency (not installed). Based on their names:
- `bank_follower_count.xlsx` (12 KB): likely bank Twitter follower metadata
- `df_dataset..xlsx` (1.1 GB): likely a large aggregated/derived dataset (not the raw tweets)
- `df_hashtags_dataset.xlsx` (684 MB): likely hashtag co-occurrence or enriched data

**South African provenance:** Confirmed. All five banks tracked — FNB (First National Bank), ABSA, Nedbank, Standard Bank, and Capitec — are South African retail banking institutions. The dataset was collected by monitoring their Twitter mentions and replies. This provides documented, institution-specific provenance for `region = "south_africa"`.

**Caveat:** No academic or commercial licence documentation was found in the archive. The data appears to have been collected from the Twitter Academic Research or similar API under terms that require checking before publication. The absence of a licence file means provenance and reuse rights cannot be fully confirmed from the archive alone.

---

## 2. Licence Information

No licence file, data card, or dataset description was found in the archive. The responsible researcher must:
1. Identify the original data source (e.g. Kaggle dataset, direct API collection, academic dataset)
2. Document the licence and reuse terms before publishing research that uses this data
3. Confirm compliance with Twitter/X Terms of Service for academic research

Recommended status: **licence unknown — must be documented before publication**.

---

## 3. File Inventory

### 3.1 Parquet files (tweets/*)

Both collections share the same 8-column schema:

| Column | Type | Description |
|---|---|---|
| `Datetime` | timestamp[us, UTC] | UTC timestamp of the tweet |
| `Tweet_Id` | int64 | Twitter unique tweet identifier |
| `Tweet` | string | Raw tweet text |
| `Username` | string | Twitter username (handle) of the author |
| `Reply_Count` | int64 | Number of replies |
| `Retweet_Count` | int64 | Number of retweets |
| `Like_Count` | int64 | Number of likes |
| `Bank` | string | Bank label applied during collection |

An additional `__index_level_0__` integer column is present in the parquet metadata (pandas index artifact, not a data column).

**No sentiment, polarity, or label columns exist in any parquet file.**

### 3.2 Base parquet files (tweets_from_*)

| File | Rows | Size |
|---|---|---|
| tweets_from_2006-01-01_to_2007-01-01.parquet | 0 | 0 MB |
| tweets_from_2007-01-01_to_2008-01-01.parquet | 69 | <0.1 MB |
| tweets_from_2008-01-01_to_2009-01-01.parquet | 1,006 | 0.1 MB |
| tweets_from_2009-01-01_to_2010-01-01.parquet | 17,881 | 1.5 MB |
| tweets_from_2010-01-01_to_2010-12-31.parquet | 75,037 | 5.6 MB |
| tweets_from_2010-01-01_to_2011-01-01.parquet | 59,270 | 4.6 MB |
| tweets_from_2011-01-01_to_2012-01-01.parquet | 156,357 | 12.8 MB |
| tweets_from_2012-01-01_to_2013-01-01.parquet | 291,793 | 23.0 MB |
| tweets_from_2013-01-01_to_2014-01-01.parquet | 378,290 | 30.9 MB |
| tweets_from_2014-01-01_to_2015-01-01.parquet | 326,750 | 25.7 MB |
| tweets_from_2015-01-01_to_2016-01-01.parquet | 289,038 | 22.8 MB |
| tweets_from_2016-01-01_to_2017-01-01.parquet | 298,055 | 23.7 MB |
| tweets_from_2017-01-01_to_2018-01-01.parquet | 319,829 | 27.9 MB |
| tweets_from_2018-01-01_to_2019-01-01.parquet | 390,883 | 39.6 MB |
| tweets_from_2019-01-01_to_2020-01-01.parquet | 367,360 | 40.1 MB |
| tweets_from_2020-01-01_to_2021-01-01.parquet | 414,295 | 44.3 MB |
| tweets_from_2021-01-01_to_2022-01-01.parquet | 533,971 | 51.1 MB |
| tweets_from_2022-01-01_to_2023-01-01.parquet | 625,064 | 58.7 MB |
| **Total** | **4,544,948** | **~412 MB** |

Note: Two files cover overlapping 2010 ranges (`tweets_from_2010-01-01_to_2010-12-31.parquet` and `tweets_from_2010-01-01_to_2011-01-01.parquet`). These must be deduplicated by `Tweet_Id` during ingestion.

### 3.3 Updated search-terms parquet files (updated_search_terms_tweets_from_*)

Files for 2006–2008 are empty (0 rows). Data begins 2009.

| File | Rows | Size |
|---|---|---|
| 2006–2008 files | 0 | 0 MB |
| updated_search_terms_tweets_from_2009-01-01_to_2010-01-01.parquet | 660 | 0.1 MB |
| updated_search_terms_tweets_from_2010-01-01_to_2011-01-01.parquet | 2,712 | 0.2 MB |
| ... *(growing each year)* | ... | ... |
| updated_search_terms_tweets_from_2022-01-01_to_2023-01-01.parquet | 281,431 | 22.7 MB |
| **Total** | **1,317,576** | **~120 MB** |

These files cover Standard Bank and Capitec only (2022–2023 sample confirmed). They likely represent a supplementary collection to fill gaps in the original base collection for these two banks.

### 3.4 Excel files (not yet parsed)

| File | Size | Status |
|---|---|---|
| `bank_follower_count.xlsx` | 12 KB | Cannot read (openpyxl not installed) |
| `df_dataset..xlsx` | 1.1 GB | Likely aggregated/derived; not primary source |
| `df_hashtags_dataset.xlsx` | 684 MB | Likely derived enriched data |

The two large Excel files are likely derived or enriched datasets built from the parquet data. They are **not** recommended as primary text sources. The parquet files should be used as the authoritative raw source.

---

## 4. Row and Column Counts

| Metric | Value |
|---|---|
| Raw parquet rows (base + updated) | ~5,862,524 |
| Columns (both file types) | 8 (same schema) |
| Years covered | 2007–2023 |
| Banks tracked | 5 (fnb, absa, nedbank, standard_bank, capitec) |
| Sentiment columns | **None** |
| Label columns | **None** |

---

## 5. Date Range

- **Earliest data:** 2007 (base collection has 69 rows in 2007–2008)
- **Latest data:** 2022-12-31 (both collections)
- **Peak volume:** 2021–2023 (>500K rows per year in base collection)

The collection shows a clear growth pattern reflecting Twitter's growing adoption in South Africa: from 69 tweets in 2007 to 625,064 in 2022.

---

## 6. Banks Represented

All five major South African retail banks:

| Bank label | Total rows (approx.) | Notes |
|---|---|---|
| `fnb` | 1,657,652 | First National Bank |
| `absa` | 1,223,716 | Amalgamated Banks of South Africa |
| `standard_bank` | 1,153,209 | Includes updated_search_terms supplement |
| `nedbank` | 1,031,771 | — |
| `capitec` | 796,176 | Includes updated_search_terms supplement |
| **Total** | **5,862,524** | — |

Note: Standard Bank and Capitec appear to have been supplemented via the `updated_search_terms` collection, which covers only these two banks for recent years.

---

## 7. Text Fields Available

| Field | Notes |
|---|---|
| `Tweet` | Raw tweet text, string type, 4–943 characters, mean ~126 characters (2022). This is the **authoritative text field**. |
| `Username` | Twitter handle of the author. Must be anonymised (treated as `[USER]`). |

There is no separate "cleaned text" field in the parquet files. The `Tweet` field is the raw collected tweet text.

---

## 8. Raw Versus Cleaned Text

The `Tweet` field is raw, uncleaned text as collected from Twitter. Characteristics observed in the 2022–2023 sample (500 rows):
- 80% contain at least one `@` mention
- 17% contain URLs
- 31% contain emoji
- 4% contain possible South African language markers (Afrikaans, Zulu)
- 70% contain common English words
- 1% contain long digit strings (potential account/reference numbers)

There is no pre-cleaned text field. All cleaning will be performed by the project's existing cleaning and anonymisation pipeline.

---

## 9. Existing Sentiment Fields

**No sentiment, polarity, predicted label, or score columns exist in any parquet file.**

The two large Excel files (`df_dataset..xlsx`, `df_hashtags_dataset.xlsx`) may contain derived enrichments but cannot be read without `openpyxl`. Even if they contain sentiment fields, those fields must be classified as `existing_weak_label_provenance_unknown` and must not be used as gold annotation labels.

---

## 10. Engagement Metadata

Available engagement metadata (2022–2023 sample):
- `Reply_Count`: mean ~1.4, max 133 (base); mean ~1.0, max 2,083 (updated)
- `Retweet_Count`: mean ~1.8, max 264 (base); mean ~0.4, max 1,607 (updated)
- `Like_Count`: mean ~6.5, max 944 (base); mean ~2.0, max 7,936 (updated)

Most tweets have zero engagement (median = 0 for replies and retweets). High engagement outliers likely reflect viral complaints or bank announcements. Engagement metrics may be useful as a secondary filter to prioritise authentic customer interactions over low-engagement automated posts, but they are not labels.

---

## 11. Missing Value Analysis

Within parquet files, missing-value counts are zero for all columns in all sampled files. The `Tweet`, `Username`, `Bank`, and `Datetime` columns are consistently populated. No NaN/NA values were observed in the columns inspected.

Note: The `__index_level_0__` metadata column is not a data field and will be dropped during ingestion.

---

## 12. Exact-Duplicate Analysis

Within-file duplicate `Tweet_Id` rates in sampled annual files:
- 2018–2019: 3.7% duplicates
- 2020–2021: 5.5% duplicates
- 2022–2023: 2.8% duplicates

These are within-file duplicates. The `updated_search_terms` collection overlaps with the base collection by approximately 8.3% for 2022–2023 (23,220 shared Tweet_Ids). Combined deduplication by `Tweet_Id` across all files is required during ingestion.

---

## 13. Near-Duplicate Analysis

Not run at this stage (would require full data load). The existing MinHash + LSH infrastructure (`clean.py`) will be applied during the preparation stage. Given the large volume (5.8M rows), near-duplicate detection should be run on the filtered customer-feedback candidate set only, after filtering reduces the working set to a manageable size.

---

## 14. Language and Text-Quality Observations

- **Dominant language:** English (~70% by keyword analysis)
- **South African language markers:** ~4% (Afrikaans/Zulu words detected in 2022 sample)
- **Tweet format:** 73.6% of tweets in 2022–2023 base collection start with `@`, indicating they are direct mentions or replies to bank accounts
- **Retweet rate:** Very low (<0.1%) in base collection — tweets were collected as mentions, not general stream retweets
- **Text quality:** Variable; includes abbreviations, hashtags, emoji, code-switching (English + Zulu/Afrikaans), informal spelling
- **Maximum length:** 943 characters (occasional long-form threads); most are ≤280 characters
- **Minimum length:** 4–5 characters (very short posts may be noise)

---

## 15. Customer-Feedback Versus Promotional-Content Observations

Analysis of `updated_search_terms` 2022–2023 sample (281,431 rows):
- **~11.4%** contain customer-feedback keywords (failed, blocked, help, fraud, fee, etc.)
- **~6.6%** contain promotional keywords (win, apply now, giveaway, competition, etc.)
- **~20.4%** originate from apparent bank official accounts (bank-name in username)

Tweets from official bank accounts are likely responses/replies rather than customer feedback and should be separately handled (they may be used as context but not as primary feedback instances). The majority of tweets (~70%) are ambiguous — they may be customer feedback without using explicit feedback keywords, or they may be general conversation.

---

## 16. Privacy Risks

| Risk | Assessment | Mitigation |
|---|---|---|
| Twitter usernames | Present in `Username` column; uniquely identifies individuals | Replace all usernames in tweet text (`@handle`) with `[USER]`; drop `Username` column from canonical output |
| URLs | 17% of tweets contain URLs; may link to personal pages or photo albums | Replace with `[URL]` |
| Phone numbers | 1% contain 9+ digit runs; likely account numbers or phone numbers | Apply existing `[PHONE]` / `[ACCOUNT_OR_REFERENCE]` patterns |
| Email addresses | Not quantified; possible in tweet text | Apply existing `[EMAIL]` pattern |
| Bank account/reference numbers | Present but low rate | Apply `[ACCOUNT_OR_REFERENCE]` pattern |
| Tweet IDs | Numeric; can be used to retrieve original tweet | Do not publish Tweet_Id in research outputs; hash it into record_id |
| Temporal data | Fine-grained UTC timestamps | Normalise to date-level (ISO 8601 date only) for privacy |

High priority: all `@username` mentions in tweet text must be replaced with `[USER]` during anonymisation, as they directly identify individuals. The `Username` column (the author's handle) must not appear in canonical output.

---

## 17. Recommended Canonical Mapping

| Canonical field | Source field | Transformation |
|---|---|---|
| `record_id` | `source` + cleaned `Tweet` | sha256(source + normalised_tweet)[:16] |
| `source` | — | Constant: `"south_african_bank_tweets"` |
| `region` | — | Constant: `"south_africa"` (confirmed by institution provenance) |
| `bank` | `Bank` | Preserve as-is (fnb, absa, nedbank, standard_bank, capitec) |
| `rating` | — | null (not available for tweets) |
| `title` | — | `""` (tweets have no title) |
| `text` | `Tweet` | Apply Unicode normalisation, whitespace normalisation, anonymisation |
| `previous_text` | — | `"[NO_CONTEXT]"` (no thread metadata available) |
| `context_available` | — | `false` (no thread metadata available) |
| `thread_id` | `Tweet_Id` | Can be stored but not used for context linkage without reply graph |
| `created_at` | `Datetime` | ISO 8601 date string (e.g. `"2022-03-15"`) |
| `created_at_raw` | `Datetime` | null if parseable; original string if unparseable |
| `split` | — | null (splits assigned separately after annotation) |
| `near_dup_group_id` | — | Assigned by MinHash/LSH during cleaning |

**Column dropped:** `Username` (contains personal identifiers); `__index_level_0__` (pandas metadata).

---

## 18. Recommended Filtering Approach

A three-stage filter is recommended:

**Stage 1 — Hard exclusions (remove):**
- Tweets from official bank accounts (username contains bank identifier)
- Tweets shorter than 15 characters
- Pure retweets (starts with `RT @`) with no added commentary
- Records with null or empty `Tweet` field

**Stage 2 — Soft customer-feedback identification (flag, do not remove):**
Apply keyword categories to set `customer_feedback_candidate = true/false`:
- Transaction keywords: `transfer`, `payment`, `failed`, `reversal`, `refund`, `atm`
- Account keywords: `account`, `blocked`, `frozen`, `balance`, `statement`
- Digital banking keywords: `app`, `online`, `internet banking`, `ussd`, `login`
- Customer support keywords: `help`, `support`, `customer service`, `complaint`, `resolve`
- Card keywords: `card`, `pin`, `debit`, `credit card`
- Fee keywords: `fee`, `charge`, `deduction`, `interest`
- Fraud keywords: `fraud`, `scam`, `unauthorised`, `stolen`, `hacked`
- Branch keywords: `branch`, `teller`, `queue`, `waiting`
- Positive feedback: `great service`, `excellent`, `impressed`, `well done`
- Churn signals: `closing`, `switching`, `cancel`, `leave this bank`

**Stage 3 — Promotional exclusions (flag separately):**
- Contest/giveaway patterns: `win`, `competition`, `giveaway`, `prize`
- Apply/join patterns: `apply now`, `open an account`, `sign up`
- Marketing patterns: `special offer`, `limited time`, `terms apply`

---

## 19. Limitations

1. **No licence documentation**: Reuse rights are unknown. Must be resolved before publication.
2. **No ground truth labels**: There are no manually annotated sentiment, aspect, or intent labels. All existing columns are raw metadata.
3. **Single-bank bias**: FNB dominates the base collection (36% of rows). Sampling for annotation must control bank imbalance.
4. **No thread context**: Without reply-chain metadata, `previous_text = "[NO_CONTEXT]"` for all records. Context-aware GRU intent models will see no context for South African records unless thread data is separately collected.
5. **Bank-official-account contamination**: ~20% of tweets in the updated_search_terms set appear to be from bank official accounts, not customers.
6. **Language diversity**: ~4% South African language markers detected; multilingual tweets (English/Zulu/Afrikaans/Sotho) may require special handling during annotation.
7. **Historical data quality**: Pre-2012 data is sparse (< 300K rows total for 2007–2011).
8. **Overlapping files**: The 2010 base collection has two overlapping annual files; deduplication by `Tweet_Id` is required.
9. **Large xlsx files unread**: The two large Excel files cannot be inspected without `openpyxl`. Their content and potential duplicates with the parquet data are unknown.
10. **Anonymisation completeness**: The pre-cleaned source corpus has already stripped many identifiers (see prior international dataset audit). However, the South African tweets are likely to contain more raw identifiers than the pre-cleaned international data, and anonymisation coverage should be verified.
