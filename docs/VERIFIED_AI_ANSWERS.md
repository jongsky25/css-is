# Verified survey answers — A12, contract v1

Introduced in **7.63**. This contains audit finding F15 without expanding AI
authority or adding a new provider, database, dependency or AI write action.

## What staff see

Fixed survey questions still use the existing official answer templates. Calendar
and office questions still use the asker's own server-side answer functions. They
skip the broader survey call, even when the optional engine is enabled.

The optional broader lookup displays one to three survey facts, or the difference
between two comparable figures. Each fact names its subject, metric and period;
the answer includes an as-of date. Satisfaction differences use percentage points.
The server supplies every value, sentence and calculation.

Unsupported questions and unsuccessful lookups return to the existing search
palette. The model cannot supply an alternative prose answer. Rankings, forecasts,
sums and open-ended formulas are deliberately unsupported in this contract.

## Enforcement

`ai_facts.py` owns the fact catalogue and strict reply validator. The provider
receives JSON descriptions and identifiers, **without the numeric fact values**.
It may return exactly `operation`, `fact_ids`, and `confidence`. Selection is
bounded to three unique IDs from the offered catalogue. Any additional property
(including `answer`, `grounded`, a proposed value or a formula) rejects the reply.

The server independently resolves each selected ID and checks its complete fact
against a fresh database snapshot after the call. Changed labels, counts, scores,
rating denominators, periods, removed/archived sources or a local date rollover
reject the answer. Differences require two non-missing values with the same metric
and catalogue group; entity comparisons also require matching periods. No model
number is compared to a whitelist or interpolated into the result.

Confidence must be a finite JSON number between zero and one and meet the 0.5
relevance threshold. It is **not** proof of factual accuracy. `grounded=true` has
no authority. Names and the question are quoted JSON data in the prompt; returned
source names remain visibly quoted, with stable entity IDs and bounded length.
The existing answer card HTML-escapes its text.

The route re-resolves the registered session and current role, bureau access,
room-approver flag and AI settings after awaited provider calls. Deactivation,
demotion, logout and revoked grants cannot serve a prepared answer. Broader
lookups also recheck the engine and their feature flag. Resource-person opt-in
is applied again when rebuilding the facts, so its revocation removes those IDs.

## Source scope and numeric definitions

- Existing bureau-wide survey aggregates are retained. This does not add access
  to documents, work records, attendee details, comments or another user's office
  and calendar data.
- Home totals cover last 30 days, this quarter, year to date and all time, using
  response submission dates. Broad facts obtain uncached Home totals. Home
  response counts retain their existing archive treatment; activity/person counts
  exclude archived forms. Labels distinguish these totals from the breakdowns.
- Survey-type and SERVQUAL dimension scores exclude archived forms. Dimensions
  use the existing locked engine map. A valid rating is an integer in the survey's
  scale with `is_na` false: ARTA 1–5, other surveys 1–7. Missing and invalid values
  are excluded from both numerator and denominator, including the Home total.
  Satisfaction is rounded top-2-box share (ARTA >=4, others >=6), not a mean score.
- Month breakdowns use **event month** and the six latest populated months, not
  six consecutive calendar months. Activity facts cover up to 40 recent activities
  with responses; organizing-unit facts cover up to 12 units by response count.
  Each label makes the bounded catalogue explicit. Response counts use distinct
  responses, while rating counts count valid answers; they are separate metrics.
- Professional resource-person names remain off by default. The existing admin
  opt-in permits up to 40 people ordered by valid rating count. No attendee or
  account tables are included. Free-text entity names are still untrusted data;
  do not assume a name field is free of personal data merely because it is a label.

The model still classifies intent: it may select an authorized fact that does not
match the question well. Explicit subject/metric/period labels let staff see what
was answered. This contract guarantees server-owned claims and arithmetic, not
perfect interpretation, complete source-data quality or a measured real-model
accuracy rate. Independent provider evaluations remain A22 work before expanding
the contract.

## Settings, budgets and telemetry

The saved engine keys remain `catalog` (default) and `maximize` for compatibility.
The admin screen calls the latter “Verified facts — broader survey lookup”.
`nl_answer` must be enabled in answers/assistant mode. The broader call also needs
`nl_answer_grounded`, retains its own daily cap and existing timeouts, and uses
the existing Gemini/Groq provider fallback. Fixed answers consume no second call.

Valid broader replies use `served_by=verified_facts` and return `sources` with
stable IDs, labels, values, valid-rating denominators where applicable and as-of
dates, plus `contract_version=1`. The current card displays the same labels and
values in its normal answer text. Rejected provider plans retain the existing
`rejected_validation` outcome; provider/budget failures retain their existing
outcomes. Existing log retention and provider governance settings are unchanged.

## Verification and rollout

`tests/test_ai_answers_grounded.py` is the version 1 deterministic evaluation set.
It exercises the real HTTP route and database with provider stubs, covering:

- server values, source labels, percentage-point arithmetic and no-data behavior;
- false numeric prose, spelled-out numbers, forged confidence and extra fields;
- invented, private, duplicate, malformed and incompatible source selections;
- misleading source names and user instructions, without executable answer HTML;
- current access/settings, opt-in revocation, changed data, archiving and dates;
- fixed/user-scoped answer paths, feature gates, budgets, errors and timeouts;
- missing, fractional and out-of-scale ratings in source and Home calculations.

Required release CI runs the full suite normally and shuffled, including existing
answer-card browser tests, deployment closure and dependency checks. This is local
and CI evidence; no manual production testing or real-provider evaluation is
claimed. No schema migration is required. After deployment, use existing AI
outcomes to watch fallback frequency. If broader lookups have compatibility
problems, switch the engine to `catalog`; keep deterministic containment enabled
instead of restoring model-authored official figures.
