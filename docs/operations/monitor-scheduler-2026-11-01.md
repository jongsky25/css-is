# Monitor scheduler investigation — November 1, 2026

## Outcome

Release **9.59** is merged in [PR #577](https://github.com/jongsky25/css-is/pull/577)
as `a7b9b38d473af15b87412717284bb17272fce518` and deployed. The owner explicitly
approved merging after the required checks. All gates passed; none were bypassed.

**Automatic monitoring remains unverified.** At the final investigation check,
the Actions API returned **zero event=schedule executions** for workflow
`403282831`, despite state `active`. Manual checks and deployment succeeded.
The schedule repair attempt has not established a fix. No scheduled job failure
exists to diagnose: GitHub has not created an execution. The root cause remains
unconfirmed; account policy and provider-side registration require further
inspection. Do not describe the original valid cron as a syntax error.

## Evidence

- Repository `jongsky25/css-is` is public, non-fork, non-archived and enabled;
  its default branch is `main`.
- File: `.github/workflows/operational-monitor.yml`, workflow ID `403282831`.
- Original cron: `2-59/5 * * * *`. It was on main in release 9.58. No automatic
  runs were observed. A state refresh at 06:15:58 UTC did not produce a run.
- PR #577 changed it to equivalent explicit minutes:
  `2,7,12,17,22,27,32,37,42,47,52,57 * * * *`.
  The new source merged at approximately 07:33 UTC. Its schedule commit author
  and committer both map to the active owner account `jongsky25`.
- A final disable/enable refresh against the new source completed at
  **07:49:18 UTC**, with final state `active`. No app restart or data change
  is caused by toggling the workflow state.
- Post-merge normal manual [run 41285718156](https://github.com/jongsky25/css-is/actions/runs/41285718156)
  on exact merge a7b9b38 succeeded: uptime, backup, audit and monitor access true
  in both observations; no incident transitions. It ran before the 9.59 app
  deployment and is **not evidence of automatic execution**.
- PR [CI 41282532154](https://github.com/jongsky25/css-is/actions/runs/41282532154)
  and production [run 41285255695](https://github.com/jongsky25/css-is/actions/runs/41285255695)
  passed normal and shuffled suites (**8,431 tests per order**, no failures/skips),
  dependencies, metadata and aggregate gates. Production backup/version gates,
  deployment and post-deployment diagnostics also passed.
- Three authenticated post-deployment observations report version **9.59**,
  commit **a7b9b38**, operational audit ok, acknowledged=true,
  checkpoint_changed=false, raw_ok=false, through_id=9452. Original audit
  records/hashes and the strict historical failure remain preserved.
- Local isolated monitor tests: **37 passed**, no failures/skips. JUnit,
  release metadata, changed documentation links and diff checks passed.
- GitHub Status reported All Systems Operational with no current incident.
  That does not rule out a repository-specific scheduling problem.
- Repository-wide Actions permissions cannot be read with the current integration
  (HTTP 403). Manual workflow_dispatch and automatic push deployments do run.
  No tool exposes the provider's internal scheduler registration or queue.
- Phone receipt of marked test [issue #576](https://github.com/jongsky25/css-is/issues/576)
  is still unconfirmed. No new delivery test was sent during this investigation.

## Recheck

These read-only commands distinguish scheduler events from manual executions:

```bash
gh api repos/jongsky25/css-is/actions/workflows/403282831 --jq '{state,path}'
gh api 'repos/jongsky25/css-is/actions/workflows/403282831/runs?event=schedule&per_page=5' --jq '{total_count,runs:[.workflow_runs[]|{id,event,status,conclusion,head_sha,html_url}]}'
```

If a scheduled run appears, open its check logs and inspect both observations.
A successful job only means reconciliation completed; confirm healthy/valid
signals and any incident transitions. Do not equate manual re-runs with scheduling.
If scheduling stays absent, request GitHub account/provider investigation before
making more speculative application changes or claiming continuous coverage.

## Submission access — owner action required

The owner explicitly authorized submission after reviewing the report. Tool
search found no GitHub Support ticket operation or authenticated browser control.
The official contact URL redirects to the Support sign-in landing page. GitHub's
[official ticket instructions](https://docs.github.com/en/support/contacting-github-support/creating-a-support-ticket)
require signing into the Support portal before creating a technical ticket.
The repository connection does not provide that browser session. No ticket has
been submitted, no ticket number exists, and no alternative public discussion
has been posted in place of a support ticket.

Open [GitHub Support](https://support.github.com/contact), sign in with the owner
account, choose GitHub Actions/technical support, and submit the text below.
If technical support is unavailable for the account's plan, preserve that outcome
and select an available official support option; do not claim a ticket exists.

Subject: **Scheduled workflow never starts — jongsky25/css-is**

Short message to copy:

> Our active GitHub Actions workflow 403282831 on default branch main never
> creates event=schedule runs. Manual dispatches and push workflows succeed.
> Valid cron source revisions and disable/enable refreshes have not resolved it.
> Please investigate scheduler registration or account/repository policy.
> Evidence, reproduction commands and successful run links:
> https://github.com/jongsky25/css-is/blob/docs/monitor-schedule-verification/docs/operations/monitor-scheduler-2026-11-01.md

## Support request draft — not submitted

> The active scheduled workflow `403282831` in `jongsky25/css-is` has never created
> an `event=schedule` run. It exists on default branch main in a public, active,
> non-fork repository. Both the original valid `2-59/5 * * * *` cron and an
> equivalent explicit-minute source revision have been tried. Manual dispatches
> and automatic push workflows succeed. The workflow was disabled and re-enabled
> at 06:15:58 UTC and, after the source revision, 07:49:18 UTC on November 1, 2026;
> final state is active. The owner account is active and authored the cron edit.
> GitHub Status reports no incident. Please inspect scheduler registration and
> any account/repository policy preventing scheduled events. We cannot inspect
> internal scheduler state, and our integration cannot read repository-wide
> Actions policy (403). Relevant source is main commit a7b9b38; successful manual
> run 41285718156 and push deployment run 41285255695 demonstrate that execution
> works. This report contains no credentials or private application records.
