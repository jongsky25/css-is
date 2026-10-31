# Working together from phone and cloud

This is the repeatable Office Connect workflow. Follow [AGENTS.md](../AGENTS.md)
and check [current status](SETUP_STATUS.md) at the beginning of each session.
No local laptop is required for the verified workflow. Repository access, a cloud
runtime and the relevant secret bindings still need to be available in each chat.

## What you send from your phone

Start with **office connect**, then describe the change in ordinary language.
For example: “On Calendar, make the next week button easier to tap. It should
work in Safari without horizontal scrolling.” Screenshots can supply context;
exclude credentials and personal records. A GitHub issue is optional for small
requests; use the [work request template](../.github/ISSUE_TEMPLATE/work_request.md)
for work that needs tracking across sessions.

The agent checks the saved status and current access, identifies the intended
result, and performs the authorized work. It asks only for a missing decision
that blocks progress. Deferred operational findings stay deferred until requested.

## Build and test

1. Check the working tree and preserve existing changes. Work on an appropriate
   review branch based on current main; record its name. If continuing saved
   work, inspect its branch and handoff before creating another branch.
2. Use the [cloud setup and isolated commands](CLOUD_WORKSPACE.md). Develop with
   synthetic data and disabled external integrations. Never use a production
   database as an application test fixture.
3. Run checks appropriate to the change, and record exact results. Documentation
   needs diff/link checks; application work needs relevant behavior checks.
   The [release gates](RELEASE_GATES.md) still apply before production promotion.
4. Save and push the implementation before publishing a preview, so the deployed
   source commit is reproducible. No merge to main is implied by a phone review.

## Publish and review on your phone

Use the existing [private preview publisher](HF_PREVIEW_SETUP.md). It stages a
code-only bundle and fixed preview target. It requires a clean committed tree,
HF_TOKEN and the remote preview password secret. Verify remote source commit,
private visibility, RUNNING state, health and banner after uploading. This preview
is shared: serialize publishes, identify whose branch/commit is live, and tell
the reviewer if a newer publish replaces their candidate. Preview data resets on
restart; keep acceptance notes in GitHub rather than relying on preview records.

Open [the private preview](https://huggingface.co/spaces/equityinhealth/office-connect-preview)
in Safari signed into the authorized Hugging Face account. Use the synthetic
account `preview@example.invalid` and the password from your password manager.
Follow the documented iOS cookie workaround only when needed; restore Safari’s
privacy setting after the test. Direct app URLs can lack private Hub authorization.

The agent gives you the exact candidate commit and a short review list:

- Open the changed page at phone width and check the requested result.
- Perform the main action using fake data, then navigate away and back.
- Check the relevant empty/error state and whether taps or scrolling are awkward.

Reply with what worked or send a screenshot of the problem. The agent fixes the
same request, retests, and republishes when appropriate. A rendered screenshot
proves that view only; it does not prove untested writes or other features.

## Review and release

Use the [PR template](../.github/pull_request_template.md) to record the problem,
resulting behavior, tests and preview evidence. Draft PRs and branch pushes are
review artifacts. CI must report the required checks on the actual candidate;
local test success alone does not mean CI passed. Every release candidate must pass the checks for its actual source commit.

Main is production-connected: merging triggers the deploy workflow. Release only
within an explicit production release request, with synchronized versions and
all existing verification/backup gates. Phone acceptance of a preview is not by
itself an instruction to merge or deploy. Report branch, commit, PR, preview and
release state accurately; omit any link that does not yet exist.

## Keep work across chats

Before ending, push the work and update the current next action in SETUP_STATUS.md.
Use [the session handoff template](SESSION_HANDOFF_TEMPLATE.md) when a task needs
more detail. Record completed work, tests, live preview source, unresolved limits
and the next action. Never record secret values or attach production databases.

A future session reads the saved branch and continues from its status. It checks
access again rather than assuming credentials, cloud files or chat history persist.
If access blocks saving, say clearly that the work has not been saved remotely.

## Monitoring and operational follow-up

Use [the monitoring guide](MONITORING_WORKFLOW.md) for the checks already available,
known gaps and symptom-driven investigation. The audit warning and historical
bucket exposure remain tracked in [operations findings](OPERATIONS_ACCESS.md).
They are deferred application/operations tasks, not automatic next development work.
