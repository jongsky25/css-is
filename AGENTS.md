# Working on Office Connect

Repository: `jongsky25/css-is`. This is Office Connect BLHSD, a Python 3.11
FastAPI/Jinja application. Do not infer its stack from connected plugins.

## Start every session

**User shorthand:** when the user says **“office connect”** (case insensitive),
resume the cloud/mobile setup on `setup/cloud-mobile-continuity` in
`jongsky25/css-is`: read these instructions and the two documents below, verify
access and working state, complete the next unfinished step, update its status,
and save progress to GitHub. An accompanying specific request takes precedence.
This mapping works when this repository's instructions are available; it is not
a global chat command or a substitute for repository access.

1. Read `docs/CLOUD_COLLABORATION.md` and `docs/SETUP_STATUS.md`.
2. Check the current branch, working tree and latest commit. Preserve existing work.
3. Read instructions and feature documentation relevant to the requested change.
4. Check current environment and connector access; prior-session access is not proof.
5. Continue the first unfinished setup step when the user asks to continue setup.

## Working preferences

- The user works mainly from a phone and cloud. Perform authorized work directly;
  provide short progress updates and concrete results, with clickable links.
- Set up the collaboration workflow one step at a time. Record outcomes and the next
  action in `docs/SETUP_STATUS.md` before ending a setup session.
- Ask only for missing information or decisions that block useful work. Do not ask
  the user to repeat information already available in the repository.
- Do not rely on conversation memory. Record durable technical decisions in the
  repository, and name the branch/commit holding any unfinished work.

## Development and verification

- Use Python 3.11 and the hashed dependency locks. Read `docs/DEPENDENCIES.md`
  and `.github/workflows/release-checks.yml` before setting up the test environment.
- For cloud setup and isolated run commands, follow `docs/CLOUD_WORKSPACE.md`.
  Use `bash scripts/cloud_setup.sh` and `.venv/bin/python scripts/cloud_workspace.py`;
  do not start the app directly against an unknown database or inherited credentials.
- Read `docs/RELEASE_GATES.md` before preparing a release. The existing gate checks
  normal/shuffled suites, skipped tests, dependencies and synchronized versions.
- Run checks appropriate to the change. Report exact outcomes and blockers; do not
  describe unrun checks as passing. Documentation-only changes need link/diff checks.
- `LOCAL_RUN.md` contains historical environment and deployment claims. Verify them
  against current code and workflows rather than assuming they describe this runtime.

## Deployment and data

- A push/merge to `main` triggers the Hugging Face deployment workflow. Use a review
  branch for setup work. The current setup request does not authorize a production release.
- Read `DEPLOY.md` and current release guidance before deployment. Effective live
  database/persistence paths require verification; older documentation conflicts.
- Do not run the application against production data to test a change. Use isolated
  temporary data and avoid outbound email, Telegram, or other real notifications.
- Keep credentials and personal data out of chat, tracked files, and logs. Record
  secret names and configuration locations only. Never bypass release/backup gates.

## End a setup session

Update the status document with what changed, verification, remaining limits and
the next action. Save changes to a GitHub branch when access permits. State clearly
whether work is local, pushed, in a PR, merged, or deployed. If remote saving fails,
explain that a fresh chat may not have the local files.
