# Operations housekeeping — November 16, 2026

## Completed release and owner decisions

[PR #627](https://github.com/jongsky25/css-is/pull/627) shipped **10.34** at
`808676dc6c3c30aa6163f1a73ba1b7d27250b101`.
[Deployment 43834399312](https://github.com/jongsky25/css-is/actions/runs/43834399312)
passed all seven jobs, including complete normal/shuffled verification, dependency
and metadata gates, deployment and sanitized diagnostics. Fresh backup verification,
RUNNING host and live version 10.34 were confirmed; its release follow-up is disabled.

The owner subsequently requested closing monitoring test #576; it is closed.
That instruction is not evidence of phone receipt. Do not reopen it or generate
another test without a new request. The owner also confirmed multiple backups and
considers existing backup arrangements complete; no additional backup setup is queued.
Storage separation and retention details were not independently reverified here.

The owner explicitly deferred backup-separation review and full recovery testing.
Recovery targets remain undecided; discussion examples of 15 minutes lost work and
4 hours restoration are not accepted targets or guarantees. Leave that discussion
and all recovery exercises deferred until requested. Telegram feature work remains
deferred; no activation or production Telegram change is part of the closeout.
Historical exposure evidence remains open but is not an active investigation.

This closeout is saved for review on `docs/housekeeping-closeout-2026-11-16`, candidate
10.35. No additional production release is requested. Next: review the notes, then
wait for the owner's selected task rather than automatically resuming old actions.

## Initial review scope (historical)

The original November 16 review reconciled Office Connect status and operations
on `docs/housekeeping-2026-11-16`. Its evidence below predates the later release and
owner decisions above. Old open-issue/next-action wording is superseded by this closeout.

## Evidence from the initial review

| Area | Evidence | Meaning and limit |
| --- | --- | --- |
| Current release | Main `33e0089ba281b76a2ea775adf0c1a3d8ad3486de`, 10.33; [deployment 43434733111](https://github.com/jongsky25/css-is/actions/runs/43434733111) succeeded | #626 is shipped; the previous “review branch” advisory status was stale. |
| Scheduled monitoring | [Run 43784570062](https://github.com/jongsky25/css-is/actions/runs/43784570062), schedule event at 01:09:27 UTC; check job 133029215989 | Uptime, backup, audit and monitor were true in both observations; no transitions. Four preceding November 15 scheduled runs also succeeded. This does not establish a five-minute SLA or phone receipt. |
| Current hosting | Authenticated metadata reports RUNNING, host commit `6116d812c9d1fd7b63cdebed0178a1a3a04c22de`; public health 200, status ok | Host commit is a separate repository SHA, not the GitHub source SHA. Health establishes liveness, not full recovery. |
| Backup access | Authenticated bucket metadata reports private; anonymous metadata request returns 401 | Current protection verified. It cannot establish prior downloads or withdraw historical copies. No backup contents were downloaded in this review. |
| Mount | Runtime volumes reports `equityinhealth/office-connect-data` mounted at `/data`, readOnly=false | Mapping is now directly verified. Configuration alone is not a controlled cold-start recovery exercise. |
| Historical audit | [November 1 investigation](audit-2026-11-01.md), current `storage.audit`, `audit_health`, existing audit regression coverage | Writer fix and exact historical acknowledgment are already deployed. No additional incident repair is indicated by this review. Current monitor audit signal is healthy. |
| Restore | [October 31 evidence](recovery-2026-10-31.json) | Database integrity and isolated restore passed; it did not test full application startup or independent retention. |
| Open work | GitHub open PR/issue lookup | Only Telegram #488 was open; no non-Telegram PR queue. Monitoring delivery test #576 remains open. |

This review used source/history, existing sanitized evidence, GitHub workflow metadata
and the monitor's closed boolean summary, plus read-only public/hosting metadata.
No administrator sign-in, database download, forced snapshot, restart, restore,
credential change, provider message or production configuration change was performed.

## Audit investigation conclusion

The earlier October 31 operations summary was superseded by the November 1 work:

- Entry 8949's content mismatch was reproduced by hashing numeric zero before its
  conversion to persisted text. The writer now normalizes the ID before hashing.
- Entries 9406 and 9452 have parent forks consistent with concurrent writers reading
  the same tail. The writer now reserves SQLite's writer before reading that tail.
  The exact historical request interleaving remains unproven.
- #573 shipped the writer fix; #574 shipped an owner-reviewed fingerprint of the
  original prefix through 9452. Strict verification is unchanged. Changed prefix
  content or later inconsistencies fail operational health.

Do not rehash records, delete the incident, or equate acknowledgment with independent
proof of business-record authenticity. The appropriate remaining work concerns
historical exposure and recovery readiness, not repeating these completed fixes.

## Deferred work and retained acceptance criteria

| Priority | Next action | Required evidence / decision |
| --- | --- | --- |
| 1 | Obtain historical bucket access evidence from the hosting account/provider | Available access period, public-visibility history and download/access records; explicitly record if unavailable. Assess affected retained snapshots and any account/key action using that evidence. No outbound provider contact or credential rotation was performed. |
| Owner complete / review deferred | Existing backup arrangements | Owner confirms multiple backups and considers setup complete. Separation review is deferred; do not select another destination or provision storage automatically. |
| Deferred | Agree recovery targets | Maximum acceptable lost work (RPO) and restoration time (RTO). Proposed discussion baseline: 15 minutes and 4 hours; neither is approved or demonstrated. |
| Deferred | Prepare a full recovery exercise | Approved private isolated destination, restricted temporary files, fresh session secret and revoked credentials, outbound integrations blocked, known source/checksum, startup and read-only application checks, timed recovery, and verified cleanup. Never use production data in a public preview. |
| Deferred | Verify cold-start access and recovery behavior in that isolated destination | Record mount access, restored snapshot age, integrity, startup/version compatibility and absence of outbound effects. Do not restart production merely to prove recovery. |
| Closed by owner request | Monitoring test #576 | Issue is closed. Phone receipt was not independently confirmed; no repeat test or reopening is queued. |

A live incident or new failing monitor signal takes priority over this planned work.
Backup setup is owner-confirmed complete; separation review, targets and recovery
testing remain deferred. Existing evidence does not establish historical bucket
download activity.
No full recovery completion can be claimed until the exercise is actually run.

## Other backlog retained

Documents phases 0–2 are shipped. Phase 3 staff usability testing needs approved
synthetic preview/consent. Remaining optional work includes request context on
consolidation/decision/message/blocker/team/manager screens, review-history pagination,
screen-reader/real-touch/other-browser checks and the documented count cold-path
performance exception. Advisory exact fonts and optional region/attention pickers
remain ideas; the office logo is already present.

## Historical pre-release verification

The initial documentation-only review passed 154 local links, whitespace and
synchronized release metadata checks. Its CI then found CVE-2026-126360 in
opentelemetry-api 1.45.1. The release repair pins fixed 1.45.2 and regenerates
runtime/test locks; see [dependency maintenance](../DEPENDENCIES.md). Fresh tests
and the complete dependency gate are required for this expanded candidate.
Local cloud setup/doctor and 69 focused tests passed without failures/skips.
Strict runtime-lock and installed-test scans found no known vulnerabilities;
installed-test inventory coverage, lock fingerprints, metadata and diff checks passed.
The owner's later request authorizes #627 merge/deployment after full CI gates.
The successful release and subsequent owner decisions at the top supersede these
pre-release next actions. Do not resume deferred recovery or feature work.
