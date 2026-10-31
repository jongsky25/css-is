# Cloud and mobile collaboration

This repository is the durable source of project instructions. Chat history and
installed connectors are useful context, but do not establish current system state.
Read [the setup status](SETUP_STATUS.md) for the next action and [AGENTS.md](../AGENTS.md)
for the working rules.

## Starting a new chat from a phone

With this repository and `main` (or your active work branch) selected, simply send
**office connect**.
`AGENTS.md` defines this as following the current saved next action and saving
progress to GitHub. The long prompt below is a recovery option if a client has
not loaded the repository instructions. The keyword is not registered globally.

Attach/select `jongsky25/css-is` and the branch holding the latest setup work, then send:

> Continue the Office Connect cloud/mobile setup in jongsky25/css-is. Read AGENTS.md,
> docs/CLOUD_COLLABORATION.md and docs/SETUP_STATUS.md. Verify the current branch and
> access, then complete the next unfinished step. Keep the status current and save
> progress to GitHub. Work one step at a time.

If these files are absent from a stale checkout, fetch current main. For ongoing
feature work, open the saved review branch named in the previous handoff.
If repository access is unavailable, reconnect GitHub or attach the repository;
the agent must not invent the prior status. A GitHub connector and a terminal's Git
credentials are separate access paths and must each be checked when needed.

## Setup sequence

1. **Continuity:** repository instructions, this handoff and a maintained status.
2. **Cloud workspace:** verify Python 3.11, locked installation, browser/OCR tools,
   isolated test data, reproducible startup, and GitHub saving from a fresh workspace.
3. **Repository gates:** inspect actual branch rules and CI results; reconcile the
   documented enforcement gap. Do not mark rules active from workflow files alone.
4. **Phone review:** determine a separate staging/preview deployment with test data,
   authentication and a stable link. Do not use the live deployment as a preview.
5. **Operations access:** verify access to actual hosting, logs and storage; document
   recovery and secret locations without recording secret values.
6. **Monitoring and reusable workflows:** assess existing error reporting first,
   then add only missing integrations and repeatable project procedures.

Each step needs recorded evidence, remaining limitations, and a next action. Mark
external settings verified only after observing them. Preserve existing release
gates; documentation changes are not an excuse to bypass the version policy.

Step 2 commands and isolation details: [Cloud workspace](CLOUD_WORKSPACE.md).
Step 4 preview implementation and access setup: [Hugging Face preview](HF_PREVIEW_SETUP.md).

## Feature workflow after setup

Use the [mobile/cloud workflow](MOBILE_CLOUD_WORKFLOW.md),
[monitoring guide](MONITORING_WORKFLOW.md) and
[session handoff template](SESSION_HANDOFF_TEMPLATE.md).

Capture the requested outcome and acceptance criteria in a GitHub issue when useful.
Implement on a branch, run relevant checks, and provide a PR/preview link with a short
phone-friendly review checklist. Record unfinished work before changing chats.
Production deployment follows the agreed release scope and existing gates.

## Limits

No setup can guarantee that every new chat automatically loads a repository or
retains account authorization. Repository files plus the explicit startup prompt
make recovery repeatable. A branch saved on GitHub survives a disposable workspace;
uncommitted local files do not provide that guarantee.
