# Document registry pagination — A13 registry slice

Introduced in **7.66**. The registry loads 30 permitted records at a time, with
“Older documents” and “Newest records” links that retain the chosen queue and
search. Search starts at the newest page. CSV exports still include the entire
matching permitted register, regardless of the page currently displayed.

Counts, unknown deadlines and queue measures describe the **full filtered
register**, not just the displayed page. The page labels make that distinction.
Missing deadlines remain unknown; the same working-day and turnaround definitions
are preserved. Invalid live deadlines or closure timestamps stop measure
calculation with a correction message instead of silently changing the figures.

## Permission and search contract

`documents_permissions.RegistryScope` resolves the current active account,
records/workflow grants, organizational paths and existing chief/OIC seats once
per read snapshot. It compiles the existing detail rules into SQL predicates:

- Restricted records always require explicit access, including for Directors,
  records officers and technical administrators.
- Verified bureau records retain their existing visibility; other records use
  creator, explicit-access and concerned-unit officer rules.
- Scoped grants use exact organizational paths and descendants, so `D1` cannot
  grant access to `D10`. Concerned-unit JSON strings cannot become integer grants.
- Merged receipts inherit their terminal record's permission. Search retains the
  existing direct-canonical lookup and ordering behavior, deduplicates before
  seeking to an older page, and denies broken/cyclic canonical chains.
- Work/release queues retain legacy assignments and migrated shared-work rules.
  Migrated participation requires current work visibility, including permission
  to every linked reference, and a confirmed, non-cancelled task owner where
  required. Proposed ownership does not become confirmed participation.
- Archived, Gmail, review, instruction, mentions, direction and other queues
  retain their existing filters. Counts use the same filtered selection.

The predicates execute **before `LIMIT`**. Hidden records cannot consume a page
slot, supply an excerpt or contribute to its totals. Numeric page cursors carry
no authority. Every request reloads current account/grants/seats within a short
SQLite read snapshot; revoking access affects the next request, including an
already saved page URL. A nested read does not commit a caller's transaction.

Search keeps existing Unicode NFKC/casefold substring behavior for metadata and
references, plus the existing FTS token/prefix behavior for stored sources. FTS
file hits still require a current fingerprint/version and the original indexer
or explicit document access; ordinary bureau visibility alone does not grant
file-text access. Only one matching body per fetched page record is retrieved
for snippets. CSV export and global-search cards skip unused snippet bodies.

## Read interfaces and indexes

- `documents.list_page(..., before=0, limit=30, totals=True, snippets=True)`:
  returns documents, lookahead/next cursor and optional full-register totals.
  Limits must be integers from 1 through 100; the query fetches at most limit+1
  record rows to determine whether another page exists.
- `documents.count_visible(...)`: counts permitted matches without loading
  document records. Home approval counts and document review notifications use it.
- `documents.list_visible(..., snippets=True)`: retains the complete-result
  contract for CSV and existing callers that need every record. CSV sets
  `snippets=False`; the approvals screen still intentionally requests all of its
  permitted review records.
- Global document search uses a capped page without totals or unused snippets.
- `documents_registry.Selection` shares the filtered selection across page,
  count, export and measure queries. Metadata normalization and date arithmetic
  use deterministic connection-local functions; no authority is cached globally.

Normal older-page reads use an indexed ID seek without sorting the register.
Schema installation adds six indexes for the active register, review queue,
assignment lookup, directives, closure events and active grants. Existing rows
are indexed during schema installation; document content and authority assignments
are not rewritten. There is no new dependency or provider. The new runtime module
is included in the deployment inventory.

## Evidence

`tests/document_registry_reference.py` freezes the previous list and measure
implementations. Tests compare new results, order, counts and excerpts across
13 queues, four search cases and eight authority profiles. Additional checks
cover pagination, newly inserted records, scoped grants, explicit-access and
OIC revocation, inactive accounts, canonical chains/cycles, shared-work states,
full CSV export, search-preserving links, malformed cursors, invalid dates,
bounded SQL/fetched rows, complete HTTP query growth and indexed seeks.

The reproducible [synthetic benchmark](audits/2026-10-19/evidence/document-registry-pagination.json)
uses a temporary database, half verified bureau records and half restricted
records, with no private grant for the reader. Both paths include full-register
measures and are checked for matching first-page records and metrics.

| Records | Search | Legacy SELECTs | New SELECTs | Legacy record rows fetched | New record rows fetched |
| ---: | --- | ---: | ---: | ---: | ---: |
| 500 | None | 1,252 | 13 | 500 | 31 |
| 5,000 | None | 12,502 | 13 | 5,000 | 31 |
| 500 | Needle | 1,503 | 14 | 500 | 31 |
| 5,000 | Needle | 15,003 | 14 | 5,000 | 31 |

These numbers describe registry service reads, excluding middleware/navigation.
HTTP tests separately check that query growth remains bounded as record counts
increase. Latencies in the JSON are single local observations; they are not a
production performance or capacity claim. Query counts are independent of record
growth in these scenarios with a fixed organizational/authority structure.

Reproduce with the pinned test environment from the repository root:

```sh
python tools/benchmark_document_registry.py --sizes 500 5000 \
  --output /tmp/document-registry-benchmark.json
```

## Limits and rollout

Full totals/measures still inspect matching records inside SQLite. Broad metadata
substring searches and canonical grouping can also do work proportional to the
matching corpus; this change bounds application record loading and removes
per-record SQL round trips, rather than claiming constant database CPU. Resolving
authority can grow with organizational structure. Full exports and the existing
approvals list intentionally remain complete-result operations.

Pagination is a live view, not a frozen cross-request snapshot. New inserts do
not shift an existing older-page cursor. Changed permissions, merges and other
edits can change where records belong; use “Newest records” to refresh. Permission
checks still apply to every request and direct record link.

Deployment uses the existing backup and required release checks. Indexes are
additive and old application versions can ignore them; keep them when reverting
a behavioral compatibility problem. No manual production testing or business
workflow change is claimed. The remaining A13 work on static-request SQL and
other Home permission queries remains a separate increment.
