# Typo-tolerant search pilot

Use the existing magnifying-glass search palette or the home search box. Type a keyword with a small spelling mistake: **reimbursment** can find **My travel claims**, **calender** can find **Office calendar**, and **jhon** can suggest a colleague named **John**, when that person is in the existing active staff directory.

Exact page and record matches remain first. Additional destinations are explicitly labeled **Close match**; search does not replace the query or automatically choose a person/action. Pick the intended result, or use arrows/Enter. Existing assistant offers and answer cards remain separate. The CSS hub's search remains scoped to CSS; **Search everything** opens the global palette with the same query.

## What is searched approximately

- Page navigation: the current request's capability-filtered navigation catalog, using title, hint, keywords and section.
- Help: the same permission-filtered guide catalog used by `/help`, using its label/step text. Results show only the guide name and a generic Page guide hint, linking to its existing tour destination.
- Colleagues: the same linked, active, non-archived internal staff directory used by existing colleague lookup, using name, nickname, position and unit. Hints include only the existing permitted basic status; the bureau/team status switch is respected. No whereabouts notes, wellness details or new contact fields are exposed.

Documents/attachments, survey resource-person records, private calendar entries, tasks and requests retain their exact search behavior. They are not fuzzy candidates. This is spelling assistance, not semantic search or a natural-language answer service. An external search engine/model, provider key or additional hosting service is not needed. No query log, embedding or persisted index is added.

## Conservative matching and bounds

RapidFuzz 3.14.6's Optimal String Alignment distance allows adjacent-letter swaps, insertion, deletion or substitution. Alphabetic tokens of 4–8 characters allow at most one edit; tokens of 9+ allow at most two. Every query term must match, either literally or within its edit budget. Short fragments and numeric/identifier terms are never guessed. Unicode case/diacritic normalization can produce a labeled close match such as Jose → José.

At most **five close destinations** are offered, deduplicated by URL and excluded when that destination already matched exactly. The updated browser opts into suggestions with `/api/search?suggest=1`; callers without this flag retain exact-only API behavior. Live API exact records retain the existing 30-result total and five-per-source caps; close matches use only remaining room. Existing exact page ranking stays in the browser, so exact pages precede exact records and all close matches.

Approximate queries are limited to 128 characters/eight normalized tokens; candidate texts to 16,000 characters/1,024 unique words, and a request to 2,500 approximate candidates. More than **2,000 directory entries** disables approximate staff matching rather than searching a truncated directory; other bounded approximate sources and existing exact search remain available. Longer/unsupported queries still use existing exact search. Numeric identifiers are matched literally, including their punctuation.

The server ranks only already-authorized candidates, without cross-user caching. Each request uses the current authenticated actor and normal destination routes recheck access. Responses use no-store. A revoked/changed session must sign in again. Approximate matching grants no new capability.

## Fallback and browser behavior

If the search service or approximate matcher fails, existing local exact page navigation remains usable. Failed approximate matching logs a static warning without query/candidate text. The native `/search?q=…` fallback retains its exact page list and adds a separate **Close matches** section, including when JavaScript is disabled. Its exact list remains page navigation, as before; live exact record search continues through `/api/search`.

The client drops responses after input clearing or query reuse, even without AbortController, and old failures cannot remove a newer loading indicator. Exact/near destination duplicates and stale No matching page placeholders are removed. Result labels remain escaped text. Changed scripts use application-version asset URLs so existing browser caches receive the update.

A delayed first-visit tour now rechecks for an open palette or a focused inline search field before starting, so it cannot steal search focus. Explicit tour replay and `?tour=1` still work; a deferred automatic tour remains eligible on a later visit.

## Verification

Focused coverage includes edit/length/numeric bounds, ranking/deduplication, current-role filtering before matching, revoked-session handling, scope isolation, status privacy, inactive/archived exclusion, non-candidate private records, oversized catalogs, matcher failure and native fallback. Real Chromium against a local application server exercises mobile exact-before-close ordering, keyboard navigation, CSS → global search, no-JavaScript links, markup-safe labels, delayed query reuse/clearing, search-service failure and deterministic delayed-tour focus protection.

```sh
CSS_TEST_CHROMIUM=/usr/bin/chromium CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_search_typo.py tests/test_search_typo_browser.py tests/test_search.py tests/test_search_sources.py tests/test_colleague_status.py tests/test_tours.py tests/test_deploy_hf.py
```

A local synthetic rank-only check over 2,000 short staff candidates returned five suggestions in about 0.032 seconds; this is an engineering smoke check, not a production latency guarantee. The locked dependency audit found no known vulnerabilities. Complete normal/shuffled suites, offline AI checks, runtime image audit and exact live version verification remain release requirements. No production record/notification is created by testing this pilot.
