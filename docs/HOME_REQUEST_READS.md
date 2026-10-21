# Home and navigation request reads

Introduced in **7.72**, the third A13 performance increment.

## Shared results

After current-session validation, middleware creates one `RequestReads` on
`request.state`. Navigation, Home's team notes and its personal tasks reuse:

- Wellness/AWA approval counts from the existing chain-routing helper.
- Document feature state and permitted document-review count.
- The same three-item personal work preview for the same local date.
- Room-approver membership for navigation and travel-flag notification display.

Home's non-calendar tabs also omit an unused team-link lookup: those tabs
already read their link state from the team payload. Calendar retains its own
live lookup. All other scoped-data builders keep their current permission reads.

## Lifetime and security

This is a display summary for one response, not a permission grant. No module,
session-cookie, database, disk or timed cache stores it. Each new HTTP request
starts empty after the account/session is validated. Changed counts, revoked
document grants, OIC delegations, room membership, bureau grants, disabled
accounts and document feature switches are checked again on the next request.

One account owns the summary; using it for another ID is rejected. Mutable
results are copied before each consumer receives them. Failed reads are not
stored, so an optional bell-source failure can be retried by the Home builder.
The summary contains no database connection and can pass from middleware to the
Home handler's worker thread.

Existing domain readers build the first result. Detail pages, scoped roster
and calendar queries, and write actions retain their live checks. In particular,
a display result warmed before revoking a chief seat cannot authorize a wellness
decision afterward. The summary is not an input to approval or document writes.
Sources without a supplied summary retain their existing fresh-read behavior.

Display consumers share the first successful result for that request. Concurrent
changes can appear on the next request; the response is not a transaction-wide
snapshot of all modules. This does not freeze counts across requests or bypass
the checks performed when a person opens a queue or acts on an item.

## Local evidence

`tests/test_home_request_reads.py` instruments complete HTTP requests against a
synthetic reference database with two sections, a chief, staff, an Administrative
Section member, an unlinked administrator, two wellness claims and one restricted
document review. Schema/session fixture work is complete before tracing.

| One chief's Home request | 7.70 baseline | 7.72 |
|---|---:|---:|
| Wellness/AWA count builds | 3 | 1 |
| Document-review count builds | 2 | 1 |
| Room-membership display checks | 2 | 1 |
| Three-item work-preview builds | 2 | 1 |
| Complete HTTP SELECT/WITH statements | 229 | 179 |

The baseline was reproduced against main `e7cacc4` before implementation, with
the same fixture and SQLite statement tracing. Run the query regression with
`python -m pytest tests/test_home_request_reads.py::test_home_reads_are_shared -s`
to print the current counts. These are local synthetic observations, not a
production latency, concurrency or capacity claim.

The tests compare shared and fresh domain-reader payloads for five user profiles
across Team, Me and Calendar tabs, including notification counts, task rows and
calendar scope/link output. They also cover next-request changes, private-record
denials, failed-source retry, result mutation, simultaneous users, the live write
boundary, and travel flags without an administrator-role bypass.

## Rollout and remaining work

The runtime closure includes the new module. There are no new dependencies,
schema changes or data migrations. No manual production testing was performed.
Public static requests retain the 7.69 path with zero application SQL.

This increment removes repeated work; it does not make the whole Home request
constant-cost. Existing full roster/approval calculations and per-item Work
permission checks still depend on the workload. Broader query redesign and
production capacity measurements remain separate work. A14's next increment
addresses blocking external operations and their responsiveness.
